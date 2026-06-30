import os
import pyodbc
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

connections = {
    'PlatformSupportDB': {
        'driver': os.environ.get('PLATFORM_DB_DRIVER', 'ODBC Driver 17 for SQL Server'),
        'server': os.environ.get('PLATFORM_DB_SERVER'),
        'database': os.environ.get('PLATFORM_DB_NAME'),
        'uid': os.environ.get('PLATFORM_DB_USERNAME'),
        'pwd': os.environ.get('PLATFORM_DB_PASSWORD'),
    },
    'TibcoDB': {
        'driver': os.environ.get('TIBCO_DB_DRIVER', 'ODBC Driver 17 for SQL Server'),
        'server': os.environ.get('TIBCO_DB_SERVER'),
        'database': os.environ.get('TIBCO_DB_NAME'),
        'uid': os.environ.get('TIBCO_DB_USERNAME'),
        'pwd': os.environ.get('TIBCO_DB_PASSWORD'),
    },
    'WSDMessagesDB': {
        'driver': os.environ.get('WSD_DB_DRIVER', 'ODBC Driver 17 for SQL Server'),
        'server': os.environ.get('WSD_DB_SERVER'),
        'database': os.environ.get('WSD_DB_NAME'),
        'uid': os.environ.get('WSD_DB_USERNAME'),
        'pwd': os.environ.get('WSD_DB_PASSWORD'),
    },
}

print("Testing DB connections...\n")
all_ok = True
for label, cfg in connections.items():
    conn_str = (
        f"DRIVER={{{cfg['driver']}}};SERVER={cfg['server']};DATABASE={cfg['database']};"
        f"UID={cfg['uid']};PWD={cfg['pwd']}"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        conn.close()
        print(f"[OK]   {label}")
        print(f"       Server:   {cfg['server']}")
        print(f"       Database: {cfg['database']}")
    except Exception as e:
        all_ok = False
        print(f"[FAIL] {label}")
        print(f"       Server:   {cfg['server']}")
        print(f"       Database: {cfg['database']}")
        print(f"       Error:    {e}")
    print()

print("All connections OK." if all_ok else "One or more connections failed.")
