from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
import json

transferuri_bp = Blueprint('transferuri', __name__, url_prefix='/transferuri')

@transferuri_bp.route('/')
@login_required
def index():
    db = get_db()
    transferuri = db.execute("""
        SELECT t.*, ls.nume as sursa_nume, ld.nume as destinatie_nume,
               COUNT(td.id) as nr_produse
        FROM transferuri t
        LEFT JOIN locatii ls ON t.locatie_sursa_id = ls.id
        LEFT JOIN locatii ld ON t.locatie_destinatie_id = ld.id
        LEFT JOIN transferuri_detalii td ON td.transfer_id = t.id
        GROUP BY t.id
        ORDER BY t.data DESC, t.id DESC
        LIMIT 100
    """).fetchall()
    db.close()
    return render_template('transferuri/index.html', transferuri=transferuri)

@transferuri_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('transferuri.index'))
    db = get_db()
    if request.method == 'POST':
        data = request.form.get('data')
        sursa_id = request.form.get('locatie_sursa_id')
        dest_id = request.form.get('locatie_destinatie_id')
        nr_document = request.form.get('nr_document', '').strip()
        observatii = request.form.get('observatii', '').strip()
        produse_json = request.form.get('produse_json', '[]')
        try:
            produse_list = json.loads(produse_json)
        except:
            produse_list = []
        if sursa_id == dest_id:
            flash('Sursa si destinatia nu pot fi aceeasi locatie.', 'danger')
        elif not data or not sursa_id or not dest_id or not produse_list:
            flash('Toate campurile sunt obligatorii.', 'danger')
        else:
            cur = db.execute("""INSERT INTO transferuri (data, locatie_sursa_id, locatie_destinatie_id,
                nr_document, observatii, utilizator_id) VALUES (?,?,?,?,?,?)""",
                (data, sursa_id, dest_id, nr_document, observatii, current_user.id))
            transfer_id = cur.lastrowid
            for p in produse_list:
                db.execute("INSERT INTO transferuri_detalii (transfer_id, produs_id, cantitate) VALUES (?,?,?)",
                           (transfer_id, p['produs_id'], p['cantitate']))
            db.commit()
            flash('Transfer inregistrat.', 'success')
            return redirect(url_for('transferuri.index'))
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('transferuri/form.html', locatii=locatii)

@transferuri_bp.route('/detalii/<int:id>')
@login_required
def detalii(id):
    db = get_db()
    transfer = db.execute("""
        SELECT t.*, ls.nume as sursa_nume, ld.nume as destinatie_nume
        FROM transferuri t
        LEFT JOIN locatii ls ON t.locatie_sursa_id = ls.id
        LEFT JOIN locatii ld ON t.locatie_destinatie_id = ld.id
        WHERE t.id=?
    """, (id,)).fetchone()
    detalii = db.execute("""
        SELECT td.*, p.denumire, p.unitate_masura
        FROM transferuri_detalii td
        JOIN produse p ON td.produs_id = p.id
        WHERE td.transfer_id=?
    """, (id,)).fetchall()
    db.close()
    return render_template('transferuri/detalii.html', transfer=transfer, detalii=detalii)
