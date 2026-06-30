"""
Quick test of the two-step TIBCO case message lookup query.
  Step 1: tibcodomain_rep on ENV3-AG-UK-ONLINE-1\\ONLINE
  Step 2: WebSupportDatabase on AJB10VSS01\\AJB10VSS01
Usage:  python test_tibco_query.py <case_number> <guid>
"""
import os
import sys
import re
import pyodbc
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

if len(sys.argv) < 3:
    print("Usage: python test_tibco_query.py <case_number> <guid>")
    sys.exit(1)

CASE_NUMBER = sys.argv[1].strip()
GUID        = sys.argv[2].strip()

# ── Connection strings ────────────────────────────────────────────────────
def make_conn_str(prefix):
    driver   = os.environ.get(f'{prefix}_DRIVER', 'ODBC Driver 17 for SQL Server')
    server   = os.environ.get(f'{prefix}_SERVER')
    database = os.environ.get(f'{prefix}_NAME')
    uid      = os.environ.get(f'{prefix}_USERNAME')
    pwd      = os.environ.get(f'{prefix}_PASSWORD')
    return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd}", server, database

tibcodomain_cs, td_server, td_db = make_conn_str('TIBCODOMAIN_DB')
wsd_cs,         wsd_server, wsd_db_name = make_conn_str('WSD_DB')

print(f"Case Number : {CASE_NUMBER}")
print(f"GUID        : {GUID}")
print(f"Step-1 DB   : {td_server} / {td_db}")
print(f"Step-2 DB   : {wsd_server} / {wsd_db_name}\n")

# ── Step 1 ────────────────────────────────────────────────────────────────
print("── Step 1: Fetching case details from tibcodomain_rep ─────────")
try:
    conn1 = pyodbc.connect(tibcodomain_cs, timeout=5)
except Exception as e:
    print(f"[FAIL] Cannot connect to tibcodomain_rep DB: {e}")
    sys.exit(1)

STEP1 = """
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

cursor1 = conn1.cursor()
try:
    cursor1.execute(STEP1, CASE_NUMBER)
    cols = [c[0] for c in cursor1.description]
    rows = cursor1.fetchall()
    cursor1.close()
    conn1.close()
    if not rows:
        print(f"No rows returned for case number: {CASE_NUMBER}")
        sys.exit(0)
    row = dict(zip(cols, rows[0]))
    for k, v in row.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"[FAIL] Step 1 error: {e}")
    conn1.close()
    sys.exit(1)

investor_id  = str(row['InvestorId'])
case_started = row['CaseStarted']
proc_id      = int(row['ProcId'])
proc_name    = str(row['ProcName'])

if not re.match(r'^[A-Za-z0-9\-_]+$', investor_id):
    print(f"[FAIL] Unexpected InvestorId format: {investor_id}")
    sys.exit(1)

if hasattr(case_started, 'strftime'):
    ms = case_started.microsecond // 1000
    case_started_str = case_started.strftime('%Y-%m-%d %H:%M:%S.') + f"{ms:03d}"
else:
    case_started_str = str(case_started)

# ── Step 2 ────────────────────────────────────────────────────────────────
print("\n── Step 2: Fetching WSD message from WebSupportDatabase ───────")
try:
    conn2 = pyodbc.connect(wsd_cs, timeout=5)
except Exception as e:
    print(f"[FAIL] Cannot connect to WSD DB: {e}")
    sys.exit(1)

STEP2 = """
SELECT TOP 1
    ? AS CaseNum,
    ? AS InvestorId,
    ? AS ProcId,
    ? AS ProcName,
    ? AS CaseStarted,
    MessageIdentifier,
    CreateDateTime,
    ABS(DATEDIFF(SECOND, CreateDateTime, ?)) AS DiffSeconds
FROM dbo.wsd_messages WITH (NOLOCK)
WHERE ClientIdentifier = ?
  AND MessageIdentifier = ?
ORDER BY DiffSeconds
"""

cursor2 = conn2.cursor()
try:
    cursor2.execute(STEP2, [CASE_NUMBER, investor_id, proc_id, proc_name,
                            case_started_str, case_started_str, investor_id, GUID])
    cols2 = [c[0] for c in cursor2.description]
    rows2 = cursor2.fetchall()
    if not rows2:
        print("No matching WSD message found.")
    else:
        result = dict(zip(cols2, rows2[0]))
        for k, v in result.items():
            print(f"  {k}: {v}")
        print("\n[OK] Query completed successfully.")
except Exception as e:
    print(f"[FAIL] Step 2 error: {e}")
finally:
    cursor2.close()
    conn2.close()
