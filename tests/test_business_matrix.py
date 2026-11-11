"""Validation and edge-case matrix for every business entity."""
import sqlite3
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import ROOT
from domain import ValidationError, action, create, integer, money, text


class BusinessMatrixTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
        self.db.execute("INSERT INTO users VALUES(1,'Admin','admin@example.test','hash','admin')")
        self.db.execute("INSERT INTO tutors VALUES(1,'Tutor','11999999999','')")
        self.db.execute("INSERT INTO pets VALUES(1,'Luna',1,'Gato','SRD','Pequeno','2020-01-01',4,'')")
        self.db.execute("INSERT INTO professionals VALUES(1,'Dra. Ana','Veterinário','BA-12345','Clínica','08:00','18:00','0,1,2,3,4,5,6',1)")
        self.db.execute("INSERT INTO services VALUES(1,'Consulta','Clínica','Avaliação',12000,60,1)")
        self.db.execute("INSERT INTO products VALUES(1,'Ração','Alimentação',5000,3)")
        self.db.commit()
        self.user={'id':1,'role':'admin'}
        self.future=(datetime.now()+timedelta(days=2)).replace(hour=10,minute=0,second=0,microsecond=0)

    def tearDown(self):
        self.db.close()

    def test_text_integer_and_money_boundaries(self):
        self.assertEqual(text({'x':'  Ok  '},'x'),'Ok')
        for value in ('', '   ', 'x'*5001):
            with self.subTest(value=value[:10]), self.assertRaises(ValidationError): text({'x':value},'x')
        self.assertEqual(integer({'q':'0'},'q',0),0)
        self.assertEqual(integer({'q':'1000000'},'q'),1000000)
        for value in ('', '0', '-1', '1.5', '01', '1000001', '1e2'):
            with self.subTest(integer=value), self.assertRaises(ValidationError): integer({'q':value},'q')
        self.assertEqual(money({'price':'12,34'}),1234)
        self.assertEqual(money({'price':'0'}),0)
        for value in ('-0.01','1.001','10000000.01','NaN','Infinity','texto'):
            with self.subTest(money=value), self.assertRaises(ValidationError): money({'price':value})

    def test_tutor_phone_and_email_validation(self):
        ident=create(self.db,'tutors',{'name':'Tutor válido','phone':'(11) 98888-7777','email':'a@b.com'},self.user)
        self.assertEqual(self.db.execute('SELECT phone FROM tutors WHERE id=?',(ident,)).fetchone()[0],'11988887777')
        for phone,email in [('123',''),('11999999999','invalido'),('11999999999','x@y')]:
            with self.subTest(phone=phone,email=email),self.assertRaises(ValidationError):
                create(self.db,'tutors',{'name':'Teste','phone':phone,'email':email},self.user)

    def test_pet_dates_weight_size_and_tutor_reference(self):
        base={'name':'Pet','tutor_id':'1','species':'Cão','breed':'SRD','size':'Médio','birth_date':'2020-01-01','weight':'10'}
        for changes in ({'birth_date':(date.today()+timedelta(days=1)).isoformat()},
                        {'birth_date':'2025-02-30'},{'weight':'0'},{'weight':'1001'},
                        {'weight':'texto'},{'size':'Gigante'},{'tutor_id':'999'}):
            data={**base,**changes}
            with self.subTest(changes=changes),self.assertRaises((ValidationError,sqlite3.IntegrityError)):
                with self.db: create(self.db,'pets',data,self.user)

    def test_professional_crmv_hours_weekdays_and_active(self):
        base={'name':'Profissional','kind':'Veterinário','crmv':'SP-12345','specialty':'Clínica','start_time':'08:00','end_time':'18:00','weekdays':'0,1,2,3,4','active':'1'}
        cases=({'crmv':'12345'},{'kind':'Outro'},{'end_time':'08:00'},{'start_time':'25:00'},
               {'weekdays':'0,7'},{'weekdays':'1,,2'},{'active':'2'})
        for changes in cases:
            with self.subTest(changes=changes),self.assertRaises(ValidationError): create(self.db,'professionals',{**base,**changes},self.user)
        groomer={**base,'kind':'Petshop','crmv':'','name':'Tosa'}
        self.assertGreater(create(self.db,'professionals',groomer,self.user),1)

    def test_service_requires_matching_professional_and_safe_price_duration(self):
        base={'name':'Banho','category':'Clínica','description':'Completo','price':'50.00','duration':'60','professional_id':'1'}
        invalid=({'category':'Petshop'},{'professional_id':'999'},{'duration':'4'},
                 {'duration':'721'},{'price':'-1'},{'price':'1.999'})
        for changes in invalid:
            with self.subTest(changes=changes),self.assertRaises(ValidationError): create(self.db,'services',{**base,**changes},self.user)
        groomer_id=create(self.db,'professionals',{'name':'Tosa','kind':'Petshop','crmv':'','specialty':'Banho','start_time':'08:00','end_time':'18:00','weekdays':'0,1,2,3,4,5,6','active':'1'},self.user)
        data={**base,'category':'Petshop','professional_id':str(groomer_id)}
        self.assertGreater(create(self.db,'services',data,self.user),1)

    def test_products_and_stock_movements_validate_and_rollback(self):
        base={'name':'Brinquedo','category':'Brinquedos','price':'29.90','stock':'0'}
        product=create(self.db,'products',base,self.user)
        self.db.commit()
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=?',(product,)).fetchone()[0],0)
        for changes in ({'name':''},{'price':'-1'},{'price':'1.009'},{'stock':'-1'}, {'stock':'1.2'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError): create(self.db,'products',{**base,**changes},self.user)
        for movement in ({'product_id':'999','quantity':'2','price':'1.00'},
                         {'product_id':str(product),'quantity':'0','price':'1.00'},
                         {'product_id':str(product),'quantity':'2','price':'-1'}):
            with self.subTest(movement=movement),self.assertRaises(ValidationError):
                with self.db: create(self.db,'stock_movements',movement,self.user)
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=?',(product,)).fetchone()[0],0)
        movement_id=create(self.db,'stock_movements',{'product_id':str(product),'quantity':'2','price':'12.50'},self.user)
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=?',(product,)).fetchone()[0],2)
        self.assertGreater(movement_id,0)

    def test_records_reject_future_and_non_veterinarian(self):
        base={'pet_id':'1','professional_id':'1','kind':'Vacina','date':date.today().isoformat(),'notes':'Dose aplicada'}
        self.assertGreater(create(self.db,'records',base,self.user),0)
        for changes in ({'date':(date.today()+timedelta(days=1)).isoformat()},
                        {'date':'2025-02-30'},{'kind':'Cirurgia'},{'professional_id':'999'},
                        {'pet_id':'999'}):
            with self.subTest(changes=changes),self.assertRaises((ValidationError,sqlite3.IntegrityError)):
                with self.db: create(self.db,'records',{**base,**changes},self.user)
        self.db.execute("UPDATE professionals SET kind='Petshop' WHERE id=1")
        with self.assertRaises(ValidationError): create(self.db,'records',base,self.user)

    def test_sales_validate_every_reference_and_keep_stock_atomic(self):
        base={'tutor_id':'1','product_id':'1','quantity':'1','status':'Pendente'}
        for changes in ({'product_id':'999'},{'tutor_id':'999'},{'quantity':'0'},
                        {'quantity':'4'},{'status':'invalid'}):
            with self.subTest(changes=changes),self.assertRaises((ValidationError,sqlite3.IntegrityError)):
                with self.db: create(self.db,'orders',{**base,**changes},self.user)
        self.assertEqual(self.db.execute('SELECT stock FROM products WHERE id=1').fetchone()[0],3)

    def test_schedule_rejects_bad_dates_availability_and_conflicts(self):
        future_day=self.future.date().isoformat()
        cases=({'service_id':'999','start':future_day+'T10:00'},
               {'service_id':'1','start':'invalid'},
               {'service_id':'1','start':(datetime.now()-timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')},
               {'service_id':'1','start':future_day+'T17:30'})
        for data in cases:
            with self.subTest(data=data),self.assertRaises(ValidationError): create(self.db,'appointments',{'pet_id':'1',**data},self.user)
        # Restrict this professional to a different weekday, then verify availability enforcement.
        unavailable=str((self.future.weekday()+1)%7)
        self.db.execute('UPDATE professionals SET weekdays=? WHERE id=1',(unavailable,))
        with self.assertRaises(ValidationError): create(self.db,'appointments',{'pet_id':'1','service_id':'1','start':future_day+'T10:00'},self.user)
        self.db.execute("UPDATE professionals SET weekdays='0,1,2,3,4,5,6',active=1 WHERE id=1")
        appointment=create(self.db,'appointments',{'pet_id':'1','service_id':'1','start':future_day+'T10:00'},self.user)
        with self.assertRaises(ValidationError): create(self.db,'appointments',{'pet_id':'1','service_id':'1','start':future_day+'T10:30'},self.user)
        self.assertGreater(appointment,0)

    def test_actions_enforce_allowed_transitions(self):
        with self.assertRaises(ValidationError): action(self.db,'orders',999,{})
        with self.assertRaises(ValidationError): action(self.db,'appointments',999,{'status':'Concluído'})
        with self.assertRaises(ValidationError): action(self.db,'tutors',1,{})
        action(self.db,'professionals',1,{'active':'0'})
        self.assertEqual(self.db.execute('SELECT active FROM professionals WHERE id=1').fetchone()[0],0)
        action(self.db,'professionals',1,{'active':'1'})
        self.assertEqual(self.db.execute('SELECT active FROM professionals WHERE id=1').fetchone()[0],1)


if __name__=='__main__':
    unittest.main()
