import os, sys
os.chdir(r'c:\case_resubmit')
from dotenv import load_dotenv
load_dotenv()
from database.connection import wsd_db

out = open(r'c:\case_resubmit\wsd_schema_out.txt', 'w', encoding='utf-8')

def p(s=''):
    print(s)
    out.write(s + '\n')

p('WSD available: ' + str(wsd_db.connection_available))

p('\n=== Tables ===')
rows = wsd_db.execute_raw_query(
    'SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE=?', ['BASE TABLE'])
for r in rows:
    p('  ' + r['TABLE_NAME'])

p('\n=== wsd_messages columns ===')
rows = wsd_db.execute_raw_query(
    'SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME=? ORDER BY ORDINAL_POSITION',
    ['wsd_messages'])
for r in rows:
    p(f"  {r['COLUMN_NAME']:40s} {r['DATA_TYPE']}")

p('\n=== All stored procs ===')
rows = wsd_db.execute_raw_query(
    "SELECT name FROM sys.objects WHERE type='P' ORDER BY name", [])
for r in rows:
    p('  ' + r['name'])

out.close()
p('DONE')
