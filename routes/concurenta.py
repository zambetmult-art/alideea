from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import get_db
from datetime import datetime, date
import json
import re
import unicodedata
import requests
import pandas as pd

concurenta_bp = Blueprint('concurenta', __name__, url_prefix='/concurenta')

_LF_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


def _slugify(text):
    """Company name → URL slug (lowercase, hyphens, no diacritics)."""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def _parse_lf_number(s):
    """Parse a Romanian number string (with \xa0 as thousand sep)."""
    s = re.sub(r'[\xa0\s]', '', str(s))
    s = re.sub(r'[^\d.-]', '', s)
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_lf_page(html, cui):
    """
    Parse listafirme.ro company page HTML.
    Returns (firma_info_dict, financial_data_list) or raises ValueError.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')

    # Verify we have the right company
    if str(cui) not in html:
        raise ValueError(f'CUI {cui} nu a fost gasit in pagina.')

    # Company name from title
    title = soup.title.text.strip() if soup.title else ''
    firma_info = {'titlu': title, 'cui': cui}

    # Find the financial table: has 'Cifraafaceri' or 'cifr' in headers
    financial_data = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue
        hdrs = [td.get_text(strip=True) for td in rows[0].find_all(['th', 'td'])]
        hdrs_low = ' '.join(hdrs).lower().replace('\xa0', '')
        if 'cifr' not in hdrs_low and 'afaceri' not in hdrs_low:
            continue
        # This is the financial table
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(['th', 'td'])]
            if not cells:
                continue
            year_str = cells[0].replace('\xa0', '').strip()
            if not re.match(r'^\d{4}$', year_str):
                continue
            # Columns (0-indexed): 0=An, 1=CA, 2=Profit, 3=Datorii,
            #                       4=ActiveImob, 5=ActiveCirc, 6=Capitaluri, 7=NrAngajati
            ca     = _parse_lf_number(cells[1]) if len(cells) > 1 else 0
            profit = _parse_lf_number(cells[2]) if len(cells) > 2 else 0
            ang    = int(_parse_lf_number(cells[7])) if len(cells) > 7 else 0
            financial_data.append({
                'an': int(year_str),
                'cifra_afaceri': ca,
                'profit_net': profit,
                'numar_angajati': ang,
            })
        break  # Only first matching table

    return firma_info, financial_data


def _fetch_listafirme(cui, company_name, stored_url=None):
    """
    Fetch financial data from listafirme.ro.
    Returns (url_used, firma_info, data_list, error_msg).
    """
    candidates = []
    if stored_url:
        candidates.append(stored_url)
    if cui:
        slug = _slugify(company_name or '')
        if slug:
            candidates.append(f'https://listafirme.ro/{slug}-{cui}/')
        # Also try with ANAF official name
        try:
            cui_nr = int(re.sub(r'\D', '', str(cui)))
            today = datetime.today().strftime('%Y-%m-%d')
            anaf = requests.post(
                'https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva',
                json=[{"cui": cui_nr, "data": today}],
                timeout=8,
            )
            if anaf.status_code == 200:
                found = anaf.json().get('found', [])
                if found:
                    official = found[0].get('denumire', '')
                    if official:
                        slug2 = _slugify(official)
                        url2 = f'https://listafirme.ro/{slug2}-{cui_nr}/'
                        if url2 not in candidates:
                            candidates.append(url2)
        except Exception:
            pass

    for url in candidates:
        try:
            resp = requests.get(url, headers=_LF_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            firma_info, data = _parse_lf_page(resp.text, cui)
            return url, firma_info, data, None
        except ValueError as e:
            continue
        except Exception as e:
            return None, {}, [], str(e)

    return None, {}, [], (
        'Nu s-a putut gasi pagina pe listafirme.ro. '
        'Verifica ca CUI-ul este corect sau completeaza manual URL-ul.'
    )


@concurenta_bp.route('/')
@login_required
def index():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    firme = db.execute("""
        SELECT f.*,
               COUNT(DISTINCT c.an) as ani_date,
               MAX(c.an) as ultimul_an,
               MAX(c.cifra_afaceri) as max_ca
        FROM concurenta_firme f
        LEFT JOIN concurenta_cifre c ON c.firma_id = f.id
        WHERE f.activa = 1
        GROUP BY f.id
        ORDER BY f.nume
    """).fetchall()
    db.close()
    return render_template('concurenta/index.html', firme=firme)


@concurenta_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('concurenta.index'))
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        cui = request.form.get('cui', '').strip()
        website = request.form.get('website', '').strip()
        descriere = request.form.get('descriere', '').strip()
        if not nume:
            flash('Numele firmei este obligatoriu.', 'danger')
            return render_template('concurenta/form_firma.html', firma=None)
        db = get_db()
        db.execute(
            "INSERT INTO concurenta_firme (nume, cui, website, descriere) VALUES (?, ?, ?, ?)",
            (nume, cui, website, descriere)
        )
        db.commit()
        db.close()
        flash(f'Firma "{nume}" a fost adaugata.', 'success')
        return redirect(url_for('concurenta.index'))
    return render_template('concurenta/form_firma.html', firma=None)


@concurenta_bp.route('/editeaza/<int:id>', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('concurenta.index'))
    db = get_db()
    firma = db.execute("SELECT * FROM concurenta_firme WHERE id=?", (id,)).fetchone()
    if not firma:
        db.close()
        flash('Firma negasita.', 'danger')
        return redirect(url_for('concurenta.index'))
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        cui = request.form.get('cui', '').strip()
        website = request.form.get('website', '').strip()
        descriere = request.form.get('descriere', '').strip()
        db.execute(
            "UPDATE concurenta_firme SET nume=?, cui=?, website=?, descriere=? WHERE id=?",
            (nume, cui, website, descriere, id)
        )
        db.commit()
        db.close()
        flash('Firma actualizata.', 'success')
        return redirect(url_for('concurenta.index'))
    db.close()
    return render_template('concurenta/form_firma.html', firma=firma)


@concurenta_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('concurenta.index'))
    db = get_db()
    db.execute("UPDATE concurenta_firme SET activa=0 WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Firma stearsa.', 'success')
    return redirect(url_for('concurenta.index'))


@concurenta_bp.route('/<int:id>/cifre', methods=['GET', 'POST'])
@login_required
def cifre(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('concurenta.index'))
    db = get_db()
    firma = db.execute("SELECT * FROM concurenta_firme WHERE id=?", (id,)).fetchone()
    if not firma:
        db.close()
        flash('Firma negasita.', 'danger')
        return redirect(url_for('concurenta.index'))
    if request.method == 'POST':
        an = request.form.get('an', '').strip()
        sursa = request.form.get('sursa', '').strip()
        observatii = request.form.get('observatii', '').strip()

        def safe_float(key):
            try:
                return float(request.form.get(key, '0').replace(',', '.') or '0')
            except Exception:
                return 0.0

        def safe_int(key):
            try:
                return int(float(request.form.get(key, '0') or '0'))
            except Exception:
                return 0

        if not an:
            flash('Anul este obligatoriu.', 'danger')
        else:
            existing = db.execute(
                "SELECT id FROM concurenta_cifre WHERE firma_id=? AND an=?", (id, an)
            ).fetchone()
            if existing:
                db.execute("""
                    UPDATE concurenta_cifre
                    SET cifra_afaceri=?, profit_net=?, numar_angajati=?, numar_locatii=?, sursa=?, observatii=?
                    WHERE firma_id=? AND an=?
                """, (safe_float('cifra_afaceri'), safe_float('profit_net'),
                      safe_int('numar_angajati'), safe_int('numar_locatii'),
                      sursa, observatii, id, an))
            else:
                db.execute("""
                    INSERT INTO concurenta_cifre
                        (firma_id, an, cifra_afaceri, profit_net, numar_angajati, numar_locatii, sursa, observatii)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (id, an, safe_float('cifra_afaceri'), safe_float('profit_net'),
                      safe_int('numar_angajati'), safe_int('numar_locatii'), sursa, observatii))
            db.commit()
            flash(f'Date pentru {an} salvate.', 'success')

    cifre_list = db.execute(
        "SELECT * FROM concurenta_cifre WHERE firma_id=? ORDER BY an DESC", (id,)
    ).fetchall()
    db.close()
    return render_template('concurenta/cifre.html', firma=firma, cifre=cifre_list,
                           an_curent=date.today().year)


@concurenta_bp.route('/<int:id>/cifre/sterge/<int:cifra_id>', methods=['POST'])
@login_required
def sterge_cifra(id, cifra_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('concurenta.cifre', id=id))
    db = get_db()
    db.execute("DELETE FROM concurenta_cifre WHERE id=? AND firma_id=?", (cifra_id, id))
    db.commit()
    db.close()
    flash('Inregistrare stearsa.', 'success')
    return redirect(url_for('concurenta.cifre', id=id))


@concurenta_bp.route('/<int:id>/listafirme-preview')
@login_required
def listafirme_preview(id):
    """AJAX: fetch & parse listafirme.ro for a company. Returns JSON preview."""
    if not current_user.is_manager():
        return jsonify({'ok': False, 'msg': 'Acces restrictionat.'})
    db = get_db()
    firma = db.execute("SELECT * FROM concurenta_firme WHERE id=?", (id,)).fetchone()
    db.close()
    if not firma:
        return jsonify({'ok': False, 'msg': 'Firma negasita.'})
    if not firma['cui']:
        return jsonify({'ok': False, 'msg': 'Firma nu are CUI completat. Editeaza firma si adauga CUI-ul.'})

    url, firma_info, data, err = _fetch_listafirme(
        firma['cui'], firma['nume'], firma['listafirme_url']
    )
    if err:
        return jsonify({'ok': False, 'msg': err})
    if not data:
        return jsonify({'ok': False, 'msg': 'Pagina gasita dar nu contine date financiare.', 'url': url})

    return jsonify({
        'ok': True,
        'url': url,
        'titlu': firma_info.get('titlu', ''),
        'date': data,
    })


@concurenta_bp.route('/<int:id>/listafirme-import', methods=['POST'])
@login_required
def listafirme_import(id):
    """Save fetched listafirme.ro data to DB."""
    if not current_user.is_manager():
        return jsonify({'ok': False, 'msg': 'Acces restrictionat.'})
    db = get_db()
    firma = db.execute("SELECT * FROM concurenta_firme WHERE id=?", (id,)).fetchone()
    if not firma:
        db.close()
        return jsonify({'ok': False, 'msg': 'Firma negasita.'})

    try:
        payload = request.get_json(force=True)
        url = payload.get('url', '')
        date_list = payload.get('date', [])

        if url:
            db.execute("UPDATE concurenta_firme SET listafirme_url=? WHERE id=?", (url, id))

        salvate = 0
        for row in date_list:
            an = str(row.get('an', ''))
            ca = float(row.get('cifra_afaceri', 0) or 0)
            profit = float(row.get('profit_net', 0) or 0)
            ang = int(row.get('numar_angajati', 0) or 0)
            if not an:
                continue
            existing = db.execute(
                "SELECT id FROM concurenta_cifre WHERE firma_id=? AND an=?", (id, an)
            ).fetchone()
            if existing:
                db.execute("""
                    UPDATE concurenta_cifre
                    SET cifra_afaceri=?, profit_net=?, numar_angajati=?, sursa='listafirme.ro'
                    WHERE firma_id=? AND an=?
                """, (ca, profit, ang, id, an))
            else:
                db.execute("""
                    INSERT INTO concurenta_cifre
                        (firma_id, an, cifra_afaceri, profit_net, numar_angajati, sursa)
                    VALUES (?, ?, ?, ?, ?, 'listafirme.ro')
                """, (id, an, ca, profit, ang))
            salvate += 1

        db.commit()
        db.close()
        return jsonify({'ok': True, 'salvate': salvate})
    except Exception as e:
        db.close()
        return jsonify({'ok': False, 'msg': str(e)})


@concurenta_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('concurenta.index'))
    if request.method == 'POST':
        f = request.files.get('fisier')
        if not f or not f.filename:
            flash('Nu ai selectat niciun fisier.', 'danger')
            return redirect(request.url)
        try:
            df = pd.read_excel(f)
            df.columns = [str(c).strip().lower() for c in df.columns]

            def find_col(candidates):
                for c in candidates:
                    if c in df.columns:
                        return c
                return None

            col_firma = find_col(['firma', 'companie', 'denumire', 'nume firma'])
            col_an = find_col(['an', 'year', 'anul'])
            col_ca = find_col(['cifra afaceri', 'cifra_afaceri', 'ca', 'revenue', 'venituri'])
            col_profit = find_col(['profit net', 'profit_net', 'profit', 'net profit'])
            col_ang = find_col(['numar angajati', 'angajati', 'nr angajati', 'employees'])
            col_loc = find_col(['numar locatii', 'locatii', 'nr locatii', 'locations'])

            if not col_firma or not col_an:
                flash('Fisierul trebuie sa contina coloanele: Firma, An', 'danger')
                return redirect(request.url)

            def safe_float(val):
                try:
                    return float(str(val).replace(',', '.').replace(' ', ''))
                except Exception:
                    return 0.0

            def safe_int(val):
                try:
                    return int(float(str(val)))
                except Exception:
                    return 0

            db = get_db()
            importat = 0
            for _, row in df.iterrows():
                nume_firma = str(row[col_firma]).strip()
                an = str(row[col_an]).strip()
                if not nume_firma or not an or nume_firma == 'nan' or an == 'nan':
                    continue
                try:
                    an = str(int(float(an)))
                except Exception:
                    continue

                firma = db.execute(
                    "SELECT id FROM concurenta_firme WHERE LOWER(nume)=LOWER(?)", (nume_firma,)
                ).fetchone()
                if not firma:
                    db.execute("INSERT INTO concurenta_firme (nume) VALUES (?)", (nume_firma,))
                    db.commit()
                    firma = db.execute(
                        "SELECT id FROM concurenta_firme WHERE LOWER(nume)=LOWER(?)", (nume_firma,)
                    ).fetchone()
                firma_id = firma['id']

                ca = safe_float(row[col_ca]) if col_ca else 0
                profit = safe_float(row[col_profit]) if col_profit else 0
                angajati = safe_int(row[col_ang]) if col_ang else 0
                locatii_nr = safe_int(row[col_loc]) if col_loc else 0

                existing = db.execute(
                    "SELECT id FROM concurenta_cifre WHERE firma_id=? AND an=?", (firma_id, an)
                ).fetchone()
                if existing:
                    db.execute("""
                        UPDATE concurenta_cifre
                        SET cifra_afaceri=?, profit_net=?, numar_angajati=?, numar_locatii=?, sursa='Excel Import'
                        WHERE firma_id=? AND an=?
                    """, (ca, profit, angajati, locatii_nr, firma_id, an))
                else:
                    db.execute("""
                        INSERT INTO concurenta_cifre
                            (firma_id, an, cifra_afaceri, profit_net, numar_angajati, numar_locatii, sursa)
                        VALUES (?, ?, ?, ?, ?, ?, 'Excel Import')
                    """, (firma_id, an, ca, profit, angajati, locatii_nr))
                importat += 1

            db.commit()
            db.close()
            flash(f'Import reusit: {importat} inregistrari procesate.', 'success')
            return redirect(url_for('concurenta.index'))
        except Exception as e:
            flash(f'Eroare la import: {str(e)}', 'danger')
            return redirect(request.url)
    return render_template('concurenta/import.html')


@concurenta_bp.route('/analiza')
@login_required
def analiza():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    firme = db.execute(
        "SELECT * FROM concurenta_firme WHERE activa=1 ORDER BY nume"
    ).fetchall()
    ani = [r['an'] for r in db.execute(
        "SELECT DISTINCT an FROM concurenta_cifre ORDER BY an DESC"
    ).fetchall()]
    cifre = db.execute("""
        SELECT c.*, f.nume as firma_nume
        FROM concurenta_cifre c
        JOIN concurenta_firme f ON f.id = c.firma_id
        WHERE f.activa = 1
        ORDER BY c.an, f.nume
    """).fetchall()
    db.close()

    firme_nume = [f['nume'] for f in firme]
    data_ca, data_profit, data_angajati, data_locatii = {}, {}, {}, {}
    for c in cifre:
        an, fn = c['an'], c['firma_nume']
        for d in (data_ca, data_profit, data_angajati, data_locatii):
            d.setdefault(an, {})
        data_ca[an][fn] = c['cifra_afaceri'] or 0
        data_profit[an][fn] = c['profit_net'] or 0
        data_angajati[an][fn] = c['numar_angajati'] or 0
        data_locatii[an][fn] = c['numar_locatii'] or 0

    return render_template('concurenta/analiza.html',
                           firme=firme, firme_nume=firme_nume, ani=ani, cifre=cifre,
                           data_ca=json.dumps(data_ca),
                           data_profit=json.dumps(data_profit),
                           data_angajati=json.dumps(data_angajati),
                           data_locatii=json.dumps(data_locatii))


@concurenta_bp.route('/api/anaf/<cui>')
@login_required
def api_anaf(cui):
    try:
        cui_nr = int(cui.replace('RO', '').replace(' ', '').strip())
        today = datetime.today().strftime('%Y-%m-%d')
        resp = requests.post(
            'https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva',
            json=[{"cui": cui_nr, "data": today}],
            timeout=10
        )
        if resp.status_code == 200:
            found = resp.json().get('found', [])
            if found:
                f = found[0]
                return jsonify({'ok': True, 'nume': f.get('denumire', ''),
                                'adresa': f.get('adresa', ''), 'cui': f.get('cui', '')})
        return jsonify({'ok': False, 'msg': 'Nu s-au gasit date ANAF'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})
