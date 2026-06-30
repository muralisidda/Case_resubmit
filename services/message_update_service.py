"""
MessageUpdateService
====================
Handles updating message status in WSD_Messages table.
Takes GUID_Result from frontend and updates MessageStatus = '1'
"""

import logging
import pyodbc
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('message_update.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class MessageUpdateService:
    """Service to handle WSD_Messages status updates."""

    def __init__(self):
        self.connection_available = False
        self._connection_string = None
        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize the database connection string."""
        try:
            driver = os.environ.get('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
            server = os.environ.get('DB_SERVER', 'localhost')
            database = os.environ.get('DB_NAME', 'WebSupportDatabase')
            username = os.environ.get('DB_USER', '')
            password = os.environ.get('DB_PASSWORD', '')

            self._connection_string = (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"UID={username};PWD={password}"
            )
            
            # Test connection
            conn = pyodbc.connect(self._connection_string, timeout=5)
            conn.close()
            self.connection_available = True
            logger.info("Database connection to WebSupportDatabase established successfully.")
        except Exception as exc:
            logger.error(f"Failed to initialize database connection: {exc}")
            self.connection_available = False

    def update_message_status(self, guid_result):
        """
        Update the MessageStatus to '1' for a specific message by GUID.
        
        Args:
            guid_result (str): The MessageIdentifier (GUID) from the frontend
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if not self.connection_available:
            logger.error("Database connection is not available.")
            return False

        if not guid_result:
            logger.error("GUID_Result cannot be empty.")
            return False

        query = (
            "UPDATE [WebSupportDatabase].[dbo].[WSD_Messages] "
            "SET MessageStatus = '1' "
            "WHERE MessageIdentifier = ?"
        )
        
        try:
            logger.info(f"Updating message status for GUID: {guid_result} to status: 1")
            conn = pyodbc.connect(self._connection_string)
            cursor = conn.cursor()
            cursor.execute(query, (guid_result,))
            
            rows_affected = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Update successful. Rows affected: {rows_affected}")
            return True
        except Exception as exc:
            logger.error(f"Error updating message status: {exc}")
            raise


# CLI usage
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python message_update_service.py <GUID_Result>")
        sys.exit(1)

    guid_result = sys.argv[1]
    service = MessageUpdateService()
    
    try:
        success = service.update_message_status(guid_result)
        if success:
            print(f"✓ Message status updated to 1 for GUID: {guid_result}")
        else:
            print(f"✗ Failed to update message status for GUID: {guid_result}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
