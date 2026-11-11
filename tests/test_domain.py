import unittest, tempfile, sqlite3, sys
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from domain import create,action,ValidationError
from database import ROOT
class BusinessRules(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript((ROOT/'schema.sql').read_text())
        self.c.execute("INSERT INTO users VALUES(1,'Admin','admin@example.com','hash','admin')")
        self.c.execute("INSERT INTO tutors VALUES(1,'Yuri','77999999999','')")
        self.c.execute("INSERT INTO pets VALUES(1,'Luna',1,'Gato','SRD','Pequeno','2020-01-01',4,'')")
        self.c.execute("INSERT INTO professionals VALUES(1,'Ana','Veterinário','BA-12345','Clínica','08:00','18:00','0,1,2,3,4,5,6',1)")
        self.c.execute("INSERT INTO services VALUES(1,'Consulta','Clínica','Avaliação',12000,60,1)")
        self.c.execute("INSERT INTO products VALUES(1,'Ração','Ração',5000,3)")
        self.c.commit();self.user={'id':1}
        self.day=(datetime.now()+timedelta(days=2)).strftime('%Y-%m-%d')
    def tearDown(self):self.c.close()
    def schedule(self,time='09:00'):
        return create(self.c,'appointments',dict(pet_id='1',service_id='1',start=self.day+'T'+time),self.user)
    def test_overlap_and_adjacent(self):
        self.schedule()
        with self.assertRaises(ValidationError):self.schedule('09:30')
        self.schedule('10:00')
    def test_unavailable_and_out_of_hours(self):
        with self.assertRaises(ValidationError):self.schedule('17:30')
        self.c.execute('UPDATE professionals SET active=0')
        with self.assertRaises(ValidationError):self.schedule()
    def test_cancel_releases_slot(self):
        ident=self.schedule();action(self.c,'appointments',ident,{'status':'Cancelado'});self.schedule()
    def test_finish_creates_exactly_one_order(self):
        ident=self.schedule();action(self.c,'appointments',ident,{'status':'Concluído'})
        with self.assertRaises(ValidationError):action(self.c,'appointments',ident,{'status':'Concluído'})
        self.assertEqual(self.c.execute('SELECT total_cents FROM orders').fetchone()[0],12000)
    def test_insufficient_stock(self):
        with self.assertRaises(ValidationError):create(self.c,'orders',dict(product_id='1',quantity='4',tutor_id='1',status='Pago'),self.user)
        self.assertEqual(self.c.execute('SELECT stock FROM products').fetchone()[0],3)
    def test_sale_and_payment(self):
        ident=create(self.c,'orders',dict(product_id='1',quantity='2',tutor_id='1',status='Pendente'),self.user)
        action(self.c,'orders',ident,{})
        self.assertEqual(self.c.execute('SELECT stock FROM products').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT status,total_cents FROM orders').fetchone()[:],('Pago',10000))
    def test_invalid_order_rolls_back_stock(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.c:create(self.c,'orders',dict(product_id='1',quantity='2',tutor_id='999',status='Pago'),self.user)
        self.assertEqual(self.c.execute('SELECT stock FROM products').fetchone()[0],3)
    def test_invalid_phone(self):
        with self.assertRaises(ValidationError):create(self.c,'tutors',{'name':'Teste','phone':'123'},self.user)
    def test_vaccine_requires_vet(self):
        self.c.execute("UPDATE professionals SET kind='Petshop'")
        with self.assertRaises(ValidationError):create(self.c,'records',dict(pet_id='1',professional_id='1',kind='Vacina',date='2026-01-01',notes='Teste'),self.user)
if __name__=='__main__':unittest.main()
