import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'alideea.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            city TEXT,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit TEXT DEFAULT 'buc',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS inventory_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id INTEGER NOT NULL,
            week_date TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (location_id) REFERENCES locations(id)
        );

        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            FOREIGN KEY (report_id) REFERENCES inventory_reports(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id INTEGER NOT NULL,
            status TEXT DEFAULT 'nou',
            seen INTEGER DEFAULT 0,
            notes TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (location_id) REFERENCES locations(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS stock_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            date TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS stock_exits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            date TEXT NOT NULL,
            order_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
    ''')

    # Seed real locations from Excel
    existing = c.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    if existing == 0:
        locations = [
            ('Cora Bratianu', 'București'),
            ('Carrefour Piatra Neamt', 'Piatra Neamț'),
            ('Carrefour Vulcan', 'București'),
            ('Carrefour Constanta', 'Constanța'),
            ('Carrefour Orhideea', 'București'),
            ('Carrefour Ploiesti Shopping', 'Ploiești'),
            ('Carrefour Baneasa', 'București'),
            ('Carrefour Galati', 'Galați'),
            ('Carrefour Ploiesti Vest', 'Ploiești'),
            ('Carrefour Brasov', 'Brașov'),
            ('Carrefour Iasi Felicia', 'Iași'),
            ('Carrefour Braila', 'Brăila'),
            ('Carrefour Berceni', 'București'),
            ('Carrefour Iasi Era', 'Iași'),
            ('Carrefour Colentina', 'București'),
        ]
        c.executemany("INSERT INTO locations (name, city) VALUES (?, ?)", locations)

    # Seed real products from Excel (93 products, unit kg)
    existing_prod = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if existing_prod == 0:
        products = [
            'ANTRICOT TARNESC DE VITA RAITAR', 'BRANZA DE BURDUF DODO', 'BRANZA FRAMANTATA DE OAIE ALIDEEA',
            'BRANZA PROASPATA', 'BURIC DE SAVENI VIOFANNY', 'CABANOS BOIERESC', 'CALTABOS RAITAR',
            'CARNATI BUCOVINEAN', 'CARNATI COPTI RAITAR', 'CARNATI CU PUI SI CURCAN',
            'CARNATI CU VIN SI BUSUIOC', 'CARNATI MANGALITA', 'CARNATI PICANTI SASCA',
            'CARNATI SASCA', 'CARNATI TRANDAFIR RAITAR', 'CAS DE VACA DODO', 'CAS DULCE DE OAIE ALIDEEA',
            'CASCAVAL BUCOVINEAN AFUMAT', 'CASCAVAL BUCOVINEAN ZADA', 'CASCAVAL DE SAVENI VIOFANNY',
            'CEAFA CRUD USCATA RAITAR', 'CEAFA HITUITA', 'CEAFA MANGALITA', 'CHISCA MOLDOVENEASCA',
            'CONDIMENT PENTRU PORC 190 G HUSTIULIUC', 'CONDIMENT PENTRU PUI 190 G HUSTIULIUC',
            'COSTITA FIARTA SI AFUM. RAITAR', 'CREMWURSTI CU PIEPT PUI', 'CREMWUSTI GROSI',
            'DROB CU OU', 'GUSA CU BOIA', 'GUSA MANGALITA', 'JAMBON MIERE ROZMARIN RAITAR',
            'JAMBON FARA OS RAITAR', 'JUMARI TARANESTI ALIDEEA', 'KAIZER RAITAR', 'LEBER RAITAR',
            'LEBERWURST CERUIT RAITAR', 'MUSCHI FILE AFUMAT HITUIT', 'MUSCHI FILE CRUD USCAT RAITAR',
            'MUSCHI FILE MANGALITA', 'MUSCHI MONTANA HITUIT', 'MUSCHI TIGANESC RAITAR',
            'MUSCHIULET MANGALITA', 'PARIZER CU SUNCA', 'PARIZER CU VITA', 'PASTA DE ARDEI DULCE',
            'PASTA DE ARDEI DULCE-PICANTA', 'PASTRAMA DE CURCAN RAITHAR', 'PASTRAMA DE VITA RAITAR',
            'PASTRAMA MANGALITA', 'PASTRAMA PIEPT CURCAN RAITAR', 'PASTRAMA PORC TARANEASCA RAITAR',
            'PATE COPT', 'PIEPT CONDIM TARANESC RAITAR', 'PIEPT CU BOIA', 'PIEPT PRESAT HITUIT RAITAR',
            'PULPA PORC HITUITA RAITAR', 'RASOL DEZOSAT SI AFUMAT RAITAR', 'RULADA PIEPT CURCAN BUCOVINA',
            'RULADA PIEPT PUI BUCOVINA', 'RULADA PORC LEGATA RAITAR', 'RULADA SASCA RAITAR',
            'SALAM CU PIPER RAITAR', 'SALAM BUCOVINEAN RAITAR', 'SALAM NEMTESC RAITAR',
            'SALAM PICANT SASCA', 'SALAM POIANA RAITAR', 'SALAM USCAT RAITAR', 'SALATA DE ARDEI COPTI',
            'SCARITA AFUMATA', 'SLANINA AFUMATA RAITAR', 'SLANINA CU USTUROI RAITAR',
            'SLANINA DIN BUCOVINA', 'SLANINA MANGALITA', 'SORIC COPT ALIDEEA', 'SUNCA DE SASCA RAITAR',
            'SUNCULITA MANGALITA', 'SUNCULITA MOSULUI', 'TELEMEA DE VACA DODO', 'TELEMEA MATURATA DE OAIE',
            'TELEMEA PROASPATA MIXTA', 'TOBA DE LIMBA', 'TOBA DE PUI RAITAR', 'TOBA TARANEASCA RAITAR',
            'TOCHITURA TARANEASCA RAITAR', 'URDA VIOFANNY', 'URECHI PORC RAITAR',
            'ZACUSCA CU CIUPECI HUSTIULIUC', 'ZACUSCA CU DE TOATE', 'ZACUSCA CU DOVLECEI',
            'ZACUSCA DE VINETE', 'ZACUSCA PICANTA',
        ]
        c.executemany("INSERT INTO products (name, unit) VALUES (?, 'kg')", [(p,) for p in products])

    conn.commit()
    conn.close()
