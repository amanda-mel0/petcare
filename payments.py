"""Stripe Checkout using Python's standard library."""
import hashlib, hmac, json, os, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from domain import ValidationError

def api(method, path, data=None, idem=None):
    key=os.environ.get('STRIPE_SECRET_KEY','')
    if not key.startswith('sk_test_'): raise ValidationError('Configure uma chave de teste Stripe.')
    headers={'Authorization':'Bearer '+key}
    if idem: headers['Idempotency-Key']=idem
    body=urlencode(data or {}).encode() if data is not None else None
    if body: headers['Content-Type']='application/x-www-form-urlencoded'
    try:
        with urlopen(Request('https://api.stripe.com/v1/'+path,data=body,headers=headers,method=method),timeout=20) as response:
            return json.loads(response.read())
    except HTTPError as e:
        try:
            detail=json.loads(e.read()).get('error',{}).get('message','')
        except Exception:
            detail=''
        raise ValidationError('Stripe recusou a cobrança: '+(detail or f'HTTP {e.code}.')) from e
    except (URLError, TimeoutError, OSError) as e:
        raise ValidationError('Falha de conexão com Stripe: '+str(getattr(e,'reason',e))) from e

def checkout(c, ident):
    base=os.environ.get('APP_BASE_URL','http://127.0.0.1:5000').rstrip('/'); u=urlparse(base)
    if u.scheme not in ('https','http') or not u.netloc or u.query or u.fragment: raise ValidationError('APP_BASE_URL inválida.')
    if not os.environ.get('STRIPE_WEBHOOK_SECRET','').startswith('whsec_'): raise ValidationError('Configure o segredo de webhook do Stripe CLI.')
    o=c.execute('SELECT * FROM orders WHERE id=?',(ident,)).fetchone()
    if not o or o['status']!='Pendente' or o['total_cents']<=0: raise ValidationError('Ordem pendente com valor positivo necessária.')
    old=c.execute('SELECT * FROM stripe_payments WHERE order_id=?',(ident,)).fetchone()
    if old and old['session_id']:
        s=api('GET','checkout/sessions/'+old['session_id'])
        if s.get('status')=='open' and 'pix' in s.get('payment_method_types',[]): return {'url':s['url']}
        if s.get('status')=='open': api('POST','checkout/sessions/'+old['session_id']+'/expire',{})
        if s.get('status')=='complete' and s.get('payment_status')!='paid':
            raise ValidationError('Existe um pagamento Pix em andamento nessa ordem. Conclua ou aguarde a expiração no Checkout aberto.')
        if s.get('status')=='complete' and s.get('payment_status')=='paid':
            raise ValidationError('Pagamento confirmado pela Stripe; aguarde a atualização do Financeiro.')
    if not old: c.execute('INSERT INTO stripe_payments(order_id,amount_cents) VALUES(?,?)',(ident,o['total_cents']))
    instance=c.execute("SELECT value FROM payment_settings WHERE name='instance'").fetchone()[0]
    data={'mode':'payment','line_items[0][price_data][currency]':'brl',
      'allowed_payment_method_types[0]':'card','allowed_payment_method_types[1]':'pix',
      'line_items[0][price_data][unit_amount]':str(o['total_cents']),'line_items[0][price_data][product_data][name]':o['description'],
      'line_items[0][quantity]':'1','client_reference_id':str(ident),'metadata[order_id]':str(ident),
      'success_url':base+'/?stripe=success','cancel_url':base+'/?stripe=cancel'}
    attempt=old['session_id'] if old and old['session_id'] else 'initial'
    s=api('POST','checkout/sessions',data,f'petcare-v3-{instance}-{ident}-{attempt}')
    c.execute('UPDATE stripe_payments SET session_id=? WHERE order_id=?',(s['id'],ident))
    return {'url':s['url']}

def webhook(c,payload,signature):
    secret=os.environ.get('STRIPE_WEBHOOK_SECRET','').encode()
    if not secret: raise ValidationError('Webhook Stripe não configurado.')
    try:
        parts=[item.split('=',1) for item in signature.split(',') if '=' in item]
        stamp=next(value for key,value in parts if key=='t')
        signatures=[value for key,value in parts if key=='v1']
        expected=hmac.new(secret,stamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
        if abs(time.time()-int(stamp))>300 or not any(hmac.compare_digest(expected,value) for value in signatures): raise ValueError()
        event=json.loads(payload)
    except Exception: raise ValidationError('Assinatura Stripe inválida.')
    if event.get('type') not in ('checkout.session.completed','checkout.session.async_payment_succeeded'): return
    s=event['data']['object']
    if s.get('payment_status')!='paid': return
    p=c.execute('SELECT * FROM stripe_payments WHERE session_id=?',(s['id'],)).fetchone()
    if not p: raise ValidationError('Sessão Stripe desconhecida.')
    if s.get('currency')!='brl' or s.get('amount_total')!=p['amount_cents'] or s.get('client_reference_id')!=str(p['order_id']): raise ValidationError('Pagamento divergente da ordem.')
    c.execute("UPDATE orders SET status='Pago' WHERE id=?",(p['order_id'],))
    c.execute("UPDATE stripe_payments SET status='paid',payment_intent=? WHERE order_id=?",(s.get('payment_intent'),p['order_id']))

def guard(c,entity,ident,operation=None):
    if entity not in ('orders','appointments'): return
    field='o.id' if entity=='orders' else 'o.appointment_id'
    row=c.execute(f'SELECT p.status,o.status AS order_status FROM stripe_payments p JOIN orders o ON o.id=p.order_id WHERE {field}=?',(ident,)).fetchone()
    if not row: return
    if (entity=='orders' and operation=='delete' and os.environ.get('STRIPE_SECRET_KEY','').startswith('sk_test_')
            and row['status']=='paid' and row['order_status']=='Pago'):
        return
    raise ValidationError('Ordem possui cobrança Stripe; alterações e baixa manual bloqueadas. Em modo de teste, pagamentos confirmados podem ser excluídos.')
