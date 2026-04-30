from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db

locatii_bp = Blueprint('locatii', __name__, url_prefix='/locatii')

@locatii_bp.route('/')
@login_required
def index():
    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('locatii/index.html', locatii=locatii)

@locatii_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('locatii.index'))
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        adresa = request.form.get('adresa', '').strip()
        if not nume:
            flash('Numele este obligatoriu.', 'danger')
        else:
            db = get_db()
            db.execute("INSERT INTO locatii (nume, adresa) VALUES (?,?)", (nume, adresa))
            db.commit()
            db.close()
            flash('Locatie adaugata.', 'success')
            return redirect(url_for('locatii.index'))
    return render_template('locatii/form.html', locatie=None)

@locatii_bp.route('/editeaza/<int:id>', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('locatii.index'))
    db = get_db()
    locatie = db.execute("SELECT * FROM locatii WHERE id=?", (id,)).fetchone()
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        adresa = request.form.get('adresa', '').strip()
        db.execute("UPDATE locatii SET nume=?, adresa=? WHERE id=?", (nume, adresa, id))
        db.commit()
        flash('Locatie actualizata.', 'success')
        return redirect(url_for('locatii.index'))
    db.close()
    return render_template('locatii/form.html', locatie=locatie)

@locatii_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('locatii.index'))
    db = get_db()
    db.execute("UPDATE locatii SET activa=0 WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Locatie dezactivata.', 'success')
    return redirect(url_for('locatii.index'))
