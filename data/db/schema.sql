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
                                               UNIQUE(date, session_id, roi_id, vehicle_type, direction),
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
                                                UNIQUE(date, hour, session_id, roi_id, vehicle_type, direction),
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_events_session_id ON counting_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON counting_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_roi_id ON counting_events(roi_id);
CREATE INDEX IF NOT EXISTS idx_events_vehicle_type ON counting_events(vehicle_type);
CREATE INDEX IF NOT EXISTS idx_daily_summaries_date ON daily_summaries(date);
CREATE INDEX IF NOT EXISTS idx_hourly_summaries_date_hour ON hourly_summaries(date, hour);