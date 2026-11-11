"""SQLite connections and schema initialization. Money is stored in cents."""
import os, sqlite3, hashlib, secrets
from contextlib import contextmanager
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DB = os.environ.get('PETSHOP_DB', str(ROOT / 'petshop_pro.db'))

# Initial catalog for demonstrations and team testing. These prices and
# quantities are illustrative and must be checked before live sales.
CATALOG = (
    ('Ração seca para cães adultos 15 kg', 'Alimentação', 17990, 12),
    ('Ração seca para cães filhotes 10 kg', 'Alimentação', 15490, 10),
    ('Ração para gatos castrados 1,5 kg', 'Alimentação', 4990, 18),
    ('Sachê para gatos sabor frango 85 g', 'Alimentação', 450, 24),
    ('Biscoito para cães 300 g', 'Petiscos', 1890, 16),
    ('Petisco dental para cães porte pequeno', 'Petiscos', 2290, 12),
    ('Areia higiênica para gatos 4 kg', 'Higiene', 2490, 20),
    ('Tapete higiênico para cães 30 unidades', 'Higiene', 5990, 15),
    ('Shampoo neutro para pets 500 ml', 'Higiene', 2990, 12),
    ('Escova dupla para cães e gatos', 'Higiene', 2490, 8),
    ('Escova removedora de pelos', 'Higiene', 3590, 8),
    ('Brinquedo de corda para cães', 'Brinquedos', 1990, 10),
    ('Bola com guizo para gatos', 'Brinquedos', 890, 16),
    ('Coleira ajustável para cães porte pequeno', 'Passeio', 1890, 8),
    ('Guia de nylon tamanho médio', 'Passeio', 3990, 8),
    ('Comedouro de inox 600 ml', 'Acessórios', 2990, 12),
    ('Bebedouro portátil 500 ml', 'Acessórios', 3490, 8),
    ('Caixa de transporte tamanho 2', 'Transporte', 14990, 5),
    ('Arranhador de papelão para gatos', 'Brinquedos', 3990, 6),
    ('Refil de saquinhos higiênicos 3 rolos', 'Passeio', 1290, 20),
)

def connect():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

@contextmanager
def session():
    """Open one SQLite unit of work and always close its file handle."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
def password_hash(value, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 310000).hex()

def seed_catalog(c):
    if c.execute("SELECT 1 FROM app_settings WHERE name='catalog_demo_v1'").fetchone():
        return
    for name, category, price_cents, stock in CATALOG:
        if not c.execute('SELECT 1 FROM products WHERE name=? AND category=?', (name, category)).fetchone():
            c.execute('INSERT INTO products(name,category,price_cents,stock) VALUES(?,?,?,?)',
                      (name, category, price_cents, stock))
    c.execute("INSERT INTO app_settings(name,value) VALUES('catalog_demo_v1','seeded')")

def initialize():
    with session() as c:
        c.executescript((ROOT/'schema.sql').read_text())
        seed_catalog(c)
        if not c.execute('SELECT 1 FROM users').fetchone():
            password = os.environ.get('PETSHOP_ADMIN_PASSWORD') or 'pet123'
            c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)', ('Administrador','admin@gmail.com',password_hash(password),'admin'))
            print('Acesso inicial: admin@gmail.com | Senha:',password,flush=True)
