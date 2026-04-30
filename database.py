import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'gestiune.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Utilizatori
    c.execute('''CREATE TABLE IF NOT EXISTS utilizatori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        parola TEXT NOT NULL,
        nume_complet TEXT,
        rol TEXT NOT NULL DEFAULT 'angajat',
        locatie_id INTEGER,
        activ INTEGER DEFAULT 1,
        FOREIGN KEY (locatie_id) REFERENCES locatii(id)
    )''')

    # Categorii produse
    c.execute('''CREATE TABLE IF NOT EXISTS categorii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT UNIQUE NOT NULL
    )''')

    # Locatii (magazine Carrefour)
    c.execute('''CREATE TABLE IF NOT EXISTS locatii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT NOT NULL,
        adresa TEXT,
        activa INTEGER DEFAULT 1
    )''')

    # Furnizori
    c.execute('''CREATE TABLE IF NOT EXISTS furnizori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT NOT NULL,
        contact TEXT,
        telefon TEXT,
        email TEXT,
        activ INTEGER DEFAULT 1
    )''')

    # Produse
    c.execute('''CREATE TABLE IF NOT EXISTS produse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_articol TEXT UNIQUE,
        cod_ean TEXT,
        denumire TEXT NOT NULL,
        categorie_id INTEGER,
        unitate_masura TEXT NOT NULL DEFAULT 'kg',
        pret_achizitie REAL DEFAULT 0,
        pret_vanzare REAL DEFAULT 0,
        stoc_minim REAL DEFAULT 0,
        activ INTEGER DEFAULT 1,
        FOREIGN KEY (categorie_id) REFERENCES categorii(id)
    )''')

    # Intrari stoc (de la furnizori)
    c.execute('''CREATE TABLE IF NOT EXISTS intrari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        furnizor_id INTEGER,
        nr_document TEXT,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (furnizor_id) REFERENCES furnizori(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS intrari_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intrare_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        pret_unitar REAL DEFAULT 0,
        FOREIGN KEY (intrare_id) REFERENCES intrari(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    # Avize distributie (stoc central → locatie)
    c.execute('''CREATE TABLE IF NOT EXISTS distributii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        locatie_id INTEGER NOT NULL,
        nr_aviz TEXT,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (locatie_id) REFERENCES locatii(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS distributii_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        distributie_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        FOREIGN KEY (distributie_id) REFERENCES distributii(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    # Transferuri intre locatii
    c.execute('''CREATE TABLE IF NOT EXISTS transferuri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        locatie_sursa_id INTEGER NOT NULL,
        locatie_destinatie_id INTEGER NOT NULL,
        nr_document TEXT,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (locatie_sursa_id) REFERENCES locatii(id),
        FOREIGN KEY (locatie_destinatie_id) REFERENCES locatii(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transferuri_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transfer_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        FOREIGN KEY (transfer_id) REFERENCES transferuri(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    # Vanzari (import Excel Carrefour)
    c.execute('''CREATE TABLE IF NOT EXISTS vanzari_import (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_raportare TEXT NOT NULL,
        locatie_id INTEGER NOT NULL,
        saptamana TEXT,
        fisier_original TEXT,
        importat_la TEXT DEFAULT (datetime('now')),
        utilizator_id INTEGER,
        FOREIGN KEY (locatie_id) REFERENCES locatii(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS vanzari_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id INTEGER NOT NULL,
        produs_id INTEGER,
        cod_articol TEXT,
        cod_ean TEXT,
        denumire_original TEXT,
        cantitate REAL NOT NULL,
        unitate_masura TEXT,
        pret REAL DEFAULT 0,
        valoare_fara_tva REAL DEFAULT 0,
        FOREIGN KEY (import_id) REFERENCES vanzari_import(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    # Retururi (locatie → stoc central)
    c.execute('''CREATE TABLE IF NOT EXISTS retururi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        locatie_id INTEGER NOT NULL,
        nr_document TEXT,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (locatie_id) REFERENCES locatii(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS retururi_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        retur_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        FOREIGN KEY (retur_id) REFERENCES retururi(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    # Sampling & Resturi (pierderi)
    c.execute('''CREATE TABLE IF NOT EXISTS pierderi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        locatie_id INTEGER NOT NULL,
        tip TEXT NOT NULL CHECK(tip IN ('sampling', 'rest')),
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (locatie_id) REFERENCES locatii(id),
        FOREIGN KEY (produs_id) REFERENCES produse(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    # Inventar saptamanal
    c.execute('''CREATE TABLE IF NOT EXISTS inventar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        locatie_id INTEGER NOT NULL,
        observatii TEXT,
        utilizator_id INTEGER,
        finalizat INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (locatie_id) REFERENCES locatii(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS inventar_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inventar_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate_sistem REAL DEFAULT 0,
        cantitate_fizica REAL NOT NULL,
        diferenta REAL GENERATED ALWAYS AS (cantitate_fizica - cantitate_sistem) STORED,
        FOREIGN KEY (inventar_id) REFERENCES inventar(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    # Adauga admin default daca nu exista
    c.execute("SELECT COUNT(*) FROM utilizatori WHERE rol='admin'")
    if c.fetchone()[0] == 0:
        c.execute('''INSERT INTO utilizatori (username, parola, nume_complet, rol)
                     VALUES (?, ?, ?, ?)''',
                  ('admin', generate_password_hash('admin123'), 'Administrator', 'admin'))

    # Categorii default
    categorii_default = ['Mezeluri', 'Branzeturi', 'Zacusca', 'Conserve', 'Lactate', 'Altele']
    for cat in categorii_default:
        c.execute("INSERT OR IGNORE INTO categorii (nume) VALUES (?)", (cat,))

    conn.commit()
    conn.close()
