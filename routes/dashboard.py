from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from database import get_db

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    db = get_db()

    zile = request.args.get('zile', 30, type=int)
    if zile not in [7, 14, 30, 60, 90]:
        zile = 30

    # Stoc central total produse
    total_produse = db.execute("SELECT COUNT(*) as cnt FROM produse WHERE activ=1").fetchone()['cnt']

    # Numar locatii active
    total_locatii = db.execute("SELECT COUNT(*) as cnt FROM locatii WHERE activa=1").fetchone()['cnt']

    # Vanzari saptamana curenta (ultimele 7 zile)
    vanzari_recente = db.execute("""
        SELECT COALESCE(SUM(vd.valoare_fara_tva), 0) as total
        FROM vanzari_detalii vd
        JOIN vanzari_import vi ON vd.import_id = vi.id
        WHERE vi.data_raportare >= date('now', '-7 days')
    """).fetchone()['total']

    # Intrari recente (ultimele 7 zile)
    intrari_recente = db.execute("""
        SELECT COUNT(*) as cnt FROM intrari
        WHERE data >= date('now', '-7 days')
    """).fetchone()['cnt']

    # Grafic vanzari ultimele 8 saptamani
    vanzari_chart = db.execute("""
        SELECT vi.saptamana, COALESCE(SUM(vd.valoare_fara_tva), 0) as total
        FROM vanzari_import vi
        LEFT JOIN vanzari_detalii vd ON vd.import_id = vi.id
        GROUP BY vi.saptamana
        ORDER BY vi.data_raportare DESC
        LIMIT 8
    """).fetchall()

    # Top 5 produse vandute (cantitate)
    top_produse = db.execute("""
        SELECT p.denumire, COALESCE(SUM(vd.cantitate), 0) as total_cant,
               COALESCE(SUM(vd.valoare_fara_tva), 0) as total_val
        FROM produse p
        JOIN vanzari_detalii vd ON vd.produs_id = p.id
        GROUP BY p.id
        ORDER BY total_val DESC
        LIMIT 5
    """).fetchall()

    # Vanzari pe locatii (perioada selectata)
    vanzari_locatii = db.execute(f"""
        SELECT l.nume, COALESCE(SUM(vd.valoare_fara_tva), 0) as total
        FROM locatii l
        LEFT JOIN vanzari_import vi ON vi.locatie_id = l.id
            AND vi.data_raportare >= date('now', '-{zile} days')
        LEFT JOIN vanzari_detalii vd ON vd.import_id = vi.id
        WHERE l.activa = 1
        GROUP BY l.id
        ORDER BY total DESC
    """).fetchall()

    # Alerte stoc minim
    alerte_stoc = db.execute("""
        SELECT p.denumire, p.stoc_minim,
        COALESCE((SELECT SUM(id2.cantitate) FROM intrari_detalii id2 WHERE id2.produs_id = p.id), 0)
        - COALESCE((SELECT SUM(dd.cantitate) FROM distributii_detalii dd WHERE dd.produs_id = p.id), 0)
        as stoc_central
        FROM produse p
        WHERE p.activ = 1 AND p.stoc_minim > 0
        AND (
            COALESCE((SELECT SUM(id2.cantitate) FROM intrari_detalii id2 WHERE id2.produs_id = p.id), 0)
            - COALESCE((SELECT SUM(dd.cantitate) FROM distributii_detalii dd WHERE dd.produs_id = p.id), 0)
        ) <= p.stoc_minim
        LIMIT 5
    """).fetchall()

    db.close()

    return render_template('dashboard.html',
        total_produse=total_produse,
        total_locatii=total_locatii,
        vanzari_recente=vanzari_recente,
        intrari_recente=intrari_recente,
        vanzari_chart=list(reversed(vanzari_chart)),
        top_produse=top_produse,
        vanzari_locatii=vanzari_locatii,
        alerte_stoc=alerte_stoc,
        zile_selectate=zile
    )
