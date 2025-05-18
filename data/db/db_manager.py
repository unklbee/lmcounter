# data/db/db_manager.py
# -*- coding: utf-8 -*-

"""
Database Manager for Vehicle Counter application
Handles SQLite database operations for storing counting data
"""

import os
import sqlite3
import json
import time
import datetime
from pathlib import Path
import threading
from typing import Dict, List, Any, Tuple, Optional, Union

from utils.logger import get_logger
from config.settings import DATABASE_PATH, DB_SCHEMA_PATH

# Setup logger
logger = get_logger(__name__)

class DatabaseManager:
    """Manages database operations for the Vehicle Counter application"""

    def __init__(self, db_path=None, schema_path=None):
        """
        Initialize database manager

        Args:
            db_path (str): Path to SQLite database file
            schema_path (str): Path to SQL schema file
        """
        self.db_path = Path(db_path or DATABASE_PATH)
        self.schema_path = Path(schema_path or DB_SCHEMA_PATH)
        self.connection = None
        self.lock = threading.Lock()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database if it doesn't exist
        if not self.db_path.exists():
            self.initialize_database()

    def initialize_database(self):
        """Initialize the database with schema"""
        try:
            if not self.schema_path.exists():
                logger.error(f"Schema file not found: {self.schema_path}")
                self._create_default_schema()

            # Create database with schema
            conn = self._get_connection()

            with open(self.schema_path, 'r') as f:
                schema_sql = f.read()

            conn.executescript(schema_sql)
            conn.commit()

            logger.info(f"Database initialized at {self.db_path}")

        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            raise

    def _create_default_schema(self):
        """Create default schema file if not exists"""
        try:
            # Create parent directory if needed
            self.schema_path.parent.mkdir(parents=True, exist_ok=True)

            # Default schema content
            default_schema = """
-- Vehicle Counter Database Schema

-- Sessions table to track analysis sessions
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    source_path TEXT,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    config TEXT,  -- JSON configuration used
    notes TEXT
);

-- Vehicle types
CREATE TABLE IF NOT EXISTS vehicle_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    description TEXT
);

-- Insert default vehicle types
INSERT OR IGNORE INTO vehicle_types (name) VALUES 
    ('car'),
    ('truck'),
    ('bus'),
    ('motorcycle'),
    ('bicycle');

-- ROI and line definitions
CREATE TABLE IF NOT EXISTS roi_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    roi_id TEXT,  -- UUID of the ROI/line
    name TEXT,
    type TEXT,    -- 'roi' or 'line'
    points TEXT,  -- JSON array of points
    direction TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Counting events
CREATE TABLE IF NOT EXISTS counting_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    roi_id TEXT,        -- References ROI/line UUID
    object_id INTEGER,  -- Tracking ID
    vehicle_type TEXT,
    direction TEXT,     -- 'in', 'out', etc.
    position TEXT,      -- JSON [x, y] coordinates
    confidence REAL,    -- Detection confidence
    frame_number INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Daily summaries (for faster querying)
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,         -- YYYY-MM-DD
    session_id INTEGER,
    roi_id TEXT,
    vehicle_type TEXT,
    direction TEXT,
    count INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Hourly summaries
CREATE TABLE IF NOT EXISTS hourly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,         -- YYYY-MM-DD
    hour INTEGER,      -- 0-23
    session_id INTEGER,
    roi_id TEXT,
    vehicle_type TEXT,
    direction TEXT,
    count INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_events_session_id ON counting_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON counting_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_roi_id ON counting_events(roi_id);
CREATE INDEX IF NOT EXISTS idx_events_vehicle_type ON counting_events(vehicle_type);
CREATE INDEX IF NOT EXISTS idx_daily_summaries_date ON daily_summaries(date);
CREATE INDEX IF NOT EXISTS idx_hourly_summaries_date_hour ON hourly_summaries(date, hour);
"""

            # Write default schema to file
            with open(self.schema_path, 'w') as f:
                f.write(default_schema)

            logger.info(f"Created default schema at {self.schema_path}")

        except Exception as e:
            logger.error(f"Error creating default schema: {str(e)}")
            raise

    def _get_connection(self):
        """
        Get database connection (create if needed)

        Returns:
            sqlite3.Connection: Database connection
        """
        if self.connection is None:
            self.connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                check_same_thread=False
            )

            # Enable foreign keys
            self.connection.execute("PRAGMA foreign_keys = ON")

            # Configure connection
            self.connection.row_factory = sqlite3.Row

        return self.connection

    def _execute_query(self, query, params=None, fetchall=False, fetchone=False, commit=False):
        """
        Execute SQL query with thread safety

        Args:
            query (str): SQL query
            params (tuple): Query parameters
            fetchall (bool): Whether to fetch all results
            fetchone (bool): Whether to fetch one result
            commit (bool): Whether to commit changes

        Returns:
            list or dict or cursor: Query results or cursor
        """
        with self.lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if commit:
                    conn.commit()

                if fetchall:
                    return [dict(row) for row in cursor.fetchall()]
                elif fetchone:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                else:
                    return cursor

            except Exception as e:
                logger.error(f"Database error in query: {query}")
                logger.error(f"Error details: {str(e)}")
                if commit:
                    conn.rollback()
                raise

    def create_session(self, name=None, source_path=None, config=None, notes=None):
        """
        Create a new session

        Args:
            name (str): Session name
            source_path (str): Video source path
            config (dict): Configuration used
            notes (str): Session notes

        Returns:
            int: Session ID
        """
        # Convert config dict to JSON string
        config_json = json.dumps(config) if config else None

        query = """
                INSERT INTO sessions (name, source_path, config, notes, start_time)
                VALUES (?, ?, ?, ?, ?) \
                """

        current_time = datetime.datetime.now().isoformat()
        cursor = self._execute_query(
            query,
            (name, source_path, config_json, notes, current_time),
            commit=True
        )

        session_id = cursor.lastrowid
        logger.info(f"Created new session with ID: {session_id}")

        return session_id

    def end_session(self, session_id):
        """
        End a session

        Args:
            session_id (int): Session ID

        Returns:
            bool: Success
        """
        current_time = datetime.datetime.now().isoformat()

        query = """
                UPDATE sessions SET end_time = ? WHERE id = ? \
                """

        self._execute_query(query, (current_time, session_id), commit=True)
        logger.info(f"Ended session with ID: {session_id}")

        return True

    def save_roi_definitions(self, session_id, roi_definitions):
        """
        Save ROI/line definitions for a session

        Args:
            session_id (int): Session ID
            roi_definitions (dict): ROI/line definitions

        Returns:
            bool: Success
        """
        # Start a transaction
        conn = self._get_connection()
        with self.lock:
            try:
                cursor = conn.cursor()

                # Clear existing ROI definitions for this session
                cursor.execute(
                    "DELETE FROM roi_definitions WHERE session_id = ?",
                    (session_id,)
                )

                # Insert ROIs
                for roi_id, roi in roi_definitions.get("rois", {}).items():
                    cursor.execute(
                        """
                        INSERT INTO roi_definitions
                            (session_id, roi_id, name, type, points, direction)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            roi_id,
                            roi.get("name", "Unnamed ROI"),
                            "roi",
                            json.dumps(roi.get("points", [])),
                            roi.get("direction", "bidirectional")
                        )
                    )

                # Insert lines
                for line_id, line in roi_definitions.get("counting_lines", {}).items():
                    cursor.execute(
                        """
                        INSERT INTO roi_definitions
                            (session_id, roi_id, name, type, points, direction)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            line_id,
                            line.get("name", "Unnamed Line"),
                            "line",
                            json.dumps(line.get("points", [])),
                            line.get("direction", "north_south")
                        )
                    )

                conn.commit()
                logger.info(f"Saved ROI definitions for session ID: {session_id}")
                return True

            except Exception as e:
                conn.rollback()
                logger.error(f"Error saving ROI definitions: {str(e)}")
                return False

    def save_counting_event(self, session_id, event_data):
        """
        Save a counting event

        Args:
            session_id (int): Session ID
            event_data (dict): Event data

        Returns:
            int: Event ID
        """
        # Extract data from event
        roi_id = event_data.get("id")
        object_id = event_data.get("object_id")
        vehicle_type = event_data.get("class_name")
        direction = event_data.get("direction")
        position = json.dumps(event_data.get("position", [0, 0]))
        confidence = event_data.get("confidence", 0.0)
        frame_number = event_data.get("frame_number", 0)
        timestamp = event_data.get("timestamp", datetime.datetime.now().isoformat())

        query = """
                INSERT INTO counting_events
                (session_id, roi_id, object_id, vehicle_type, direction, position, confidence, frame_number, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) \
                """

        cursor = self._execute_query(
            query,
            (session_id, roi_id, object_id, vehicle_type, direction, position, confidence, frame_number, timestamp),
            commit=True
        )

        event_id = cursor.lastrowid

        # Update daily summary
        self._update_summaries(session_id, roi_id, vehicle_type, direction, timestamp)

        return event_id

    def save_counting_events_batch(self, session_id, events):
        """
        Save multiple counting events in a batch

        Args:
            session_id (int): Session ID
            events (list): List of event data dicts

        Returns:
            int: Number of events saved
        """
        if not events:
            return 0

        # Start a transaction
        conn = self._get_connection()
        with self.lock:
            try:
                cursor = conn.cursor()

                # Insert events
                for event_data in events:
                    # Extract data from event
                    roi_id = event_data.get("id")
                    object_id = event_data.get("object_id")
                    vehicle_type = event_data.get("class_name")
                    direction = event_data.get("direction")
                    position = json.dumps(event_data.get("position", [0, 0]))
                    confidence = event_data.get("confidence", 0.0)
                    frame_number = event_data.get("frame_number", 0)
                    timestamp = event_data.get("timestamp", datetime.datetime.now().isoformat())

                    cursor.execute(
                        """
                        INSERT INTO counting_events
                        (session_id, roi_id, object_id, vehicle_type, direction, position, confidence, frame_number, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (session_id, roi_id, object_id, vehicle_type, direction, position, confidence, frame_number, timestamp)
                    )

                    # Update daily summary
                    self._update_summaries(session_id, roi_id, vehicle_type, direction, timestamp)

                conn.commit()
                logger.info(f"Saved {len(events)} events for session ID: {session_id}")
                return len(events)

            except Exception as e:
                conn.rollback()
                logger.error(f"Error saving batch events: {str(e)}")
                return 0

    def _update_summaries(self, session_id, roi_id, vehicle_type, direction, timestamp):
        """
        Update daily and hourly summaries

        Args:
            session_id (int): Session ID
            roi_id (str): ROI/line ID
            vehicle_type (str): Vehicle type
            direction (str): Direction
            timestamp (str): ISO timestamp
        """
        try:
            # Parse timestamp
            if isinstance(timestamp, str):
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                dt = timestamp

            date_str = dt.strftime("%Y-%m-%d")
            hour = dt.hour

            # Update daily summary
            self._execute_query(
                """
                INSERT INTO daily_summaries (date, session_id, roi_id, vehicle_type, direction, count)
                VALUES (?, ?, ?, ?, ?, 1)
                    ON CONFLICT (date, session_id, roi_id, vehicle_type, direction) DO UPDATE
                                                                                           SET count = count + 1
                """,
                (date_str, session_id, roi_id, vehicle_type, direction),
                commit=True
            )

            # Update hourly summary
            self._execute_query(
                """
                INSERT INTO hourly_summaries (date, hour, session_id, roi_id, vehicle_type, direction, count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT (date, hour, session_id, roi_id, vehicle_type, direction) DO UPDATE
                                                                                                 SET count = count + 1
                """,
                (date_str, hour, session_id, roi_id, vehicle_type, direction),
                commit=True
            )

        except Exception as e:
            logger.error(f"Error updating summaries: {str(e)}")

    def get_sessions(self, limit=50, offset=0):
        """
        Get list of sessions

        Args:
            limit (int): Maximum number of sessions
            offset (int): Offset for pagination

        Returns:
            list: List of session dicts
        """
        query = """
                SELECT * FROM sessions
                ORDER BY start_time DESC
                    LIMIT ? OFFSET ? \
                """

        return self._execute_query(query, (limit, offset), fetchall=True)

    def get_session(self, session_id):
        """
        Get session by ID

        Args:
            session_id (int): Session ID

        Returns:
            dict: Session data
        """
        query = "SELECT * FROM sessions WHERE id = ?"
        return self._execute_query(query, (session_id,), fetchone=True)

    def get_roi_definitions(self, session_id):
        """
        Get ROI/line definitions for session

        Args:
            session_id (int): Session ID

        Returns:
            dict: ROI definitions
        """
        query = "SELECT * FROM roi_definitions WHERE session_id = ?"
        rows = self._execute_query(query, (session_id,), fetchall=True)

        result = {
            "rois": {},
            "counting_lines": {}
        }

        for row in rows:
            # Parse points from JSON
            points = json.loads(row["points"])

            if row["type"] == "roi":
                result["rois"][row["roi_id"]] = {
                    "name": row["name"],
                    "points": points,
                    "direction": row["direction"]
                }
            else:  # line
                result["counting_lines"][row["roi_id"]] = {
                    "name": row["name"],
                    "points": points,
                    "direction": row["direction"]
                }

        return result

    def get_counting_events(self, session_id, start_time=None, end_time=None,
                            roi_id=None, vehicle_type=None, limit=1000):
        """
        Get counting events with filters

        Args:
            session_id (int): Session ID
            start_time (str): Start time (ISO format)
            end_time (str): End time (ISO format)
            roi_id (str): ROI/line ID filter
            vehicle_type (str): Vehicle type filter
            limit (int): Maximum number of events

        Returns:
            list: List of event dicts
        """
        query = "SELECT * FROM counting_events WHERE session_id = ?"
        params = [session_id]

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        if roi_id:
            query += " AND roi_id = ?"
            params.append(roi_id)

        if vehicle_type:
            query += " AND vehicle_type = ?"
            params.append(vehicle_type)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        return self._execute_query(query, tuple(params), fetchall=True)

    def get_count_by_type(self, session_id, roi_id=None):
        """
        Get counts grouped by vehicle type

        Args:
            session_id (int): Session ID
            roi_id (str): Optional ROI/line ID filter

        Returns:
            dict: Counts by vehicle type
        """
        if roi_id:
            query = """
                    SELECT vehicle_type, COUNT(*) as count
                    FROM counting_events
                    WHERE session_id = ? AND roi_id = ?
                    GROUP BY vehicle_type \
                    """
            rows = self._execute_query(query, (session_id, roi_id), fetchall=True)
        else:
            query = """
                    SELECT vehicle_type, COUNT(*) as count
                    FROM counting_events
                    WHERE session_id = ?
                    GROUP BY vehicle_type \
                    """
            rows = self._execute_query(query, (session_id,), fetchall=True)

        # Convert to dict format
        result = {}
        for row in rows:
            result[row["vehicle_type"]] = row["count"]

        return result

    def get_daily_counts(self, session_id=None, start_date=None, end_date=None, roi_id=None):
        """
        Get daily counting summaries

        Args:
            session_id (int): Optional session ID filter
            start_date (str): Start date (YYYY-MM-DD)
            end_date (str): End date (YYYY-MM-DD)
            roi_id (str): Optional ROI/line ID filter

        Returns:
            list: Daily count summaries
        """
        query = "SELECT date, SUM(count) as total_count, vehicle_type, direction FROM daily_summaries WHERE 1=1"
        params = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        if roi_id:
            query += " AND roi_id = ?"
            params.append(roi_id)

        query += " GROUP BY date, vehicle_type, direction ORDER BY date"

        return self._execute_query(query, tuple(params), fetchall=True)

    def get_hourly_counts(self, date, session_id=None, roi_id=None):
        """
        Get hourly counting summaries for a specific date

        Args:
            date (str): Date (YYYY-MM-DD)
            session_id (int): Optional session ID filter
            roi_id (str): Optional ROI/line ID filter

        Returns:
            list: Hourly count summaries
        """
        query = "SELECT hour, SUM(count) as total_count, vehicle_type, direction FROM hourly_summaries WHERE date = ?"
        params = [date]

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if roi_id:
            query += " AND roi_id = ?"
            params.append(roi_id)

        query += " GROUP BY hour, vehicle_type, direction ORDER BY hour"

        return self._execute_query(query, tuple(params), fetchall=True)

    def get_total_counts(self, session_id=None):
        """
        Get total counts summary

        Args:
            session_id (int): Optional session ID filter

        Returns:
            dict: Total counts
        """
        if session_id:
            query = """
                    SELECT vehicle_type, direction, SUM(count) as total_count
                    FROM daily_summaries
                    WHERE session_id = ?
                    GROUP BY vehicle_type, direction \
                    """
            rows = self._execute_query(query, (session_id,), fetchall=True)
        else:
            query = """
                    SELECT vehicle_type, direction, SUM(count) as total_count
                    FROM daily_summaries
                    GROUP BY vehicle_type, direction \
                    """
            rows = self._execute_query(query, fetchall=True)

        # Organize into nested dict
        result = {}
        for row in rows:
            vehicle_type = row["vehicle_type"]
            direction = row["direction"]
            count = row["total_count"]

            if vehicle_type not in result:
                result[vehicle_type] = {}

            result[vehicle_type][direction] = count

        return result

    def export_session_data(self, session_id, format="csv"):
        """
        Export session data in various formats

        Args:
            session_id (int): Session ID
            format (str): Export format ("csv", "json")

        Returns:
            str: Exported data
        """
        # Get all data for the session
        session = self.get_session(session_id)

        if not session:
            return None

        events = self.get_counting_events(session_id, limit=100000)
        roi_definitions = self.get_roi_definitions(session_id)

        data = {
            "session": session,
            "events": events,
            "roi_definitions": roi_definitions
        }

        if format.lower() == "json":
            return json.dumps(data, indent=2)
        elif format.lower() == "csv":
            # Generate CSV for events
            csv_lines = ["timestamp,roi_id,object_id,vehicle_type,direction,confidence,frame_number"]

            for event in events:
                line = (
                    f"{event['timestamp']},{event['roi_id']},{event['object_id']},"
                    f"{event['vehicle_type']},{event['direction']},{event['confidence']},"
                    f"{event['frame_number']}"
                )
                csv_lines.append(line)

            return "\n".join(csv_lines)

        return None

    def vacuum_database(self):
        """
        Optimize database by running VACUUM

        Returns:
            bool: Success
        """
        try:
            with self.lock:
                conn = self._get_connection()
                conn.execute("VACUUM")
                conn.commit()
                logger.info("Database vacuumed successfully")
                return True
        except Exception as e:
            logger.error(f"Error vacuuming database: {str(e)}")
            return False

    def cleanup_old_data(self, days_to_keep=90):
        """
        Delete old data to prevent database growth

        Args:
            days_to_keep (int): Number of days to keep

        Returns:
            int: Number of sessions deleted
        """
        try:
            # Calculate cutoff date
            cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days_to_keep)).isoformat()

            # Delete old sessions (cascade will delete related data)
            query = "DELETE FROM sessions WHERE start_time < ?"
            cursor = self._execute_query(query, (cutoff_date,), commit=True)

            deleted_count = cursor.rowcount
            logger.info(f"Cleaned up {deleted_count} old sessions (older than {days_to_keep} days)")

            # Vacuum database to reclaim space
            self.vacuum_database()

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
            return 0

    def close(self):
        """Close database connection"""
        with self.lock:
            if self.connection:
                self.connection.close()
                self.connection = None
                logger.debug("Database connection closed")


# Singleton instance
_db_manager = None

def get_db_manager():
    """
    Get or create database manager singleton

    Returns:
        DatabaseManager: Database manager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager