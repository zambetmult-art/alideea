from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from database import get_db

analiza_bp = Blueprint('analiza', __name__, url_prefix='/analiza')

@analiza_bp.route('/')
@login_required
def index():
    return redirect_to_magazin()

def redirect_to_magazin():
    from flask import redirect, url_for
    return redirect(url_for('analiza.magazin'))

@analiza_bp.route('/magazin')
@login_required
def magazin():
    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    categorii = db.execute("SELECT * FROM categorii ORDER BY nume").fetchall()
    db.close()
    return render_template('analiza/magazin.html', locatii=locatii, categorii=categorii)

@analiza_bp.route('/companie')
@login_required
def companie():
    db = get_db()
    # Totale generale
    total = db.execute("""
        SELECT COALESCE(SUM(vd.valoare_fara_tva),0) as total_val,
               COALESCE(SUM(vd.cantitate),0) as total_cant,
               COUNT(DISTINCT vi.locatie_id) as nr_locatii
        FROM vanzari_detalii vd
        JOIN vanzari_import vi ON vd.import_id=vi.id
    """).fetchone()
    # Per luna
    per_luna = db.execute("""
        SELECT strftime('%Y-%m', vi.data_raportare) as luna,
               COALESCE(SUM(vd.valoare_fara_tva),0) as valoare,
               COALESCE(SUM(vd.cantitate),0) as cantitate
        FROM vanzari_import vi
        JOIN vanzari_detalii vd ON vd.import_id=vi.id
        GROUP BY luna ORDER BY luna DESC LIMIT 24
    """).fetchall()
    db.close()
    return render_template('analiza/companie.html', total=total,
                           per_luna=list(reversed(per_luna)))

@analiza_bp.route('/produs')
@login_required
def produs():
    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    categorii = db.execute("SELECT * FROM categorii ORDER BY nume").fetchall()
    db.close()
    return render_template('analiza/produs.html', locatii=locatii, categorii=categorii)

@analiza_bp.route('/comparatii')
@login_required
def comparatii():
    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('analiza/comparatii.html', locatii=locatii)

@analiza_bp.route('/api/vanzari_saptamanale')
@login_required
def api_vanzari_saptamanale():
    db = get_db()
    locatie_id = request.args.get('locatie_id')
    params = []
    q = """
        SELECT vi.saptamana, vi.data_raportare,
               COALESCE(SUM(vd.valoare_fara_tva), 0) as valoare,
               COALESCE(SUM(vd.cantitate), 0) as cantitate,
               l.nume as locatie_nume
        FROM vanzari_import vi
        LEFT JOIN vanzari_detalii vd ON vd.import_id=vi.id
        LEFT JOIN locatii l ON vi.locatie_id=l.id
    """
    if locatie_id and locatie_id != 'toate':
        q += " WHERE vi.locatie_id=?"
        params.append(locatie_id)
    q += " GROUP BY vi.id ORDER BY vi.data_raportare DESC LIMIT 52"
    rows = db.execute(q, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in reversed(rows)])

@analiza_bp.route('/api/vanzari_pe_locatii')
@login_required
def api_vanzari_pe_locatii():
    db = get_db()
    data_start = request.args.get('data_start', '')
    data_end = request.args.get('data_end', '')
    q = """
        SELECT l.nume as locatie, l.id,
               COALESCE(SUM(vd.valoare_fara_tva), 0) as valoare,
               COALESCE(SUM(vd.cantitate), 0) as cantitate
        FROM locatii l
        LEFT JOIN vanzari_import vi ON vi.locatie_id=l.id
    """
    params = []
    if data_start and data_end:
        q += " AND vi.data_raportare BETWEEN ? AND ?"
        params += [data_start, data_end]
    elif data_start:
        q += " AND vi.data_raportare >= ?"
        params.append(data_start)
    q += " LEFT JOIN vanzari_detalii vd ON vd.import_id=vi.id WHERE l.activa=1 GROUP BY l.id ORDER BY valoare DESC"
    rows = db.execute(q, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@analiza_bp.route('/api/top_produse')
@login_required
def api_top_produse():
    db = get_db()
    locatie_id = request.args.get('locatie_id')
    categorie_id = request.args.get('categorie_id')
    data_start = request.args.get('data_start', '')
    data_end = request.args.get('data_end', '')
    q = """
        SELECT p.denumire, p.unitate_masura, c.nume as categorie,
               COALESCE(SUM(vd.cantitate), 0) as total_cant,
               COALESCE(SUM(vd.valoare_fara_tva), 0) as total_val
        FROM produse p
        LEFT JOIN categorii c ON p.categorie_id=c.id
        LEFT JOIN vanzari_detalii vd ON vd.produs_id=p.id
        LEFT JOIN vanzari_import vi ON vd.import_id=vi.id
        WHERE p.activ=1
    """
    params = []
    if locatie_id and locatie_id != 'toate':
        q += " AND vi.locatie_id=?"
        params.append(locatie_id)
    if categorie_id and categorie_id != 'toate':
        q += " AND p.categorie_id=?"
        params.append(categorie_id)
    if data_start and data_end:
        q += " AND vi.data_raportare BETWEEN ? AND ?"
        params += [data_start, data_end]
    q += " GROUP BY p.id ORDER BY total_val DESC LIMIT 20"
    rows = db.execute(q, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@analiza_bp.route('/api/vanzari_pe_categorii')
@login_required
def api_vanzari_pe_categorii():
    db = get_db()
    locatie_id = request.args.get('locatie_id')
    data_start = request.args.get('data_start', '')
    data_end = request.args.get('data_end', '')
    q = """
        SELECT c.nume as categorie,
               COALESCE(SUM(vd.valoare_fara_tva), 0) as valoare,
               COALESCE(SUM(vd.cantitate), 0) as cantitate
        FROM categorii c
        LEFT JOIN produse p ON p.categorie_id=c.id
        LEFT JOIN vanzari_detalii vd ON vd.produs_id=p.id
        LEFT JOIN vanzari_import vi ON vd.import_id=vi.id
    """
    params = []
    cond = []
    if locatie_id and locatie_id != 'toate':
        cond.append("vi.locatie_id=?")
        params.append(locatie_id)
    if data_start and data_end:
        cond.append("vi.data_raportare BETWEEN ? AND ?")
        params += [data_start, data_end]
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " GROUP BY c.id ORDER BY valoare DESC"
    rows = db.execute(q, params).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@analiza_bp.route('/api/comparatie_locatii')
@login_required
def api_comparatie_locatii():
    db = get_db()
    rows = db.execute("""
        SELECT l.nume as locatie,
            COALESCE(SUM(CASE WHEN vi.data_raportare >= date('now', '-7 days') THEN vd.valoare_fara_tva ELSE 0 END), 0) as saptamana_curenta,
            COALESCE(SUM(CASE WHEN vi.data_raportare BETWEEN date('now', '-14 days') AND date('now', '-8 days') THEN vd.valoare_fara_tva ELSE 0 END), 0) as saptamana_trecuta,
            COALESCE(SUM(CASE WHEN vi.data_raportare >= date('now', '-30 days') THEN vd.valoare_fara_tva ELSE 0 END), 0) as luna_curenta
        FROM locatii l
        LEFT JOIN vanzari_import vi ON vi.locatie_id=l.id
        LEFT JOIN vanzari_detalii vd ON vd.import_id=vi.id
        WHERE l.activa=1
        GROUP BY l.id ORDER BY luna_curenta DESC
    """).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])
