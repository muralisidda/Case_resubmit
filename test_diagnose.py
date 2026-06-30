import os, pyodbc
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

cs = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={os.environ['TIBCODOMAIN_DB_SERVER']};"
    f"DATABASE={os.environ['TIBCODOMAIN_DB_NAME']};"
    f"UID={os.environ['TIBCODOMAIN_DB_USERNAME']};"
    f"PWD={os.environ['TIBCODOMAIN_DB_PASSWORD']}"
)

conn = pyodbc.connect(cs, timeout=5)
cur = conn.cursor()

print("--- Does case 62738806 exist in case_information? ---")
cur.execute(
    "SELECT TOP 1 casenum, proc_id, started FROM swpro.case_information WITH (NOLOCK) WHERE casenum = ?",
    "62738806"
)
rows = cur.fetchall()
print(rows if rows else "NOT FOUND")

print()
print("--- field_names in case_data for case 62738806 ---")
cur.execute(
    "SELECT field_name, field_value FROM swpro.case_data WITH (NOLOCK) WHERE casenum = ?",
    "62738806"
)
for r in cur.fetchall():
    print(r)

print()
print("--- Sample case numbers from case_information (TOP 5) ---")
cur.execute("SELECT TOP 5 casenum, proc_id, started FROM swpro.case_information WITH (NOLOCK)")
for r in cur.fetchall():
    print(r)

conn.close()
