from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import get_db
from datetime import date, datetime

financiar_bp = Blueprint('financiar', __name__, url_prefix='/financiar')


# ── DASHBOARD ──────────────────────────────────────────────────────────────────

@financiar_bp.route('/')
@login_required
def index():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    luna = request.args.get('luna', date.today().strftime('%Y-%m'))

    an, lun = luna[:4], luna[5:7]
    data_start = f"{an}-{lun}-01"
    data_end   = f"{an}-{lun}-31"

    venituri = db.execute(
        "SELECT COALESCE(SUM(total_cu_tva),0) as total FROM facturi_emise WHERE data BETWEEN ? AND ?",
        (data_start, data_end)
    ).fetchone()['total']

    cheltuieli_luna = db.execute(
        "SELECT COALESCE(SUM(suma),0) as total FROM cheltuieli WHERE data BETWEEN ? AND ?",
        (data_start, data_end)
    ).fetchone()['total']

    facturi_primite_luna = db.execute(
        "SELECT COALESCE(SUM(total_cu_tva),0) as total FROM facturi_primite WHERE data BETWEEN ? AND ?",
        (data_start, data_end)
    ).fetchone()['total']

    total_cheltuieli = cheltuieli_luna + facturi_primite_luna
    profit = venituri - total_cheltuieli

    neplatite_emise = db.execute(
        "SELECT COUNT(*) as nr, COALESCE(SUM(total_cu_tva),0) as total FROM facturi_emise WHERE status='neplatita'"
    ).fetchone()

    neplatite_primite = db.execute(
        "SELECT COUNT(*) as nr, COALESCE(SUM(total_cu_tva),0) as total FROM facturi_primite WHERE status='neplatita'"
    ).fetchone()

    # Grafic lunar (ultimele 6 luni)
    grafic = db.execute("""
        SELECT strftime('%Y-%m', data) as luna,
               SUM(total_cu_tva) as venituri
        FROM facturi_emise
        WHERE data >= date('now', '-6 months')
        GROUP BY luna ORDER BY luna
    """).fetchall()

    cheltuieli_grafic = db.execute("""
        SELECT strftime('%Y-%m', data) as luna,
               SUM(suma) as cheltuieli
        FROM cheltuieli
        WHERE data >= date('now', '-6 months')
        GROUP BY luna ORDER BY luna
    """).fetchall()

    grafic_dict = {r['luna']: r['venituri'] for r in grafic}
    chelt_dict  = {r['luna']: r['cheltuieli'] for r in cheltuieli_grafic}

    # Ultimele 5 facturi emise si cheltuieli
    facturi_recente = db.execute("""
        SELECT fe.*, c.nume as client_nume_db
        FROM facturi_emise fe LEFT JOIN clienti c ON fe.client_id = c.id
        ORDER BY fe.data DESC, fe.id DESC LIMIT 5
    """).fetchall()

    cheltuieli_recente = db.execute(
        "SELECT * FROM cheltuieli ORDER BY data DESC, id DESC LIMIT 5"
    ).fetchall()

    db.close()
    return render_template('financiar/index.html',
        luna=luna, venituri=venituri, total_cheltuieli=total_cheltuieli,
        profit=profit, neplatite_emise=neplatite_emise, neplatite_primite=neplatite_primite,
        facturi_recente=facturi_recente, cheltuieli_recente=cheltuieli_recente,
        grafic_dict=grafic_dict, chelt_dict=chelt_dict)


# ── CLIENTI ────────────────────────────────────────────────────────────────────

@financiar_bp.route('/clienti/')
@login_required
def clienti():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    lista = db.execute("SELECT * FROM clienti WHERE activ=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('financiar/clienti.html', clienti=lista)


@financiar_bp.route('/clienti/adauga', methods=['GET', 'POST'])
@login_required
def clienti_adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.clienti'))
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        if not nume:
            flash('Numele este obligatoriu.', 'danger')
        else:
            db = get_db()
            db.execute("""INSERT INTO clienti (nume, cui, reg_com, adresa, telefon, email, banca, iban)
                VALUES (?,?,?,?,?,?,?,?)""",
                (nume, request.form.get('cui','').strip(), request.form.get('reg_com','').strip(),
                 request.form.get('adresa','').strip(), request.form.get('telefon','').strip(),
                 request.form.get('email','').strip(), request.form.get('banca','').strip(),
                 request.form.get('iban','').strip()))
            db.commit()
            db.close()
            flash('Client adaugat.', 'success')
            return redirect(url_for('financiar.clienti'))
    return render_template('financiar/client_form.html', client=None)


@financiar_bp.route('/clienti/editeaza/<int:id>', methods=['GET', 'POST'])
@login_required
def clienti_editeaza(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.clienti'))
    db = get_db()
    client = db.execute("SELECT * FROM clienti WHERE id=?", (id,)).fetchone()
    if request.method == 'POST':
        nume = request.form.get('nume', '').strip()
        if not nume:
            flash('Numele este obligatoriu.', 'danger')
        else:
            db.execute("""UPDATE clienti SET nume=?, cui=?, reg_com=?, adresa=?, telefon=?, email=?, banca=?, iban=?
                WHERE id=?""",
                (nume, request.form.get('cui','').strip(), request.form.get('reg_com','').strip(),
                 request.form.get('adresa','').strip(), request.form.get('telefon','').strip(),
                 request.form.get('email','').strip(), request.form.get('banca','').strip(),
                 request.form.get('iban','').strip(), id))
            db.commit()
            db.close()
            flash('Client actualizat.', 'success')
            return redirect(url_for('financiar.clienti'))
    db.close()
    return render_template('financiar/client_form.html', client=client)


@financiar_bp.route('/clienti/sterge/<int:id>', methods=['POST'])
@login_required
def clienti_sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.clienti'))
    db = get_db()
    db.execute("UPDATE clienti SET activ=0 WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Client sters.', 'success')
    return redirect(url_for('financiar.clienti'))


# ── FACTURI EMISE ──────────────────────────────────────────────────────────────

@financiar_bp.route('/facturi-emise/')
@login_required
def facturi_emise():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    status_f = request.args.get('status', '')
    data_start = request.args.get('data_start', '')
    data_end   = request.args.get('data_end', '')
    if not data_start:
        data_start = (date.today().replace(day=1)).strftime('%Y-%m-%d')

    where, params = ["1=1"], []
    if status_f:
        where.append("fe.status=?"); params.append(status_f)
    if data_start:
        where.append("fe.data >= ?"); params.append(data_start)
    if data_end:
        where.append("fe.data <= ?"); params.append(data_end)

    lista = db.execute(f"""
        SELECT fe.*, c.nume as client_nume_db
        FROM facturi_emise fe LEFT JOIN clienti c ON fe.client_id = c.id
        WHERE {' AND '.join(where)}
        ORDER BY fe.data DESC, fe.id DESC LIMIT 200
    """, params).fetchall()

    total_val = sum(r['total_cu_tva'] for r in lista)
    db.close()
    return render_template('financiar/facturi_emise.html',
        lista=lista, status_f=status_f, data_start=data_start, data_end=data_end,
        total_val=total_val)


@financiar_bp.route('/facturi-emise/adauga', methods=['GET', 'POST'])
@login_required
def facturi_emise_adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_emise'))
    db = get_db()
    if request.method == 'POST':
        import json
        nr_factura   = request.form.get('nr_factura', '').strip()
        data_f       = request.form.get('data', date.today().strftime('%Y-%m-%d'))
        client_id    = request.form.get('client_id') or None
        client_liber = request.form.get('client_liber', '').strip()
        data_scad    = request.form.get('data_scadenta', '')
        observatii   = request.form.get('observatii', '').strip()
        linii_json   = request.form.get('linii_json', '[]')

        if not nr_factura:
            flash('Numarul facturii este obligatoriu.', 'danger')
        else:
            try:
                linii = json.loads(linii_json)
            except:
                linii = []

            if client_id:
                c = db.execute("SELECT nume FROM clienti WHERE id=?", (client_id,)).fetchone()
                client_nume = c['nume'] if c else client_liber
            else:
                client_nume = client_liber

            total_fara = sum(float(l.get('valoare', 0)) for l in linii)
            total_tva  = sum(float(l.get('valoare', 0)) * float(l.get('tva_proc', 19)) / 100 for l in linii)
            total_cu   = total_fara + total_tva

            cur = db.execute("""INSERT INTO facturi_emise
                (nr_factura, data, client_id, client_nume, total_fara_tva, tva, total_cu_tva,
                 data_scadenta, observatii, utilizator_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (nr_factura, data_f, client_id, client_nume, total_fara, total_tva, total_cu,
                 data_scad or None, observatii, current_user.id))
            fid = cur.lastrowid
            for l in linii:
                val = float(l.get('cantitate', 1)) * float(l.get('pret_unitar', 0))
                db.execute("""INSERT INTO facturi_emise_detalii
                    (factura_id, denumire, cantitate, pret_unitar, tva_proc, valoare) VALUES (?,?,?,?,?,?)""",
                    (fid, l['denumire'], l.get('cantitate', 1), l.get('pret_unitar', 0),
                     l.get('tva_proc', 19), val))
            db.commit()
            db.close()
            flash(f'Factura {nr_factura} adaugata.', 'success')
            return redirect(url_for('financiar.factura_emisa_detalii', id=fid))

    clienti_lista = db.execute("SELECT id, nume FROM clienti WHERE activ=1 ORDER BY nume").fetchall()
    # Numar factura sugerat
    last = db.execute("SELECT nr_factura FROM facturi_emise ORDER BY id DESC LIMIT 1").fetchone()
    nr_sugerat = ''
    if last:
        try:
            nr_sugerat = str(int(''.join(filter(str.isdigit, last['nr_factura']))) + 1).zfill(4)
        except:
            nr_sugerat = ''
    db.close()
    return render_template('financiar/factura_emisa_form.html',
        clienti=clienti_lista, nr_sugerat=nr_sugerat,
        today=date.today().strftime('%Y-%m-%d'))


@financiar_bp.route('/facturi-emise/<int:id>')
@login_required
def factura_emisa_detalii(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_emise'))
    db = get_db()
    factura = db.execute("""
        SELECT fe.*, c.cui, c.reg_com, c.adresa as client_adresa,
               c.banca, c.iban, c.telefon as client_tel
        FROM facturi_emise fe LEFT JOIN clienti c ON fe.client_id = c.id
        WHERE fe.id=?
    """, (id,)).fetchone()
    linii = db.execute(
        "SELECT * FROM facturi_emise_detalii WHERE factura_id=? ORDER BY id", (id,)
    ).fetchall()
    setari = db.execute("SELECT cheie, valoare FROM setari WHERE cheie IN ('firma_nume','firma_cui','firma_adresa','firma_banca','firma_iban')").fetchall()
    setari_dict = {r['cheie']: r['valoare'] for r in setari}
    db.close()
    return render_template('financiar/factura_emisa_detalii.html',
        factura=factura, linii=linii, setari=setari_dict)


@financiar_bp.route('/facturi-emise/<int:id>/status', methods=['POST'])
@login_required
def factura_emisa_status(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_emise'))
    status = request.form.get('status', 'neplatita')
    db = get_db()
    db.execute("UPDATE facturi_emise SET status=? WHERE id=?", (status, id))
    db.commit()
    db.close()
    flash('Status actualizat.', 'success')
    return redirect(url_for('financiar.factura_emisa_detalii', id=id))


@financiar_bp.route('/facturi-emise/<int:id>/sterge', methods=['POST'])
@login_required
def factura_emisa_sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_emise'))
    db = get_db()
    db.execute("DELETE FROM facturi_emise WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Factura stearsa.', 'success')
    return redirect(url_for('financiar.facturi_emise'))


# ── FACTURI PRIMITE ────────────────────────────────────────────────────────────

@financiar_bp.route('/facturi-primite/')
@login_required
def facturi_primite():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    status_f   = request.args.get('status', '')
    data_start = request.args.get('data_start', '')
    data_end   = request.args.get('data_end', '')
    if not data_start:
        data_start = (date.today().replace(day=1)).strftime('%Y-%m-%d')

    where, params = ["1=1"], []
    if status_f:
        where.append("fp.status=?"); params.append(status_f)
    if data_start:
        where.append("fp.data >= ?"); params.append(data_start)
    if data_end:
        where.append("fp.data <= ?"); params.append(data_end)

    lista = db.execute(f"""
        SELECT fp.*, f.nume as furnizor_nume_db
        FROM facturi_primite fp LEFT JOIN furnizori f ON fp.furnizor_id = f.id
        WHERE {' AND '.join(where)}
        ORDER BY fp.data DESC, fp.id DESC LIMIT 200
    """, params).fetchall()

    total_val = sum(r['total_cu_tva'] for r in lista)
    db.close()
    return render_template('financiar/facturi_primite.html',
        lista=lista, status_f=status_f, data_start=data_start, data_end=data_end,
        total_val=total_val)


@financiar_bp.route('/facturi-primite/adauga', methods=['GET', 'POST'])
@login_required
def facturi_primite_adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_primite'))
    db = get_db()
    if request.method == 'POST':
        nr_factura    = request.form.get('nr_factura', '').strip()
        data_f        = request.form.get('data', date.today().strftime('%Y-%m-%d'))
        furnizor_id   = request.form.get('furnizor_id') or None
        furnizor_liber= request.form.get('furnizor_liber', '').strip()
        total_fara    = float(request.form.get('total_fara_tva', 0) or 0)
        tva           = float(request.form.get('tva', 0) or 0)
        total_cu      = total_fara + tva
        data_scad     = request.form.get('data_scadenta', '')
        observatii    = request.form.get('observatii', '').strip()

        if not nr_factura:
            flash('Numarul facturii este obligatoriu.', 'danger')
        else:
            if furnizor_id:
                f = db.execute("SELECT nume FROM furnizori WHERE id=?", (furnizor_id,)).fetchone()
                furnizor_nume = f['nume'] if f else furnizor_liber
            else:
                furnizor_nume = furnizor_liber

            db.execute("""INSERT INTO facturi_primite
                (nr_factura, data, furnizor_id, furnizor_nume, total_fara_tva, tva, total_cu_tva,
                 data_scadenta, observatii, utilizator_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (nr_factura, data_f, furnizor_id, furnizor_nume, total_fara, tva, total_cu,
                 data_scad or None, observatii, current_user.id))
            db.commit()
            db.close()
            flash(f'Factura {nr_factura} inregistrata.', 'success')
            return redirect(url_for('financiar.facturi_primite'))

    furnizori_lista = db.execute("SELECT id, nume FROM furnizori WHERE activ=1 ORDER BY nume").fetchall()
    db.close()
    return render_template('financiar/factura_primita_form.html',
        furnizori=furnizori_lista, today=date.today().strftime('%Y-%m-%d'))


@financiar_bp.route('/facturi-primite/<int:id>/status', methods=['POST'])
@login_required
def factura_primita_status(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_primite'))
    status = request.form.get('status', 'neplatita')
    db = get_db()
    db.execute("UPDATE facturi_primite SET status=? WHERE id=?", (status, id))
    db.commit()
    db.close()
    flash('Status actualizat.', 'success')
    return redirect(url_for('financiar.facturi_primite'))


@financiar_bp.route('/facturi-primite/<int:id>/sterge', methods=['POST'])
@login_required
def factura_primita_sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.facturi_primite'))
    db = get_db()
    db.execute("DELETE FROM facturi_primite WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Factura stearsa.', 'success')
    return redirect(url_for('financiar.facturi_primite'))


# ── CHELTUIELI ─────────────────────────────────────────────────────────────────

CATEGORII_CHELTUIELI = ['Chirie', 'Utilitati', 'Transport', 'Salarii', 'Materiale', 'Marketing', 'Altele']


@financiar_bp.route('/cheltuieli/')
@login_required
def cheltuieli():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    categorie_f = request.args.get('categorie', '')
    data_start  = request.args.get('data_start', '')
    data_end    = request.args.get('data_end', '')
    if not data_start:
        data_start = (date.today().replace(day=1)).strftime('%Y-%m-%d')

    where, params = ["1=1"], []
    if categorie_f:
        where.append("categorie=?"); params.append(categorie_f)
    if data_start:
        where.append("data >= ?"); params.append(data_start)
    if data_end:
        where.append("data <= ?"); params.append(data_end)

    lista = db.execute(
        f"SELECT * FROM cheltuieli WHERE {' AND '.join(where)} ORDER BY data DESC, id DESC LIMIT 200",
        params
    ).fetchall()

    total = sum(r['suma'] for r in lista)

    per_categ = db.execute("""
        SELECT categorie, SUM(suma) as total
        FROM cheltuieli
        WHERE data >= ? AND data <= COALESCE(?, date('now'))
        GROUP BY categorie ORDER BY total DESC
    """, (data_start, data_end or None)).fetchall()

    db.close()
    return render_template('financiar/cheltuieli.html',
        lista=lista, total=total, categorie_f=categorie_f,
        data_start=data_start, data_end=data_end,
        per_categ=per_categ, categorii=CATEGORII_CHELTUIELI)


@financiar_bp.route('/cheltuieli/adauga', methods=['GET', 'POST'])
@login_required
def cheltuieli_adauga():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.cheltuieli'))
    if request.method == 'POST':
        data_c    = request.form.get('data', date.today().strftime('%Y-%m-%d'))
        categorie = request.form.get('categorie', '').strip()
        descriere = request.form.get('descriere', '').strip()
        suma      = request.form.get('suma', '0').strip()
        observatii= request.form.get('observatii', '').strip()
        if not descriere or not suma:
            flash('Descrierea si suma sunt obligatorii.', 'danger')
        else:
            db = get_db()
            db.execute("""INSERT INTO cheltuieli (data, categorie, descriere, suma, observatii, utilizator_id)
                VALUES (?,?,?,?,?,?)""",
                (data_c, categorie, descriere, float(suma), observatii, current_user.id))
            db.commit()
            db.close()
            flash('Cheltuiala adaugata.', 'success')
            return redirect(url_for('financiar.cheltuieli'))
    return render_template('financiar/cheltuiala_form.html',
        categorii=CATEGORII_CHELTUIELI, today=date.today().strftime('%Y-%m-%d'))


@financiar_bp.route('/cheltuieli/<int:id>/sterge', methods=['POST'])
@login_required
def cheltuiala_sterge(id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.cheltuieli'))
    db = get_db()
    db.execute("DELETE FROM cheltuieli WHERE id=?", (id,))
    db.commit()
    db.close()
    flash('Cheltuiala stearsa.', 'success')
    return redirect(url_for('financiar.cheltuieli'))


# ── RAPOARTE ───────────────────────────────────────────────────────────────────

@financiar_bp.route('/rapoarte/')
@login_required
def rapoarte():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    an = request.args.get('an', str(date.today().year))

    lunar = []
    for luna in range(1, 13):
        ds = f"{an}-{luna:02d}-01"
        de = f"{an}-{luna:02d}-31"
        v = db.execute("SELECT COALESCE(SUM(total_cu_tva),0) as t FROM facturi_emise WHERE data BETWEEN ? AND ?", (ds, de)).fetchone()['t']
        c = db.execute("SELECT COALESCE(SUM(suma),0) as t FROM cheltuieli WHERE data BETWEEN ? AND ?", (ds, de)).fetchone()['t']
        fp = db.execute("SELECT COALESCE(SUM(total_cu_tva),0) as t FROM facturi_primite WHERE data BETWEEN ? AND ?", (ds, de)).fetchone()['t']
        lunar.append({'luna': luna, 'venituri': v, 'cheltuieli': c + fp, 'profit': v - c - fp})

    total_v  = sum(r['venituri'] for r in lunar)
    total_ch = sum(r['cheltuieli'] for r in lunar)
    total_p  = total_v - total_ch

    top_clienti = db.execute("""
        SELECT client_nume, SUM(total_cu_tva) as total
        FROM facturi_emise WHERE data LIKE ?
        GROUP BY client_nume ORDER BY total DESC LIMIT 5
    """, (f"{an}%",)).fetchall()

    top_cheltuieli = db.execute("""
        SELECT categorie, SUM(suma) as total
        FROM cheltuieli WHERE data LIKE ?
        GROUP BY categorie ORDER BY total DESC
    """, (f"{an}%",)).fetchall()

    ani_disponibili = db.execute("""
        SELECT DISTINCT strftime('%Y', data) as an FROM facturi_emise
        UNION SELECT DISTINCT strftime('%Y', data) FROM cheltuieli
        ORDER BY an DESC
    """).fetchall()

    db.close()
    return render_template('financiar/rapoarte.html',
        an=an, lunar=lunar, total_v=total_v, total_ch=total_ch, total_p=total_p,
        top_clienti=top_clienti, top_cheltuieli=top_cheltuieli,
        ani_disponibili=ani_disponibili)


# ── SETARI FIRMA ───────────────────────────────────────────────────────────────

@financiar_bp.route('/setari/', methods=['GET', 'POST'])
@login_required
def setari():
    if not current_user.is_admin():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('financiar.index'))
    db = get_db()
    if request.method == 'POST':
        for cheie in ['firma_nume', 'firma_cui', 'firma_reg_com', 'firma_adresa', 'firma_banca', 'firma_iban', 'firma_telefon', 'firma_email']:
            val = request.form.get(cheie, '').strip()
            db.execute("INSERT INTO setari (cheie, valoare) VALUES (?,?) ON CONFLICT(cheie) DO UPDATE SET valoare=excluded.valoare",
                       (cheie, val))
        db.commit()
        db.close()
        flash('Datele firmei au fost salvate.', 'success')
        return redirect(url_for('financiar.setari'))
    setari_rows = db.execute("SELECT cheie, valoare FROM setari").fetchall()
    setari_dict = {r['cheie']: r['valoare'] for r in setari_rows}
    db.close()
    return render_template('financiar/setari.html', setari=setari_dict)
