from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
import json

distributii_bp = Blueprint('distributii', __name__, url_prefix='/distributii')

@distributii_bp.route('/')
@login_required
def index():
    db = get_db()
    distributii = db.execute("""
        SELECT d.*, l.nume as locatie_nume,
               COUNT(dd.id) as nr_produse,
               COALESCE(SUM(dd.cantitate), 0) as total_cantitate
        FROM distributii d
        LEFT JOIN locatii l ON d.locatie_id = l.id
        LEFT JOIN distributii_detalii dd ON dd.distributie_id = d.id
        GROUP BY d.id
        ORDER BY d.data DESC, d.id DESC
        LIMIT 100
    """).fetchall()
    db.close()
    return render_template('distributii/index.html', distributii=distributii)

@distributii_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('distributii.index'))
    db = get_db()
    if request.method == 'POST':
        data = request.form.get('data')
        locatie_id = request.form.get('locatie_id')
        nr_aviz = request.form.get('nr_aviz', '').strip()
        observatii = request.form.get('observatii', '').strip()
        produse_json = request.form.get('produse_json', '[]')
        try:
            produse_list = json.loads(produse_json)
        except:
            produse_list = []
        if not data or not locatie_id or not produse_list:
            flash('Data, locatia si cel putin un produs sunt obligatorii.', 'danger')
        else:
            cur = db.execute("""INSERT INTO distributii (data, locatie_id, nr_aviz, observatii, utilizator_id)
                VALUES (?,?,?,?,?)""", (data, locatie_id, nr_aviz, observatii, current_user.id))
            dist_id = cur.lastrowid
            for p in produse_list:
                db.execute("INSERT INTO distributii_detalii (distributie_id, produs_id, cantitate) VALUES (?,?,?)",
                           (dist_id, p['produs_id'], p['cantitate']))
            db.commit()
            flash('Aviz distributie inregistrat.', 'success')
            return redirect(url_for('distributii.index'))
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('distributii/form.html', locatii=locatii)

@distributii_bp.route('/detalii/<int:id>')
@login_required
def detalii(id):
    db = get_db()
    distributie = db.execute("""
        SELECT d.*, l.nume as locatie_nume
        FROM distributii d LEFT JOIN locatii l ON d.locatie_id = l.id
        WHERE d.id=?
    """, (id,)).fetchone()
    detalii = db.execute("""
        SELECT dd.*, p.denumire, p.unitate_masura
        FROM distributii_detalii dd
        JOIN produse p ON dd.produs_id = p.id
        WHERE dd.distributie_id=?
    """, (id,)).fetchall()
    db.close()
    return render_template('distributii/detalii.html', distributie=distributie, detalii=detalii)

@distributii_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('distributii.index'))
    db = get_db()
    db.execute("DELETE FROM distributii WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Distributie stearsa.', 'success')
    return redirect(url_for('distributii.index'))
