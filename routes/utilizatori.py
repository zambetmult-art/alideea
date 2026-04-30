from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from database import get_db

utilizatori_bp = Blueprint('utilizatori', __name__, url_prefix='/utilizatori')

@utilizatori_bp.route('/')
@login_required
def index():
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    utilizatori = db.execute("""
        SELECT u.*, l.nume as locatie_nume
        FROM utilizatori u
        LEFT JOIN locatii l ON u.locatie_id = l.id
        WHERE u.activ=1 ORDER BY u.rol, u.nume_complet
    """).fetchall()
    db.close()
    return render_template('utilizatori/index.html', utilizatori=utilizatori)

@utilizatori_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        parola = request.form.get('parola', '')
        nume_complet = request.form.get('nume_complet', '').strip()
        rol = request.form.get('rol', 'angajat')
        locatie_id = request.form.get('locatie_id') or None
        if not username or not parola:
            flash('Username si parola sunt obligatorii.', 'danger')
        else:
            try:
                db.execute("""INSERT INTO utilizatori (username, parola, nume_complet, rol, locatie_id)
                    VALUES (?,?,?,?,?)""",
                    (username, generate_password_hash(parola), nume_complet, rol, locatie_id))
                db.commit()
                flash('Utilizator adaugat.', 'success')
                return redirect(url_for('utilizatori.index'))
            except Exception as e:
                flash(f'Eroare: username exista deja.', 'danger')
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('utilizatori/form.html', utilizator=None, locatii=locatii)

@utilizatori_bp.route('/editeaza/<int:id>', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    utilizator = db.execute("SELECT * FROM utilizatori WHERE id=?", (id,)).fetchone()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        parola = request.form.get('parola', '')
        nume_complet = request.form.get('nume_complet', '').strip()
        rol = request.form.get('rol', 'angajat')
        locatie_id = request.form.get('locatie_id') or None
        if parola:
            db.execute("""UPDATE utilizatori SET username=?, parola=?, nume_complet=?, rol=?, locatie_id=?
                WHERE id=?""", (username, generate_password_hash(parola), nume_complet, rol, locatie_id, id))
        else:
            db.execute("""UPDATE utilizatori SET username=?, nume_complet=?, rol=?, locatie_id=?
                WHERE id=?""", (username, nume_complet, rol, locatie_id, id))
        db.commit()
        flash('Utilizator actualizat.', 'success')
        return redirect(url_for('utilizatori.index'))
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('utilizatori/form.html', utilizator=utilizator, locatii=locatii)

@utilizatori_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    if id == current_user.id:
        flash('Nu te poti sterge pe tine insuti.', 'danger')
        return redirect(url_for('utilizatori.index'))
    db = get_db()
    db.execute("UPDATE utilizatori SET activ=0 WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Utilizator dezactivat.', 'success')
    return redirect(url_for('utilizatori.index'))
