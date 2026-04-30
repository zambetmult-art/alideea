from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

documente_bp = Blueprint('documente', __name__, url_prefix='/documente')

TIPURI = {
    'analize':     {'label': 'Analize Medicale',  'luni': 6,    'icon': 'bi-clipboard2-pulse'},
    'curs_igiena': {'label': 'Curs Igiena',        'luni': 36,   'icon': 'bi-mortarboard'},
    'delegatie':   {'label': 'Delegatie',           'luni': 1,    'icon': 'bi-file-earmark-text'},
}

def calc_expirare(data_emitere_str, tip):
    d = datetime.strptime(data_emitere_str, '%Y-%m-%d').date()
    luni = TIPURI[tip]['luni']
    return (d + relativedelta(months=luni)).strftime('%Y-%m-%d')

ZILE_AVERTIZARE = {
    'analize':     30,
    'curs_igiena': 14,
    'delegatie':   7,
}

def status_doc(data_expirare_str, tip=None):
    if not data_expirare_str:
        return 'lipsa'
    exp = datetime.strptime(data_expirare_str, '%Y-%m-%d').date()
    azi = date.today()
    if exp < azi:
        return 'expirat'
    zile = ZILE_AVERTIZARE.get(tip, 30)
    if (exp - azi).days <= zile:
        return 'expira_curand'
    return 'valid'

STATUS_BADGE = {
    'valid':        ('bg-success', 'Valid'),
    'expira_curand':('bg-warning text-dark', 'Expira curand'),
    'expirat':      ('bg-danger',  'Expirat'),
    'lipsa':        ('bg-secondary','Lipsa'),
}


@documente_bp.route('/')
@login_required
def index():
    db = get_db()
    angajati = db.execute("""
        SELECT a.*, l.nume as locatie_nume
        FROM angajati a
        LEFT JOIN locatii l ON a.locatie_id = l.id
        WHERE a.activ=1
        ORDER BY l.nume, a.nume
    """).fetchall()

    azi = date.today().strftime('%Y-%m-%d')
    rezultate = []
    alerte = 0

    for ang in angajati:
        docs = {}
        for tip in TIPURI:
            ultim = db.execute("""
                SELECT * FROM documente_angajati
                WHERE angajat_id=? AND tip=?
                ORDER BY data_emitere DESC LIMIT 1
            """, (ang['id'], tip)).fetchone()
            st = status_doc(ultim['data_expirare'] if ultim else None, tip)
            docs[tip] = {
                'doc': ultim,
                'status': st,
                'badge': STATUS_BADGE[st],
                'expirare': ultim['data_expirare'] if ultim else None,
            }
            if st in ('expirat', 'expira_curand', 'lipsa'):
                alerte += 1
        rezultate.append({'ang': ang, 'docs': docs})

    db.close()
    return render_template('documente/index.html',
                           rezultate=rezultate, tipuri=TIPURI,
                           status_badge=STATUS_BADGE, alerte=alerte, azi=azi)


@documente_bp.route('/angajat/adauga', methods=['GET', 'POST'])
@login_required
def adauga_angajat():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('documente.index'))
    db = get_db()
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        locatie_id = request.form.get('locatie_id') or None
        if not nume:
            flash('Numele este obligatoriu.', 'danger')
        else:
            db.execute("INSERT INTO angajati (nume, locatie_id) VALUES (?,?)", (nume, locatie_id))
            db.commit()
            flash(f'Angajat "{nume}" adaugat.', 'success')
            db.close()
            return redirect(url_for('documente.index'))
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('documente/form_angajat.html', locatii=locatii, angajat=None)


@documente_bp.route('/angajat/<int:id>/editeaza', methods=['GET', 'POST'])
@login_required
def editeaza_angajat(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('documente.index'))
    db = get_db()
    angajat = db.execute("SELECT * FROM angajati WHERE id=?", (id,)).fetchone()
    if not angajat:
        db.close()
        flash('Angajat negasit.', 'danger')
        return redirect(url_for('documente.index'))
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        locatie_id = request.form.get('locatie_id') or None
        activ = 1 if request.form.get('activ') else 0
        if not nume:
            flash('Numele este obligatoriu.', 'danger')
        else:
            db.execute("UPDATE angajati SET nume=?, locatie_id=?, activ=? WHERE id=?",
                       (nume, locatie_id, activ, id))
            db.commit()
            flash('Angajat actualizat.', 'success')
            db.close()
            return redirect(url_for('documente.index'))
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('documente/form_angajat.html', locatii=locatii, angajat=angajat)


@documente_bp.route('/angajat/<int:id>')
@login_required
def detalii_angajat(id):
    db = get_db()
    angajat = db.execute("""
        SELECT a.*, l.nume as locatie_nume
        FROM angajati a LEFT JOIN locatii l ON a.locatie_id=l.id
        WHERE a.id=?
    """, (id,)).fetchone()
    if not angajat:
        db.close()
        flash('Angajat negasit.', 'danger')
        return redirect(url_for('documente.index'))

    istoricul = {}
    for tip in TIPURI:
        docs = db.execute("""
            SELECT * FROM documente_angajati
            WHERE angajat_id=? AND tip=?
            ORDER BY data_emitere DESC
        """, (ang_id := id, tip)).fetchall()
        istoricul[tip] = [
            {**dict(d), 'status': status_doc(d['data_expirare'], tip),
             'badge': STATUS_BADGE[status_doc(d['data_expirare'], tip)]}
            for d in docs
        ]

    db.close()
    return render_template('documente/detalii_angajat.html',
                           angajat=angajat, istoricul=istoricul,
                           tipuri=TIPURI, azi=date.today().strftime('%Y-%m-%d'))


@documente_bp.route('/angajat/<int:id>/adauga-document', methods=['POST'])
@login_required
def adauga_document(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('documente.detalii_angajat', id=id))
    tip = request.form.get('tip')
    data_emitere = request.form.get('data_emitere')
    observatii = request.form.get('observatii', '').strip()

    if not tip or tip not in TIPURI or not data_emitere:
        flash('Date incomplete.', 'danger')
        return redirect(url_for('documente.detalii_angajat', id=id))

    data_expirare = calc_expirare(data_emitere, tip)
    db = get_db()
    db.execute("""
        INSERT INTO documente_angajati (angajat_id, tip, data_emitere, data_expirare, observatii, utilizator_id, created_at)
        VALUES (?,?,?,?,?,?,?)
    """, (id, tip, data_emitere, data_expirare, observatii, current_user.id,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()
    db.close()
    flash(f'{TIPURI[tip]["label"]} adaugat. Expira: {data_expirare}.', 'success')
    return redirect(url_for('documente.detalii_angajat', id=id))


@documente_bp.route('/analize')
@login_required
def analize():
    return _lista_tip('analize', 'Analize Medicale')

@documente_bp.route('/curs-igiena')
@login_required
def curs_igiena():
    return _lista_tip('curs_igiena', 'Curs Igiena')

def _lista_tip(tip, titlu):
    db = get_db()
    azi = date.today()
    angajati = db.execute("""
        SELECT a.*, l.nume as locatie_nume,
               d.data_emitere, d.data_expirare, d.observatii
        FROM angajati a
        LEFT JOIN locatii l ON a.locatie_id = l.id
        LEFT JOIN (
            SELECT angajat_id, data_emitere, data_expirare, observatii
            FROM documente_angajati
            WHERE tip=?
            GROUP BY angajat_id HAVING data_emitere = MAX(data_emitere)
        ) d ON d.angajat_id = a.id
        WHERE a.activ = 1
        ORDER BY d.data_expirare ASC, a.nume
    """, (tip,)).fetchall()
    rezultate = []
    for a in angajati:
        st = status_doc(a['data_expirare'], tip)
        rezultate.append({**dict(a), 'status': st, 'badge': STATUS_BADGE[st]})
    db.close()
    return render_template('documente/lista_tip.html',
                           rezultate=rezultate, titlu=titlu, tip=tip,
                           azi=azi.strftime('%Y-%m-%d'))

@documente_bp.route('/document/<int:id>/sterge', methods=['POST'])
@login_required
def sterge_document(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('documente.index'))
    db = get_db()
    doc = db.execute("SELECT angajat_id FROM documente_angajati WHERE id=?", (id,)).fetchone()
    angajat_id = doc['angajat_id'] if doc else None
    db.execute("DELETE FROM documente_angajati WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Document sters.', 'success')
    if angajat_id:
        return redirect(url_for('documente.detalii_angajat', id=angajat_id))
    return redirect(url_for('documente.index'))
