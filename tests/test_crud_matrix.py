"""Edit/delete and history-preservation checks for every CRUD module."""
import sqlite3
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crud import delete, tutor_for_pet, update
from database import ROOT, password_hash
from domain import ValidationError, action, create


class CrudMatrixTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
        self.db.execute("INSERT INTO users VALUES(1,'Admin','admin@example.test','hash','admin')")
        self.db.execute("INSERT INTO users VALUES(2,'Staff','staff@example.test','hash','atendente')")
        self.db.execute("INSERT INTO users VALUES(3,'Admin 2','admin2@example.test','hash','admin')")
        self.db.execute("INSERT INTO tutors VALUES(1,'Tutor','11999999999','')")
        self.db.execute("INSERT INTO pets VALUES(1,'Luna',1,'Gato','SRD','Pequeno','2020-01-01',4,'')")
        self.db.execute("INSERT INTO professionals VALUES(1,'Dra. Ana','Veterinário','BA-12345','Clínica','08:00','18:00','0,1,2,3,4,5,6',1)")
        self.db.execute("INSERT INTO professionals VALUES(2,'Equipe Banho','Petshop','','Banho e tosa','08:00','18:00','0,1,2,3,4,5,6',1)")
        self.db.execute("INSERT INTO services VALUES(1,'Consulta','Clínica','Avaliação',12000,60,1)")
        self.db.execute("INSERT INTO services VALUES(2,'Banho','Petshop','Banho completo',8000,60,2)")
        self.db.execute("INSERT INTO products VALUES(1,'Ração','Alimentação',5000,10)")
        self.db.execute("INSERT INTO products VALUES(2,'Brinquedo','Brinquedos',2000,5)")
        self.db.commit()
        self.admin={'id':1,'role':'admin'}
        self.attendant={'id':2,'role':'atendente'}
        self.start=(datetime.now()+timedelta(days=2)).replace(hour=10,minute=0,second=0,microsecond=0)

    def tearDown(self):
        self.db.close()

    def appointment(self, service='1'):
        return create(self.db,'appointments',{'pet_id':'1','service_id':service,'start':self.start.strftime('%Y-%m-%dT%H:%M')},self.admin)

    def test_tutor_edit_and_unlinked_delete(self):
        update(self.db,'tutors',1,{'name':'Tutor atualizado','phone':'(11) 98888-7777','email':'novo@example.test'},self.admin)
        row=self.db.execute('SELECT * FROM tutors WHERE id=1').fetchone()
        self.assertEqual((row['name'],row['phone'],row['email']),('Tutor atualizado','11988887777','novo@example.test'))
        ident=create(self.db,'tutors',{'name':'Temporário','phone':'11988887776','email':''},self.admin)
        delete(self.db,'tutors',ident,self.admin)
        self.assertIsNone(self.db.execute('SELECT 1 FROM tutors WHERE id=?',(ident,)).fetchone())

    def test_pet_edit_inline_updates_shared_tutor(self):
        data={'tutor_id':'1','tutor_name':'Tutor atualizado','tutor_phone':'11911112222','tutor_email':'tutor@example.test',
              'name':'Luna II','species':'Gato','breed':'SRD','size':'Médio','birth_date':'2021-01-01','weight':'4.5','allergies':'Frango'}
        update(self.db,'pets',1,data,self.admin)
        pet=self.db.execute('SELECT * FROM pets WHERE id=1').fetchone()
        tutor=self.db.execute('SELECT * FROM tutors WHERE id=1').fetchone()
        self.assertEqual((pet['name'],pet['weight'],pet['allergies']),('Luna II',4.5,'Frango'))
        self.assertEqual((tutor['name'],tutor['phone']),('Tutor atualizado','11911112222'))

    def test_professional_edit_and_linked_kind_change_block(self):
        update(self.db,'professionals',2,{'name':'Equipe Banho II','kind':'Petshop','crmv':'','specialty':'Tosa','start_time':'09:00','end_time':'17:00','weekdays':'1,2,3','active':'0'},self.admin)
        self.assertEqual(self.db.execute('SELECT active,start_time FROM professionals WHERE id=2').fetchone()[:],(0,'09:00'))
        with self.assertRaises(ValidationError):
            update(self.db,'professionals',1,{'name':'Dra. Ana','kind':'Petshop','crmv':'','specialty':'Clínica','start_time':'08:00','end_time':'18:00','weekdays':'0,1,2,3,4,5,6','active':'1'},self.admin)
        with self.assertRaises(ValidationError): update(self.db,'professionals',2,{'name':'x'},self.attendant)

    def test_service_edit_and_category_change_with_appointments_block(self):
        update(self.db,'services',2,{'name':'Banho premium','category':'Petshop','description':'Banho e hidratação','price':'95.00','duration':'75','professional_id':'2'},self.admin)
        self.assertEqual(self.db.execute('SELECT price_cents,duration FROM services WHERE id=2').fetchone()[:],(9500,75))
        self.appointment('2')
        with self.assertRaises(ValidationError):
            update(self.db,'services',2,{'name':'Banho premium','category':'Clínica','description':'Banho','price':'95.00','duration':'75','professional_id':'1'},self.admin)

    def test_product_edit_delete_and_history_reference(self):
        update(self.db,'products',1,{'name':'Ração nova','category':'Alimentação','price':'60.00','stock':'12'},self.admin)
        self.assertEqual(self.db.execute('SELECT name,price_cents,stock FROM products WHERE id=1').fetchone()[:],('Ração nova',6000,12))
        sale=create(self.db,'orders',{'tutor_id':'1','product_id':'1','quantity':'1','status':'Pendente'},self.admin)
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db: delete(self.db,'products',1,self.admin)
        with self.db: delete(self.db,'orders',sale,self.admin)
        delete(self.db,'products',1,self.admin)
        self.assertIsNone(self.db.execute('SELECT 1 FROM products WHERE id=1').fetchone())

    def test_stock_movement_edit_and_delete_reconcile_inventory(self):
        movement=create(self.db,'stock_movements',{'product_id':'1','quantity':'3','price':'30.00'},self.admin)
        self.db.commit()
        before=self.db.execute('SELECT created FROM stock_movements WHERE id=?',(movement,)).fetchone()[0]
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],13)
        update(self.db,'stock_movements',movement,{'product_id':'2','quantity':'2','price':'25.00'},self.admin)
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],10)
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=2').fetchone()[0],7)
        self.assertEqual(self.db.execute('SELECT created FROM stock_movements WHERE id=?',(movement,)).fetchone()[0],before)
        delete(self.db,'stock_movements',movement,self.admin)
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=2').fetchone()[0],5)

    def test_stock_movement_reversal_cannot_make_stock_negative(self):
        movement=create(self.db,'stock_movements',{'product_id':'1','quantity':'3','price':'30.00'},self.admin)
        self.db.commit()
        create(self.db,'orders',{'tutor_id':'1','product_id':'1','quantity':'12','status':'Pago'},self.admin)
        self.db.commit()
        with self.assertRaises(ValidationError): delete(self.db,'stock_movements',movement,self.admin)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM stock_movements WHERE id=?',(movement,)).fetchone())

    def test_record_edit_preserves_original_author_and_delete(self):
        ident=create(self.db,'records',{'pet_id':'1','professional_id':'1','kind':'Consulta','date':date.today().isoformat(),'notes':'Inicial'},self.admin)
        self.db.commit()
        update(self.db,'records',ident,{'pet_id':'1','professional_id':'1','kind':'Vacina','date':date.today().isoformat(),'notes':'Atualizado'},self.attendant)
        row=self.db.execute('SELECT kind,notes,author_id FROM records WHERE id=?',(ident,)).fetchone()
        self.assertEqual(tuple(row),('Vacina','Atualizado',1))
        delete(self.db,'records',ident,self.admin)
        self.assertIsNone(self.db.execute('SELECT 1 FROM records WHERE id=?',(ident,)).fetchone())

    def test_appointment_edit_syncs_linked_service_order_and_delete_reopens(self):
        appointment=self.appointment()
        action(self.db,'appointments',appointment,{'status':'Concluído'})
        self.db.commit()
        order=self.db.execute('SELECT id FROM orders WHERE appointment_id=?',(appointment,)).fetchone()[0]
        changed=self.start+timedelta(hours=2)
        update(self.db,'appointments',appointment,{'pet_id':'1','service_id':'2','start':changed.strftime('%Y-%m-%dT%H:%M')},self.admin)
        row=self.db.execute('SELECT start,status FROM appointments WHERE id=?',(appointment,)).fetchone()
        synced=self.db.execute('SELECT description,total_cents FROM orders WHERE id=?',(order,)).fetchone()
        self.assertEqual((row['start'],row['status']),(changed.strftime('%Y-%m-%dT%H:%M'),'Concluído'))
        self.assertEqual(tuple(synced),('Banho',8000))
        delete(self.db,'appointments',appointment,self.admin)
        self.assertEqual(self.db.execute('SELECT count(*) FROM orders WHERE appointment_id=?',(appointment,)).fetchone()[0],0)

    def test_user_edit_password_and_admin_protections(self):
        update(self.db,'users',2,{'name':'Atendente nova','email':'STAFF@example.test','role':'atendente','password':'NewPassword_2026!'},self.admin)
        row=self.db.execute('SELECT name,email,password FROM users WHERE id=2').fetchone()
        self.assertEqual((row['name'],row['email']),('Atendente nova','staff@example.test'))
        self.assertNotEqual(row['password'],'NewPassword_2026!')
        with self.assertRaises(ValidationError): update(self.db,'users',1,{'name':'Admin','email':'admin@example.test','role':'atendente'},self.admin)
        with self.assertRaises(ValidationError): delete(self.db,'users',1,self.admin)
        delete(self.db,'users',3,self.admin)
        with self.assertRaises(ValidationError): delete(self.db,'users',1,{'id':3,'role':'admin'})


if __name__=='__main__':
    unittest.main()
