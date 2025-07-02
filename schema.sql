-- /bunker_game/schema.sql

-- Видаляємо старі таблиці для чистої ініціалізації
DROP TABLE IF EXISTS admins;
DROP TABLE IF EXISTS game_sessions;
DROP TABLE IF EXISTS votes;

-- Таблиця адміністраторів
CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

-- Оновлена таблиця ігрових сесій зі статусом
CREATE TABLE game_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_code TEXT UNIQUE NOT NULL,
    admin_login TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'lobby', -- 'lobby', 'running', 'finished'
    win_condition_limit INTEGER NOT NULL DEFAULT 2,
    is_voting_active BOOLEAN NOT NULL DEFAULT 0
);

-- Таблиця для збереження голосів
CREATE TABLE votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_code TEXT NOT NULL,
    voter_username TEXT NOT NULL,
    voted_for_username TEXT NOT NULL
);