import imaplib
import email
import os
import json

GMAIL_EMAIL = 'zambetmult@gmail.com'
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gmail_config.json')
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')


def get_app_password():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f).get('app_password', '')
    return ''


def descarca_excel_din_email():
    """
    Se conecteaza la Gmail via IMAP, cauta emailuri necitite cu fisiere Excel atasate,
    le descarca in folderul uploads si returneaza lista de cai + id-uri email procesate.
    """
    app_password = get_app_password()
    if not app_password:
        return [], 'Parola Gmail nu este configurata.'

    os.makedirs(UPLOADS_DIR, exist_ok=True)

    fisiere_descarcate = []
    eroare = None

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login(GMAIL_EMAIL, app_password)
        mail.select('inbox')

        # Cauta emailuri necitite care au "stocuri" sau "raport" sau "carrefour" in subiect
        # sau orice email necitit cu atasament Excel
        _, msgs = mail.search(None, 'UNSEEN')
        id_list = msgs[0].split()

        if not id_list:
            mail.logout()
            return [], None  # Niciun email nou

        for email_id in id_list:
            _, data = mail.fetch(email_id, '(RFC822)')
            msg = email.message_from_bytes(data[0][1])

            gasit_excel = False
            for part in msg.walk():
                content_disp = str(part.get('Content-Disposition', ''))
                filename = part.get_filename()
                if filename:
                    # Decodare nume fisier daca e encoded
                    decoded_parts = email.header.decode_header(filename)
                    filename = ''
                    for part_bytes, charset in decoded_parts:
                        if isinstance(part_bytes, bytes):
                            filename += part_bytes.decode(charset or 'utf-8', errors='replace')
                        else:
                            filename += part_bytes

                if filename and filename.lower().endswith(('.xlsx', '.xls')):
                    payload = part.get_payload(decode=True)
                    if payload:
                        cale = os.path.join(UPLOADS_DIR, filename)
                        # Evita suprascrierea - adauga sufix daca exista
                        base, ext = os.path.splitext(cale)
                        contor = 1
                        while os.path.exists(cale):
                            cale = f"{base}_{contor}{ext}"
                            contor += 1
                        with open(cale, 'wb') as f:
                            f.write(payload)
                        fisiere_descarcate.append(cale)
                        gasit_excel = True

            if gasit_excel:
                # Marcheaza emailul ca citit
                mail.store(email_id, '+FLAGS', '\\Seen')

        mail.logout()

    except imaplib.IMAP4.error as e:
        eroare = f'Eroare autentificare Gmail: {str(e)}'
    except Exception as e:
        eroare = f'Eroare la citirea emailului: {str(e)}'

    return fisiere_descarcate, eroare
