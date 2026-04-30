from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db

pierderi_bp = Blueprint('pierderi', __name__, url_prefix='/pierderi')


def _get_pierderi(db, tip):
    q = """
        SELECT p.*, l.nume as locatie_nume,
               pr.denumire as produs_denumire, pr.unitate_masura,
               pr.pret_vanzare,
               ROUND(p.cantitate * COALESCE(pr.pret_vanzare, 0), 2) as valoare
        FROM pierderi p
        LEFT JOIN locatii l ON p.locatie_id = l.id
        LEFT JOIN produse pr ON p.produs_id = pr.id
        WHERE p.tip = ?
    """
    params = [tip]
    if not current_user.is_manager() and current_user.locatie_id:
        q += " AND p.locatie_id = ?"
        params.append(current_user.locatie_id)
    q += " ORDER BY p.data DESC, p.id DESC LIMIT 300"
    return db.execute(q, params).fetchall()


@pierderi_bp.route('/')
@login_required
def index():
    return redirect(url_for('pierderi.sampling'))


@pierderi_bp.route('/sampling')
@login_required
def sampling():
    db = get_db()
    inregistrari = _get_pierderi(db, 'sampling')
    total_valoare = sum(r['valoare'] for r in inregistrari)
    db.close()
    return render_template('pierderi/lista.html',
                           inregistrari=inregistrari,
                           tip='sampling', titlu='Sampling',
                           total_valoare=total_valoare)


@pierderi_bp.route('/resturi')
@login_required
def resturi():
    db = get_db()
    inregistrari = _get_pierderi(db, 'rest')
    total_valoare = sum(r['valoare'] for r in inregistrari)
    db.close()
    return render_template('pierderi/lista.html',
                           inregistrari=inregistrari,
                           tip='rest', titlu='Resturi',
                           total_valoare=total_valoare)


@pierderi_bp.route('/adauga/<tip>', methods=['GET', 'POST'])
@login_required
def adauga(tip):
    if tip not in ('sampling', 'rest'):
        return redirect(url_for('pierderi.sampling'))
    db = get_db()
    if request.method == 'POST':
        data = request.form.get('data')
        locatie_id = request.form.get('locatie_id')
        if not current_user.is_manager():
            locatie_id = current_user.locatie_id
        produs_id = request.form.get('produs_id')
        cantitate = request.form.get('cantitate', 0)
        observatii = request.form.get('observatii', '').strip()
        if not data or not locatie_id or not produs_id or not cantitate:
            flash('Toate campurile obligatorii trebuie completate.', 'danger')
        else:
            db.execute("""
                INSERT INTO pierderi (data, locatie_id, tip, produs_id, cantitate, observatii, utilizator_id)
                VALUES (?,?,?,?,?,?,?)
            """, (data, locatie_id, tip, produs_id, float(cantitate), observatii, current_user.id))
            db.commit()
            flash(f'{"Sampling" if tip == "sampling" else "Rest"} inregistrat.', 'success')
            db.close()
            return redirect(url_for('pierderi.sampling' if tip == 'sampling' else 'pierderi.resturi'))

    if current_user.is_manager():
        locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    else:
        locatii = db.execute("SELECT * FROM locatii WHERE id=?", (current_user.locatie_id,)).fetchall()
    produse = db.execute(
        "SELECT id, denumire, unitate_masura, pret_vanzare FROM produse WHERE activ=1 ORDER BY denumire"
    ).fetchall()
    db.close()
    return render_template('pierderi/form.html', locatii=locatii, produse=produse,
                           tip=tip, titlu='Sampling' if tip == 'sampling' else 'Rest')


@pierderi_bp.route('/sterge/<int:id>', methods=['POST'])
@login_required
def sterge(id):
    db = get_db()
    p = db.execute("SELECT tip FROM pierderi WHERE id=?", (id,)).fetchone()
    tip = p['tip'] if p else 'sampling'
    db.execute("DELETE FROM pierderi WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Inregistrare stearsa.', 'success')
    return redirect(url_for('pierderi.sampling' if tip == 'sampling' else 'pierderi.resturi'))
