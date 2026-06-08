import sqlite3
from pathlib import Path
from datetime import datetime
from utils.logger import get_logger

logger = get_logger("Tracker")

class JobTracker:
    def __init__(self, db_path: str = "bot_state.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._init_db()

    def _init_db(self):
        # Create table with description column
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                job_id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                status TEXT,
                reason TEXT,
                description TEXT,
                timestamp DATETIME
            )
        """)
        
        # Auto-migrate: check if description column exists, if not, add it
        self.cursor.execute("PRAGMA table_info(applications)")
        columns = [col[1] for col in self.cursor.fetchall()]
        if "description" not in columns:
            logger.info("Migrating database: Adding description column to applications table.")
            self.cursor.execute("ALTER TABLE applications ADD COLUMN description TEXT")
            
        self.conn.commit()

    def is_processed(self, job_id: str) -> bool:
        """Check if a job has already been fully processed (Applied, Skipped, etc.)"""
        self.cursor.execute("SELECT status FROM applications WHERE job_id = ?", (job_id,))
        result = self.cursor.fetchone()
        return result is not None

    def record(self, job_id: str, title: str, company: str, status: str, reason: str = "", description: str = ""):
        """Record the final disposition of a job"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO applications (job_id, title, company, status, reason, description, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (job_id, title, company, status, reason, description, now))
            self.conn.commit()
            logger.debug(f"Recorded job {job_id} as {status}")
        except Exception as e:
            logger.error(f"Failed to record job {job_id} in tracker: {e}")

    def close(self):
        if self.conn:
            self.conn.close()
