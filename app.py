from flask import Flask, redirect, url_for
from flask_login import LoginManager
from database import init_db, get_db
from models import User
import os
import calendar
from datetime import date, datetime

app = Flask(__name__)
app.secret_key = 'gestiune_stocuri_secret_2024'

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Trebuie sa te autentifici pentru a accesa aceasta pagina.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    u = db.execute('SELECT * FROM utilizatori WHERE id=? AND activ=1', (user_id,)).fetchone()
    db.close()
    if u:
        return User(u['id'], u['username'], u['rol'], u['nume_complet'], u['locatie_id'])
    return None

# Import routes
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.produse import produse_bp
from routes.furnizori import furnizori_bp
from routes.locatii import locatii_bp
from routes.utilizatori import utilizatori_bp
from routes.intrari import intrari_bp
from routes.distributii import distributii_bp
from routes.transferuri import transferuri_bp
from routes.vanzari import vanzari_bp
from routes.retururi import retururi_bp
from routes.pierderi import pierderi_bp
from routes.inventar import inventar_bp
from routes.stoc import stoc_bp
from routes.analiza import analiza_bp
from routes.angajat import angajat_bp
from routes.documente import documente_bp
from routes.delegatii import delegatii_bp
from routes.salarii import salarii_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(produse_bp)
app.register_blueprint(furnizori_bp)
app.register_blueprint(locatii_bp)
app.register_blueprint(utilizatori_bp)
app.register_blueprint(intrari_bp)
app.register_blueprint(distributii_bp)
app.register_blueprint(transferuri_bp)
app.register_blueprint(vanzari_bp)
app.register_blueprint(retururi_bp)
app.register_blueprint(pierderi_bp)
app.register_blueprint(inventar_bp)
app.register_blueprint(stoc_bp)
app.register_blueprint(analiza_bp)
app.register_blueprint(angajat_bp)
app.register_blueprint(documente_bp)
app.register_blueprint(delegatii_bp)
app.register_blueprint(salarii_bp)

@app.context_processor
def inject_online_users():
    from flask_login import current_user
    if current_user.is_authenticated:
        db = get_db()
        rows = db.execute("""
            SELECT username, nume_complet, rol FROM utilizatori
            WHERE activ=1 AND last_seen >= datetime('now', '-5 minutes', 'localtime')
            ORDER BY last_seen DESC
        """).fetchall()
        db.close()
        return {'online_users': rows}
    return {'online_users': []}

@app.before_request
def update_last_seen():
    from flask_login import current_user
    if current_user.is_authenticated:
        db = get_db()
        db.execute("UPDATE utilizatori SET last_seen=? WHERE id=?",
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), current_user.id))
        db.commit()
        db.close()

@app.route('/')
def index():
    return redirect(url_for('dashboard.index'))


def _auto_genereaza_delegatii():
    """Called by scheduler: 7 days before month end, generate next month's delegations."""
    azi = date.today()
    ultima_zi = calendar.monthrange(azi.year, azi.month)[1]
    zile_ramase = ultima_zi - azi.day
    if zile_ramase != 7:
        return

    luna_urm = azi.month + 1 if azi.month < 12 else 1
    an_urm   = azi.year if azi.month < 12 else azi.year + 1

    with app.app_context():
        db = get_db()
        existent = db.execute(
            "SELECT id FROM delegatii_generare WHERE luna=? AND an=?",
            (luna_urm, an_urm)
        ).fetchone()
        if existent:
            db.close()
            return

        angajati = db.execute("""
            SELECT a.*, l.nume as locatie_nume
            FROM angajati a LEFT JOIN locatii l ON a.locatie_id=l.id
            WHERE a.activ=1 ORDER BY l.nume, a.nume
        """).fetchall()

        if not angajati:
            db.close()
            return

        from routes.delegatii import _get_next_nr, _genereaza_fisier
        nr_start = _get_next_nr(db, len(angajati))
        data_emitere_str = azi.strftime('%d.%m.%Y')

        try:
            out_path, filename = _genereaza_fisier(luna_urm, an_urm, angajati, nr_start, data_emitere_str)
        except Exception as e:
            db.close()
            print(f'[Auto-delegatii] Eroare: {e}')
            return

        nr_stop = nr_start + len(angajati) - 1
        db.execute("""
            INSERT INTO delegatii_generare (luna, an, nr_start, nr_stop, data_generare, fisier_path)
            VALUES (?,?,?,?,?,?)
        """, (luna_urm, an_urm, nr_start, nr_stop,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), filename))

        prima_zi_data  = f'{an_urm}-{luna_urm:02d}-01'
        ultima_zi_val  = calendar.monthrange(an_urm, luna_urm)[1]
        ultima_zi_data = f'{an_urm}-{luna_urm:02d}-{ultima_zi_val:02d}'
        for ang in angajati:
            db.execute("""
                INSERT INTO documente_angajati
                    (angajat_id, tip, data_emitere, data_expirare, observatii, created_at)
                VALUES (?,?,?,?,?,?)
            """, (ang['id'], 'delegatie', prima_zi_data, ultima_zi_data,
                  f'Delegatie {luna_urm:02d}/{an_urm}',
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        db.commit()
        db.close()
        print(f'[Auto-delegatii] Generate {len(angajati)} delegatii pentru {luna_urm:02d}/{an_urm}.')


# APScheduler – check daily at 08:00
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(_auto_genereaza_delegatii, 'cron', hour=8, minute=0)
    scheduler.start()
except Exception as _e:
    print(f'[Scheduler] Nu a pornit: {_e}')


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
