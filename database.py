import sqlite3
import os
import re
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get('DATABASE_URL')
DB_PATH = os.path.join(os.path.dirname(__file__), 'gestiune.db')


# ── PostgreSQL compatibility layer ────────────────────────────────────────────

def _pg_sql(sql):
    """Convert SQLite SQL syntax to PostgreSQL."""
    sql = sql.strip()
    if sql.upper().startswith('PRAGMA'):
        return ''
    sql = sql.replace('?', '%s')
    sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    sql = sql.replace("DEFAULT (datetime('now'))",
                      "DEFAULT (to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS'))")
    sql = sql.replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT NOW()")
    sql = sql.replace("datetime('now', 'localtime')",
                      "to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')")
    sql = sql.replace("datetime('now')",
                      "to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')")
    sql = re.sub(
        r"datetime\('now'\s*,\s*'([+-]?\d+)\s+minutes'(?:\s*,\s*'localtime')?\)",
        lambda m: f"to_char(NOW() + INTERVAL '{m.group(1)} minutes', 'YYYY-MM-DD HH24:MI:SS')",
        sql,
    )
    if 'INSERT OR IGNORE INTO' in sql:
        sql = sql.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
        sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    return sql


class _PgRow(dict):
    """sqlite3.Row-compatible dict."""
    def __getitem__(self, k):
        return list(self.values())[k] if isinstance(k, int) else super().__getitem__(k)
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)
    def keys(self): return list(super().keys())


class _PgCursor:
    def __init__(self, cur):
        self._c = cur

    def fetchone(self):
        if not self._c: return None
        r = self._c.fetchone()
        return _PgRow(r) if r else None

    def fetchall(self):
        if not self._c: return []
        return [_PgRow(r) for r in self._c.fetchall()]

    @property
    def rowcount(self): return self._c.rowcount if self._c else 0

    @property
    def lastrowid(self):
        if not self._c: return None
        try:
            self._c.execute("SELECT lastval()")
            row = self._c.fetchone()
            return list(row.values())[0] if row else None
        except Exception:
            return None


class _PgConn:
    """Drop-in sqlite3.Connection replacement backed by PostgreSQL."""

    def __init__(self, dsn):
        import psycopg2
        import psycopg2.extras
        if dsn.startswith('postgres://'):
            dsn = 'postgresql://' + dsn[len('postgres://'):]
        self._raw = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, sql, params=None):
        sql = _pg_sql(sql)
        if not sql:
            return _PgCursor(None)
        cur = self._raw.cursor()
        cur.execute(sql, params or ())
        return _PgCursor(cur)

    def executemany(self, sql, seq):
        sql = _pg_sql(sql)
        if not sql:
            return _PgCursor(None)
        cur = self._raw.cursor()
        cur.executemany(sql, seq)
        return _PgCursor(cur)

    def executescript(self, script):
        for stmt in script.split(';'):
            s = stmt.strip()
            if s:
                self.execute(s)

    def commit(self): self._raw.commit()

    def close(self):
        self._raw.commit()
        self._raw.close()

    def __enter__(self): return self
    def __exit__(self, exc, *_):
        self._raw.rollback() if exc else self._raw.commit()
        self._raw.close()


# ── Public API ────────────────────────────────────────────────────────────────

def get_db():
    if DATABASE_URL:
        return _PgConn(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    # Ordinea conteaza: tabelele referentiate trebuie create primele
    conn.execute('''CREATE TABLE IF NOT EXISTS locatii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT NOT NULL,
        adresa TEXT,
        activa INTEGER DEFAULT 1
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS categorii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT UNIQUE NOT NULL
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS furnizori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT NOT NULL,
        contact TEXT,
        telefon TEXT,
        email TEXT,
        activ INTEGER DEFAULT 1
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS utilizatori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        parola TEXT NOT NULL,
        nume_complet TEXT,
        rol TEXT NOT NULL DEFAULT 'angajat',
        locatie_id INTEGER,
        activ INTEGER DEFAULT 1,
        token TEXT,
        last_seen TEXT,
        FOREIGN KEY (locatie_id) REFERENCES locatii(id)
    )''')
    for col in ('token TEXT', 'last_seen TEXT'):
        try:
            conn.execute(f"ALTER TABLE utilizatori ADD COLUMN {col}")
        except Exception:
            pass

    conn.execute('''CREATE TABLE IF NOT EXISTS produse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cod_articol TEXT,
        cod_ean TEXT,
        denumire TEXT NOT NULL,
        categorie_id INTEGER,
        unitate_masura TEXT NOT NULL DEFAULT 'buc',
        pret_achizitie REAL DEFAULT 0,
        pret_vanzare REAL DEFAULT 0,
        stoc_minim REAL DEFAULT 0,
        activ INTEGER DEFAULT 1,
        FOREIGN KEY (categorie_id) REFERENCES categorii(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS angajati (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nume TEXT NOT NULL,
        locatie_id INTEGER,
        activ INTEGER DEFAULT 1,
        angajator TEXT,
        serie_ci TEXT,
        nr_ci TEXT,
        eliberat_de TEXT,
        data_ci TEXT,
        functia TEXT,
        magazin_delegatie TEXT,
        FOREIGN KEY (locatie_id) REFERENCES locatii(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS documente_angajati (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        angajat_id INTEGER NOT NULL,
        tip TEXT NOT NULL,
        data_emitere TEXT NOT NULL,
        data_expirare TEXT NOT NULL,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT,
        FOREIGN KEY (angajat_id) REFERENCES angajati(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS intrari (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS intrari_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        intrare_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        pret_unitar REAL DEFAULT 0,
        FOREIGN KEY (intrare_id) REFERENCES intrari(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS distributii (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS distributii_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        distributie_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        FOREIGN KEY (distributie_id) REFERENCES distributii(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS transferuri (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS transferuri_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transfer_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        FOREIGN KEY (transfer_id) REFERENCES transferuri(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS vanzari_import (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_raportare TEXT NOT NULL,
        locatie_id INTEGER NOT NULL,
        saptamana TEXT,
        fisier_original TEXT,
        importat_la TEXT DEFAULT (datetime('now')),
        nr_comanda TEXT,
        utilizator_id INTEGER,
        FOREIGN KEY (locatie_id) REFERENCES locatii(id),
        FOREIGN KEY (utilizator_id) REFERENCES utilizatori(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS vanzari_detalii (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS retururi (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS retururi_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        retur_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate REAL NOT NULL,
        FOREIGN KEY (retur_id) REFERENCES retururi(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS pierderi (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS inventar (
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

    conn.execute('''CREATE TABLE IF NOT EXISTS inventar_detalii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inventar_id INTEGER NOT NULL,
        produs_id INTEGER NOT NULL,
        cantitate_sistem REAL DEFAULT 0,
        cantitate_fizica REAL NOT NULL,
        diferenta REAL GENERATED ALWAYS AS (cantitate_fizica - cantitate_sistem) STORED,
        stoc_initial REAL DEFAULT 0,
        intrari REAL DEFAULT 0,
        FOREIGN KEY (inventar_id) REFERENCES inventar(id) ON DELETE CASCADE,
        FOREIGN KEY (produs_id) REFERENCES produse(id)
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS delegatii_generare (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        luna INTEGER NOT NULL,
        an INTEGER NOT NULL,
        nr_start INTEGER NOT NULL,
        nr_stop INTEGER NOT NULL,
        data_generare TEXT NOT NULL,
        fisier_path TEXT,
        trimis_email INTEGER DEFAULT 0,
        utilizator_id INTEGER
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS setari (
        cheie TEXT PRIMARY KEY,
        valoare TEXT
    )''')

    conn.execute('''CREATE TABLE IF NOT EXISTS salarii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        angajat_id INTEGER NOT NULL,
        luna INTEGER NOT NULL,
        an INTEGER NOT NULL,
        salariu_brut REAL DEFAULT 0,
        salariu_net REAL DEFAULT 0,
        bonusuri REAL DEFAULT 0,
        alte_costuri REAL DEFAULT 0,
        observatii TEXT,
        utilizator_id INTEGER,
        created_at TEXT,
        UNIQUE(angajat_id, luna, an)
    )''')

    # Admin default
    row = conn.execute("SELECT COUNT(*) FROM utilizatori WHERE rol='admin'").fetchone()
    if row[0] == 0:
        conn.execute(
            "INSERT INTO utilizatori (username, parola, nume_complet, rol) VALUES (?, ?, ?, ?)",
            ('admin', generate_password_hash('admin123'), 'Administrator', 'admin')
        )

    # Categorii default
    for cat in ['Mezeluri', 'Branzeturi', 'Zacusca', 'Conserve', 'Lactate', 'Altele']:
        conn.execute("INSERT OR IGNORE INTO categorii (nume) VALUES (?)", (cat,))

    conn.commit()
    conn.close()
