from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
from datetime import date

angajat_bp = Blueprint('angajat', __name__, url_prefix='/angajat')

def get_stoc_locatie(db, locatie_id):
    return db.execute("""
        SELECT p.id, p.denumire, p.unitate_masura,
               COALESCE((SELECT SUM(dd.cantitate) FROM distributii_detalii dd
                          JOIN distributii d ON dd.distributie_id=d.id
                          WHERE dd.produs_id=p.id AND d.locatie_id=?), 0)
               + COALESCE((SELECT SUM(td.cantitate) FROM transferuri_detalii td
                            JOIN transferuri t ON td.transfer_id=t.id
                            WHERE td.produs_id=p.id AND t.locatie_destinatie_id=?), 0)
               - COALESCE((SELECT SUM(rd.cantitate) FROM retururi_detalii rd
                            JOIN retururi r ON rd.retur_id=r.id
                            WHERE rd.produs_id=p.id AND r.locatie_id=?), 0)
               - COALESCE((SELECT SUM(td2.cantitate) FROM transferuri_detalii td2
                            JOIN transferuri t2 ON td2.transfer_id=t2.id
                            WHERE td2.produs_id=p.id AND t2.locatie_sursa_id=?), 0)
               - COALESCE((SELECT SUM(vd.cantitate) FROM vanzari_detalii vd
                            JOIN vanzari_import vi ON vd.import_id=vi.id
                            WHERE vd.produs_id=p.id AND vi.locatie_id=?), 0)
               - COALESCE((SELECT SUM(pi.cantitate) FROM pierderi pi
                            WHERE pi.produs_id=p.id AND pi.locatie_id=?), 0)
               as stoc_curent
        FROM produse p
        WHERE p.activ=1
        ORDER BY p.denumire
    """, (locatie_id,)*6).fetchall()

@angajat_bp.route('/')
@login_required
def index():
    if current_user.is_manager():
        return redirect(url_for('dashboard.index'))
    if not current_user.locatie_id:
        return render_template('angajat/fara_locatie.html')

    db = get_db()
    locatie = db.execute("SELECT * FROM locatii WHERE id=?",
                         (current_user.locatie_id,)).fetchone()
    azi = date.today().strftime('%Y-%m-%d')

    # Verifica daca a fost deja facut inventarul azi
    inventar_azi = db.execute("""
        SELECT * FROM inventar
        WHERE locatie_id=? AND data=? AND finalizat=1
    """, (current_user.locatie_id, azi)).fetchone()

    if inventar_azi:
        # Arata pagina de confirmare - deja trimis
        detalii = db.execute("""
            SELECT id2.*, p.denumire, p.unitate_masura
            FROM inventar_detalii id2
            JOIN produse p ON id2.produs_id=p.id
            WHERE id2.inventar_id=?
            ORDER BY p.denumire
        """, (inventar_azi['id'],)).fetchall()
        db.close()
        return render_template('angajat/deja_trimis.html',
                               locatie=locatie, inventar=inventar_azi,
                               detalii=detalii, azi=azi)

    # Verifica daca exista un inventar nefinalizat azi
    inventar_draft = db.execute("""
        SELECT * FROM inventar
        WHERE locatie_id=? AND data=? AND finalizat=0
    """, (current_user.locatie_id, azi)).fetchone()

    if inventar_draft:
        inv_id = inventar_draft['id']
        detalii = db.execute("""
            SELECT id2.*, p.denumire, p.unitate_masura
            FROM inventar_detalii id2
            JOIN produse p ON id2.produs_id=p.id
            WHERE id2.inventar_id=?
            ORDER BY p.denumire
        """, (inv_id,)).fetchall()
        db.close()
        return render_template('angajat/inventar.html',
                               locatie=locatie, detalii=detalii,
                               inv_id=inv_id, azi=azi)

    # Creeaza inventar nou
    stocuri = get_stoc_locatie(db, current_user.locatie_id)
    produse_active = [s for s in stocuri if s['stoc_curent'] > 0]

    if not produse_active:
        # Arata toate produsele daca nu exista stoc calculat
        produse_active = stocuri

    cur = db.execute("""
        INSERT INTO inventar (data, locatie_id, utilizator_id)
        VALUES (?,?,?)
    """, (azi, current_user.locatie_id, current_user.id))
    inv_id = cur.lastrowid

    for s in produse_active:
        db.execute("""
            INSERT INTO inventar_detalii (inventar_id, produs_id, cantitate_sistem, cantitate_fizica)
            VALUES (?,?,?,?)
        """, (inv_id, s['id'], s['stoc_curent'], s['stoc_curent']))

    db.commit()

    detalii = db.execute("""
        SELECT id2.*, p.denumire, p.unitate_masura
        FROM inventar_detalii id2
        JOIN produse p ON id2.produs_id=p.id
        WHERE id2.inventar_id=?
        ORDER BY p.denumire
    """, (inv_id,)).fetchall()
    db.close()

    return render_template('angajat/inventar.html',
                           locatie=locatie, detalii=detalii,
                           inv_id=inv_id, azi=azi)


@angajat_bp.route('/salveaza', methods=['POST'])
@login_required
def salveaza():
    if current_user.is_manager():
        return redirect(url_for('dashboard.index'))

    inv_id = request.form.get('inv_id')
    azi = date.today().strftime('%Y-%m-%d')

    db = get_db()

    # Verifica ca inventarul apartine angajatei si nu e finalizat
    inv = db.execute("""
        SELECT * FROM inventar WHERE id=? AND locatie_id=? AND finalizat=0
    """, (inv_id, current_user.locatie_id)).fetchone()

    if not inv:
        db.close()
        flash('Inventarul nu a fost gasit sau a fost deja trimis.', 'danger')
        return redirect(url_for('angajat.index'))

    detalii_ids = request.form.getlist('detaliu_id')
    cantitati = request.form.getlist('cantitate_fizica')

    erori = []
    for det_id, cant_str in zip(detalii_ids, cantitati):
        cant_str = cant_str.strip().replace(',', '.')
        if not cant_str:
            erori.append(det_id)
            continue
        try:
            cant = float(cant_str)
            if cant < 0:
                erori.append(det_id)
                continue
            db.execute("UPDATE inventar_detalii SET cantitate_fizica=? WHERE id=?",
                       (cant, int(det_id)))
        except ValueError:
            erori.append(det_id)

    if erori:
        db.rollback()
        db.close()
        flash('Toate cantitatile trebuie sa fie numere valide (ex: 2.5)', 'danger')
        return redirect(url_for('angajat.index'))

    # Finalizeaza inventarul
    db.execute("UPDATE inventar SET finalizat=1 WHERE id=?", (inv_id,))
    db.commit()
    db.close()

    return redirect(url_for('angajat.index'))
