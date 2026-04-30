from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from database import get_db
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from docxtpl import DocxTemplate
from docx import Document
from docx.oxml.ns import qn
from copy import deepcopy
import os
import calendar
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

delegatii_bp = Blueprint('delegatii', __name__, url_prefix='/delegatii')

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'template_delegatie.docx')
OUTPUT_DIR    = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'delegatii_generate')

os.makedirs(OUTPUT_DIR, exist_ok=True)


def _ultima_zi(luna, an):
    return calendar.monthrange(an, luna)[1]


def _get_next_nr(db, count):
    """Increment the delegation counter and return the starting number."""
    row = db.execute("SELECT valoare FROM setari WHERE cheie='delegatii_ultim_nr'").fetchone()
    ultim = int(row['valoare']) if row else 6600
    nou = ultim + count
    db.execute("UPDATE setari SET valoare=? WHERE cheie='delegatii_ultim_nr'", (str(nou),))
    return ultim + 1  # first number to use


def _append_doc(base, src):
    """Append all body content from src Document into base Document."""
    # Add page break before appending (not before the very first)
    from docx.oxml import OxmlElement
    # Insert page break as last para of current content
    p = OxmlElement('w:p')
    r = OxmlElement('w:r')
    br = OxmlElement('w:br')
    br.set(qn('w:type'), 'page')
    r.append(br)
    p.append(r)
    base.element.body.append(p)

    for elem in src.element.body:
        if elem.tag.endswith('}sectPr'):
            continue
        base.element.body.append(deepcopy(elem))


def _genereaza_fisier(luna, an, angajati, nr_start, data_emitere_str):
    """Generate a Word doc with all delegations. Returns file path."""
    prima_zi = f'01'
    ultima_zi = str(_ultima_zi(luna, an))
    luna_str  = f'{luna:02d}'
    an_str    = str(an)
    luna_ro   = ['', 'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
                 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie'][luna]

    master = None
    for idx, ang in enumerate(angajati):
        ctx = {
            'NR_DELEGATIE': str(nr_start + idx),
            'DATA_EMITERE': data_emitere_str,
            'NUME_DELEGAT': ang['nume'] or '',
            'FUNCTIA':      ang['functia'] or 'lucrator comercial',
            'SERIE_CI':     ang['serie_ci'] or '',
            'NR_CI':        ang['nr_ci'] or '',
            'ELIBERAT_DE':  ang['eliberat_de'] or '',
            'DATA_CI':      ang['data_ci'] or '',
            'MAGAZIN':      ang['magazin_delegatie'] or (ang['locatie_nume'] or ''),
            'PRIMA_ZI':     prima_zi,
            'ULTIMA_ZI':    ultima_zi,
            'LUNA_NR':      luna_str,
            'AN':           an_str,
        }
        tpl = DocxTemplate(TEMPLATE_PATH)
        tpl.render(ctx)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tf:
            tmp_path = tf.name
        tpl.save(tmp_path)

        rendered = Document(tmp_path)
        os.unlink(tmp_path)

        if master is None:
            master = rendered
        else:
            _append_doc(master, rendered)

    filename = f'delegatii_{an}_{luna:02d}.docx'
    out_path  = os.path.join(OUTPUT_DIR, filename)
    if master:
        master.save(out_path)
    return out_path, filename


@delegatii_bp.route('/')
@login_required
def index():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('dashboard.index'))
    db = get_db()
    generari = db.execute("""
        SELECT dg.*, u.username
        FROM delegatii_generare dg
        LEFT JOIN utilizatori u ON dg.utilizator_id = u.id
        ORDER BY dg.an DESC, dg.luna DESC
    """).fetchall()

    azi = date.today()
    # Suggest next month
    luna_urm = azi.month + 1 if azi.month < 12 else 1
    an_urm   = azi.year if azi.month < 12 else azi.year + 1

    row_dest = db.execute("SELECT valoare FROM setari WHERE cheie='email_dest_default'").fetchone()
    angajati_count = db.execute("SELECT COUNT(*) FROM angajati WHERE activ=1").fetchone()[0]
    db.close()
    return render_template('delegatii/index.html',
                           generari=generari,
                           luna_urm=luna_urm, an_urm=an_urm,
                           luna_cur=azi.month, an_cur=azi.year,
                           azi=azi,
                           email_dest_default=row_dest['valoare'] if row_dest else '',
                           angajati_count=angajati_count)


@delegatii_bp.route('/genereaza', methods=['POST'])
@login_required
def genereaza():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('delegatii.index'))

    luna = int(request.form.get('luna', 0))
    an   = int(request.form.get('an', 0))
    if not (1 <= luna <= 12) or an < 2024:
        flash('Luna sau an invalid.', 'danger')
        return redirect(url_for('delegatii.index'))

    data_emitere_str = request.form.get('data_emitere') or date.today().strftime('%d.%m.%Y')

    db = get_db()
    # Check if already generated
    existent = db.execute(
        "SELECT id FROM delegatii_generare WHERE luna=? AND an=?", (luna, an)
    ).fetchone()
    if existent:
        flash(f'Delegatiile pentru {luna:02d}/{an} au fost deja generate. Sterge-le mai intai daca vrei sa regenerezi.', 'warning')
        db.close()
        return redirect(url_for('delegatii.index'))

    angajati = db.execute("""
        SELECT a.*, l.nume as locatie_nume
        FROM angajati a
        LEFT JOIN locatii l ON a.locatie_id = l.id
        WHERE a.activ=1
        ORDER BY l.nume, a.nume
    """).fetchall()

    if not angajati:
        flash('Nu exista angajati activi.', 'danger')
        db.close()
        return redirect(url_for('delegatii.index'))

    nr_start = _get_next_nr(db, len(angajati))

    try:
        out_path, filename = _genereaza_fisier(luna, an, angajati, nr_start, data_emitere_str)
    except Exception as e:
        db.close()
        flash(f'Eroare la generare: {e}', 'danger')
        return redirect(url_for('delegatii.index'))

    nr_stop = nr_start + len(angajati) - 1
    db.execute("""
        INSERT INTO delegatii_generare (luna, an, nr_start, nr_stop, data_generare, fisier_path, utilizator_id)
        VALUES (?,?,?,?,?,?,?)
    """, (luna, an, nr_start, nr_stop, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          filename, current_user.id))

    # Register delegations in documente_angajati
    prima_zi_data = f'{an}-{luna:02d}-01'
    ultima_zi_val = _ultima_zi(luna, an)
    ultima_zi_data = f'{an}-{luna:02d}-{ultima_zi_val:02d}'
    for ang in angajati:
        db.execute("""
            INSERT INTO documente_angajati (angajat_id, tip, data_emitere, data_expirare, observatii, utilizator_id, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (ang['id'], 'delegatie', prima_zi_data, ultima_zi_data,
              f'Delegatie {luna:02d}/{an}',
              current_user.id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    db.commit()
    db.close()

    flash(f'Generate {len(angajati)} delegatii pentru {luna:02d}/{an} (Nr. {nr_start}-{nr_stop}).', 'success')
    return redirect(url_for('delegatii.index'))


@delegatii_bp.route('/descarca/<int:gen_id>')
@login_required
def descarca(gen_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('delegatii.index'))
    db = get_db()
    gen = db.execute("SELECT * FROM delegatii_generare WHERE id=?", (gen_id,)).fetchone()
    db.close()
    if not gen:
        flash('Generare negasita.', 'danger')
        return redirect(url_for('delegatii.index'))
    filepath = os.path.join(OUTPUT_DIR, gen['fisier_path'])
    if not os.path.exists(filepath):
        flash('Fisierul nu mai exista pe server.', 'danger')
        return redirect(url_for('delegatii.index'))
    return send_file(filepath, as_attachment=True, download_name=gen['fisier_path'])


@delegatii_bp.route('/sterge/<int:gen_id>', methods=['POST'])
@login_required
def sterge(gen_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('delegatii.index'))
    db = get_db()
    gen = db.execute("SELECT * FROM delegatii_generare WHERE id=?", (gen_id,)).fetchone()
    if gen:
        filepath = os.path.join(OUTPUT_DIR, gen['fisier_path'])
        if os.path.exists(filepath):
            os.unlink(filepath)
        db.execute("DELETE FROM delegatii_generare WHERE id=?", (gen_id,))
        db.commit()
        flash('Generare stearsa.', 'success')
    db.close()
    return redirect(url_for('delegatii.index'))


@delegatii_bp.route('/trimite-email/<int:gen_id>', methods=['POST'])
@login_required
def trimite_email(gen_id):
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('delegatii.index'))

    email_dest = request.form.get('email_dest', '').strip()
    if not email_dest:
        flash('Adresa de email lipseste.', 'danger')
        return redirect(url_for('delegatii.index'))

    db = get_db()
    gen = db.execute("SELECT * FROM delegatii_generare WHERE id=?", (gen_id,)).fetchone()
    if not gen:
        db.close()
        flash('Generare negasita.', 'danger')
        return redirect(url_for('delegatii.index'))

    filepath = os.path.join(OUTPUT_DIR, gen['fisier_path'])
    if not os.path.exists(filepath):
        db.close()
        flash('Fisierul nu mai exista.', 'danger')
        return redirect(url_for('delegatii.index'))

    # Read Gmail credentials from setari
    row_user = db.execute("SELECT valoare FROM setari WHERE cheie='gmail_user'").fetchone()
    row_pass = db.execute("SELECT valoare FROM setari WHERE cheie='gmail_pass'").fetchone()
    db.close()

    if not row_user or not row_pass:
        flash('Credentialele Gmail nu sunt configurate. Mergi la Setari.', 'warning')
        return redirect(url_for('delegatii.index'))

    gmail_user = row_user['valoare']
    gmail_pass = row_pass['valoare']

    try:
        msg = MIMEMultipart()
        msg['From']    = gmail_user
        msg['To']      = email_dest
        msg['Subject'] = f'Delegatii {gen["luna"]:02d}/{gen["an"]}'

        body = (f'Buna ziua,\n\nIn atasament gasiti delegatiile pentru luna '
                f'{gen["luna"]:02d}/{gen["an"]} '
                f'(Nr. {gen["nr_start"]} - {gen["nr_stop"]}).\n\nAlideea 2014 SRL')
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with open(filepath, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{gen["fisier_path"]}"')
        msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, email_dest, msg.as_string())

        db2 = get_db()
        db2.execute("UPDATE delegatii_generare SET trimis_email=1 WHERE id=?", (gen_id,))
        db2.commit()
        db2.close()

        flash(f'Email trimis cu succes catre {email_dest}.', 'success')
    except Exception as e:
        flash(f'Eroare la trimitere email: {e}', 'danger')

    return redirect(url_for('delegatii.index'))


@delegatii_bp.route('/setari-email', methods=['GET', 'POST'])
@login_required
def setari_email():
    if not current_user.is_manager():
        flash('Acces restrictionat.', 'danger')
        return redirect(url_for('delegatii.index'))
    db = get_db()
    if request.method == 'POST':
        gmail_user = request.form.get('gmail_user', '').strip()
        gmail_pass = request.form.get('gmail_pass', '').strip()
        email_dest = request.form.get('email_dest_default', '').strip()
        db.execute("INSERT OR REPLACE INTO setari (cheie, valoare) VALUES ('gmail_user', ?)", (gmail_user,))
        db.execute("INSERT OR REPLACE INTO setari (cheie, valoare) VALUES ('gmail_pass', ?)", (gmail_pass,))
        db.execute("INSERT OR REPLACE INTO setari (cheie, valoare) VALUES ('email_dest_default', ?)", (email_dest,))
        db.commit()
        flash('Setari email salvate.', 'success')
        db.close()
        return redirect(url_for('delegatii.index'))

    row_user  = db.execute("SELECT valoare FROM setari WHERE cheie='gmail_user'").fetchone()
    row_dest  = db.execute("SELECT valoare FROM setari WHERE cheie='email_dest_default'").fetchone()
    db.close()
    return render_template('delegatii/setari_email.html',
                           gmail_user=row_user['valoare'] if row_user else '',
                           email_dest_default=row_dest['valoare'] if row_dest else '')
