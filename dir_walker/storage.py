"""
    CREATE TABLE IF NOT EXISTS files (
        file_id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        file_type INTEGER NOT NULL, # 0 is directory, 1 is file, 
        size_types INTEGER NOT NULL,
        creation_date DATE NOT NULL,
        directory_id INTEGER,
        FOREIGN KEY (directory_id) REFERENCES directories(directory_id)

"""
import sqlite3
from datetime import datetime

# Connect to SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect('dir.sqlite')
cursor = conn.cursor()

# Function to create tables
def create_tables():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS directories (
        directory_id INTEGER PRIMARY KEY AUTOINCREMENT,
        directory_path TEXT NOT NULL UNIQUE
    );''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS files (
        file_id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        file_type INTEGER NOT NULL,
        byte_size INTEGER NOT NULL,
        creation_date DATE NOT NULL,
        directory_id INTEGER,
        FOREIGN KEY (directory_id) REFERENCES directories(directory_id)
    );''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS file_metadata (
        metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER NOT NULL,
        meta_key TEXT NOT NULL,
        meta_value TEXT,
        FOREIGN KEY (file_id) REFERENCES files(file_id)
    );''')

    # Create indexes to improve search performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_filename ON files(filename);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_filetype ON files(file_type);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_creationdate ON files(creation_date);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_directory ON files(directory_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_metadata_key_value ON file_metadata(meta_key, meta_value);')

    conn.commit()

# Function to insert or update file information
def insert_or_update_file(directory_path, filename, file_type, file_size, creation_date, metadata_dict):
    # Check if the directory exists, insert if not
    cursor.execute('SELECT directory_id FROM directories WHERE directory_path = ?', (directory_path,))
    directory = cursor.fetchone()
    if directory is None:
        cursor.execute('INSERT INTO directories (directory_path) VALUES (?)', (directory_path,))
        directory_id = cursor.lastrowid
    else:
        directory_id = directory[0]

    # Check if the file exists
    cursor.execute('SELECT file_id FROM files WHERE filename = ? AND directory_id = ?', (filename, directory_id))
    file = cursor.fetchone()
    if file is None:
        # Insert new file record
        cursor.execute('INSERT INTO files (filename, file_type, byte_size, creation_date, directory_id) VALUES (?, ?, ?, ?, ?)',
                       (filename, file_type, file_size, creation_date, directory_id))
        file_id = cursor.lastrowid
    else:
        file_id = file[0]
        # Update file record (if you have specific fields to update, modify this query accordingly)
        cursor.execute('UPDATE files SET file_type = ?, creation_date = ?, byte_size = ? WHERE file_id = ?',
                       (file_type, creation_date, file_size, file_id))

    # Insert or update metadata
    for key, value in metadata_dict.items():
        cursor.execute('SELECT metadata_id FROM file_metadata WHERE file_id = ? AND meta_key = ?', (file_id, key))
        metadata = cursor.fetchone()
        if metadata is None:
            cursor.execute('INSERT INTO file_metadata (file_id, meta_key, meta_value) VALUES (?, ?, ?)',
                           (file_id, key, value))
        else:
            cursor.execute('UPDATE file_metadata SET meta_value = ? WHERE file_id = ? AND meta_key = ?',
                           (value, file_id, key))

    conn.commit()


