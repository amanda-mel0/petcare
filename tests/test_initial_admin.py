import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database


class InitialAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='petcare-admin-')
        self.old_db=database.DB
        self.old_password=os.environ.pop('PETSHOP_ADMIN_PASSWORD',None)
        database.DB=str(Path(self.temp.name)/'fresh.sqlite')

    def tearDown(self):
        database.DB=self.old_db
        if self.old_password is not None: os.environ['PETSHOP_ADMIN_PASSWORD']=self.old_password
        self.temp.cleanup()

    def test_fresh_install_has_requested_easy_login_and_keeps_it_on_restart(self):
        with contextlib.redirect_stdout(io.StringIO()): database.initialize()
        with database.session() as c:
            row=c.execute('SELECT email,password,role FROM users').fetchone()
            self.assertEqual((row['email'],row['role']),('admin@gmail.com','admin'))
            salt=row['password'].split(':',1)[0]
            self.assertEqual(database.password_hash('pet123',salt),row['password'])
        with contextlib.redirect_stdout(io.StringIO()): database.initialize()
        with database.session() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT email FROM users').fetchone()[0],'admin@gmail.com')

    def test_explicit_initial_password_override_still_works(self):
        os.environ['PETSHOP_ADMIN_PASSWORD']='LongerInitialPassword_2026!'
        with contextlib.redirect_stdout(io.StringIO()): database.initialize()
        with database.session() as c:
            row=c.execute('SELECT password FROM users WHERE email=?',('admin@gmail.com',)).fetchone()
            salt=row['password'].split(':',1)[0]
            self.assertEqual(database.password_hash(os.environ['PETSHOP_ADMIN_PASSWORD'],salt),row['password'])


if __name__=='__main__':
    unittest.main()
