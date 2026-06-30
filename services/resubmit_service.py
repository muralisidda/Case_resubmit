"""
ResubmitService
===============
Fetches case resubmission data from:
  - Platform Support DB  (message queue / orchestration records)
  - TIBCO Case Data DB   (case_data table)

When no live database connection is available the service returns realistic
mock/sample data so the UI can still be developed and demonstrated.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock / sample data (used when DB is unavailable)
# ---------------------------------------------------------------------------

_MOCK_RECORDS = [
    {
        'RecordId': 'REC-00001',
        'ProcedureName': 'iProcess.CaseSubmit.MainFlow',
        'MessageIdentifier': 'MSG-20240601-001',
        'AdviserIdentifier': 'ADV-10045',
        'ClientIdentifier': 'CLI-78901',
        'MessageTypeQueue': 'CASE_SUBMIT_QUEUE',
        'MessageStatus': 'FAILED',
        'CreateDateTime': '2024-06-01 09:15:32',
        'CompleteDateTime': '2024-06-01 09:16:10',
        'MessageBody': '<Message><CaseNumber>123456</CaseNumber><Status>FAILED</Status><Reason>Timeout on downstream service</Reason></Message>',
        'CaseNumber': '123456',
        'GUID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    },
    {
        'RecordId': 'REC-00002',
        'ProcedureName': 'iProcess.DocumentValidation.SubFlow',
        'MessageIdentifier': 'MSG-20240601-002',
        'AdviserIdentifier': 'ADV-10045',
        'ClientIdentifier': 'CLI-78901',
        'MessageTypeQueue': 'DOC_VALIDATION_QUEUE',
        'MessageStatus': 'PENDING',
        'CreateDateTime': '2024-06-01 09:16:15',
        'CompleteDateTime': None,
        'MessageBody': '<Message><CaseNumber>123456</CaseNumber><DocumentType>ISA_TRANSFER</DocumentType></Message>',
        'CaseNumber': '123456',
        'GUID': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    },
]


class ResubmitService:
    """Service layer for case resubmission operations."""

    # ------------------------------------------------------------------
    # Platform Support DB query
    # ------------------------------------------------------------------

    _PLATFORM_QUERY = """
        SELECT
            ps.RecordId,
            ps.ProcedureName,
            ps.MessageIdentifier,
            ps.AdviserIdentifier,
            ps.ClientIdentifier,
            ps.MessageTypeQueue,
            ps.MessageStatus,
            ps.CreateDateTime,
            ps.CompleteDateTime,
            ps.MessageBody,
            ps.CaseNumber,
            ps.GUID
        FROM dbo.PlatformSupportMessages ps
        WHERE 1=1
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def fetch_case_records(case_number: str, guid: str):
        """
        Return (records, error_message).
        Falls back to mock data when the DB is unavailable or on error.
        """
        from database.connection import platform_db

        db_error = None

        # Build query dynamically depending on which identifier was supplied
        query = ResubmitService._PLATFORM_QUERY
        params = []
        if case_number:
            query += " AND ps.CaseNumber = ?"
            params.append(case_number)
        if guid:
            query += " AND ps.GUID = ?"
            params.append(guid)

        records = []

        # Try Platform Support DB
        if platform_db.connection_available:
            try:
                records = platform_db.execute_raw_query(query, params if params else None)
            except Exception as exc:
                logger.error(f"Platform DB query failed: {exc}")
                db_error = f"Platform Support DB error: {exc}"
        else:
            db_error = (
                "Platform Support DB is not connected. "
                "Showing sample data for demonstration."
            )
            records = ResubmitService._filter_mock(case_number, guid)

        return records, db_error

    @staticmethod
    def fetch_message_body(record_id: str):
        """Return (body_text, error_message) for a specific record."""
        from database.connection import platform_db

        if platform_db.connection_available:
            try:
                rows = platform_db.execute_raw_query(
                    "SELECT MessageBody FROM dbo.PlatformSupportMessages WHERE RecordId = ?",
                    [record_id],
                )
                if rows:
                    return rows[0].get('MessageBody', ''), None
                return '', 'No record found.'
            except Exception as exc:
                logger.error(f"fetch_message_body error: {exc}")
                return None, str(exc)
        else:
            # Return mock body
            for rec in _MOCK_RECORDS:
                if rec['RecordId'] == record_id:
                    return rec.get('MessageBody', ''), None
            return '<Message><Info>Sample message body - DB not connected</Info></Message>', None

    @staticmethod
    def _ensure_ems_producer_compiled(java_exe: str, tibjms_jar: str, sender_dir: str):
        """
        Compile EmsProducer.java if EmsProducer.class does not already exist.
        Uses javac from the same JRE as java_exe.  Raises RuntimeError on failure.
        javax.jms-api.jar must sit alongside tibjms.jar.
        """
        import subprocess, os
        class_file = os.path.join(sender_dir, 'EmsProducer.class')
        java_file  = os.path.join(sender_dir, 'EmsProducer.java')
        if os.path.exists(class_file):
            return
        jms_api_jar = os.path.join(os.path.dirname(tibjms_jar), 'javax.jms-api.jar')
        cp = tibjms_jar + ';' + jms_api_jar
        javac = java_exe.replace('java.exe', 'javac.exe')
        cmd = [javac, '-cp', cp, java_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"EmsProducer compile failed:\n{result.stderr}"
            )
        logger.info("EmsProducer.java compiled successfully.")

    @staticmethod
    def resubmit_case(
        case_number: str,
        record_id: str,
        reason: str,
        submitted_by: str,
        investor_id: str = '',
        proc_name: str = '',
    ):
        """
        Build a workflowMessageRequest XML envelope and send it to TIBCO EMS
        as a synchronous request, then return the reply body.
        Returns (success: bool, message: str, queue: str, sent_xml: str, response_xml: str).
        """
        import os
        import subprocess
        import xml.etree.ElementTree as ET

        logger.info(
            f"Resubmit requested: case={case_number}, guid={record_id}, "
            f"investor={investor_id}, by={submitted_by}, reason={reason}"
        )

        # ── Config from .env ───────────────────────────────────────────
        java_exe    = os.environ.get('JMS_JAVA_EXE',   r'C:\tibco\tibcojre\1.6.0\bin\java.exe')
        tibjms_jar  = os.environ.get('JMS_TIBJMS_JAR', '').strip()
        sender_dir  = os.environ.get('JMS_SENDER_DIR', r'C:\case_resubmit\jms_sender')
        host        = os.environ.get('JMS_HOST',       'UK-man-ems-01')
        port        = os.environ.get('JMS_PORT',       '7222')
        username    = os.environ.get('JMS_USERNAME',   '')
        password    = os.environ.get('JMS_PASSWORD',   '')
        queue       = os.environ.get('JMS_QUEUE',      'AJBG.FrameworkServices.CreateCase')

        if not tibjms_jar or not os.path.isfile(tibjms_jar):
            return False, (
                "JMS not configured – set JMS_TIBJMS_JAR in .env to the full path "
                "of tibjms.jar (ask your TIBCO administrator)."
            ), queue, '', ''

        # ── Build workflowMessageRequest XML (namespace-correct per XSD) ──
        WMR_NS = 'http://www.ajbell.co.uk/schemas/xsd/businessModel/workflow/workflowMessage.xsd'
        WA_NS  = 'http://www.ajbell.co.uk/schemas/xsd/businessModel/workflow/workflowAttributes.xsd'
        ET.register_namespace('wmr', WMR_NS)
        ET.register_namespace('wa',  WA_NS)

        root  = ET.Element(f'{{{WMR_NS}}}workflowMessageRequest')
        attrs = ET.SubElement(root, f'{{{WA_NS}}}workflowAttributes')
        ET.SubElement(attrs, f'{{{WA_NS}}}procedureName').text = 'MASProce'
        ET.SubElement(attrs, f'{{{WA_NS}}}stepName').text      = '001MAS01'
        ET.SubElement(attrs, f'{{{WA_NS}}}startedBy').text     = 'tibcoadmin'

        fields = ET.SubElement(root, f'{{{WMR_NS}}}Fields')
        field  = ET.SubElement(fields, f'{{{WMR_NS}}}Field')
        ET.SubElement(field, f'{{{WMR_NS}}}Name').text  = 'OLDCASENUM'
        ET.SubElement(field, f'{{{WMR_NS}}}Value').text = case_number

        envelope = '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding='unicode')

        # ── Compile Java helper if needed ──────────────────────────────
        try:
            ResubmitService._ensure_ems_producer_compiled(java_exe, tibjms_jar, sender_dir)
        except RuntimeError as exc:
            logger.error(str(exc))
            return False, f"EmsProducer compile error: {exc}", queue, envelope, ''

        # ── Launch Java subprocess ─────────────────────────────────────
        jms_api_jar = os.path.join(os.path.dirname(tibjms_jar), 'javax.jms-api.jar')
        classpath = tibjms_jar + ';' + jms_api_jar + ';' + sender_dir
        cmd = [
            java_exe,
            '-cp', classpath,
            'EmsProducer',
            host, port, username, password, queue, envelope,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=35,
            )
            if result.returncode == 0:
                response_xml = result.stdout.strip()
                logger.info(f"JMS reply received for case {case_number}: {response_xml[:120]}")
                return True, f"Case {case_number} has been successfully resubmitted.", queue, envelope, response_xml
            elif result.returncode == 2:
                logger.error("EmsProducer timed out waiting for reply.")
                return False, "Resubmit failed – no reply from EMS within 30 s.", queue, envelope, ''
            else:
                err = result.stderr.strip() or result.stdout.strip()
                logger.error(f"EmsProducer exited {result.returncode}: {err}")
                return False, f"Resubmit failed – EMS error: {err}", queue, '', ''
        except subprocess.TimeoutExpired:
            logger.error("EmsProducer subprocess timed out after 35 s.")
            return False, "Resubmit failed – EMS connection timed out (35 s).", queue, '', ''
        except Exception as exc:
            logger.error(f"EmsProducer subprocess error: {exc}")
            return False, f"Resubmit failed – subprocess error: {exc}", queue, '', ''

    @staticmethod
    def amend_message_status(message_identifier: str):
        """
        Set MessageStatus = 1 in WSD_Messages for the given MessageIdentifier.
        Returns (success: bool, error_message | None).
        """
        import re
        from database.connection import wsd_db

        if not message_identifier or not re.match(r'^[A-Za-z0-9\-]+$', message_identifier):
            return False, "Invalid MessageIdentifier format."

        if not wsd_db.connection_available:
            return False, "WebSupportDatabase is not connected."

        try:
            wsd_db.execute_non_query(
                "UPDATE [dbo].[WSD_Messages] SET MessageStatus = 1 WHERE MessageIdentifier = ?",
                [message_identifier],
            )
            logger.info(f"MessageStatus set to 1 for MessageIdentifier={message_identifier}")
            return True, None
        except Exception as exc:
            logger.error(f"amend_message_status error: {exc}")
            return False, str(exc)

    # ------------------------------------------------------------------
    # TIBCO case message lookup (primary search by case number)
    # ------------------------------------------------------------------

    _TIBCO_STEP1_QUERY = """
        SELECT TOP 1
            cda.field_value  AS InvestorId,
            cia.started      AS CaseStarted,
            cia.proc_id      AS ProcId,
            pi.proc_name     AS ProcName
        FROM swpro.case_data cda WITH (NOLOCK)
        INNER JOIN swpro.case_information cia WITH (NOLOCK)
            ON cia.casenum = cda.casenum
        INNER JOIN swpro.proc_index pi WITH (NOLOCK)
            ON pi.proc_id = cia.proc_id
        WHERE cda.casenum = ?
          AND cda.field_name = 'IVINVESTORID'
    """

    @staticmethod
    def fetch_tibco_case_message(case_number: str, guid: str):
        """
        Two-step lookup using both case_number and guid (MessageIdentifier):
          1. Direct query to tibcodomain (AG-UK-TIBCO-1\\TIBCO) to fetch
             InvestorId / CaseStarted / ProcId / ProcName using casenum.
          2. Direct query to WebSupportDatabase (AJB10VSS01\\AJB10VSS01) filtered
             by both ClientIdentifier (InvestorId) AND MessageIdentifier (GUID),
             ordered by closest CreateDateTime to CaseStarted.

        Returns (result_dict | None, error_message | None).
        Falls back to mock data when DB connections are unavailable.
        """
        import re
        from database.connection import tibcodomain_db, wsd_db

        if not case_number or not guid:
            return None, "Both case number and GUID are required."

        if not re.match(r'^[A-Za-z0-9\-_]+$', case_number):
            return None, "Invalid case number format."

        # GUID may contain hyphens — validate as UUID-like string
        if not re.match(r'^[A-Za-z0-9\-]+$', guid):
            return None, "Invalid GUID format."

        if not tibcodomain_db.connection_available:
            logger.warning("tibcodomain DB unavailable – returning mock data for case lookup.")
            return {
                'CaseNum': case_number,
                'InvestorId': 'MOCK-INV-001',
                'ProcId': 1001,
                'ProcName': 'iProcess.CaseSubmit.MainFlow',
                'CaseStarted': '2024-06-01 09:15:00.000',
                'MessageIdentifier': guid,
                'AdviserIdentifier': 'MOCK-ADV-001',
                'ClientIdentifier': 'MOCK-INV-001',
                'MessageType': 'CASE_SUBMIT',
                'MessageBody': '<Message><CaseNumber>123456</CaseNumber><Status>FAILED</Status><Reason>Mock data – DB not connected</Reason></Message>',
                'MessageStatus': 'FAILED',
                'CreateDateTime': '2024-06-01 09:15:32.000',
                'CompletedDateTime': None,
                'DiffSeconds': 32,
            }, "tibcodomain DB not connected – showing sample data."

        # ── Step 1: get case details from tibcodomain ──────────────────
        try:
            rows = tibcodomain_db.execute_raw_query(
                ResubmitService._TIBCO_STEP1_QUERY, [case_number]
            )
        except Exception as exc:
            logger.error(f"tibcodomain step-1 query failed: {exc}")
            return None, f"TIBCO case lookup failed: {exc}"

        if not rows:
            return None, f"No case found for case number: {case_number}"

        row = rows[0]
        investor_id  = str(row['InvestorId'])
        case_started = row['CaseStarted']
        proc_id      = int(row['ProcId'])
        proc_name    = str(row['ProcName'])

        if not re.match(r'^[A-Za-z0-9\-_]+$', investor_id):
            return None, f"Unexpected InvestorId format returned from DB: {investor_id}"

        # Format datetime for comparison
        if hasattr(case_started, 'strftime'):
            ms = case_started.microsecond // 1000
            case_started_str = case_started.strftime('%Y-%m-%d %H:%M:%S.') + f"{ms:03d}"
        else:
            case_started_str = str(case_started)

        # ── Step 2: query WebSupportDatabase by ClientIdentifier + GUID ──
        if not wsd_db.connection_available:
            logger.warning("WSD DB unavailable – returning partial result without message details.")
            return {
                'CaseNum': case_number,
                'InvestorId': investor_id,
                'ProcId': proc_id,
                'ProcName': proc_name,
                'CaseStarted': case_started_str,
                'MessageIdentifier': guid,
                'CreateDateTime': None,
                'DiffSeconds': None,
            }, "WebSupportDatabase not connected – message details unavailable."

        step2_sql = """
            SELECT TOP 1
                ? AS CaseNum,
                ? AS InvestorId,
                ? AS ProcId,
                ? AS ProcName,
                ? AS CaseStarted,
                MessageIdentifier,
                AdviserIdentifier,
                ClientIdentifier,
                MessageType,
                MessageBody,
                MessageStatus,
                CreateDateTime,
                CompletedDateTime,
                ABS(DATEDIFF(SECOND, CreateDateTime, ?)) AS DiffSeconds
            FROM dbo.wsd_messages WITH (NOLOCK)
            WHERE ClientIdentifier = ?
              AND MessageIdentifier = ?
            ORDER BY DiffSeconds
        """

        try:
            result_rows = wsd_db.execute_raw_query(
                step2_sql,
                [case_number, investor_id, proc_id, proc_name,
                 case_started_str, case_started_str, investor_id, guid],
            )
            if result_rows:
                return result_rows[0], None
            return None, f"No WSD message found for case {case_number} with GUID {guid}."
        except Exception as exc:
            logger.error(f"WSD messages step-2 query failed: {exc}")
            return None, f"WSD message lookup failed: {exc}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_mock(case_number: str, guid: str):
        """Filter mock records by case number and/or GUID."""
        result = []
        for rec in _MOCK_RECORDS:
            match = True
            if case_number and rec.get('CaseNumber') != case_number:
                match = False
            if guid and rec.get('GUID') != guid:
                match = False
            if match:
                result.append(dict(rec))
        # If no filter applied, return all mock data
        if not case_number and not guid:
            return [dict(r) for r in _MOCK_RECORDS]
        return result
