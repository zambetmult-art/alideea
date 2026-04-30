from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
import json

retururi_bp = Blueprint('retururi', __name__, url_prefix='/retururi')

@retururi_bp.route('/')
@login_required
def index():
    db = get_db()
    q = "SELECT r.*, l.nume as locatie_nume, COUNT(rd.id) as nr_produse FROM retururi r LEFT JOIN locatii l ON r.locatie_id=l.id LEFT JOIN retururi_detalii rd ON rd.retur_id=r.id"
    if not current_user.is_manager() and current_user.locatie_id:
        q += f" WHERE r.locatie_id={current_user.locatie_id}"
    q += " GROUP BY r.id ORDER BY r.data DESC, r.id DESC LIMIT 100"
    retururi = db.execute(q).fetchall()
    db.close()
    return render_template('retururi/index.html', retururi=retururi)

@retururi_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    db = get_db()
    if request.method == 'POST':
        data = request.form.get('data')
        locatie_id = request.form.get('locatie_id')
        if not current_user.is_manager():
            locatie_id = current_user.locatie_id
        nr_document = request.form.get('nr_document', '').strip()
        observatii = request.form.get('observatii', '').strip()
        produse_json = request.form.get('produse_json', '[]')
        try:
            produse_list = json.loads(produse_json)
        except:
            produse_list = []
        if not data or not locatie_id or not produse_list:
            flash('Data, locatia si cel putin un produs sunt obligatorii.', 'danger')
        else:
            cur = db.execute("""INSERT INTO retururi (data, locatie_id, nr_document, observatii, utilizator_id)
                VALUES (?,?,?,?,?)""", (data, locatie_id, nr_document, observatii, current_user.id))
            retur_id = cur.lastrowid
            for p in produse_list:
                db.execute("INSERT INTO retururi_detalii (retur_id, produs_id, cantitate) VALUES (?,?,?)",
                           (retur_id, p['produs_id'], p['cantitate']))
            db.commit()
            flash('Retur inregistrat.', 'success')
            return redirect(url_for('retururi.index'))
    if current_user.is_manager():
        locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    else:
        locatii = db.execute("SELECT * FROM locatii WHERE id=?", (current_user.locatie_id,)).fetchall()
    db.close()
    return render_template('retururi/form.html', locatii=locatii)

@retururi_bp.route('/detalii/<int:id>')
@login_required
def detalii(id):
    db = get_db()
    retur = db.execute("""
        SELECT r.*, l.nume as locatie_nume FROM retururi r
        LEFT JOIN locatii l ON r.locatie_id=l.id WHERE r.id=?
    """, (id,)).fetchone()
    detalii = db.execute("""
        SELECT rd.*, p.denumire, p.unitate_masura FROM retururi_detalii rd
        JOIN produse p ON rd.produs_id=p.id WHERE rd.retur_id=?
    """, (id,)).fetchall()
    db.close()
    return render_template('retururi/detalii.html', retur=retur, detalii=detalii)
