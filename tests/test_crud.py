from test_domain import BusinessRules
from crud import update,delete,tutor_for_pet
from domain import create, ValidationError
import sqlite3
class CrudRules(BusinessRules):
 def setUp(self):
  super().setUp();self.user={'id':1,'role':'admin'}
 def test_inline_tutor_and_pet(self):
  with self.c:
   d=dict(tutor_name='Novo',tutor_phone='77988887777',tutor_email='',name='Bob',species='Cão',breed='SRD',size='Médio',birth_date='2020-01-01',weight='10')
   d['tutor_id']=str(tutor_for_pet(self.c,d,self.user));pid=create(self.c,'pets',d,self.user)
  self.assertEqual(self.c.execute('SELECT tutor_id FROM pets WHERE id=?',(pid,)).fetchone()[0],2)
 def test_edit_and_delete_sale_reverses_stock(self):
  with self.c:ident=create(self.c,'orders',dict(product_id='1',quantity='2',tutor_id='1',status='Pago'),self.user)
  with self.c:update(self.c,'orders',ident,dict(product_id='1',quantity='1',tutor_id='1',status='Pendente'),self.user)
  self.assertEqual(self.c.execute('SELECT stock FROM products').fetchone()[0],2)
  with self.c:delete(self.c,'orders',ident,self.user)
  self.assertEqual(self.c.execute('SELECT stock FROM products').fetchone()[0],3)
 def test_invalid_edit_rolls_back(self):
  with self.c:ident=create(self.c,'orders',dict(product_id='1',quantity='2',tutor_id='1',status='Pago'),self.user)
  with self.assertRaises(ValidationError):
   with self.c:update(self.c,'orders',ident,dict(product_id='1',quantity='9',tutor_id='1',status='Pago'),self.user)
  self.assertEqual(self.c.execute('SELECT stock FROM products').fetchone()[0],1)
  self.assertEqual(self.c.execute('SELECT quantity FROM orders').fetchone()[0],2)
 def test_master_delete_blocks_history(self):
  with self.assertRaises(sqlite3.IntegrityError):
   with self.c:delete(self.c,'tutors',1,self.user)
 def test_appointment_edit_ignores_own_interval(self):
  ident=self.schedule();self.c.commit()
  with self.c:update(self.c,'appointments',ident,dict(pet_id='1',service_id='1',start=self.day+'T09:30'),self.user)
  self.assertTrue(self.c.execute('SELECT start FROM appointments WHERE id=?',(ident,)).fetchone()[0].endswith('09:30'))
 def test_appointment_delete_removes_os(self):
  from domain import action
  ident=self.schedule();action(self.c,'appointments',ident,dict(status='Concluído'));self.c.commit()
  with self.c:delete(self.c,'appointments',ident,self.user)
  self.assertEqual(self.c.execute('SELECT count(*) FROM orders').fetchone()[0],0)
 def test_cannot_delete_self_admin(self):
  with self.assertRaises(ValidationError):delete(self.c,'users',1,self.user)
