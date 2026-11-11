"""End-to-end checks for the local HTTP routes using an isolated SQLite file."""
import http.cookiejar
import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import database


class QuietHandler(app.Handler):
    def log_message(self, fmt, *args):
        pass


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='petcare-api-')
        self.old_db = database.DB
        self.old_session = app.session
        self.old_sessions = app.SESSIONS.copy()
        database.DB = str(Path(self.temp.name) / 'test.sqlite')
        app.session = database.session
        app.SESSIONS.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            database.initialize()
        self.admin_password = 'pet123'
        self.attendant_password = 'ApiTestStaff_2026!'
        with database.session() as c:
            c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',
                      ('Atendente de Teste', 'staff@example.test',
                       database.password_hash(self.attendant_password), 'atendente'))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.server.daemon_threads = False
        self.server.block_on_close = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.admin = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.staff = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.login(self.admin, 'admin@gmail.com', self.admin_password)
        self.state = self.json_call(self.admin, 'GET', '/api/state')[1]
        self.csrf = self.state['csrf']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        app.session = self.old_session
        app.SESSIONS.clear()
        app.SESSIONS.update(self.old_sessions)
        database.DB = self.old_db
        self.temp.cleanup()

    def json_call(self, opener, method, path, data=None, csrf=None):
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-CSRF-Token'] = csrf
        body = None if method == 'GET' else json.dumps(data or {}).encode()
        request = Request(self.base + path, data=body, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        raw = response.read()
        try:
            result = json.loads(raw) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            result = raw
        return response.code, result, response.headers

    def login(self, opener, email, password):
        code, _, headers = self.json_call(opener, 'POST', '/api/login', {'email': email, 'password': password})
        self.assertEqual(code, 200)
        cookie = headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)

    def post(self, path, data):
        return self.json_call(self.admin, 'POST', path, data, self.csrf)

    def test_static_login_state_csrf_and_logout(self):
        self.assertEqual(self.json_call(self.admin, 'GET', '/') [0], 200)
        self.assertEqual(self.json_call(self.admin, 'GET', '/static/app.js')[0], 200)
        self.assertEqual(self.json_call(self.admin, 'GET', '/api/state')[0], 200)
        self.assertEqual(len(self.state['products']), 20)
        self.assertTrue(all('password' not in user for user in self.state['users']))
        self.assertEqual(self.json_call(self.admin, 'POST', '/api/tutors', {'name':'Bloqueado'})[0], 403)
        code, _, headers = self.json_call(self.admin, 'POST', '/api/logout', {}, self.csrf)
        self.assertEqual(code, 200)
        self.assertIn('Max-Age=0', headers.get('Set-Cookie', ''))
        self.assertEqual(self.json_call(self.admin, 'GET', '/api/state')[0], 401)

    def test_all_primary_create_and_action_routes(self):
        today = date.today()
        future = today + timedelta(days=2)
        self.assertEqual(self.post('/api/tutors', {'name':'Tutor API','phone':'11987654321','email':'tutor@example.test'})[0], 201)
        self.assertEqual(self.post('/api/pets', {
            'tutor_name':'Tutor Pet Inline','tutor_phone':'11987654322','tutor_email':'inline@example.test',
            'name':'Nina','species':'Cão','breed':'SRD','size':'Médio','birth_date':'2022-04-05',
            'weight':'12.5','allergies':'Nenhuma',
        })[0], 201)
        self.assertEqual(self.post('/api/professionals', {
            'name':'Banho API','kind':'Petshop','crmv':'','specialty':'Banho e tosa',
            'start_time':'08:00','end_time':'18:00','weekdays':'0,1,2,3,4,5,6','active':'1',
        })[0], 201)
        self.assertEqual(self.post('/api/professionals', {
            'name':'Dra. API','kind':'Veterinário','crmv':'SP-12345','specialty':'Clínica geral',
            'start_time':'08:00','end_time':'18:00','weekdays':'0,1,2,3,4,5,6','active':'1',
        })[0], 201)
        with database.session() as c:
            pet_id = c.execute("SELECT id FROM pets WHERE name='Nina'").fetchone()[0]
            tutor_id = c.execute("SELECT id FROM tutors WHERE email='tutor@example.test'").fetchone()[0]
            groomer_id = c.execute("SELECT id FROM professionals WHERE name='Banho API'").fetchone()[0]
            vet_id = c.execute("SELECT id FROM professionals WHERE name='Dra. API'").fetchone()[0]
        self.assertEqual(self.post('/api/services', {
            'name':'Banho completo','category':'Petshop','description':'Banho, secagem e escovação',
            'price':'85.00','duration':'60','professional_id':str(groomer_id),
        })[0], 201)
        self.assertEqual(self.post('/api/services', {
            'name':'Consulta geral','category':'Clínica','description':'Avaliação veterinária',
            'price':'120.00','duration':'45','professional_id':str(vet_id),
        })[0], 201)
        with database.session() as c:
            service_id = c.execute("SELECT id FROM services WHERE name='Banho completo'").fetchone()[0]
        self.assertEqual(self.post('/api/appointments', {
            'pet_id':str(pet_id),'service_id':str(service_id),
            'start':future.isoformat()+'T10:00',
        })[0], 201)
        self.assertEqual(self.post('/api/records', {
            'pet_id':str(pet_id),'professional_id':str(vet_id),'kind':'Consulta',
            'date':today.isoformat(),'notes':'Animal ativo e sem alterações.',
        })[0], 201)
        self.assertEqual(self.post('/api/products', {
            'name':'Produto API','category':'Acessórios','price':'10.50','stock':'2',
        })[0], 201)
        with database.session() as c:
            product_id = c.execute("SELECT id FROM products WHERE name='Produto API'").fetchone()[0]
        self.assertEqual(self.post('/api/stock_movements', {
            'product_id':str(product_id),'quantity':'3','price':'6.25',
        })[0], 201)
        self.assertEqual(self.post('/api/orders', {
            'tutor_id':str(tutor_id),'product_id':str(product_id),'quantity':'2','status':'Pendente',
        })[0], 201)
        with database.session() as c:
            order = c.execute("SELECT id,total_cents,status FROM orders WHERE product_id=?",(product_id,)).fetchone()
            self.assertEqual(tuple(order), (order['id'],2100,'Pendente'))
            self.assertEqual(c.execute('SELECT stock FROM products WHERE id=?',(product_id,)).fetchone()[0],3)
            appointment_id = c.execute('SELECT id FROM appointments').fetchone()[0]
        self.assertEqual(self.post(f'/api/appointments/{appointment_id}', {'status':'Concluído'})[0], 201)
        with database.session() as c:
            service_order = c.execute('SELECT id,total_cents FROM orders WHERE appointment_id=?',(appointment_id,)).fetchone()
        self.assertEqual(service_order['total_cents'],8500)
        self.assertEqual(self.post(f"/api/orders/{order['id']}", {})[0], 201)
        state = self.json_call(self.admin, 'GET', '/api/state')[1]
        self.assertEqual(next(o for o in state['orders'] if o['id']==order['id'])['status'], 'Pago')
        self.assertEqual(len(state['records']), 1)

    def test_attendant_cannot_manage_users_and_account_deletion_revokes_session(self):
        code, _, _ = self.post('/api/users', {
            'name':'Novo atendente','email':'novo@example.test',
            'password':'NewStaffPassword_2026!','role':'atendente',
        })
        self.assertEqual(code, 201)
        with database.session() as c:
            staff_id = c.execute("SELECT id FROM users WHERE email='staff@example.test'").fetchone()[0]
            new_id = c.execute("SELECT id FROM users WHERE email='novo@example.test'").fetchone()[0]
        self.login(self.staff, 'staff@example.test', self.attendant_password)
        staff_state = self.json_call(self.staff, 'GET', '/api/state')[1]
        self.assertNotIn('users', staff_state)
        self.assertEqual(self.json_call(self.staff, 'POST', '/api/users', {
            'name':'Negado','email':'denied@example.test','password':'LongPassword_123!','role':'admin'
        }, staff_state['csrf'])[0], 403)
        self.assertEqual(self.json_call(self.staff, 'POST', f'/api/users/{new_id}', {
            '_action':'edit','name':'Alterado','email':'novo@example.test','role':'atendente'
        }, staff_state['csrf'])[0], 403)
        self.assertEqual(self.json_call(self.staff, 'POST', f'/api/users/{new_id}', {
            '_action':'delete'
        }, staff_state['csrf'])[0], 403)
        self.assertEqual(self.post(f'/api/users/{staff_id}', {'_action':'delete'})[0], 201)
        self.assertEqual(self.json_call(self.staff, 'GET', '/api/state')[0], 401)

    def test_role_demotion_revokes_existing_session(self):
        self.assertEqual(self.post('/api/users', {
            'name':'Administrador Secundário','email':'second-admin@example.test',
            'password':'SecondAdminPassword_2026!','role':'admin',
        })[0], 201)
        with database.session() as c:
            ident=c.execute("SELECT id FROM users WHERE email='second-admin@example.test'").fetchone()[0]
        second=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.login(second,'second-admin@example.test','SecondAdminPassword_2026!')
        self.assertEqual(self.post(f'/api/users/{ident}', {
            '_action':'edit','name':'Administrador Secundário','email':'second-admin@example.test',
            'role':'atendente','password':'',
        })[0],201)
        self.assertEqual(self.json_call(second,'GET','/api/state')[0],401)


if __name__ == '__main__':
    unittest.main()

