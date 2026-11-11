"""Local ERP HTTP API. Run python app.py; no third-party dependencies."""
import json, secrets, hmac, time, sqlite3, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from pathlib import Path
from database import session, initialize, password_hash, ROOT
from domain import create, action, ValidationError
from crud import update, delete, tutor_for_pet
from payments import checkout, webhook, guard
SESSIONS={}
ENTITIES=('tutors','pets','professionals','services','appointments','records','products','orders','stock_movements')

def revoke_sessions(user_id):
    for active in SESSIONS.values():
        if active['user']['id']==user_id:
            active['expires']=0

class Handler(BaseHTTPRequestHandler):
    def reply(self,data,status=200,headers=None):
        body=json.dumps(data,ensure_ascii=False).encode() if not isinstance(data,bytes) else data
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8' if not isinstance(data,bytes) else 'text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def session(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        token=cookie.get('pet_session'); s=SESSIONS.get(token.value) if token else None
        return s if s and s['expires']>time.time() else None
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ('/','/static/app.js','/static/style.css'):
            f=ROOT/('static/index.html' if path=='/' else path.lstrip('/'))
            data=f.read_bytes(); self.send_response(200)
            self.send_header('Content-Type',{'html':'text/html','js':'text/javascript','css':'text/css'}[f.suffix[1:]]+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data); return
        s=self.session()
        if not s: return self.reply({'error':'Faça login.'},401)
        if path=='/api/state':
            with session() as c:
                state={e:[dict(r) for r in c.execute('SELECT * FROM '+e+' ORDER BY id DESC')] for e in ENTITIES}
                state['stripe_payments']=[dict(r) for r in c.execute('SELECT order_id,status FROM stripe_payments')]
                if s['user']['role']=='admin': state['users']=[dict(r) for r in c.execute('SELECT id,name,email,role FROM users')]
            return self.reply(dict(state,user=s['user'],csrf=s['csrf']))
        self.reply({'error':'Não encontrado.'},404)
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536: return self.reply({'error':'Corpo inválido.'},400)
            payload=self.rfile.read(size)
            if urlparse(self.path).path=='/api/stripe/webhook':
                with session() as c:
                    c.execute('BEGIN IMMEDIATE')
                    webhook(c,payload,self.headers.get('Stripe-Signature',''))
                return self.reply({'ok':True})
            d=json.loads(payload)
            if not isinstance(d,dict): raise ValidationError('Objeto JSON esperado.')
            path=urlparse(self.path).path
            if path=='/api/login':
                with session() as c: u=c.execute('SELECT * FROM users WHERE email=?',(str(d.get('email','')).lower(),)).fetchone()
                if not u or not hmac.compare_digest(password_hash(str(d.get('password','')),u['password'].split(':')[0]),u['password']): return self.reply({'error':'E-mail ou senha incorretos.'},401)
                token=secrets.token_urlsafe(32); SESSIONS[token]=dict(user={k:u[k] for k in ('id','name','email','role')},csrf=secrets.token_urlsafe(24),expires=time.time()+28800)
                return self.reply({'ok':True},headers={'Set-Cookie':f'pet_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'})
            s=self.session()
            if not s: return self.reply({'error':'Faça login.'},401)
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): return self.reply({'error':'Sessão inválida. Recarregue a página.'},403)
            if path=='/api/logout':
                s['expires']=0
                return self.reply({'ok':True},headers={'Set-Cookie':'pet_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})
            segments=path.strip('/').split('/')
            if len(segments) not in (2,3) or segments[0]!='api': return self.reply({'error':'Rota inválida.'},404)
            entity=segments[1]
            with session() as c:
                c.execute('BEGIN IMMEDIATE') # Serialize availability check and write, including concurrent requests.
                if entity=='stripe' and len(segments)==3 and segments[2]=='checkout':
                    result=checkout(c,int(d['order_id']))
                    c.commit()
                    return self.reply(result)
                if len(segments)==3: guard(c,entity,int(segments[2]),d.get('_action'))
                if len(segments)==3 and d.get('_action') in ('edit','delete'):
                    if entity=='users' and s['user']['role']!='admin': return self.reply({'error':'Somente administrador.'},403)
                    target_id=int(segments[2])
                    prior_user=c.execute('SELECT role,password FROM users WHERE id=?',(target_id,)).fetchone() if entity=='users' else None
                    if d['_action']=='edit':
                        update(c,entity,target_id,d,s['user'])
                        if entity=='users':
                            new_user=c.execute('SELECT role,password FROM users WHERE id=?',(target_id,)).fetchone()
                            if prior_user and new_user and (prior_user['role']!=new_user['role'] or prior_user['password']!=new_user['password']):
                                revoke_sessions(target_id)
                    else:
                        delete(c,entity,target_id,s['user'])
                        if entity=='users': revoke_sessions(target_id)
                elif entity=='users':
                    if s['user']['role']!='admin': return self.reply({'error':'Somente administrador.'},403)
                    from domain import text, choice
                    import re
                    email=text(d,'email').lower(); password=text(d,'password')
                    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(password)<10: raise ValidationError('E-mail válido e senha com 10 caracteres são obrigatórios.')
                    c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',(text(d,'name'),email,password_hash(password),choice(d,'role',['admin','atendente'])))
                elif len(segments)==3: action(c,entity,int(segments[2]),d)
                else:
                    if entity=='pets' and 'tutor_name' in d: d['tutor_id']=str(tutor_for_pet(c,d,s['user']))
                    create(c,entity,d,s['user'])
            self.reply({'ok':True},201)
        except (ValidationError,ValueError,TypeError,KeyError): self.reply({'error':str(__import__('sys').exc_info()[1])},400)
        except sqlite3.IntegrityError: self.reply({'error':'Operação bloqueada: este registro possui vínculos no histórico, uma relação inválida ou dados duplicados. Remova os registros vinculados antes de excluir.'},409)
        except Exception:
            import traceback; traceback.print_exc(); self.reply({'error':'Erro interno. Consulte o terminal.'},500)
if __name__=='__main__':
    initialize(); port=int(os.environ.get('PORT','5000'))
    print(f'PetCare: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
