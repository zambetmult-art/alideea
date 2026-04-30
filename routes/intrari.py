from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import get_db
import json, os, re
import pandas as pd
from datetime import datetime, timedelta, date

intrari_bp = Blueprint('intrari', __name__, url_prefix='/intrari')

@intrari_bp.route('/')
@login_required
def index():
    db = get_db()
    intrari = db.execute("""
        SELECT i.*, f.nume as furnizor_nume,
               COUNT(id2.id) as nr_produse,
               COALESCE(SUM(id2.cantitate * id2.pret_unitar), 0) as valoare_totala
        FROM intrari i
        LEFT JOIN furnizori f ON i.furnizor_id = f.id
        LEFT JOIN intrari_detalii id2 ON id2.intrare_id = i.id
        GROUP BY i.id
        ORDER BY i.data DESC, i.id DESC
        LIMIT 100
    """).fetchall()
    db.close()
    return render_template('intrari/index.html', intrari=intrari)

@intrari_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('intrari.index'))
    db = get_db()
    if request.method == 'POST':
        data = request.form.get('data')
        furnizor_id = request.form.get('furnizor_id') or None
        nr_document = request.form.get('nr_document', '').strip()
        observatii = request.form.get('observatii', '').strip()
        produse_json = request.form.get('produse_json', '[]')
        try:
            produse_list = json.loads(produse_json)
        except:
            produse_list = []
        if not data or not produse_list:
            flash('Data si cel putin un produs sunt obligatorii.', 'danger')
        else:
            cur = db.execute("""INSERT INTO intrari (data, furnizor_id, nr_document, observatii, utilizator_id)
                VALUES (?,?,?,?,?)""", (data, furnizor_id, nr_document, observatii, current_user.id))
            intrare_id = cur.lastrowid
            for p in produse_list:
                db.execute("INSERT INTO intrari_detalii (intrare_id, produs_id, cantitate, pret_unitar) VALUES (?,?,?,?)",
                           (intrare_id, p['produs_id'], p['cantitate'], p.get('pret_unitar', 0)))
            db.commit()
            flash('Intrare stoc inregistrata.', 'success')
            return redirect(url_for('intrari.index'))
    furnizori = db.execute("SELECT * FROM furnizori WHERE activ=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('intrari/form.html', furnizori=furnizori, today=date.today().strftime('%Y-%m-%d'))

@intrari_bp.route('/detalii/<int:id>')
@login_required
def detalii(id):
    db = get_db()
    intrare = db.execute("""
        SELECT i.*, f.nume as furnizor_nume
        FROM intrari i LEFT JOIN furnizori f ON i.furnizor_id = f.id
        WHERE i.id=?
    """, (id,)).fetchone()
    detalii = db.execute("""
        SELECT id2.*, p.denumire, p.unitate_masura
        FROM intrari_detalii id2
        JOIN produse p ON id2.produs_id = p.id
        WHERE id2.intrare_id=?
    """, (id,)).fetchall()
    db.close()
    return render_template('intrari/detalii.html', intrare=intrare, detalii=detalii)


def _cauta_locatie(db, txt_locatie):
    """Cauta locatia in DB dupa scor de potrivire a cuvintelor."""
    if not txt_locatie:
        return None, None
    txt = txt_locatie.strip().upper()
    # Normalizeaza spatii multiple
    txt = re.sub(r'\s+', ' ', txt)
    loc = db.execute("SELECT id, nume FROM locatii WHERE UPPER(TRIM(nume))=? AND activa=1", (txt,)).fetchone()
    if loc:
        return loc['id'], loc['nume']
    cuvinte = [c for c in txt.split() if len(c) >= 2]
    toate = db.execute("SELECT id, nume FROM locatii WHERE activa=1").fetchall()
    scoruri = []
    for loc in toate:
        nume_db = re.sub(r'\s+', ' ', loc['nume'].upper().strip())
        potriviri = sum(1 for c in cuvinte if c in nume_db)
        if potriviri > 0:
            # Tiebreaker: prefer shorter DB name (mai exact); id ensures Row never compared
            scoruri.append((-potriviri, len(loc['nume']), loc['id'], loc))
    if scoruri:
        scoruri.sort()
        best = scoruri[0][3]
        return best['id'], best['nume']
    return None, None


def _excel_serial_to_date(val):
    """Converteste serial Excel sau string data in format YYYY-MM-DD."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    try:
        return (datetime(1899, 12, 30) + timedelta(days=int(float(val)))).strftime('%Y-%m-%d')
    except:
        s = str(val).strip()[:10]
        if re.match(r'\d{4}-\d{2}-\d{2}', s):
            return s
        return None


def _norm(s):
    s = str(s or '').strip().upper()
    s = re.sub(r'^\d+\.\s*', '', s)
    return s


@intrari_bp.route('/import-excel', methods=['GET', 'POST'])
@login_required
def import_excel():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('intrari.index'))

    UPLOADS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
    os.makedirs(UPLOADS, exist_ok=True)

    db = get_db()
    furnizori = db.execute("SELECT * FROM furnizori WHERE activ=1 ORDER BY nume").fetchall()
    produse_db = db.execute("SELECT id, denumire, cod_articol FROM produse WHERE activ=1").fetchall()
    db.close()

    if request.method == 'POST':
        pas = request.form.get('pas', '1')

        # ── PAS 1: upload fisiere → detecteaza format → preview ─────────────
        if pas == '1':
            files = request.files.getlist('fisiere')
            valid_files = [f for f in files if f and f.filename.endswith(('.xlsx', '.xls'))]
            if not valid_files:
                flash('Incarca cel putin un fisier Excel (.xlsx sau .xls).', 'danger')
                return render_template('intrari/import_excel.html', furnizori=furnizori, pas=1)

            prod_by_cod  = {}
            prod_by_name = {}
            for p in produse_db:
                if p['cod_articol']:
                    prod_by_cod[str(p['cod_articol']).strip().upper()] = p
                prod_by_name[_norm(p['denumire'])] = p
            prod_dict = {_norm(p['denumire']): {'id': p['id'], 'denumire': p['denumire']} for p in produse_db}

            db2 = get_db()
            groups    = {}   # key: (client_raw, data_str) — format intrari
            locatii_all = [] # format inventar
            format_detected = None

            for fisier in valid_files:
                cale = os.path.join(UPLOADS, fisier.filename)
                fisier.save(cale)
                try:
                    engine = 'xlrd' if fisier.filename.endswith('.xls') else 'openpyxl'
                    df = pd.read_excel(cale, engine=engine)
                    df.columns = [str(c).strip() for c in df.columns]
                    cols_lower = [c.lower() for c in df.columns]

                    has_client   = any('client' in c for c in cols_lower)
                    has_den_gest = any(c in ('den_gest', 'gest', 'gestiune', 'locatie') for c in cols_lower)

                    if has_client or has_den_gest:
                        # ── FORMAT INTRARI (rand per livrare) ──
                        format_detected = 'intrari'

                        def find_col(*keywords, _df=df):
                            for kw in keywords:
                                for col in _df.columns:
                                    if kw.lower() in col.lower():
                                        return col
                            return None

                        col_cod  = find_col('cod_art', 'cod articol', 'cod_articol', 'cod art', 'codarticol')
                        col_den  = find_col('denumire')
                        col_cli  = find_col('den_gest', 'gest', 'client', 'locatie')
                        col_cant = find_col('cantitate', 'cant')
                        col_data = find_col('data')
                        col_pret = find_col('pretintrare', 'pret intrare', 'pret_intrare', 'pret')
                        col_um   = find_col('um', 'unitate masura', 'unitate_masura')

                        for _, row in df.iterrows():
                            client_raw = str(row[col_cli] if col_cli else '').strip()
                            if not client_raw or client_raw.lower() == 'nan':
                                continue

                            locatie_excel = client_raw.split(' - ')[-1].strip() if ' - ' in client_raw else client_raw
                            data_val = row[col_data] if col_data else None
                            data_str = _excel_serial_to_date(data_val) or date.today().strftime('%Y-%m-%d')

                            key = (client_raw, data_str)
                            if key not in groups:
                                locatie_id, locatie_db = _cauta_locatie(db2, locatie_excel)
                                groups[key] = {
                                    'client_raw':    client_raw,
                                    'locatie_excel': locatie_excel,
                                    'locatie_id':    locatie_id,
                                    'locatie_db':    locatie_db or locatie_excel,
                                    'locatie_gasita': locatie_id is not None,
                                    'data':          data_str,
                                    'produse':       [],
                                    'nerecunoscute': [],
                                    'fisier_sursa':  fisier.filename
                                }

                            cod = str(row[col_cod] if col_cod else '').strip()
                            if cod.lower() == 'nan': cod = ''
                            den_excel = str(row[col_den] if col_den else '').strip()
                            if den_excel.lower() == 'nan': den_excel = ''
                            try: cant = float(row[col_cant]) if col_cant else 0
                            except: cant = 0
                            try: pret = float(row[col_pret]) if col_pret else 0
                            except: pret = 0
                            um = str(row[col_um] if col_um else 'kg').strip()
                            if um.lower() == 'nan': um = 'kg'

                            if cant <= 0:
                                continue

                            produs = prod_by_cod.get(cod.upper()) if cod else None
                            if not produs and den_excel:
                                produs = prod_by_name.get(_norm(den_excel))

                            if produs:
                                groups[key]['produse'].append({
                                    'produs_id':      produs['id'],
                                    'denumire':       produs['denumire'],
                                    'denumire_excel': den_excel,
                                    'cantitate':      cant,
                                    'pret_unitar':    pret,
                                    'um':             um
                                })
                            else:
                                groups[key]['nerecunoscute'].append({
                                    'denumire_excel': den_excel,
                                    'cod':            cod,
                                    'cantitate':      cant
                                })

                    else:
                        # ── FORMAT INVENTAR (matrice) ──
                        format_detected = 'inventar'
                        df_raw = pd.read_excel(cale, engine=engine, header=None)
                        rows_mat = [list(r) for _, r in df_raw.iterrows()]
                        if rows_mat:
                            header = rows_mat[0]
                            for col_idx in range(1, len(header)):
                                if not header[col_idx]:
                                    continue
                                locatie_nume = str(header[col_idx]).strip()
                                produse_ok, produse_nok = [], []
                                for mat_row in rows_mat[1:]:
                                    if not mat_row[0]:
                                        continue
                                    try: cantitate = float(mat_row[col_idx] or 0)
                                    except: cantitate = 0
                                    if cantitate <= 0:
                                        continue
                                    nume_excel = _norm(mat_row[0])
                                    den_excel  = re.sub(r'^\d+\.\s*', '', str(mat_row[0]).strip())
                                    p_db = prod_dict.get(nume_excel)
                                    if not p_db:
                                        for k, v in prod_dict.items():
                                            if nume_excel in k or k in nume_excel:
                                                p_db = v
                                                break
                                    if p_db:
                                        produse_ok.append({'produs_id': p_db['id'], 'denumire': p_db['denumire'],
                                                           'denumire_excel': den_excel, 'cantitate': cantitate})
                                    else:
                                        produse_nok.append({'denumire_excel': den_excel, 'cantitate': cantitate})
                                if produse_ok:
                                    locatii_all.append({'col_idx': col_idx, 'nume': locatie_nume,
                                                        'produse': produse_ok, 'nerecunoscute': produse_nok,
                                                        'fisier_sursa': fisier.filename})

                except Exception as e:
                    flash(f'Eroare la fisierul {fisier.filename}: {str(e)}', 'warning')
                finally:
                    try: os.remove(cale)
                    except: pass

            db2.close()

            fisiere_nr    = len(valid_files)
            fisiere_names = ', '.join(f.filename for f in valid_files)

            if format_detected == 'intrari':
                grupuri_list = list(groups.values())
                if not grupuri_list:
                    flash('Niciun grup valid nu a fost gasit in fisierele incarcate.', 'warning')
                    return render_template('intrari/import_excel.html', furnizori=furnizori, pas=1)
                return render_template('intrari/import_excel.html',
                    furnizori=furnizori, pas=2,
                    format_type='intrari',
                    fisier_nume=fisiere_names,
                    fisiere_nr=fisiere_nr,
                    grupuri=grupuri_list,
                    azi_ro=date.today())
            elif format_detected == 'inventar':
                if not locatii_all:
                    flash('Nicio locatie valida nu a fost gasita in fisierele incarcate.', 'warning')
                    return render_template('intrari/import_excel.html', furnizori=furnizori, pas=1)
                return render_template('intrari/import_excel.html',
                    furnizori=furnizori, pas=2,
                    format_type='inventar',
                    fisier_nume=fisiere_names,
                    fisiere_nr=fisiere_nr,
                    locatii=locatii_all,
                    azi_ro=date.today())
            else:
                flash('Niciun fisier valid nu a putut fi procesat.', 'danger')
                return render_template('intrari/import_excel.html', furnizori=furnizori, pas=1)

        # ── PAS 2: confirmare → salveaza in DB ──────────────────────────────
        elif pas == '2':
            format_type = request.form.get('format_type', 'inventar')
            furnizor_id = request.form.get('furnizor_id') or None
            nr_document = request.form.get('nr_document', '').strip()

            if format_type == 'intrari':
                grupuri_json = request.form.get('grupuri_json', '[]')
                try:
                    grupuri = json.loads(grupuri_json)
                except:
                    grupuri = []

                db2 = get_db()
                total_intrari = 0
                total_produse = 0
                erori = []

                for g in grupuri:
                    if not g.get('produse'):
                        continue
                    if not g.get('locatie_id'):
                        erori.append(f"Locatia '{g.get('locatie_excel')}' nu a fost gasita in sistem.")
                        continue
                    cur = db2.execute("""INSERT INTO intrari (data, furnizor_id, nr_document, observatii, utilizator_id)
                        VALUES (?,?,?,?,?)""",
                        (g['data'], furnizor_id, nr_document, g['locatie_db'], current_user.id))
                    intrare_id = cur.lastrowid
                    for p in g['produse']:
                        db2.execute("INSERT INTO intrari_detalii (intrare_id, produs_id, cantitate, pret_unitar) VALUES (?,?,?,?)",
                                   (intrare_id, p['produs_id'], p['cantitate'], p.get('pret_unitar', 0)))
                        total_produse += 1
                    total_intrari += 1

                db2.commit()
                db2.close()
                for err in erori:
                    flash(err, 'warning')
                flash(f'Import reusit: {total_intrari} intrari, {total_produse} produse importate.', 'success')
                return redirect(url_for('intrari.index'))

            else:
                # Matrix format
                data = request.form.get('data')
                locatii_json = request.form.get('locatii_json', '[]')
                try:
                    locatii_data = json.loads(locatii_json)
                except:
                    locatii_data = []

                if not data or not locatii_data:
                    flash('Data si datele sunt obligatorii.', 'danger')
                    return redirect(url_for('intrari.import_excel'))

                db2 = get_db()
                total_intrari = 0
                total_produse = 0
                for loc in locatii_data:
                    if not loc.get('produse'):
                        continue
                    cur = db2.execute("""INSERT INTO intrari (data, furnizor_id, nr_document, observatii, utilizator_id)
                        VALUES (?,?,?,?,?)""",
                        (data, furnizor_id, nr_document, loc['nume'], current_user.id))
                    intrare_id = cur.lastrowid
                    for p in loc['produse']:
                        db2.execute("INSERT INTO intrari_detalii (intrare_id, produs_id, cantitate, pret_unitar) VALUES (?,?,?,0)",
                                   (intrare_id, p['produs_id'], p['cantitate']))
                        total_produse += 1
                    total_intrari += 1
                db2.commit()
                db2.close()
                flash(f'Import reusit: {total_intrari} locatii, {total_produse} produse importate.', 'success')
                return redirect(url_for('intrari.index'))

    return render_template('intrari/import_excel.html', furnizori=furnizori, pas=1, azi_ro=date.today())


@intrari_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('intrari.index'))
    db = get_db()
    db.execute("DELETE FROM intrari WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Intrare stearsa.', 'success')
    return redirect(url_for('intrari.index'))
