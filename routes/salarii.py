from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
from datetime import date, datetime

salarii_bp = Blueprint('salarii', __name__, url_prefix='/salarii')


@salarii_bp.route('/')
@login_required
def index():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    azi = date.today()
    luna = int(request.args.get('luna', azi.month))
    an   = int(request.args.get('an', azi.year))

    angajati = db.execute("""
        SELECT a.*, l.nume as locatie_nume,
               s.id as sal_id, s.salariu_brut, s.salariu_net,
               s.bonusuri, s.alte_costuri, s.observatii,
               ROUND(COALESCE(s.salariu_brut,0) + COALESCE(s.bonusuri,0) + COALESCE(s.alte_costuri,0), 2) as total_cost
        FROM angajati a
        LEFT JOIN locatii l ON a.locatie_id = l.id
        LEFT JOIN salarii s ON s.angajat_id = a.id AND s.luna = ? AND s.an = ?
        WHERE a.activ = 1
        ORDER BY l.nume, a.nume
    """, (luna, an)).fetchall()

    total_brut  = sum(r['salariu_brut'] or 0 for r in angajati)
    total_net   = sum(r['salariu_net'] or 0 for r in angajati)
    total_bonus = sum(r['bonusuri'] or 0 for r in angajati)
    total_alte  = sum(r['alte_costuri'] or 0 for r in angajati)
    total_cost  = sum(r['total_cost'] or 0 for r in angajati)

    db.close()
    return render_template('salarii/index.html',
                           angajati=angajati, luna=luna, an=an,
                           total_brut=total_brut, total_net=total_net,
                           total_bonus=total_bonus, total_alte=total_alte,
                           total_cost=total_cost)


@salarii_bp.route('/salveaza', methods=['POST'])
@login_required
def salveaza():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('salarii.index'))
    db = get_db()
    luna = int(request.form.get('luna'))
    an   = int(request.form.get('an'))
    angajat_ids = request.form.getlist('angajat_id')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for aid in angajat_ids:
        brut  = float(request.form.get(f'brut_{aid}') or 0)
        net   = float(request.form.get(f'net_{aid}') or 0)
        bonus = float(request.form.get(f'bonus_{aid}') or 0)
        alte  = float(request.form.get(f'alte_{aid}') or 0)
        obs   = request.form.get(f'obs_{aid}', '').strip()
        db.execute("""
            INSERT INTO salarii (angajat_id, luna, an, salariu_brut, salariu_net, bonusuri, alte_costuri, observatii, utilizator_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(angajat_id, luna, an) DO UPDATE SET
                salariu_brut=excluded.salariu_brut,
                salariu_net=excluded.salariu_net,
                bonusuri=excluded.bonusuri,
                alte_costuri=excluded.alte_costuri,
                observatii=excluded.observatii,
                utilizator_id=excluded.utilizator_id,
                created_at=excluded.created_at
        """, (aid, luna, an, brut, net, bonus, alte, obs, current_user.id, now))

    db.commit()
    db.close()
    flash(f'Salarii salvate pentru {luna:02d}/{an}.', 'success')
    return redirect(url_for('salarii.index', luna=luna, an=an))
