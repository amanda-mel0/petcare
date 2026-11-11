import hashlib
import hmac
import json
import os
import sqlite3
import time
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import ROOT
from domain import ValidationError
from payments import webhook


class StripeWebhookTests(unittest.TestCase):
    def setUp(self):
        self.old_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
        os.environ['STRIPE_WEBHOOK_SECRET'] = 'whsec_unit_test_secret'
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        self.db.execute("INSERT INTO tutors VALUES(1,'Tutor Teste','11999999999','')")
        self.db.execute("INSERT INTO orders(id,tutor_id,description,total_cents,status,created) VALUES(1,1,'Banho',5000,'Pendente','2026-11-10T12:00:00')")
        self.db.execute("INSERT INTO stripe_payments(order_id,session_id,amount_cents,status) VALUES(1,'cs_test_123',5000,'pending')")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        if self.old_secret is None:
            os.environ.pop('STRIPE_WEBHOOK_SECRET', None)
        else:
            os.environ['STRIPE_WEBHOOK_SECRET'] = self.old_secret

    def payload(self, event='checkout.session.completed', **overrides):
        session = {
            'id': 'cs_test_123',
            'payment_status': 'paid',
            'currency': 'brl',
            'amount_total': 5000,
            'client_reference_id': '1',
            'payment_intent': 'pi_test_123',
        }
        session.update(overrides)
        return json.dumps({'type': event, 'data': {'object': session}}, separators=(',', ':')).encode()

    def signed(self, payload):
        stamp = str(int(time.time()))
        value = hmac.new(os.environ['STRIPE_WEBHOOK_SECRET'].encode(), stamp.encode() + b'.' + payload,
                         hashlib.sha256).hexdigest()
        return f't={stamp},v1={value}'

    def test_completed_event_confirms_matching_order(self):
        body = self.payload()
        webhook(self.db, body, self.signed(body))
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0], 'Pago')
        self.assertEqual(self.db.execute('SELECT status,payment_intent FROM stripe_payments WHERE order_id=1').fetchone()[:],
                         ('paid', 'pi_test_123'))

    def test_async_pix_success_confirms_order(self):
        body = self.payload(event='checkout.session.async_payment_succeeded')
        webhook(self.db, body, self.signed(body))
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0], 'Pago')

    def test_bad_signature_is_rejected(self):
        with self.assertRaises(ValidationError):
            webhook(self.db, self.payload(), 't=1,v1=invalid')
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0], 'Pendente')

    def test_signature_rotation_accepts_any_matching_v1(self):
        body=self.payload()
        valid=self.signed(body)
        stamp,signature=valid.split(',')
        webhook(self.db,body,stamp+',v1=older-invalid-signature,'+signature)
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0],'Pago')

    def test_stale_signature_is_rejected(self):
        body=self.payload()
        stamp=str(int(time.time())-301)
        value=hmac.new(os.environ['STRIPE_WEBHOOK_SECRET'].encode(),stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
        with self.assertRaises(ValidationError): webhook(self.db,body,f't={stamp},v1={value}')

    def test_unpaid_and_irrelevant_events_do_not_confirm(self):
        pending=self.payload(payment_status='unpaid')
        webhook(self.db,pending,self.signed(pending))
        unrelated=self.payload(event='checkout.session.expired')
        webhook(self.db,unrelated,self.signed(unrelated))
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0],'Pendente')

    def test_mismatched_amount_is_rejected(self):
        body = self.payload(amount_total=1)
        with self.assertRaises(ValidationError):
            webhook(self.db, body, self.signed(body))
        self.assertEqual(self.db.execute('SELECT status FROM orders WHERE id=1').fetchone()[0], 'Pendente')

    def test_mismatched_currency_reference_and_unknown_session_are_rejected(self):
        for overrides in ({'currency':'usd'},{'client_reference_id':'99'},{'id':'cs_test_unknown'}):
            body=self.payload(**overrides)
            with self.subTest(overrides=overrides),self.assertRaises(ValidationError): webhook(self.db,body,self.signed(body))


if __name__ == '__main__':
    unittest.main()
