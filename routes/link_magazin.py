from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import get_db
import secrets
from datetime import datetime, date

link_magazin_bp = Blueprint('link_magazin', __name__, url_prefix='/link-magazin')


def _init_tables(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS linkuri_acces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tip TEXT NOT NULL,
            locatie_id INTEGER,
            token TEXT NOT NULL UNIQUE,
            descriere TEXT,
            valid_pana_la TEXT,
            creat_de INTEGER,
            creat_la TEXT DEFAULT CURRENT_TIMESTAMP,
            activ INTEGER DEFAULT 1
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS submisii (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL,
            locatie_id INTEGER NOT NULL,
            tip TEXT NOT NULL,
            data_submisie TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            obs_magazin TEXT,
            obs_admin TEXT,
            revizuit_de INTEGER,
            revizuit_la TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS submisii_detalii (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submisie_id INTEGER NOT NULL,
            produs_id INTEGER,
            denumire_original TEXT,
            cantitate REAL DEFAULT 0
        )
    """)
    db.commit()


@link_magazin_bp.route('/')
@login_required
def index():
    db = get_db()
    _init_tables(db)

    linkuri = db.execute("""
        SELECT la.*,
               COALESCE(l.nume, 'Toate locatiile') as locatie_nume,
               u.nume_complet as creat_de_nume,
               (SELECT COUNT(*) FROM submisii s WHERE s.link_id=la.id AND s.status='pending') as nr_pending,
               (SELECT COUNT(*) FROM submisii s WHERE s.link_id=la.id) as nr_total
        FROM linkuri_acces la
        LEFT JOIN locatii l ON la.locatie_id=l.id
        LEFT JOIN utilizatori u ON la.creat_de=u.id
        ORDER BY la.creat_la DESC
    """).fetchall()

    pending_total = db.execute(
        "SELECT COUNT(*) as cnt FROM submisii WHERE status='pending'"
    ).fetchone()['cnt']

    db.close()
    return render_template('link_magazin/index.html',
                           linkuri=linkuri,
                           pending_total=pending_total,
                           today=date.today().strftime('%Y-%m-%d'))


@link_magazin_bp.route('/genereaza', methods=['POST'])
@login_required
def genereaza():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('link_magazin.index'))

    tip = request.form.get('tip')
    descriere = request.form.get('descriere', '').strip()
    valid_pana_la = request.form.get('valid_pana_la', '').strip() or None

    if tip not in ('inventar', 'comanda'):
        flash('Tipul este obligatoriu.', 'danger')
        return redirect(url_for('link_magazin.index'))

    token = secrets.token_urlsafe(24)
    db = get_db()
    _init_tables(db)
    db.execute("""
        INSERT INTO linkuri_acces (tip, locatie_id, token, descriere, valid_pana_la, creat_de)
        VALUES (?, NULL, ?, ?, ?, ?)
    """, (tip, token, descriere, valid_pana_la, current_user.id))
    db.commit()
    db.close()
    flash(f'Link generat cu succes. Token: {token}', 'success')
    return redirect(url_for('link_magazin.index'))


@link_magazin_bp.route('/dezactiveaza/<int:link_id>', methods=['POST'])
@login_required
def dezactiveaza(link_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('link_magazin.index'))
    db = get_db()
    db.execute("UPDATE linkuri_acces SET activ=0 WHERE id=?", (link_id,))
    db.commit()
    db.close()
    flash('Link dezactivat.', 'success')
    return redirect(url_for('link_magazin.index'))


@link_magazin_bp.route('/reactiveaza/<int:link_id>', methods=['POST'])
@login_required
def reactiveaza(link_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('link_magazin.index'))
    db = get_db()
    db.execute("UPDATE linkuri_acces SET activ=1 WHERE id=?", (link_id,))
    db.commit()
    db.close()
    flash('Link reactivat.', 'success')
    return redirect(url_for('link_magazin.index'))


@link_magazin_bp.route('/sterge/<int:link_id>', methods=['POST'])
@login_required
def sterge(link_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('link_magazin.index'))
    db = get_db()
    sub_ids = [r['id'] for r in db.execute(
        "SELECT id FROM submisii WHERE link_id=?", (link_id,)
    ).fetchall()]
    for sid in sub_ids:
        db.execute("DELETE FROM submisii_detalii WHERE submisie_id=?", (sid,))
    db.execute("DELETE FROM submisii WHERE link_id=?", (link_id,))
    db.execute("DELETE FROM linkuri_acces WHERE id=?", (link_id,))
    db.commit()
    db.close()
    flash('Link sters cu succes.', 'success')
    return redirect(url_for('link_magazin.index'))


@link_magazin_bp.route('/submisii')
@login_required
def submisii():
    db = get_db()
    _init_tables(db)
    status_filter = request.args.get('status', 'pending')

    q = """
        SELECT s.*, l.nume as locatie_nume,
               la.tip as link_tip, la.token,
               u.nume_complet as revizuit_de_nume,
               (SELECT COUNT(*) FROM submisii_detalii sd WHERE sd.submisie_id=s.id) as nr_produse,
               (SELECT SUM(sd.cantitate) FROM submisii_detalii sd WHERE sd.submisie_id=s.id) as total_cant
        FROM submisii s
        LEFT JOIN locatii l ON s.locatie_id=l.id
        LEFT JOIN linkuri_acces la ON s.link_id=la.id
        LEFT JOIN utilizatori u ON s.revizuit_de=u.id
    """
    params = []
    if status_filter and status_filter != 'toate':
        q += " WHERE s.status=?"
        params.append(status_filter)
    q += " ORDER BY s.data_submisie DESC"

    rows = db.execute(q, params).fetchall()
    cnt_pending = db.execute("SELECT COUNT(*) as c FROM submisii WHERE status='pending'").fetchone()['c']
    db.close()
    return render_template('link_magazin/submisii.html',
                           submisii=rows,
                           status_filter=status_filter,
                           cnt_pending=cnt_pending)


@link_magazin_bp.route('/submisii/<int:sub_id>')
@login_required
def detalii_submisie(sub_id):
    db = get_db()
    sub = db.execute("""
        SELECT s.*, l.nume as locatie_nume, la.tip as link_tip, la.token
        FROM submisii s
        LEFT JOIN locatii l ON s.locatie_id=l.id
        LEFT JOIN linkuri_acces la ON s.link_id=la.id
        WHERE s.id=?
    """, (sub_id,)).fetchone()
    if not sub:
        flash('Submisie negasita.', 'danger')
        return redirect(url_for('link_magazin.submisii'))

    detalii = db.execute("""
        SELECT sd.*, p.denumire as produs_denumire, p.unitate_masura
        FROM submisii_detalii sd
        LEFT JOIN produse p ON sd.produs_id=p.id
        WHERE sd.submisie_id=?
        ORDER BY COALESCE(p.denumire, sd.denumire_original)
    """, (sub_id,)).fetchall()
    db.close()
    return render_template('link_magazin/detalii_submisie.html', sub=sub, detalii=detalii)


@link_magazin_bp.route('/submisii/<int:sub_id>/aprobare', methods=['POST'])
@login_required
def aprobare(sub_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('link_magazin.submisii'))

    db = get_db()
    sub = db.execute("SELECT * FROM submisii WHERE id=?", (sub_id,)).fetchone()
    if not sub or sub['status'] != 'pending':
        flash('Submisie invalida sau deja procesata.', 'danger')
        db.close()
        return redirect(url_for('link_magazin.submisii'))

    obs_admin = request.form.get('obs_admin', '').strip()
    data_aprobare = datetime.now().strftime('%Y-%m-%d')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    detalii = db.execute(
        "SELECT * FROM submisii_detalii WHERE submisie_id=? AND produs_id IS NOT NULL",
        (sub_id,)
    ).fetchall()

    if sub['tip'] == 'inventar':
        # Insereaza in stoc_initial_locatii
        for d in detalii:
            existing = db.execute("""
                SELECT id FROM stoc_initial_locatii
                WHERE locatie_id=? AND produs_id=? AND data=?
            """, (sub['locatie_id'], d['produs_id'], data_aprobare)).fetchone()
            if existing:
                db.execute("""
                    UPDATE stoc_initial_locatii SET cantitate=?, utilizator_id=?, created_at=?
                    WHERE id=?
                """, (d['cantitate'], current_user.id, now, existing['id']))
            else:
                db.execute("""
                    INSERT INTO stoc_initial_locatii (locatie_id, produs_id, cantitate, data, utilizator_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sub['locatie_id'], d['produs_id'], d['cantitate'], data_aprobare, current_user.id, now))

    elif sub['tip'] == 'comanda':
        db.execute("""
            CREATE TABLE IF NOT EXISTS comenzi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                locatie_id INTEGER NOT NULL,
                submisie_id INTEGER,
                data_comanda TEXT,
                status TEXT DEFAULT 'noua',
                obs TEXT,
                creat_de INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS comenzi_detalii (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comanda_id INTEGER NOT NULL,
                produs_id INTEGER NOT NULL,
                cantitate REAL DEFAULT 0
            )
        """)
        cur = db.execute("""
            INSERT INTO comenzi (locatie_id, submisie_id, data_comanda, creat_de, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (sub['locatie_id'], sub_id, data_aprobare, current_user.id, now))
        comanda_id = cur.lastrowid
        for d in detalii:
            db.execute("""
                INSERT INTO comenzi_detalii (comanda_id, produs_id, cantitate)
                VALUES (?, ?, ?)
            """, (comanda_id, d['produs_id'], d['cantitate']))

    db.execute("""
        UPDATE submisii SET status='aprobat', obs_admin=?, revizuit_de=?, revizuit_la=?
        WHERE id=?
    """, (obs_admin, current_user.id, now, sub_id))
    db.commit()
    db.close()

    tip_text = 'Stocul a fost importat' if sub['tip'] == 'inventar' else 'Comanda a fost inregistrata'
    flash(f'Submisie aprobata. {tip_text} in baza de date.', 'success')
    return redirect(url_for('link_magazin.submisii'))


@link_magazin_bp.route('/submisii/<int:sub_id>/respingere', methods=['POST'])
@login_required
def respingere(sub_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('link_magazin.submisii'))

    db = get_db()
    obs_admin = request.form.get('obs_admin', '').strip()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.execute("""
        UPDATE submisii SET status='respins', obs_admin=?, revizuit_de=?, revizuit_la=?
        WHERE id=? AND status='pending'
    """, (obs_admin, current_user.id, now, sub_id))
    db.commit()
    db.close()
    flash('Submisie respinsa.', 'warning')
    return redirect(url_for('link_magazin.submisii'))
