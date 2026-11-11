import os, sqlite3, secrets, hashlib, hmac, html, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from http.cookies import SimpleCookie
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, 'petshop.db')
SESSIONS = {}
CATEGORIES = ('Ração', 'Brinquedos', 'Higiene')
def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 200000).hex()
def init():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, telefone TEXT NOT NULL, senha TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS produtos(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT NOT NULL, preco REAL NOT NULL, estoque INTEGER NOT NULL DEFAULT 0, ativo INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS movimentos(id INTEGER PRIMARY KEY, produto_id INTEGER NOT NULL REFERENCES produtos(id), operacao TEXT NOT NULL, quantidade INTEGER NOT NULL, valor REAL NOT NULL, data TEXT NOT NULL, usuario TEXT NOT NULL);''')
        if not c.execute('SELECT 1 FROM usuarios WHERE admin=1').fetchone():
            c.execute('INSERT INTO usuarios(nome,email,telefone,senha,admin) VALUES(?,?,?,?,1)', ('Administrador','admin@petshop.com','Não informado',hash_password('admin123')))
def e(s): return html.escape(str(s), quote=True)
def money(x): return 'R$ ' + f'{x:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
def layout(title, body, user=None, msg=''):
    nav = '<nav class="main-nav"><a href="/">⌂ <span>Início</span></a><a href="/usuarios">♙ <span>Usuários</span></a><a href="/produtos">▣ <span>Produtos</span></a><a href="/movimentos">↔ <span>Compras e vendas</span></a><a href="/sair">⇥ <span>Sair</span></a></nav>' if user else ''
    tools = '<div class="header-tools"><span class="signed-in">'+e(user['nome'])+'</span><button type="button" class="theme-toggle" aria-label="Alternar tema" title="Alternar tema">☾</button></div>' if user else ''
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#153d36"><title>{e(title)} | Pet Shop</title><style>
    :root{{--bg:#f3f6f4;--surface:#fff;--text:#1d2c27;--muted:#708078;--line:#e4ebe6;--primary:#19735b;--primary-dark:#125642;--soft:#e9f5ef;--shadow:0 12px 32px #173c2d0c}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);font:15px Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);transition:background .25s,color .25s}}body.theme-dark{{--bg:#111a17;--surface:#1b2722;--text:#e9f2ed;--muted:#9caaa2;--line:#33423a;--soft:#253d32;--shadow:0 12px 32px #0004}}
    header{{background:linear-gradient(115deg,#123b33,#1d6851 70%,#248464);color:white;padding:16px max(22px,calc((100% - 1180px)/2));display:flex;align-items:center;gap:26px;min-height:78px;box-shadow:0 8px 24px #164d3a25}}
    .brand{{font-weight:800;font-size:19px;letter-spacing:-.4px;white-space:nowrap;display:flex;align-items:center;gap:10px}}.brand-mark{{width:38px;height:38px;border-radius:13px;background:#ffffff20;display:grid;place-items:center;font-size:21px}}
    .main-nav{{display:flex;align-items:center;gap:5px;flex:1}}.main-nav a{{display:inline-flex;align-items:center;gap:8px;color:#e5f3ec;text-decoration:none;padding:10px 13px;border-radius:10px;font-weight:600;font-size:14px;transition:.2s}}.main-nav a:hover,.main-nav a.active{{background:#ffffff20;color:white;transform:translateY(-1px)}}
    .header-tools{{display:flex;align-items:center;gap:12px;margin-left:auto}}.signed-in{{font-size:13px;color:#e1f0e8;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.theme-toggle,.menu-toggle{{width:38px;height:38px;padding:0;background:#ffffff18;border:1px solid #ffffff25;border-radius:11px;color:white;font-size:18px;display:grid;place-items:center}}
    main{{max-width:1180px;margin:36px auto;padding:0 24px 55px}}.page-heading{{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:20px}}h1{{font-size:clamp(26px,3vw,34px);letter-spacing:-1px;margin:0;font-weight:750}}h2{{font-size:18px;letter-spacing:-.3px;margin:0 0 16px}}p{{line-height:1.6}}.intro{{color:var(--muted);margin:8px 0 22px}}
    .card{{background:var(--surface);padding:23px;border:1px solid var(--line);border-radius:17px;box-shadow:var(--shadow);margin:18px 0;overflow:auto;animation:rise .35s both}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px}}.metric-card{{min-height:142px;position:relative;overflow:hidden}}.metric-card:after{{content:"";position:absolute;width:120px;height:120px;border-radius:50%;background:var(--soft);right:-32px;top:-35px}}.metric-label{{color:var(--muted);font-size:13px;font-weight:650}}.metric{{font-size:34px;font-weight:800;color:var(--primary);margin-top:14px;letter-spacing:-1px;position:relative;z-index:1}}.metric-icon{{font-size:19px;position:absolute;right:18px;bottom:18px;z-index:1}}
    label{{display:block;font-weight:650;font-size:13px;margin-bottom:7px;color:var(--muted)}}input,select{{width:100%;padding:12px 13px;border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:10px;font-size:14px;outline:none;transition:border .2s,box-shadow .2s}}input:focus,select:focus{{border-color:#43a17f;box-shadow:0 0 0 3px #45a37d22}}button{{background:var(--primary);color:white;border:0;border-radius:10px;padding:11px 16px;cursor:pointer;font-weight:700;font-size:14px;transition:transform .16s,background .16s,box-shadow .16s}}button:hover{{background:var(--primary-dark);transform:translateY(-1px);box-shadow:0 5px 14px #19735b28}}button:disabled{{opacity:.7;cursor:wait;transform:none}}button.danger{{background:#b94c49}}button.danger:hover{{background:#973936}}form.inline{{display:inline}}.wide{{margin-top:18px}}.hint{{color:var(--muted);font-size:13px;margin-top:-6px}}
    table{{width:100%;border-collapse:collapse;min-width:640px}}td,th{{text-align:left;padding:13px 12px;border-bottom:1px solid var(--line)}}th{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}}tbody tr{{transition:background .15s}}tbody tr:hover{{background:var(--soft)}}.notice{{background:var(--soft);border:1px solid #cce7d6;color:var(--primary-dark);padding:13px 16px;border-radius:11px;margin:0 0 18px;font-weight:600;transition:opacity .3s,transform .3s}}.notice.hide{{opacity:0;transform:translateY(-8px)}}.hint{{color:var(--muted)}}.table-tools{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 14px}}.table-search{{max-width:330px}}.row-count{{font-size:12px;color:var(--muted);white-space:nowrap}}.empty-state{{padding:24px;text-align:center;color:var(--muted)}}.stock-low{{color:#b94c49;font-weight:800}}.stock-ok{{color:var(--primary);font-weight:700}}.login-shell{{max-width:460px;margin:7vh auto}}.login-shell .card{{padding:30px}}.login-intro{{color:var(--muted)}}.login-logo{{font-size:44px;margin-bottom:12px}}.login-submit{{width:100%;margin-top:12px;padding:13px}}.login-shell input{{margin-bottom:14px}}.quick-link{{display:block;padding:15px;border-radius:11px;background:var(--soft);color:var(--primary);text-decoration:none;font-weight:700;transition:transform .2s}}.quick-link:hover{{transform:translateY(-2px)}}
    @keyframes rise{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}@media(max-width:780px){{header{{flex-wrap:wrap;gap:12px;padding:14px 18px}}.brand{{flex:1}}.main-nav{{order:3;width:100%;overflow:auto;gap:2px}}.main-nav a{{padding:9px 10px;white-space:nowrap}}.main-nav a span{{font-size:13px}}.signed-in{{display:none}}main{{margin:27px auto;padding:0 16px 40px}}.card{{padding:18px}}.page-heading{{align-items:flex-start}}}}
    @media(max-width:480px){{.main-nav a{{font-size:0;gap:0}}.main-nav a span{{font-size:12px}}.main-nav{{justify-content:space-between}}.grid{{grid-template-columns:1fr}}.table-tools{{align-items:stretch;flex-direction:column}}.table-search{{max-width:none}}}}
    </style></head><body><header><div class="brand"><span class="brand-mark">🐾</span><span>Pet Shop</span></div>{nav}{tools}</header><main><div class="page-heading"><h1>{e(title)}</h1></div>{'<p class="notice" role="status">'+e(msg)+'</p>' if msg else ''}{body}</main><script src="/app.js" defer></script></body></html>'''
def field(name,label,typ='text',extra=''):
    return f'<div><label for="{name}">{label}</label><input id="{name}" name="{name}" type="{typ}" {extra} required></div>'
def csrf(token): return f'<input type="hidden" name="csrf" value="{e(token)}">'
class Handler(BaseHTTPRequestHandler):
    def session(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        token=cookie.get('sessao')
        return SESSIONS.get(token.value) if token else None
    def send_page(self, content, status=200, headers=None):
        data=content.encode('utf-8'); self.send_response(status)
        self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def send_script(self, path):
        try:
            with open(path, 'rb') as asset: data=asset.read()
        except OSError:
            return self.send_page('Arquivo não encontrado',404)
        self.send_response(200); self.send_header('Content-Type','text/javascript; charset=utf-8')
        self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-cache'); self.end_headers(); self.wfile.write(data)
    def redirect(self, path, headers=None):
        self.send_response(303); self.send_header('Location',path)
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()
    def do_GET(self):
        p=urlparse(self.path); path=p.path; msg=parse_qs(p.query).get('msg',[''])[0]; user=self.session()
        if path=='/app.js': return self.send_script(os.path.join(ROOT,'static','app.js'))
        if path=='/sair':
            cookie=SimpleCookie(); cookie.load(self.headers.get('Cookie','')); key=cookie.get('sessao')
            if key: SESSIONS.pop(key.value,None)
            return self.redirect('/login',{'Set-Cookie':'sessao=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax'})
        if path=='/login':
            form=f'''<div class="card" style="max-width:440px"><p>Entre para acessar o sistema.</p><form method="post" action="/login">{field('email','E-mail','email')}{field('senha','Senha','password')}<div class="wide"><button>Entrar</button></div></form></div>'''
            return self.send_page(layout('Login',form,msg=msg))
        if not user: return self.redirect('/login')
        token=user['csrf']
        with db() as c:
            if path=='/':
                counts=[c.execute('SELECT count(*) FROM usuarios').fetchone()[0],c.execute('SELECT count(*) FROM produtos WHERE ativo=1').fetchone()[0],c.execute('SELECT coalesce(sum(estoque),0) FROM produtos WHERE ativo=1').fetchone()[0]]
                body='<p class="intro">Olá, '+e(user['nome'])+'! Aqui está o resumo da sua loja.</p><div class="grid">'+''.join(f'<div class="card metric-card"><div class="metric-label">{t}</div><div class="metric" data-count="{n}">0</div><span class="metric-icon">{icon}</span></div>' for n,t,icon in zip(counts,['Usuários','Produtos cadastrados','Itens em estoque'],['♙','▣','▤']))+'</div><div class="card"><h2>Comece por aqui</h2><p class="intro">Cadastre produtos, registre compras para dar entrada no estoque e vendas para dar saída. O estoque é atualizado automaticamente.</p><div class="grid"><a class="quick-link" href="/produtos">▣ &nbsp; Gerenciar produtos</a><a class="quick-link" href="/movimentos">↔ &nbsp; Registrar compra ou venda</a></div></div>'
                return self.send_page(layout('Painel',body,user,msg))
            if path=='/usuarios':
                if not user['admin']: return self.send_page(layout('Acesso negado','<p>Somente o administrador pode gerenciar usuários.</p>',user),403)
                rows=c.execute('SELECT id,nome,email,telefone,admin FROM usuarios ORDER BY id').fetchall()
                form=f'''<div class="card"><h2>Cadastrar usuário</h2><form method="post" action="/usuarios/adicionar">{csrf(token)}<div class="grid">{field('id','ID','number','min="1"')}{field('nome','Nome completo')}{field('email','E-mail','email')}{field('telefone','Telefone','tel')}{field('senha','Senha de acesso','password','minlength="6"')}</div><div class="wide"><button>Cadastrar usuário</button></div></form></div>'''
                lines=''.join(f'<tr><td>{r["id"]}</td><td>{e(r["nome"])}</td><td>{e(r["email"])}</td><td>{e(r["telefone"])}</td><td>{"Administrador" if r["admin"] else "Usuário"}</td><td>'+('—' if r['admin'] else f'<form class="inline" method="post" action="/usuarios/remover" onsubmit="return confirm(\'Remover este usuário?\')">{csrf(token)}<input type="hidden" name="id" value="{r["id"]}"><button class="danger">Remover</button></form>')+'</td></tr>' for r in rows)
                return self.send_page(layout('Usuários',form+'<div class="card"><h2>Usuários cadastrados</h2><table><tr><th>ID</th><th>Nome</th><th>E-mail</th><th>Telefone</th><th>Perfil</th><th>Ação</th></tr>'+lines+'</table></div>',user,msg))
            if path=='/produtos':
                rows=c.execute('SELECT * FROM produtos WHERE ativo=1 ORDER BY nome').fetchall(); opts=''.join(f'<option>{e(x)}</option>' for x in CATEGORIES)
                form=f'''<div class="card"><h2>Cadastrar produto</h2><form method="post" action="/produtos/adicionar">{csrf(token)}<div class="grid">{field('nome','Nome do produto')}<div><label>Tipo</label><select name="tipo">{opts}</select></div>{field('preco','Preço de venda (R$)','number','min="0" step="0.01"')}{field('estoque','Estoque inicial','number','min="0" step="1" value="0"')}</div><div class="wide"><button>Cadastrar produto</button></div></form></div>'''
                lines=''.join(f'<tr><td>{r["id"]}</td><td>{e(r["nome"])}</td><td>{e(r["tipo"])}</td><td>{money(r["preco"])}</td><td>{r["estoque"]}</td><td><form class="inline" method="post" action="/produtos/remover" onsubmit="return confirm(\'Remover este produto?\')">{csrf(token)}<input type="hidden" name="id" value="{r["id"]}"><button class="danger">Remover</button></form></td></tr>' for r in rows)
                return self.send_page(layout('Produtos e estoque',form+'<div class="card"><h2>Produtos cadastrados</h2><table><tr><th>ID</th><th>Produto</th><th>Tipo</th><th>Preço de venda</th><th>Estoque</th><th>Ação</th></tr>'+lines+'</table></div>',user,msg))
            if path=='/movimentos':
                products=c.execute('SELECT * FROM produtos WHERE ativo=1 ORDER BY nome').fetchall(); opts=''.join(f'<option value="{r["id"]}">{e(r["nome"])} — estoque: {r["estoque"]}</option>' for r in products)
                form=f'''<div class="card"><h2>Registrar compra ou venda</h2><p class="hint">Compra adiciona itens ao estoque; venda retira itens. Informe o valor unitário da operação.</p><form method="post" action="/movimentos/adicionar">{csrf(token)}<div class="grid"><div><label>Operação</label><select name="operacao"><option>Compra</option><option>Venda</option></select></div><div><label>Produto</label><select name="produto" required><option value="">Selecione</option>{opts}</select></div>{field('quantidade','Quantidade','number','min="1" step="1"')}{field('valor','Valor unitário (R$)','number','min="0" step="0.01"')}</div><div class="wide"><button>Registrar</button></div></form></div>'''
                rows=c.execute('SELECT m.*,p.nome FROM movimentos m JOIN produtos p ON p.id=m.produto_id ORDER BY m.id DESC LIMIT 100').fetchall()
                lines=''.join(f'<tr><td>{e(r["data"])}</td><td>{e(r["operacao"])}</td><td>{e(r["nome"])}</td><td>{r["quantidade"]}</td><td>{money(r["valor"])}</td><td>{money(r["valor"]*r["quantidade"])}</td><td>{e(r["usuario"])}</td></tr>' for r in rows)
                return self.send_page(layout('Compras e vendas',form+'<div class="card"><h2>Histórico de movimentações</h2><table><tr><th>Data</th><th>Operação</th><th>Produto</th><th>Qtd.</th><th>Valor unitário</th><th>Total</th><th>Usuário</th></tr>'+lines+'</table></div>',user,msg))
        self.send_page(layout('Página não encontrada','',user),404)
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>100000: return self.send_page('Requisição muito grande',413)
            data=parse_qs(self.rfile.read(size).decode('utf-8'),keep_blank_values=True)
            get=lambda key:data.get(key,[''])[0].strip()
            if path=='/login':
                with db() as c: row=c.execute('SELECT * FROM usuarios WHERE email=?',(get('email'),)).fetchone()
                if row and hmac.compare_digest(row['senha'],hash_password(get('senha'),row['senha'].split(':')[0])):
                    sid=secrets.token_urlsafe(32); SESSIONS[sid]={'id':row['id'],'nome':row['nome'],'admin':bool(row['admin']),'csrf':secrets.token_urlsafe(24)}
                    return self.redirect('/',{'Set-Cookie':f'sessao={sid}; Path=/; HttpOnly; SameSite=Lax'})
                return self.redirect('/login?msg=E-mail+ou+senha+inv%C3%A1lidos')
            user=self.session()
            if not user: return self.redirect('/login')
            if not hmac.compare_digest(get('csrf'),user['csrf']): return self.send_page('Sessão inválida',403)
            dest='/usuarios' if path.startswith('/usuarios') else '/produtos' if path.startswith('/produtos') else '/movimentos'
            with db() as c:
                if path.startswith('/usuarios') and not user['admin']: return self.send_page('Acesso negado',403)
                if path=='/usuarios/adicionar':
                    uid=int(get('id')); nome=get('nome'); email=get('email'); tel=get('telefone'); senha=get('senha')
                    if uid<1 or not nome or '@' not in email or not tel or len(senha)<6: raise ValueError('Preencha todos os campos corretamente; a senha deve ter pelo menos 6 caracteres.')
                    c.execute('INSERT INTO usuarios VALUES(?,?,?,?,?,0)',(uid,nome,email,tel,hash_password(senha)))
                elif path=='/usuarios/remover':
                    uid=int(get('id')); c.execute('DELETE FROM usuarios WHERE id=? AND admin=0',(uid,))
                    for sid,s in list(SESSIONS.items()):
                        if s['id']==uid: SESSIONS.pop(sid,None)
                elif path=='/produtos/adicionar':
                    nome=get('nome'); tipo=get('tipo'); preco=float(get('preco')); estoque=int(get('estoque'))
                    if not nome or tipo not in CATEGORIES or not (0<=preco<=10000000) or not (0<=estoque<=10000000): raise ValueError('Confira os dados do produto.')
                    c.execute('INSERT INTO produtos(nome,tipo,preco,estoque) VALUES(?,?,?,?)',(nome,tipo,preco,estoque))
                elif path=='/produtos/remover': c.execute('UPDATE produtos SET ativo=0 WHERE id=?',(int(get('id')),))
                elif path=='/movimentos/adicionar':
                    produto=int(get('produto')); qtd=int(get('quantidade')); valor=float(get('valor')); op=get('operacao')
                    if qtd<1 or qtd>10000000 or not (0<=valor<=10000000) or op not in ('Compra','Venda'): raise ValueError('Confira os dados da movimentação.')
                    c.execute('BEGIN IMMEDIATE')
                    row=c.execute('SELECT estoque FROM produtos WHERE id=? AND ativo=1',(produto,)).fetchone()
                    if not row: raise ValueError('Produto não encontrado.')
                    if op=='Venda' and qtd>row['estoque']: raise ValueError('Estoque insuficiente para realizar a venda.')
                    c.execute('UPDATE produtos SET estoque=estoque+? WHERE id=?',(qtd if op=='Compra' else -qtd,produto))
                    c.execute('INSERT INTO movimentos(produto_id,operacao,quantidade,valor,data,usuario) VALUES(?,?,?,?,?,?)',(produto,op,qtd,valor,datetime.now().strftime('%d/%m/%Y %H:%M'),user['nome']))
                else: return self.send_page('Página não encontrada',404)
            return self.redirect(dest+'?msg=Opera%C3%A7%C3%A3o+realizada+com+sucesso')
        except (ValueError,sqlite3.IntegrityError) as ex:
            from urllib.parse import quote
            msg='ID ou e-mail já cadastrado.' if isinstance(ex,sqlite3.IntegrityError) else str(ex) or 'Dados inválidos.'
            return self.redirect((dest if 'dest' in locals() else '/login')+'?msg='+quote(msg))
if __name__=='__main__':
    init(); address='http://127.0.0.1:5000'; print('Sistema disponível em '+address+' — pressione Ctrl+C para encerrar.',flush=True)
    threading.Timer(1,lambda:webbrowser.open(address)).start()
    try: ThreadingHTTPServer(('127.0.0.1',5000),Handler).serve_forever()
    except KeyboardInterrupt: print('\nSistema encerrado.')
