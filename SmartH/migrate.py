import sqlite3

DATABASE = 'health.db'

def migrate():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Check if file_path column exists
    cursor.execute("PRAGMA table_info(messages)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'file_path' not in columns:
        print("Adding file_path column to messages...")
        cursor.execute("ALTER TABLE messages ADD COLUMN file_path TEXT")
    
    if 'file_type' not in columns:
        print("Adding file_type column to messages...")
        cursor.execute("ALTER TABLE messages ADD COLUMN file_type TEXT")
        
    # Also update message to be nullable
    # SQLite doesn't support ALTER TABLE to change constraints easily, 
    # but we can just leave it as it is if it's already NOT NULL, 
    # or recreate if really needed. For now, let's just add the columns.
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    migrate()
