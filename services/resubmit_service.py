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
        from database.connection import platform_db, tibco_db

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

        # Enrich with TIBCO case data if available
        if tibco_db.connection_available and records:
            case_nums = list({r.get('CaseNumber') for r in records if r.get('CaseNumber')})
            if case_nums:
                placeholders = ','.join(['?'] * len(case_nums))
                tibco_query = f"""
                    SELECT casenum, field_name, field_value
                    FROM [tibcodomain].[swpro].[case_data]
                    WHERE casenum IN ({placeholders})
                """
                try:
                    tibco_rows = tibco_db.execute_raw_query(tibco_query, case_nums)
                    # Build a lookup: {casenum: {field_name: field_value}}
                    tibco_map: dict = {}
                    for row in tibco_rows:
                        cn = row['casenum']
                        tibco_map.setdefault(cn, {})[row['field_name']] = row['field_value']
                    # Attach TIBCO fields to each record
                    for rec in records:
                        rec['TibcoCaseData'] = tibco_map.get(rec.get('CaseNumber'), {})
                except Exception as exc:
                    logger.warning(f"TIBCO DB enrichment failed: {exc}")

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
    def resubmit_case(case_number: str, record_id: str, reason: str, submitted_by: str):
        """
        Attempt to resubmit the case.
        Returns (success: bool, message: str).
        """
        from database.connection import platform_db

        logger.info(
            f"Resubmit requested: case={case_number}, record={record_id}, "
            f"by={submitted_by}, reason={reason}"
        )

        if platform_db.connection_available:
            try:
                # Log the resubmission attempt
                platform_db.execute_non_query(
                    """
                    INSERT INTO dbo.ResubmitAuditLog
                        (CaseNumber, RecordId, Reason, SubmittedBy, SubmittedAt)
                    VALUES (?, ?, ?, ?, GETDATE())
                    """,
                    [case_number, record_id, reason, submitted_by],
                )
                # Trigger resubmit (adjust stored-proc name to your environment)
                platform_db.execute_non_query(
                    "EXEC dbo.usp_ResubmitCase @CaseNumber=?, @RecordId=?, @Reason=?",
                    [case_number, record_id, reason],
                )
                return True, f"Case {case_number} has been successfully resubmitted."
            except Exception as exc:
                logger.error(f"Resubmit error: {exc}")
                return False, f"Resubmit failed: {exc}"
        else:
            # Simulate success when no DB is connected (demo mode)
            logger.info("Demo mode: resubmit simulated (no DB connection).")
            return (
                True,
                f"[Demo] Case {case_number} resubmit logged. "
                f"(DB not connected – this is a simulated response.)",
            )

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
