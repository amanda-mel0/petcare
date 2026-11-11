import sqlite3
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import CATALOG, seed_catalog
from database import ROOT


class CatalogSeedTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))

    def tearDown(self):
        self.db.close()

    def test_seeds_realistic_petshop_catalog_once(self):
        seed_catalog(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM products').fetchone()[0], len(CATALOG))
        self.assertGreaterEqual(len({item[1] for item in CATALOG}), 6)
        seed_catalog(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM products').fetchone()[0], len(CATALOG))

    def test_preserves_existing_product_and_stock(self):
        name, category, _, _ = CATALOG[0]
        self.db.execute('INSERT INTO products(name,category,price_cents,stock) VALUES(?,?,?,?)',
                        (name, category, 12345, 7))
        seed_catalog(self.db)
        row = self.db.execute('SELECT price_cents,stock FROM products WHERE name=? AND category=?',
                              (name, category)).fetchone()
        self.assertEqual(row, (12345, 7))
        self.assertEqual(self.db.execute('SELECT count(*) FROM products').fetchone()[0], len(CATALOG))


if __name__ == '__main__':
    unittest.main()
