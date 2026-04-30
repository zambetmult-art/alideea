from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db

furnizori_bp = Blueprint('furnizori', __name__, url_prefix='/furnizori')

@furnizori_bp.route('/')
@login_required
def index():
    db = get_db()
    furnizori = db.execute("SELECT * FROM furnizori WHERE activ=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('furnizori/index.html', furnizori=furnizori)

@furnizori_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('furnizori.index'))
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        contact = request.form.get('contact', '').strip()
        telefon = request.form.get('telefon', '').strip()
        email = request.form.get('email', '').strip()
        if not nume:
            flash('Numele este obligatoriu.', 'danger')
        else:
            db = get_db()
            db.execute("INSERT INTO furnizori (nume, contact, telefon, email) VALUES (?,?,?,?)",
                       (nume, contact, telefon, email))
            db.commit()
            db.close()
            flash('Furnizor adaugat.', 'success')
            return redirect(url_for('furnizori.index'))
    return render_template('furnizori/form.html', furnizor=None)

@furnizori_bp.route('/editeaza/<int:id>', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('furnizori.index'))
    db = get_db()
    furnizor = db.execute("SELECT * FROM furnizori WHERE id=?", (id,)).fetchone()
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        contact = request.form.get('contact', '').strip()
        telefon = request.form.get('telefon', '').strip()
        email = request.form.get('email', '').strip()
        db.execute("UPDATE furnizori SET nume=?, contact=?, telefon=?, email=? WHERE id=?",
                   (nume, contact, telefon, email, id))
        db.commit()
        flash('Furnizor actualizat.', 'success')
        return redirect(url_for('furnizori.index'))
    db.close()
    return render_template('furnizori/form.html', furnizor=furnizor)

@furnizori_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('furnizori.index'))
    db = get_db()
    db.execute("UPDATE furnizori SET activ=0 WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Furnizor dezactivat.', 'success')
    return redirect(url_for('furnizori.index'))
