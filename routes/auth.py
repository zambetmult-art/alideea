from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        parola = request.form.get('parola', '')
        db = get_db()
        u = db.execute('SELECT * FROM utilizatori WHERE username=? AND activ=1', (username,)).fetchone()
        db.close()
        if u and check_password_hash(u['parola'], parola):
            user = User(u['id'], u['username'], u['rol'], u['nume_complet'], u['locatie_id'])
            login_user(user)
            if user.rol == 'angajat':
                return redirect(url_for('angajat.index'))
            return redirect(url_for('dashboard.index'))
        flash('Username sau parola incorecte.', 'danger')
    return render_template('login.html')

@auth_bp.route('/schimba-parola', methods=['POST'])
@login_required
def schimba_parola():
    if not current_user.is_admin():
        flash('Doar administratorul poate schimba parole.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))
    user_id = request.form.get('user_id', current_user.id)
    parola_noua = request.form.get('parola_noua', '')
    confirmare = request.form.get('confirmare_parola', '')
    if len(parola_noua) < 4:
        flash('Parola noua trebuie sa aiba cel putin 4 caractere.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))
    if parola_noua != confirmare:
        flash('Parolele nu coincid.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))
    db = get_db()
    db.execute('UPDATE utilizatori SET parola=? WHERE id=?',
               (generate_password_hash(parola_noua), user_id))
    db.commit()
    db.close()
    flash('Parola a fost schimbata cu succes!', 'success')
    return redirect(request.referrer or url_for('dashboard.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
