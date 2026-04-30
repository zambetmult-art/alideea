from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from database import get_db

stoc_bp = Blueprint('stoc', __name__, url_prefix='/stoc')

@stoc_bp.route('/')
@login_required
def index():
    db = get_db()
    locatii = db.execute("SELECT * FROM locatii WHERE activa=1 ORDER BY nume").fetchall()
    locatie_id = request.args.get('locatie_id', 'central')

    if locatie_id == 'central':
        # Stoc central = total intrari - total distributii
        stoc = db.execute("""
            SELECT p.id, p.cod_articol, p.denumire, p.unitate_masura, p.stoc_minim,
                   c.nume as categorie_nume,
                   COALESCE(SUM(CASE WHEN src='intrare' THEN cant ELSE -cant END), 0) as stoc_curent
            FROM produse p
            LEFT JOIN categorii c ON p.categorie_id=c.id
            LEFT JOIN (
                SELECT produs_id, cantitate as cant, 'intrare' as src FROM intrari_detalii
                UNION ALL
                SELECT produs_id, cantitate, 'iesire' FROM distributii_detalii
            ) mv ON mv.produs_id = p.id
            WHERE p.activ=1
            GROUP BY p.id
            ORDER BY c.nume, p.denumire
        """).fetchall()
        titlu = "Stoc Central"
    else:
        try:
            lid = int(locatie_id)
        except:
            lid = 0
        locatie = db.execute("SELECT * FROM locatii WHERE id=?", (lid,)).fetchone()
        titlu = f"Stoc - {locatie['nume']}" if locatie else "Stoc Locatie"

        stoc = db.execute("""
            SELECT p.id, p.cod_articol, p.denumire, p.unitate_masura, p.stoc_minim,
                   c.nume as categorie_nume,
                   COALESCE((SELECT SUM(dd.cantitate) FROM distributii_detalii dd
                              JOIN distributii d ON dd.distributie_id=d.id
                              WHERE dd.produs_id=p.id AND d.locatie_id=?), 0)
                   + COALESCE((SELECT SUM(td.cantitate) FROM transferuri_detalii td
                                JOIN transferuri t ON td.transfer_id=t.id
                                WHERE td.produs_id=p.id AND t.locatie_destinatie_id=?), 0)
                   - COALESCE((SELECT SUM(rd.cantitate) FROM retururi_detalii rd
                                JOIN retururi r ON rd.retur_id=r.id
                                WHERE rd.produs_id=p.id AND r.locatie_id=?), 0)
                   - COALESCE((SELECT SUM(td2.cantitate) FROM transferuri_detalii td2
                                JOIN transferuri t2 ON td2.transfer_id=t2.id
                                WHERE td2.produs_id=p.id AND t2.locatie_sursa_id=?), 0)
                   - COALESCE((SELECT SUM(vd.cantitate) FROM vanzari_detalii vd
                                JOIN vanzari_import vi ON vd.import_id=vi.id
                                WHERE vd.produs_id=p.id AND vi.locatie_id=?), 0)
                   - COALESCE((SELECT SUM(pi.cantitate) FROM pierderi pi
                                WHERE pi.produs_id=p.id AND pi.locatie_id=?), 0)
                   as stoc_curent
            FROM produse p
            LEFT JOIN categorii c ON p.categorie_id=c.id
            WHERE p.activ=1
            ORDER BY c.nume, p.denumire
        """, (lid, lid, lid, lid, lid, lid)).fetchall()

    db.close()
    return render_template('stoc/index.html',
        stoc=stoc, locatii=locatii,
        locatie_id=locatie_id, titlu=titlu)
