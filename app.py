# /bunker_game/app.py

import random
import string
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from werkzeug.security import check_password_hash
import database
import game_data

app = Flask(__name__)
application = app  # Псевдонім для WSGI-сервера, як-от uWSGI
app.config['SECRET_KEY'] = 'a_very_secret_key_for_flask_sessions'

@app.teardown_appcontext
def close_connection(exception):
    """Закриває з'єднання з БД після кожного запиту."""
    database.close_db(exception)

def generate_player_profile():
    """Створює повний профіль для нового гравця."""
    return {
        "gender": random.choice(game_data.GENDERS),
        "profession": random.choice(game_data.PROFESSIONS),
        "health": random.choice(game_data.HEALTH_CONDITIONS),
        "hobby": random.choice(game_data.HOBBIES),
        "inventory": random.choice(game_data.INVENTORY),
        "human_trait": random.choice(game_data.HUMAN_TRAITS),
        "secret": random.choice(game_data.SECRETS),
    }

# --- Player and Main Game Routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        session_code = request.form['session-code'].upper()
        if not username or not session_code: return render_template('error.html', error_message="Ім'я та код сесії є обов'язковими.")
        session_details = database.get_session_details(session_code)
        if not session_details: return render_template('error.html', error_message=f"Сесію '{session_code}' не знайдено.")
        if session_details['status'] != 'lobby': return render_template('error.html', error_message=f"Гра в сесії '{session_code}' вже почалась або завершена.")
        player = database.get_player(session_code, username)
        if player:
            session['username'], session['session_code'] = player['username'], session_code
            return redirect(url_for('game_room'))
        if not database.add_player(session_code, username, generate_player_profile()):
            return render_template('error.html', error_message=f"Ім'я '{username}' вже зайняте у цій сесії.")
        session['username'], session['session_code'] = username, session_code
        return redirect(url_for('game_room'))
    return render_template('index.html')

@app.route('/game')
def game_room():
    if 'username' not in session or 'session_code' not in session: return redirect(url_for('index'))
    session_details = database.get_session_details(session['session_code'])
    if not session_details or session_details['status'] == 'finished':
        session.clear()
        return render_template('error.html', error_message="Сесію, до якої ви були підключені, було завершено.")
    player = database.get_player(session['session_code'], session['username'])
    if not player or player['status'] != 'in_game':
        session.clear()
        return render_template('error.html', error_message="Вас було виключено з гри.")
    if session_details['status'] == 'lobby':
        return render_template('lobby.html', player=player, session_code=session['session_code'])
    if session_details['status'] == 'running':
        active_players_count = database.count_active_players(session['session_code'])
        if active_players_count <= session_details['win_condition_limit']: return redirect(url_for('game_over'))
        other_players = [p for p in database.get_players_in_session(session['session_code']) if p['status'] == 'in_game' and p['username'] != player['username']]
        has_voted = database.get_player_vote(session['session_code'], player['username'])
        return render_template('game_room.html', player=player, session_details=session_details, other_players=other_players, has_voted=has_voted)
    return redirect(url_for('index'))


@app.route('/game/vote', methods=['POST'])
def player_vote():
    if 'username' not in session: abort(401)
    # Отримуємо значення однієї обраної радіокнопки
    candidate = request.form.get('candidate')

    # Перевіряємо, чи було зроблено вибір
    if not candidate:
        # Можна додати повідомлення про помилку, якщо потрібно
        return redirect(url_for('game_room'))

    database.cast_vote(session['session_code'], session['username'], candidate)
    return redirect(url_for('game_room'))

@app.route('/game_over')
def game_over():
    if 'session_code' not in session: return redirect(url_for('index'))
    session_code = session['session_code']
    session_details = database.get_session_details(session_code)
    winners = [p for p in database.get_players_in_session(session_code) if p['status'] == 'in_game']
    return render_template('game_over.html', winners=winners, session_details=session_details)


# --- API Endpoints ---
@app.route('/api/game_state/<session_code>')
def api_game_state(session_code):
    if 'username' not in session: abort(401)
    session_details = database.get_session_details(session_code)
    if not session_details: abort(404)
    players_in_lobby = database.get_players_in_session(session_code)
    players_html = render_template('_player_list.html', players_in_lobby=players_in_lobby)
    return jsonify({'session_status': session_details['status'], 'is_voting_active': session_details['is_voting_active'], 'players_html': players_html})

@app.route('/api/admin_session_state/<session_code>')
def api_admin_session_state(session_code):
    if 'admin_login' not in session: abort(401)
    session_details = database.get_session_details(session_code)
    if not session_details: abort(404)
    players = database.get_players_in_session(session_code)
    active_player_count = database.count_active_players(session_code)
    players_html = render_template('_admin_player_list.html', players=players, session=session_details, active_player_count=active_player_count)
    return jsonify({'players_html': players_html})


# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        admin = database.get_admin_by_login(request.form['login'])
        if admin and check_password_hash(admin['password_hash'], request.form['password']):
            session['admin_login'] = admin['login']
            return redirect(url_for('admin_dashboard'))
        return render_template('admin_login.html', error="Невірний логін або пароль")
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_login' not in session: return redirect(url_for('admin_login'))
    all_sessions = database.get_all_sessions()
    return render_template('admin_dashboard.html', sessions=all_sessions, username=session['admin_login'])

@app.route('/admin/session/<session_code>')
def admin_session_details(session_code):
    if 'admin_login' not in session: return redirect(url_for('admin_login'))
    session_details = database.get_session_details(session_code)
    if not session_details: abort(404)
    players = database.get_players_in_session(session_code)
    active_player_count = database.count_active_players(session_code)
    return render_template('admin_session_details.html', session=session_details, players=players, active_player_count=active_player_count)

@app.route('/admin/create_session', methods=['POST'])
def create_session():
    if 'admin_login' not in session: abort(401)
    chars = string.ascii_uppercase + string.digits
    while True:
        session_code = ''.join(random.choice(chars) for _ in range(5))
        if not database.check_table_exists(session_code): break
    database.create_game_session(session_code, session['admin_login'])
    return jsonify({'session_code': session_code})

@app.route('/admin/start_game/<session_code>', methods=['POST'])
def start_game(session_code):
    if 'admin_login' not in session: abort(401)
    database.start_game_session(session_code)
    return redirect(url_for('admin_session_details', session_code=session_code))

@app.route('/admin/force_end_session/<session_code>', methods=['POST'])
def force_end_session(session_code):
    if 'admin_login' not in session: abort(401)
    database.end_session(session_code)
    return redirect(url_for('admin_session_details', session_code=session_code))

@app.route('/admin/delete_session/<session_code>', methods=['POST'])
def delete_session(session_code):
    if 'admin_login' not in session: abort(401)
    database.delete_session_data(session_code)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kick_player/<session_code>/<username>', methods=['POST'])
def kick_player(session_code, username):
    if 'admin_login' not in session: abort(401)
    database.set_player_status(session_code, username, 'kicked_by_admin')
    return redirect(url_for('admin_session_details', session_code=session_code))

@app.route('/admin/update_win_limit/<session_code>', methods=['POST'])
def update_win_limit(session_code):
    if 'admin_login' not in session: abort(401)
    limit = int(request.form['win_limit'])
    database.update_win_condition(session_code, limit)
    return redirect(url_for('admin_session_details', session_code=session_code))

@app.route('/admin/manage_vote/<session_code>', methods=['POST'])
def manage_vote(session_code):
    if 'admin_login' not in session: abort(401)
    action = request.form['action']
    if action == 'start':
        database.clear_votes(session_code)
        database.set_voting_status(session_code, True)
    elif action == 'cancel':
        database.set_voting_status(session_code, False)
        database.clear_votes(session_code)
    elif action == 'tally':
        database.set_voting_status(session_code, False)
        player_to_kick = database.tally_votes(session_code)
        if player_to_kick: database.set_player_status(session_code, player_to_kick, 'voted_out')
        database.clear_votes(session_code)
    return redirect(url_for('admin_session_details', session_code=session_code))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    database.init_db(app)
    app.run(debug=True, port=5000)