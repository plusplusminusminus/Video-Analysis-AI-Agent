import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict

# Database configuration
DB_NAME: str = "video_database.sqlite"

def generate_schema(cursor: sqlite3.Cursor) -> None:
    """
    Generate the SQLite database schema.

    Creates tables for Videos and Scenes if they don't already exist.

    Args:
        cursor (sqlite3.Cursor): The database cursor used to execute SQL queries.
    """
    # Create Videos Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            director TEXT,
            release_year INTEGER,
            source_file TEXT NOT NULL
        )
    ''')

    # Create Scenes Table (Foreign key links to videos table)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            scene_number INTEGER,
            start_time TEXT,
            end_time TEXT,
            location TEXT,
            description TEXT,
            characters TEXT,
            FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE
        )
    ''')
    print("[*] Database schema generated successfully.")

def parse_scene_file(filepath: str) -> Dict[str, Any]:
    """
    Read and parse the .scene JSON file.

    Args:
        filepath (str): The path to the .scene file to be parsed.

    Returns:
        Dict[str, Any]: The parsed JSON data as a dictionary.

    Raises:
        SystemExit: If the file is not found or contains invalid JSON.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            data: Dict[str, Any] = json.load(file)
            return data
    except json.JSONDecodeError as e:
        print(f"[!] Error: {filepath} is not a valid JSON file.\nDetails: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"[!] Error: The file {filepath} was not found.")
        sys.exit(1)

def insert_data(conn: sqlite3.Connection, data: Dict[str, Any], filename: str) -> None:
    """
    Insert the parsed video and scene data into the SQLite database.

    Args:
        conn (sqlite3.Connection): The database connection object.
        data (Dict[str, Any]): The parsed JSON data containing video and scenes info.
        filename (str): The name of the source file.
    """
    cursor: sqlite3.Cursor = conn.cursor()

    # 1. Insert Video Metadata
    cursor.execute('''
        INSERT INTO videos (title, director, release_year, source_file)
        VALUES (?, ?, ?, ?)
    ''', (
        data.get('video_title', 'Unknown Title'),
        data.get('director', 'Unknown'),
        data.get('release_year', None),
        filename
    ))
    
    video_id: int = cursor.lastrowid or 0
    print(f"[*] Inserted Video: '{data.get('video_title')}' (ID: {video_id})")

    # 2. Insert Scenes
    scenes = data.get('scenes', [])
    for scene in scenes:
        # Convert characters list to a comma-separated string for easy storage
        characters_list = scene.get('characters', [])
        characters_str: str = ", ".join(characters_list) if isinstance(characters_list, list) else str(characters_list)

        cursor.execute('''
            INSERT INTO scenes (video_id, scene_number, start_time, end_time, location, description, characters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            video_id,
            scene.get('scene_number'),
            scene.get('start_time'),
            scene.get('end_time'),
            scene.get('location'),
            scene.get('description'),
            characters_str
        ))
    
    # Commit changes
    conn.commit()
    print(f"[*] Successfully inserted {len(scenes)} scenes into the database.")

def main() -> None:
    """
    Main function to execute the script. Parses arguments, reads the scene file,
    and populates the SQLite database.
    """
    # Setup Argument Parser
    parser = argparse.ArgumentParser(description="Parse a .scene video description file and store it in a SQLite DB.")
    parser.add_argument("scene_file", help="Path to the .scene file")
    
    args = parser.parse_args()
    filepath: str = args.scene_file

    # Validate file extension
    if not filepath.lower().endswith('.scene'):
        print("[!] Warning: The provided file does not have a .scene extension.")

    # Parse the file
    print(f"[*] Reading file: {filepath}")
    scene_data: Dict[str, Any] = parse_scene_file(filepath)

    # Connect to SQLite (Creates file if it doesn't exist)
    conn: sqlite3.Connection = sqlite3.connect(DB_NAME)
    
    try:
        cursor: sqlite3.Cursor = conn.cursor()
        
        # Turn on foreign keys enforcement for SQLite
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # Generate Schema
        generate_schema(cursor)
        
        # Insert Data
        insert_data(conn, scene_data, os.path.basename(filepath))
        
    except sqlite3.Error as e:
        print(f"[!] SQLite Error: {e}")
    finally:
        conn.close()
        print(f"[*] Database connection closed. Data saved in {DB_NAME}")

if __name__ == "__main__":
    main()