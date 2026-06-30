import os
import logging
import pyodbc
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('db_queries.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class _BaseDBConnection:
    """Generic SQL Server connection wrapper (pyodbc)."""

    def __init__(self, driver_env, server_env, db_env, user_env, pwd_env, label):
        self.label = label
        self.connection_available = False
        self._connection_string = None

        driver = os.environ.get(driver_env, 'ODBC Driver 17 for SQL Server')
        server = os.environ.get(server_env, 'localhost')
        database = os.environ.get(db_env, '')
        username = os.environ.get(user_env, '')
        password = os.environ.get(pwd_env, '')

        self._connection_string = (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"UID={username};PWD={password}"
        )
        self._test_connection()

    def _test_connection(self):
        try:
            conn = pyodbc.connect(self._connection_string, timeout=5)
            conn.close()
            self.connection_available = True
            logger.info(f"[{self.label}] Database connection established successfully.")
        except Exception as exc:
            logger.warning(
                f"[{self.label}] Could not connect to database: {exc}. "
                "Application will use mock data."
            )
            self.connection_available = False

    def execute_raw_query(self, query, params=None):
        """Execute a SELECT query and return a list of dicts."""
        if not self.connection_available:
            raise ConnectionError(
                f"[{self.label}] Database connection is not available."
            )
        try:
            logger.info(f"[{self.label}] Executing: {query}")
            if params:
                logger.info(f"[{self.label}] Params: {params}")

            conn = pyodbc.connect(self._connection_string)
            cursor = conn.cursor()

            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            return [dict(zip(columns, row)) for row in rows]
        except Exception as exc:
            logger.error(f"[{self.label}] Query error: {exc}")
            raise

    def execute_non_query(self, query, params=None):
        """Execute INSERT / UPDATE / stored-proc calls."""
        if not self.connection_available:
            raise ConnectionError(
                f"[{self.label}] Database connection is not available."
            )
        try:
            conn = pyodbc.connect(self._connection_string)
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as exc:
            logger.error(f"[{self.label}] Non-query error: {exc}")
            raise


# ---------------------------------------------------------------------------
# Singleton instances
# ---------------------------------------------------------------------------

class _PlatformDBConnection(_BaseDBConnection):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__(
                'PLATFORM_DB_DRIVER', 'PLATFORM_DB_SERVER',
                'PLATFORM_DB_NAME', 'PLATFORM_DB_USERNAME',
                'PLATFORM_DB_PASSWORD', 'PlatformSupportDB',
            )
        return cls._instance


class _TibcoDBConnection(_BaseDBConnection):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__(
                'TIBCO_DB_DRIVER', 'TIBCO_DB_SERVER',
                'TIBCO_DB_NAME', 'TIBCO_DB_USERNAME',
                'TIBCO_DB_PASSWORD', 'TibcoCaseDataDB',
            )
        return cls._instance


# Public singletons used by services
platform_db = _PlatformDBConnection()
tibco_db = _TibcoDBConnection()
