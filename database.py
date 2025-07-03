# /bunker_game/database.py

import sqlite3
import re
from flask import g
from werkzeug.security import generate_password_hash
from datetime import datetime

DATABASE = 'bunker.db'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
    return db


def close_db(exception=None):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db(app):
    with app.app_context():
        db = get_db()
        # schema.sql тепер не потрібен, бо ми створюємо всі таблиці тут
        # Створення таблиці адміністраторів
        db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
        """)
        # Створення таблиці ігрових сесій
        db.execute("""
            CREATE TABLE IF NOT EXISTS game_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_code TEXT UNIQUE NOT NULL,
                admin_login TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'lobby',
                win_condition_limit INTEGER NOT NULL DEFAULT 2,
                is_voting_active BOOLEAN NOT NULL DEFAULT 0
            );
        """)
        # Створення таблиці голосів
        db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_code TEXT NOT NULL,
                voter_username TEXT NOT NULL,
                voted_for_username TEXT NOT NULL
            );
        """)

        cursor = db.cursor()
        default_admins = [('admin', 'password'), ('fl1wory', 'F#She37bd8m1903')]
        for login, password in default_admins:
            cursor.execute("SELECT login FROM admins WHERE login = ?", (login,))
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO admins (login, password_hash) VALUES (?, ?)",
                               (login, generate_password_hash(password)))
        db.commit()
        print("Database initialized.")


def check_table_exists(table_name):
    cursor = get_db().cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None


# --- Session Management ---
def create_game_session(session_code, admin_login):
    db = get_db()
    db.execute("INSERT INTO game_sessions (session_code, admin_login, created_at) VALUES (?, ?, ?)",
               (session_code, admin_login, datetime.now()))
    db.execute(f'''
        CREATE TABLE "{session_code}" (
            id INTEGER PRIMARY KEY, 
            username TEXT NOT NULL UNIQUE, 
            status TEXT NOT NULL DEFAULT "in_game", 
            gender TEXT, 
            profession TEXT, 
            health TEXT, 
            hobby TEXT, 
            inventory TEXT, 
            human_trait TEXT, 
            secret TEXT,
            is_profession_revealed BOOLEAN NOT NULL DEFAULT 0,
            is_health_revealed BOOLEAN NOT NULL DEFAULT 0,
            is_gender_revealed BOOLEAN NOT NULL DEFAULT 0,
            is_hobby_revealed BOOLEAN NOT NULL DEFAULT 0,
            is_inventory_revealed BOOLEAN NOT NULL DEFAULT 0,
            is_trait_revealed BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    db.commit()


def get_session_details(session_code):
    cursor = get_db().cursor()
    cursor.execute("SELECT * FROM game_sessions WHERE session_code = ?", (session_code,))
    return cursor.fetchone()


def start_game_session(session_code):
    db = get_db()
    db.execute("UPDATE game_sessions SET status = 'running' WHERE session_code = ?", (session_code,))
    db.commit()


def end_session(session_code):
    db = get_db()
    db.execute("UPDATE game_sessions SET status = 'finished' WHERE session_code = ?", (session_code,))
    db.commit()


def delete_session_data(session_code):
    db = get_db()
    db.execute("DELETE FROM game_sessions WHERE session_code = ?", (session_code,))
    db.execute("DELETE FROM votes WHERE session_code = ?", (session_code,))
    if check_table_exists(session_code):
        db.execute(f'DROP TABLE "{session_code}"')
    db.commit()


def get_all_sessions():
    cursor = get_db().cursor()
    cursor.execute("SELECT * FROM game_sessions ORDER BY created_at DESC")
    return cursor.fetchall()


def update_win_condition(session_code, limit):
    db = get_db()
    db.execute("UPDATE game_sessions SET win_condition_limit = ? WHERE session_code = ?", (limit, session_code))
    db.commit()


# --- Player Management ---
def add_player(session_code, username, profile):
    db = get_db()
    try:
        db.execute(
            f'INSERT INTO "{session_code}" (username, gender, profession, health, hobby, inventory, human_trait, secret) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (username, profile['gender'], profile['profession'], profile['health'], profile['hobby'],
             profile['inventory'], profile['human_trait'], profile['secret']))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_player(session_code, username):
    if not check_table_exists(session_code): return None
    cursor = get_db().cursor()
    cursor.execute(f'SELECT * FROM "{session_code}" WHERE username = ?', (username,))
    return cursor.fetchone()


def get_players_in_session(session_code):
    if not check_table_exists(session_code): return []
    cursor = get_db().cursor()
    cursor.execute(f'SELECT * FROM "{session_code}" ORDER BY username')
    return cursor.fetchall()


def count_active_players(session_code):
    if not check_table_exists(session_code): return 0
    cursor = get_db().cursor()
    cursor.execute(f'SELECT COUNT(id) FROM "{session_code}" WHERE status = "in_game"')
    return cursor.fetchone()[0]


def set_player_status(session_code, username, status):
    db = get_db()
    db.execute(f'UPDATE "{session_code}" SET status = ? WHERE username = ?', (status, username))
    db.commit()


def toggle_attribute_visibility(session_code, username, attribute_name):
    valid_attributes = ['profession', 'health', 'gender', 'hobby', 'inventory', 'trait']
    if attribute_name not in valid_attributes: return False
    column_name = f'is_{attribute_name}_revealed'
    db = get_db()
    query = f'UPDATE "{session_code}" SET {column_name} = NOT {column_name} WHERE username = ?'
    db.execute(query, (username,))
    db.commit()
    return True


# --- Admin and Voting Management ---
def get_admin_by_login(login):
    cursor = get_db().cursor()
    cursor.execute("SELECT * FROM admins WHERE login = ?", (login,))
    return cursor.fetchone()


def set_voting_status(session_code, status: bool):
    db = get_db()
    db.execute("UPDATE game_sessions SET is_voting_active = ? WHERE session_code = ?", (status, session_code))
    db.commit()


def clear_votes(session_code):
    db = get_db()
    db.execute("DELETE FROM votes WHERE session_code = ?", (session_code,))
    db.commit()


def cast_vote(session_code, voter_username, candidate):
    db = get_db()
    db.execute("INSERT INTO votes (session_code, voter_username, voted_for_username) VALUES (?, ?, ?)",
               (session_code, voter_username, candidate))
    db.commit()


def tally_votes(session_code):
    cursor = get_db().cursor()
    cursor.execute(
        "SELECT voted_for_username, COUNT(id) as vote_count FROM votes WHERE session_code = ? GROUP BY voted_for_username ORDER BY vote_count DESC LIMIT 1",
        (session_code,))
    result = cursor.fetchone()
    return result['voted_for_username'] if result else None


def get_player_vote(session_code, voter_username):
    cursor = get_db().cursor()
    cursor.execute("SELECT id FROM votes WHERE session_code = ? AND voter_username = ?", (session_code, voter_username))
    return cursor.fetchone() is not None