from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import get_db
import pandas as pd
import os

produse_bp = Blueprint('produse', __name__, url_prefix='/produse')

@produse_bp.route('/')
@login_required
def index():
    db = get_db()
    produse = db.execute("""
        SELECT p.*, c.nume as categorie_nume
        FROM produse p
        LEFT JOIN categorii c ON p.categorie_id = c.id
        WHERE p.activ = 1
        ORDER BY c.nume, p.denumire
    """).fetchall()
    categorii = db.execute("SELECT * FROM categorii ORDER BY nume").fetchall()
    db.close()
    return render_template('produse/index.html', produse=produse, categorii=categorii)

@produse_bp.route('/adauga', methods=['GET', 'POST'])
@login_required
def adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('produse.index'))
    db = get_db()
    if request.method == 'POST':
        cod_articol = request.form.get('cod_articol', '').strip()
        cod_ean = request.form.get('cod_ean', '').strip()
        denumire = request.form.get('denumire', '').strip()
        categorie_id = request.form.get('categorie_id') or None
        um = request.form.get('unitate_masura', 'kg')
        pret_ach = float(request.form.get('pret_achizitie', 0) or 0)
        pret_van = float(request.form.get('pret_vanzare', 0) or 0)
        stoc_min = float(request.form.get('stoc_minim', 0) or 0)
        if not denumire:
            flash('Denumirea este obligatorie.', 'danger')
        else:
            try:
                db.execute("""INSERT INTO produse (cod_articol, cod_ean, denumire, categorie_id,
                    unitate_masura, pret_achizitie, pret_vanzare, stoc_minim)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (cod_articol or None, cod_ean or None, denumire, categorie_id, um, pret_ach, pret_van, stoc_min))
                db.commit()
                flash('Produs adaugat cu succes.', 'success')
                return redirect(url_for('produse.index'))
            except Exception as e:
                flash(f'Eroare: {str(e)}', 'danger')
    categorii = db.execute("SELECT * FROM categorii ORDER BY nume").fetchall()
    db.close()
    return render_template('produse/form.html', categorii=categorii, produs=None)

@produse_bp.route('/editeaza/<int:id>', methods=['GET', 'POST'])
@login_required
def editeaza(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('produse.index'))
    db = get_db()
    produs = db.execute("SELECT * FROM produse WHERE id=?", (id,)).fetchone()
    if not produs:
        flash('Produs negasit.', 'danger')
        return redirect(url_for('produse.index'))
    if request.method == 'POST':
        cod_articol = request.form.get('cod_articol', '').strip()
        cod_ean = request.form.get('cod_ean', '').strip()
        denumire = request.form.get('denumire', '').strip()
        categorie_id = request.form.get('categorie_id') or None
        um = request.form.get('unitate_masura', 'kg')
        pret_ach = float(request.form.get('pret_achizitie', 0) or 0)
        pret_van = float(request.form.get('pret_vanzare', 0) or 0)
        stoc_min = float(request.form.get('stoc_minim', 0) or 0)
        if not denumire:
            flash('Denumirea este obligatorie.', 'danger')
        else:
            db.execute("""UPDATE produse SET cod_articol=?, cod_ean=?, denumire=?, categorie_id=?,
                unitate_masura=?, pret_achizitie=?, pret_vanzare=?, stoc_minim=? WHERE id=?""",
                (cod_articol or None, cod_ean or None, denumire, categorie_id, um, pret_ach, pret_van, stoc_min, id))
            db.commit()
            flash('Produs actualizat.', 'success')
            return redirect(url_for('produse.index'))
    categorii = db.execute("SELECT * FROM categorii ORDER BY nume").fetchall()
    db.close()
    return render_template('produse/form.html', categorii=categorii, produs=produs)

@produse_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    if not current_user.is_manager():
        return jsonify({'error': 'Acces restrictionat'}), 403
    db = get_db()
    db.execute("UPDATE produse SET activ=0 WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Produs dezactivat.', 'success')
    return redirect(url_for('produse.index'))

@produse_bp.route('/sterge-multiple', methods=['POST'])
@login_required
def sterge_multiple():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('produse.index'))
    ids = request.form.getlist('produse_selectate')
    if not ids:
        flash('Nu ai selectat niciun produs.', 'warning')
        return redirect(url_for('produse.index'))
    db = get_db()
    placeholders = ','.join('?' for _ in ids)
    db.execute(f"UPDATE produse SET activ=0 WHERE id IN ({placeholders})", ids)
    db.commit()
    db.close()
    flash(f'{len(ids)} produs(e) dezactivate.', 'success')
    return redirect(url_for('produse.index'))

@produse_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('produse.index'))
    if request.method == 'POST':
        f = request.files.get('fisier')
        if not f or not f.filename.endswith(('.xlsx', '.xls')):
            flash('Selectati un fisier Excel valid (.xlsx sau .xls).', 'danger')
            return redirect(url_for('produse.import_excel'))
        upload_path = os.path.join('uploads', f.filename)
        f.save(upload_path)
        try:
            df = pd.read_excel(upload_path)
            df.columns = [str(c).strip().lower() for c in df.columns]
            db = get_db()
            categorii = {r['nume'].lower(): r['id'] for r in db.execute("SELECT * FROM categorii").fetchall()}
            importate = 0
            actualizate = 0
            for _, row in df.iterrows():
                denumire = str(row.get('denumire', row.get('articol', row.get('nume', '')))).strip()
                if not denumire or denumire == 'nan':
                    continue
                cod_articol = str(row.get('cod articol', row.get('cod_articol', ''))).strip()
                if cod_articol == 'nan': cod_articol = ''
                cod_ean = str(row.get('cod ean', row.get('cod_ean', ''))).strip()
                if cod_ean == 'nan': cod_ean = ''
                um_raw = str(row.get('unitate masura', row.get('um', row.get('unitate_masura', 'kg')))).strip().lower()
                um = 'kg'
                cat_raw = str(row.get('categorie', '')).strip().lower()
                cat_id = categorii.get(cat_raw)
                pret_ach = 0
                try: pret_ach = float(row.get('pret achizitie', row.get('pret_achizitie', 0)) or 0)
                except: pass
                pret_van = 0
                try: pret_van = float(row.get('pret vanzare', row.get('pret_vanzare', row.get('pret', 0))) or 0)
                except: pass

                # Cauta produs existent — prioritate: cod_articol > cod_ean > denumire (case-insensitive)
                # Cauta inclusiv in produsele dezactivate pentru a nu crea duplicate
                existing = None
                if cod_articol:
                    existing = db.execute(
                        "SELECT id FROM produse WHERE LOWER(TRIM(cod_articol))=LOWER(TRIM(?))",
                        (cod_articol,)).fetchone()
                if not existing and cod_ean:
                    existing = db.execute(
                        "SELECT id FROM produse WHERE LOWER(TRIM(cod_ean))=LOWER(TRIM(?))",
                        (cod_ean,)).fetchone()
                if not existing:
                    existing = db.execute(
                        "SELECT id FROM produse WHERE LOWER(TRIM(denumire))=LOWER(TRIM(?))",
                        (denumire,)).fetchone()

                if existing:
                    db.execute("""UPDATE produse SET
                        cod_articol=COALESCE(NULLIF(TRIM(?), ''), cod_articol),
                        cod_ean=COALESCE(NULLIF(TRIM(?), ''), cod_ean),
                        denumire=?,
                        categorie_id=COALESCE(?, categorie_id),
                        unitate_masura=?,
                        pret_achizitie=CASE WHEN ?>0 THEN ? ELSE pret_achizitie END,
                        pret_vanzare=CASE WHEN ?>0 THEN ? ELSE pret_vanzare END,
                        activ=1
                        WHERE id=?""",
                        (cod_articol, cod_ean, denumire, cat_id, um,
                         pret_ach, pret_ach, pret_van, pret_van, existing['id']))
                    actualizate += 1
                else:
                    db.execute("""INSERT INTO produse (cod_articol, cod_ean, denumire, categorie_id,
                        unitate_masura, pret_achizitie, pret_vanzare) VALUES (?,?,?,?,?,?,?)""",
                        (cod_articol or None, cod_ean or None, denumire, cat_id, um, pret_ach, pret_van))
                    importate += 1
            db.commit()
            db.close()
            flash(f'Import finalizat: {importate} produse noi, {actualizate} actualizate.', 'success')
        except Exception as e:
            flash(f'Eroare la import: {str(e)}', 'danger')
        finally:
            if os.path.exists(upload_path):
                os.remove(upload_path)
        return redirect(url_for('produse.index'))
    db = get_db()
    categorii = db.execute("SELECT * FROM categorii ORDER BY nume").fetchall()
    db.close()
    return render_template('produse/import.html', categorii=categorii)

@produse_bp.route('/api/search')
@login_required
def api_search():
    q = request.args.get('q', '')
    db = get_db()
    produse = db.execute("""
        SELECT p.id, p.cod_articol, p.denumire, p.unitate_masura, p.pret_achizitie, p.pret_vanzare
        FROM produse p WHERE p.activ=1 AND (p.denumire LIKE ? OR p.cod_articol LIKE ? OR p.cod_ean LIKE ?)
        LIMIT 20
    """, (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
    db.close()
    return jsonify([dict(p) for p in produse])
