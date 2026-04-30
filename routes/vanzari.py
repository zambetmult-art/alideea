from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
import pandas as pd
import os
import io
from email_import import descarca_excel_din_email

vanzari_bp = Blueprint('vanzari', __name__, url_prefix='/vanzari')

@vanzari_bp.route('/')
@login_required
def index():
    db = get_db()
    importuri = db.execute("""
        SELECT vi.*, l.nume as locatie_nume,
               COUNT(vd.id) as nr_produse,
               COALESCE(SUM(vd.valoare_fara_tva), 0) as total_valoare,
               COALESCE(SUM(vd.cantitate), 0) as total_cantitate
        FROM vanzari_import vi
        LEFT JOIN locatii l ON vi.locatie_id = l.id
        LEFT JOIN vanzari_detalii vd ON vd.import_id = vi.id
        GROUP BY vi.id
        ORDER BY vi.data_raportare DESC, vi.id DESC
        LIMIT 100
    """).fetchall()
    db.close()
    return render_template('vanzari/index.html', importuri=importuri)

def cauta_locatie_in_db(db, locatie_din_excel):
    """Cauta locatia in DB dupa continutul din Excel. Returneaza (id, nume) sau (None, None)."""
    if not locatie_din_excel:
        return None, None
    txt = locatie_din_excel.strip().upper()

    # 1. Match exact (case insensitive)
    loc = db.execute("SELECT id, nume FROM locatii WHERE UPPER(nume)=? AND activa=1", (txt,)).fetchone()
    if loc:
        return loc['id'], loc['nume']

    # 2. Match dupa toate cuvintele semnificative din Excel
    cuvinte = [c for c in txt.split() if len(c) >= 2]
    toate_locatiile = db.execute("SELECT id, nume FROM locatii WHERE activa=1").fetchall()
    scoruri = []
    for loc in toate_locatiile:
        nume_db = loc['nume'].upper()
        potriviri = sum(1 for c in cuvinte if c in nume_db)
        if potriviri > 0:
            scoruri.append((potriviri, loc))
    if scoruri:
        scoruri.sort(key=lambda x: x[0], reverse=True)
        best = scoruri[0][1]
        return best['id'], best['nume']

    return None, None


def proceseaza_fisier_excel(db, file_bytes, filename, utilizator_id):
    """Proceseaza un fisier Excel Carrefour si il importa. Returneaza (mesaj, succes)."""
    def _buf():
        return io.BytesIO(file_bytes)
    try:
        xl = pd.ExcelFile(_buf())
        sheet_names = xl.sheet_names
        xl.close()

        # Identifica sheet-urile
        sheet_antet = next((s for s in sheet_names if 'antet' in s.lower()), None)
        sheet_linii = next((s for s in sheet_names if 'lini' in s.lower()), None)
        if not sheet_antet:
            sheet_antet = sheet_names[1] if len(sheet_names) > 1 else None
        if not sheet_linii:
            sheet_linii = sheet_names[0]

        locatie_din_excel = None
        data_raportare = None
        saptamana = None
        nr_comanda = None

        # --- Citeste ANTET: cauta Nr, Magazin si Data IN CONTINUT ---
        if sheet_antet:
            df_a = pd.read_excel(_buf(), sheet_name=sheet_antet, header=None)
            for _, row in df_a.iterrows():
                vals = [str(v).strip() if pd.notna(v) else '' for v in row]
                for i, v in enumerate(vals):
                    v_low = v.lower().rstrip(':').strip()
                    # Numar comanda / Nr
                    if v_low in ('nr', 'nr.', 'numar', 'numar comanda', 'nr comanda'):
                        nxt = vals[i+1] if i+1 < len(vals) else ''
                        if nxt and nxt.lower() not in ('nan', ''):
                            nr_comanda = nxt.strip()
                    # Magazin / Locatie
                    if v_low in ('magazin', 'locatie', 'unitate', 'magazin destinatar'):
                        nxt = vals[i+1] if i+1 < len(vals) else ''
                        if nxt and nxt.lower() not in ('nan', ''):
                            locatie_din_excel = nxt
                    # Data
                    if v_low in ('data', 'data raportare', 'data comenzii', 'data comanda', 'data emitere'):
                        try:
                            data_val = row.iloc[i+1]
                            if pd.notna(data_val):
                                if hasattr(data_val, 'strftime'):
                                    data_raportare = data_val.strftime('%Y-%m-%d')
                                    saptamana = data_val.strftime('S%W/%Y')
                                else:
                                    data_raportare = str(data_val).strip()[:10]
                                    saptamana = data_raportare[:7]
                        except:
                            pass

        # --- Gaseste locatia in DB ---
        locatie_id, locatie_nume = cauta_locatie_in_db(db, locatie_din_excel)
        if not locatie_id:
            return (f'Fisier {filename}: locatia "{locatie_din_excel}" nu a fost gasita in sistem. '
                    f'Adaug-o la Locatii si reincearca.'), False

        # --- Verifica DUPLICATE: acelasi nr_comanda sau aceeasi locatie+data ---
        if nr_comanda:
            dup = db.execute("SELECT id FROM vanzari_import WHERE nr_comanda=?", (nr_comanda,)).fetchone()
            if dup:
                return (f'ATENTIE: Comanda nr. {nr_comanda} pentru {locatie_nume} a fost deja importata! '
                        f'Nu s-a importat din nou.'), False
        elif data_raportare:
            dup = db.execute("""SELECT id FROM vanzari_import
                WHERE locatie_id=? AND data_raportare=?""", (locatie_id, data_raportare)).fetchone()
            if dup:
                return (f'ATENTIE: Raportul pentru {locatie_nume} din {data_raportare} '
                        f'a fost deja importat! Nu s-a importat din nou.'), False

        if not data_raportare:
            from datetime import date
            data_raportare = date.today().strftime('%Y-%m-%d')
            saptamana = date.today().strftime('S%W/%Y')

        # --- Citeste LINII: primul rand e titlu ("Linii comanda"), al doilea e headerul real ---
        df_raw = pd.read_excel(_buf(), sheet_name=sheet_linii, header=None)
        # Gaseste randul cu headerul real (contine "Articol" sau "Cod" sau "EAN")
        header_row = 0
        for i, row in df_raw.iterrows():
            vals = [str(v).strip().lower() for v in row if pd.notna(v)]
            if any(k in vals for k in ('articol', 'cod', 'ean', 'cant')):
                header_row = i
                break
        df_data = pd.read_excel(_buf(), sheet_name=sheet_linii, header=header_row)
        df_data.columns = [str(c).strip().lower() for c in df_data.columns]

        # Mapeaza coloanele
        col_map = {}
        for col in df_data.columns:
            c = col.strip()
            if c == 'cod' or (c.startswith('cod') and 'ean' not in c and 'magazin' not in c):
                col_map.setdefault('cod_art', col)
            if 'ean' in c:
                col_map['ean'] = col
            if c == 'articol' or (c.startswith('articol') and 'cod' not in c):
                col_map['denumire'] = col
            if c in ('cant', 'cantitate') or (c.startswith('cant') and 'total' not in c):
                col_map['cantitate'] = col
            if c == 'pret' or (c.startswith('pret') and 'total' not in c and 'tva' not in c):
                col_map['pret'] = col
            if 'total fara tva' in c or c in ('total fara tva', 'valoare fara tva'):
                col_map['valoare'] = col

        if 'denumire' not in col_map:
            return f'Fisier {filename}: nu s-a gasit coloana Articol in sheet-ul {sheet_linii}.', False

        cur = db.execute("""INSERT INTO vanzari_import (data_raportare, locatie_id, saptamana,
            fisier_original, utilizator_id, nr_comanda) VALUES (?,?,?,?,?,?)""",
            (data_raportare, locatie_id, saptamana, filename, utilizator_id, nr_comanda))
        import_id = cur.lastrowid

        nr_rand = 0
        for _, row in df_data.iterrows():
            def get_val(key, default=''):
                col = col_map.get(key)
                if not col or col not in row.index: return default
                v = row[col]
                return default if pd.isna(v) else v

            denumire = str(get_val('denumire', '')).strip()
            if not denumire or denumire.lower() in ('nan', 'none', 'articol', ''):
                continue

            cod_art = str(get_val('cod_art', '')).strip()
            cod_ean = str(get_val('ean', '')).strip()
            if cod_art in ('nan', 'none'): cod_art = ''
            if cod_ean in ('nan', 'none'): cod_ean = ''

            try: cantitate = float(get_val('cantitate', 0))
            except: cantitate = 0
            try: pret = float(get_val('pret', 0))
            except: pret = 0
            try: valoare = float(get_val('valoare', 0))
            except: valoare = 0

            if cantitate == 0 and valoare == 0:
                continue

            # Cauta produsul
            produs_id = None
            if cod_art:
                p = db.execute("SELECT id FROM produse WHERE cod_articol=?", (cod_art,)).fetchone()
                if p: produs_id = p['id']
            if not produs_id and cod_ean:
                p = db.execute("SELECT id FROM produse WHERE cod_ean=?", (cod_ean,)).fetchone()
                if p: produs_id = p['id']
            if not produs_id:
                p = db.execute("SELECT id FROM produse WHERE UPPER(denumire)=?",
                               (denumire.upper(),)).fetchone()
                if p: produs_id = p['id']

            db.execute("""INSERT INTO vanzari_detalii (import_id, produs_id, cod_articol, cod_ean,
                denumire_original, cantitate, unitate_masura, pret, valoare_fara_tva)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (import_id, produs_id, cod_art, cod_ean, denumire, cantitate, 'kg', pret, valoare))
            nr_rand += 1

        db.commit()
        return f'{filename}: {nr_rand} produse → {locatie_nume} ({data_raportare})', True

    except Exception as e:
        return f'Fisier {filename}: eroare - {str(e)}', False


@vanzari_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_vanzari():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('vanzari.index'))
    if request.method == 'POST':
        fisiere = request.files.getlist('fisiere')
        if not fisiere:
            flash('Selectati cel putin un fisier Excel.', 'danger')
            return redirect(url_for('vanzari.import_vanzari'))

        db = get_db()
        total_importate = 0
        mesaje = []

        for f in fisiere:
            if not f.filename or not f.filename.endswith(('.xlsx', '.xls')):
                continue
            file_bytes = f.read()
            msg, succes = proceseaza_fisier_excel(db, file_bytes, f.filename, current_user.id)
            mesaje.append((msg, succes))
            if succes:
                total_importate += 1

        db.close()
        for msg, succes in mesaje:
            flash(msg, 'success' if succes else 'warning')
        if total_importate > 0:
            flash(f'Total: {total_importate} fisiere importate cu succes.', 'success')
        return redirect(url_for('vanzari.index'))

    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('vanzari/import.html', locatii=locatii)


@vanzari_bp.route('/import-email', methods=['POST'])
@login_required
def import_din_email():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('vanzari.index'))

    fisiere, eroare = descarca_excel_din_email()

    if eroare:
        flash(f'Eroare Gmail: {eroare}', 'danger')
        return redirect(url_for('vanzari.import_vanzari'))

    if not fisiere:
        flash('Nu exista emailuri noi cu fisiere Excel.', 'info')
        return redirect(url_for('vanzari.import_vanzari'))

    db = get_db()
    total_importate = 0
    mesaje = []

    for cale_fisier in fisiere:
        filename = os.path.basename(cale_fisier)
        try:
            msg, succes = proceseaza_fisier_excel(db, cale_fisier, filename, current_user.id)
            mesaje.append((msg, succes))
            if succes:
                total_importate += 1
        finally:
            if os.path.exists(cale_fisier):
                os.remove(cale_fisier)

    db.close()
    for msg, succes in mesaje:
        flash(msg, 'success' if succes else 'warning')
    if total_importate > 0:
        flash(f'Total: {total_importate} fisiere importate din email cu succes.', 'success')
    return redirect(url_for('vanzari.index'))

@vanzari_bp.route('/detalii/<int:id>')
@login_required
def detalii(id):
    db = get_db()
    import_rec = db.execute("""
        SELECT vi.*, l.nume as locatie_nume
        FROM vanzari_import vi LEFT JOIN locatii l ON vi.locatie_id = l.id
        WHERE vi.id=?
    """, (id,)).fetchone()
    detalii = db.execute("""
        SELECT vd.*, p.denumire as produs_denumire
        FROM vanzari_detalii vd
        LEFT JOIN produse p ON vd.produs_id = p.id
        WHERE vd.import_id=?
        ORDER BY vd.denumire_original
    """, (id,)).fetchall()
    total_valoare = sum(d['valoare_fara_tva'] for d in detalii)
    db.close()
    return render_template('vanzari/detalii.html', import_rec=import_rec, detalii=detalii, total_valoare=total_valoare)

@vanzari_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('vanzari.index'))
    db = get_db()
    db.execute("DELETE FROM vanzari_import WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Import sters.', 'success')
    return redirect(url_for('vanzari.index'))
