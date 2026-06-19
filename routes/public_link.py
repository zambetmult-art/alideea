"""
Rute publice (fara autentificare) — pentru magazinele care acceseaza prin link unic.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db
from datetime import datetime
import openpyxl, io, re, unicodedata

public_bp = Blueprint('public', __name__, url_prefix='/s')


def _norm(s):
    if not s:
        return ''
    s = str(s)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s.lower().strip())


def _get_link(db, token):
    """Returneaza link-ul activ, sau None daca e invalid/expirat."""
    row = db.execute(
        "SELECT * FROM linkuri_acces WHERE token=? AND activ=1", (token,)
    ).fetchone()
    if not row:
        return None
    if row['valid_pana_la'] and row['valid_pana_la'] < datetime.now().strftime('%Y-%m-%d'):
        return None
    return row


@public_bp.route('/<token>', methods=['GET', 'POST'])
def formular(token):
    db = get_db()

    # Asigura tabele necesare
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

    link = _get_link(db, token)
    if not link:
        db.close()
        return render_template('public/link_invalid.html'), 404

    locatii = db.execute(
        "SELECT id, nume FROM locatii WHERE activa=1 ORDER BY nume"
    ).fetchall()

    produse = db.execute("""
        SELECT id, denumire, unitate_masura, cod_articol
        FROM produse WHERE activ=1 ORDER BY denumire
    """).fetchall()

    if request.method == 'POST':
        obs = request.form.get('obs_magazin', '').strip()
        metoda = request.form.get('metoda', 'manual')
        locatie_id_sel = request.form.get('locatie_id', '').strip()

        if not locatie_id_sel:
            flash('Selecteaza locatia ta inainte de a trimite.', 'danger')
            db.close()
            return render_template('public/formular.html', link=link, produse=produse, locatii=locatii)

        try:
            locatie_id_sel = int(locatie_id_sel)
        except ValueError:
            flash('Locatie invalida.', 'danger')
            db.close()
            return render_template('public/formular.html', link=link, produse=produse, locatii=locatii)

        intrari = []  # list of (produs_id, denumire, cantitate)

        if metoda == 'excel':
            fisier = request.files.get('fisier')
            if not fisier or not fisier.filename:
                flash('Selecteaza un fisier Excel.', 'danger')
                db.close()
                return render_template('public/formular.html', link=link, produse=produse)

            try:
                continut = fisier.read()
                wb = openpyxl.load_workbook(io.BytesIO(continut), read_only=True, data_only=True)
                ws = wb.active

                # Construieste index de potrivire
                by_cod = {str(p['cod_articol']).strip().upper(): p for p in produse if p['cod_articol']}
                by_norm = {_norm(p['denumire']): p for p in produse}

                matched = 0
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or row[0] is None:
                        continue
                    ident = str(row[0]).strip()
                    if not ident:
                        continue
                    try:
                        cant = float(str(row[1] or 0).replace(',', '.'))
                    except (ValueError, TypeError):
                        cant = 0

                    prod = by_cod.get(ident.upper()) or by_norm.get(_norm(ident))
                    if not prod:
                        # potrivire partiala
                        ni = _norm(ident)
                        for key, p in by_norm.items():
                            if ni in key or key in ni:
                                prod = p
                                break

                    if prod:
                        intrari.append((prod['id'], prod['denumire'], cant))
                        matched += 1
                    else:
                        intrari.append((None, ident, cant))

                wb.close()
                if matched == 0:
                    flash('Niciun produs nu a putut fi identificat in Excel. Verifica formatul.', 'warning')
                    db.close()
                    return render_template('public/formular.html', link=link, produse=produse, locatii=locatii)

            except Exception as e:
                flash(f'Eroare la citirea Excel: {e}', 'danger')
                db.close()
                return render_template('public/formular.html', link=link, produse=produse, locatii=locatii)

        else:
            # Completare manuala
            for p in produse:
                val = request.form.get(f'cant_{p["id"]}', '').strip()
                try:
                    cant = float(val.replace(',', '.')) if val else 0
                except ValueError:
                    cant = 0
                if cant > 0:
                    intrari.append((p['id'], p['denumire'], cant))

            if not intrari:
                flash('Nu ai introdus nicio cantitate. Completeaza cel putin un produs.', 'warning')
                db.close()
                return render_template('public/formular.html', link=link, produse=produse, locatii=locatii)

        # Salveaza submisia
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur = db.execute("""
            INSERT INTO submisii (link_id, locatie_id, tip, data_submisie, obs_magazin)
            VALUES (?, ?, ?, ?, ?)
        """, (link['id'], locatie_id_sel, link['tip'], now, obs))
        sub_id = cur.lastrowid

        for pid, den, cant in intrari:
            db.execute("""
                INSERT INTO submisii_detalii (submisie_id, produs_id, denumire_original, cantitate)
                VALUES (?, ?, ?, ?)
            """, (sub_id, pid, den, cant))

        db.commit()
        locatie_sel = next((l for l in locatii if l['id'] == locatie_id_sel), None)
        db.close()
        return render_template('public/confirmare.html', link=link,
                               nr_produse=len(intrari), locatie_sel=locatie_sel)

    db.close()
    return render_template('public/formular.html', link=link, produse=produse, locatii=locatii)
