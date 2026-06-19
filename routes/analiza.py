from flask import Blueprint, render_template, request, jsonify, redirect, url_for
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


@analiza_bp.route('/profitabilitate')
@login_required
def profitabilitate():
    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()

    toti_ani = [r['an'] for r in db.execute("""
        SELECT DISTINCT CAST(strftime('%Y', data_raportare) AS INTEGER) as an
        FROM vanzari_import ORDER BY an DESC
    """).fetchall()]

    locatie_id     = request.args.get('locatie_id', '').strip()
    an_sel         = request.args.get('an', '').strip()
    luna_start_sel = request.args.get('luna_start', '').strip()
    luna_fim_sel   = request.args.get('luna_fim', '').strip()

    luna_start_int = int(luna_start_sel) if luna_start_sel else None
    luna_fim_int   = int(luna_fim_sel)   if luna_fim_sel   else None

    # Numarul de luni din perioada selectata (pentru scalarea salariilor)
    nr_luni = None
    if luna_start_int and luna_fim_int:
        nr_luni = max(1, luna_fim_int - luna_start_int + 1)
    elif an_sel and not luna_start_int:
        nr_luni = 12

    # WHERE pentru vanzari
    cond_v = []; pv = []
    if an_sel:
        cond_v.append("strftime('%Y', vi.data_raportare)=?"); pv.append(an_sel)
    if luna_start_int:
        cond_v.append("CAST(strftime('%m',vi.data_raportare) AS INTEGER)>=?"); pv.append(luna_start_int)
    if luna_fim_int:
        cond_v.append("CAST(strftime('%m',vi.data_raportare) AS INTEGER)<=?"); pv.append(luna_fim_int)
    wv = ("AND " + " AND ".join(cond_v)) if cond_v else ""

    # WHERE pentru intrari (cost marfa)
    cond_i = []; pi = []
    if an_sel:
        cond_i.append("strftime('%Y', i.data)=?"); pi.append(an_sel)
    if luna_start_int:
        cond_i.append("CAST(strftime('%m',i.data) AS INTEGER)>=?"); pi.append(luna_start_int)
    if luna_fim_int:
        cond_i.append("CAST(strftime('%m',i.data) AS INTEGER)<=?"); pi.append(luna_fim_int)
    wi = ("AND " + " AND ".join(cond_i)) if cond_i else ""

    # WHERE pentru salarii (doar an, fara filtru de luna — calculam media lunara)
    cond_sal = []; ps = []
    if an_sel:
        cond_sal.append("s.an=?"); ps.append(int(an_sel))
    ws = ("AND " + " AND ".join(cond_sal)) if cond_sal else ""

    locatii_list = locatii if not locatie_id else [l for l in locatii if str(l['id']) == locatie_id]

    rezultate = []
    for loc in locatii_list:
        lid = loc['id']

        # Venit vanzari
        venit = db.execute(f"""
            SELECT COALESCE(SUM(vd.valoare_fara_tva),0) as val
            FROM vanzari_import vi
            JOIN vanzari_detalii vd ON vd.import_id=vi.id
            WHERE vi.locatie_id=? {wv}
        """, [lid]+pv).fetchone()['val'] or 0

        # Cost marfa (intrari destinate locatiei)
        cost_marfa = db.execute(f"""
            SELECT COALESCE(SUM(id2.cantitate * COALESCE(id2.pret_unitar,0)),0) as val
            FROM intrari i
            JOIN intrari_detalii id2 ON id2.intrare_id=i.id
            WHERE i.locatie_id=? {wi}
        """, [lid]+pi).fetchone()['val'] or 0

        # Salarii: filtru DOAR an+locatie, nu luna — calculam media lunara si inmultim cu nr_luni
        sal_r = db.execute(f"""
            SELECT COALESCE(SUM(s.salariu_brut + s.bonusuri + s.alte_costuri
                               + ROUND(s.salariu_brut * 0.0225, 2)),0) as total,
                   COUNT(DISTINCT s.luna) as luni_in_db,
                   COUNT(DISTINCT s.angajat_id) as nr_ang
            FROM salarii s
            JOIN angajati a ON a.id = s.angajat_id
            WHERE a.locatie_id=? AND a.activ=1 {ws}
        """, [lid]+ps).fetchone()

        cost_a_raw = sal_r['total'] or 0
        luni_in_db = sal_r['luni_in_db'] or 0
        nr_ang     = sal_r['nr_ang'] or 0

        if nr_luni and luni_in_db > 0:
            cost_a = round(cost_a_raw / luni_in_db * nr_luni, 2)
        else:
            cost_a = round(cost_a_raw, 2)

        marja_bruta = venit - cost_marfa
        marja_pct   = (marja_bruta / venit * 100) if venit > 0 else 0
        profit      = marja_bruta - cost_a
        profit_pct  = (profit / venit * 100) if venit > 0 else 0

        rezultate.append({
            'id': lid, 'nume': loc['nume'],
            'venit': venit, 'cost_marfa': cost_marfa,
            'marja_bruta': marja_bruta, 'marja_pct': marja_pct,
            'cost_angajati': cost_a, 'nr_angajati': nr_ang,
            'profit': profit, 'profit_pct': profit_pct,
        })

    rezultate.sort(key=lambda r: r['profit'], reverse=True)

    total_venit          = sum(r['venit'] for r in rezultate)
    total_cost_marfa     = sum(r['cost_marfa'] for r in rezultate)
    total_marja          = total_venit - total_cost_marfa
    total_marja_pct      = (total_marja / total_venit * 100) if total_venit > 0 else 0
    total_cost_angajati  = sum(r['cost_angajati'] for r in rezultate)
    total_profit         = total_marja - total_cost_angajati
    total_profit_pct     = (total_profit / total_venit * 100) if total_venit > 0 else 0

    locatie_sel = next((l for l in locatii if str(l['id']) == locatie_id), None) if locatie_id else None

    sal_detalii = []
    if locatie_id:
        rows_sal = db.execute(f"""
            SELECT a.nume as nume, s.luna, s.an,
                   s.salariu_brut as brut,
                   ROUND(s.salariu_brut * 0.0225, 2) as cam,
                   0 as tichete,
                   s.bonusuri, s.alte_costuri,
                   ROUND(s.salariu_brut + s.bonusuri + s.alte_costuri + s.salariu_brut*0.0225, 2) as cost_total
            FROM salarii s
            JOIN angajati a ON a.id = s.angajat_id
            WHERE a.locatie_id=? AND a.activ=1 {ws}
            ORDER BY s.an DESC, s.luna DESC, a.nume
        """, [int(locatie_id)]+ps).fetchall()
        sal_detalii = [dict(r) for r in rows_sal]

    db.close()
    return render_template('analiza/profitabilitate.html',
        locatii=locatii, toti_ani=toti_ani,
        locatie_id=locatie_id, locatie_sel=locatie_sel,
        an_sel=an_sel,
        luna_start_sel=luna_start_sel, luna_fim_sel=luna_fim_sel,
        nr_luni=nr_luni,
        rezultate=rezultate,
        total_venit=total_venit, total_cost_marfa=total_cost_marfa,
        total_marja=total_marja, total_marja_pct=total_marja_pct,
        total_cost_angajati=total_cost_angajati,
        total_profit=total_profit, total_profit_pct=total_profit_pct,
        sal_detalii=sal_detalii,
    )


@analiza_bp.route('/api/profitabilitate_trend')
@login_required
def api_profitabilitate_trend():
    db = get_db()
    locatie_id = request.args.get('locatie_id', 'toate')

    loc_cond = ""; params = []
    if locatie_id and locatie_id != 'toate':
        loc_cond = "AND vi.locatie_id=?"
        params.append(locatie_id)

    rows_v = db.execute(f"""
        SELECT strftime('%Y-%m', vi.data_raportare) as luna,
               COALESCE(SUM(vd.valoare_fara_tva),0) as venit
        FROM vanzari_import vi
        JOIN vanzari_detalii vd ON vd.import_id=vi.id
        WHERE 1=1 {loc_cond}
        GROUP BY luna ORDER BY luna DESC LIMIT 18
    """, params).fetchall()

    loc_cond_i = ""; params_i = []
    if locatie_id and locatie_id != 'toate':
        loc_cond_i = "AND i.locatie_destinatie_id=?"
        params_i.append(locatie_id)

    rows_i = db.execute(f"""
        SELECT strftime('%Y-%m', i.data) as luna,
               COALESCE(SUM(id2.cantitate * COALESCE(id2.pret_unitar,0)),0) as cost_marfa
        FROM intrari i
        JOIN intrari_detalii id2 ON id2.intrare_id=i.id
        WHERE 1=1 {loc_cond_i}
        GROUP BY luna ORDER BY luna DESC LIMIT 18
    """, params_i).fetchall()

    venit_map = {r['luna']: r['venit'] for r in rows_v}
    cost_map  = {r['luna']: r['cost_marfa'] for r in rows_i}
    luni_set  = sorted(set(list(venit_map.keys()) + list(cost_map.keys())))[-18:]

    rezultat = []
    for luna in luni_set:
        v = venit_map.get(luna, 0)
        c = cost_map.get(luna, 0)
        marja = v - c
        rezultat.append({'luna': luna, 'venit': v, 'cost_marfa': c,
                         'cost_angajati': 0, 'profit': marja})

    db.close()
    return jsonify(rezultat)
