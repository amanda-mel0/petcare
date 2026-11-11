"""Stripe Checkout creation and retry rules, with every network call mocked."""
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import ROOT
from domain import ValidationError
from payments import api, checkout, guard


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
        self.db.execute("INSERT INTO tutors VALUES(1,'Tutor','11999999999','')")
        self.db.execute("INSERT INTO orders(id,tutor_id,description,total_cents,status,created) VALUES(1,1,'Banho e tosa',8500,'Pendente','2026-11-10T12:00:00')")
        self.db.commit()
        self.original={key:os.environ.get(key) for key in ('STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','APP_BASE_URL')}
        os.environ['STRIPE_SECRET_KEY']='sk_test_unit_test'
        os.environ['STRIPE_WEBHOOK_SECRET']='whsec_unit_test'
        os.environ['APP_BASE_URL']='http://127.0.0.1:5000'

    def tearDown(self):
        self.db.close()
        for key,value in self.original.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value

    def test_checkout_creates_card_and_pix_session_with_fixed_order_amount(self):
        response={'id':'cs_test_new','url':'https://checkout.stripe.com/c/pay/cs_test_new'}
        with patch('payments.api',return_value=response) as request:
            result=checkout(self.db,1)
        self.assertEqual(result,{'url':response['url']})
        self.assertEqual(request.call_count,1)
        args=request.call_args.args
        self.assertEqual(args[:2],('POST','checkout/sessions'))
        data=args[2]
        self.assertEqual(data['line_items[0][price_data][unit_amount]'],'8500')
        self.assertEqual(data['allowed_payment_method_types[0]'],'card')
        self.assertEqual(data['allowed_payment_method_types[1]'],'pix')
        self.assertEqual(data['client_reference_id'],'1')
        self.assertTrue(args[3].startswith('petcare-v3-'))
        self.assertEqual(self.db.execute('SELECT session_id,amount_cents FROM stripe_payments WHERE order_id=1').fetchone()[:],('cs_test_new',8500))

    def test_existing_open_pix_checkout_is_reused(self):
        self.db.execute("INSERT INTO stripe_payments(order_id,session_id,amount_cents) VALUES(1,'cs_test_open',8500)")
        with patch('payments.api',return_value={'status':'open','payment_method_types':['card','pix'],'url':'https://checkout.stripe.com/c/pay/cs_test_open'}) as request:
            result=checkout(self.db,1)
        self.assertEqual(result['url'],'https://checkout.stripe.com/c/pay/cs_test_open')
        request.assert_called_once_with('GET','checkout/sessions/cs_test_open')

    def test_open_checkout_without_pix_is_expired_before_replacement(self):
        self.db.execute("INSERT INTO stripe_payments(order_id,session_id,amount_cents) VALUES(1,'cs_test_card',8500)")
        created={'id':'cs_test_replacement','url':'https://checkout.stripe.com/c/pay/cs_test_replacement'}
        with patch('payments.api',side_effect=[{'status':'open','payment_method_types':['card'],'url':'old'}, {}, created]) as request:
            result=checkout(self.db,1)
        self.assertEqual(result,{'url':created['url']})
        self.assertEqual([item.args[:2] for item in request.call_args_list], [
            ('GET','checkout/sessions/cs_test_card'),
            ('POST','checkout/sessions/cs_test_card/expire'),
            ('POST','checkout/sessions'),
        ])
        self.assertEqual(self.db.execute('SELECT session_id FROM stripe_payments WHERE order_id=1').fetchone()[0],'cs_test_replacement')

    def test_complete_unpaid_or_paid_checkout_is_not_recreated(self):
        self.db.execute("INSERT INTO stripe_payments(order_id,session_id,amount_cents) VALUES(1,'cs_test_old',8500)")
        for response in ({'status':'complete','payment_status':'unpaid'}, {'status':'complete','payment_status':'paid'}):
            with patch('payments.api',return_value=response) as request, self.assertRaises(ValidationError): checkout(self.db,1)
            request.assert_called_once_with('GET','checkout/sessions/cs_test_old')

    def test_invalid_order_amount_or_settings_fail_before_network(self):
        for ident in (999,):
            with patch('payments.api') as request,self.assertRaises(ValidationError): checkout(self.db,ident)
            request.assert_not_called()
        self.db.execute("UPDATE orders SET total_cents=0 WHERE id=1")
        with patch('payments.api') as request,self.assertRaises(ValidationError): checkout(self.db,1)
        request.assert_not_called()
        self.db.execute("UPDATE orders SET total_cents=8500,status='Pago' WHERE id=1")
        with patch('payments.api') as request,self.assertRaises(ValidationError): checkout(self.db,1)
        request.assert_not_called()
        self.db.execute("UPDATE orders SET status='Pendente' WHERE id=1")
        os.environ['APP_BASE_URL']='javascript:alert(1)'
        with patch('payments.api') as request,self.assertRaises(ValidationError): checkout(self.db,1)
        request.assert_not_called()

    def test_stripe_api_rejects_live_key_in_test_package(self):
        os.environ['STRIPE_SECRET_KEY']='sk_live_not_for_tests'
        with self.assertRaises(ValidationError): api('GET','checkout/sessions')

    def test_stripe_orders_cannot_be_manually_changed_or_deleted_while_pending(self):
        self.db.execute("INSERT INTO stripe_payments(order_id,session_id,amount_cents) VALUES(1,'cs_test_pending',8500)")
        self.db.execute("INSERT INTO pets VALUES(1,'Luna',1,'Gato','SRD','Pequeno','2020-01-01',4,'')")
        self.db.execute("INSERT INTO professionals VALUES(1,'Banho','Petshop','','Banho','08:00','18:00','0,1,2,3,4,5,6',1)")
        self.db.execute("INSERT INTO services VALUES(1,'Tosa','Petshop','Banho',8500,60,1)")
        self.db.execute("INSERT INTO appointments VALUES(1,1,1,1,'2026-11-12T10:00','2026-11-12T11:00',8500,'Agendado')")
        self.db.execute("INSERT INTO orders(id,tutor_id,appointment_id,description,total_cents,status,created) VALUES(2,1,1,'Tosa',8500,'Pendente','2026-11-10T12:00:00')")
        self.db.execute("INSERT INTO stripe_payments(order_id,session_id,amount_cents) VALUES(2,'cs_test_appointment',8500)")
        for entity,ident,operation in (('orders',1,'edit'),('orders',1,'delete'),('appointments',1,'delete')):
            with self.subTest(entity=entity,operation=operation),self.assertRaises(ValidationError): guard(self.db,entity,ident,operation)


if __name__=='__main__':
    unittest.main()
