"""Validation and atomic business transactions shared by all HTTP endpoints."""
import re
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation

class ValidationError(ValueError): pass

def text(d,k):
    value=str(d.get(k,'')).strip()
    if not value or len(value)>5000: raise ValidationError('Preencha corretamente: '+k)
    return value

def integer(d,k,minimum=1,maximum=1000000):
    try:
        raw=str(d.get(k,'')); value=int(raw)
        if str(value)!=raw or not minimum<=value<=maximum: raise ValueError()
        return value
    except (ValueError,TypeError): raise ValidationError('Valor inválido: '+k)

def money(d,k='price'):
    try:
        v=Decimal(str(d.get(k,'')).replace(',','.'))
        if not v.is_finite() or v<0 or v>10000000 or v.as_tuple().exponent < -2: raise ValueError()
        return int(v*100)
    except (ValueError,InvalidOperation): raise ValidationError('Informe um valor monetário válido com até 2 casas.')

def choice(d,k,values):
    value=text(d,k)
    if value not in values: raise ValidationError('Opção inválida: '+k)
    return value

def iso_date(d,k):
    try: return date.fromisoformat(text(d,k)).isoformat()
    except ValueError: raise ValidationError('Data inválida: '+k)

def clock(d,k):
    v=text(d,k)
    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',v): raise ValidationError('Horário inválido.')
    return v

def create(c,entity,d,user):
    if entity=='tutors':
        phone=re.sub(r'\D','',text(d,'phone'))
        if len(phone) not in (10,11,12,13): raise ValidationError('Telefone deve conter DDD e número.')
        email=str(d.get('email','')).strip()
        if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValidationError('E-mail inválido.')
        values=dict(name=text(d,'name'),phone=phone,email=email)
    elif entity=='pets':
        born=iso_date(d,'birth_date')
        if born>date.today().isoformat(): raise ValidationError('Nascimento não pode ser futuro.')
        try:
            weight=float(d.get('weight',0))
            if not 0<weight<=1000: raise ValueError()
        except (ValueError,TypeError): raise ValidationError('Peso inválido.')
        values=dict(name=text(d,'name'),tutor_id=integer(d,'tutor_id'),species=text(d,'species'),breed=text(d,'breed'),size=choice(d,'size',['Pequeno','Médio','Grande']),birth_date=born,weight=weight,allergies=str(d.get('allergies',''))[:5000])
    elif entity=='professionals':
        kind=choice(d,'kind',['Veterinário','Petshop']); crmv=str(d.get('crmv','')).strip()
        if kind=='Veterinário' and not re.fullmatch(r'[A-Za-z]{2}[- /]?\d{3,10}',crmv): raise ValidationError('CRMV: informe UF e número, ex.: BA-12345.')
        start,end=clock(d,'start_time'),clock(d,'end_time')
        if start>=end: raise ValidationError('Fim do expediente deve ser após o início.')
        days=text(d,'weekdays')
        if not re.fullmatch(r'[0-6](,[0-6])*',days): raise ValidationError('Dias: 0=segunda a 6=domingo, separados por vírgulas.')
        values=dict(name=text(d,'name'),kind=kind,crmv=crmv,specialty=text(d,'specialty'),start_time=start,end_time=end,weekdays=days,active=integer(d,'active',0,1))
    elif entity=='services':
        pid=integer(d,'professional_id'); category=choice(d,'category',['Clínica','Petshop'])
        p=c.execute('SELECT * FROM professionals WHERE id=?',(pid,)).fetchone()
        if not p or (category=='Clínica')!=(p['kind']=='Veterinário'): raise ValidationError('Profissional incompatível com a categoria.')
        values=dict(name=text(d,'name'),description=text(d,'description'),category=category,price_cents=money(d),duration=integer(d,'duration',5,720),professional_id=pid)
    elif entity=='products':
        values=dict(name=text(d,'name'),category=text(d,'category'),price_cents=money(d),stock=integer(d,'stock',0))
    elif entity=='records':
        p=c.execute('SELECT * FROM professionals WHERE id=?',(integer(d,'professional_id'),)).fetchone()
        if not p or p['kind']!='Veterinário': raise ValidationError('Selecione um veterinário.')
        day=iso_date(d,'date')
        if day>date.today().isoformat(): raise ValidationError('Registro clínico não pode ter data futura.')
        values=dict(pet_id=integer(d,'pet_id'),professional_id=p['id'],kind=choice(d,'kind',['Consulta','Vacina','Observação']),date=day,notes=text(d,'notes'),author_id=user['id'])
    elif entity=='appointments': return schedule(c,d)
    elif entity=='orders': return sell(c,d)
    elif entity=='stock_movements':
        pid=integer(d,'product_id'); qty=integer(d,'quantity'); unit=money(d)
        if not c.execute('UPDATE products SET stock=stock+? WHERE id=?',(qty,pid)).rowcount: raise ValidationError('Produto não encontrado.')
        values=dict(product_id=pid,quantity=qty,unit_cents=unit,created=datetime.now().isoformat(timespec='seconds'),author_id=user['id'])
    else: raise ValidationError('Cadastro não permitido.')
    columns=','.join(values); placeholders=','.join('?' for _ in values)
    return c.execute(f'INSERT INTO {entity}({columns}) VALUES({placeholders})',list(values.values())).lastrowid

def schedule(c,d):
    service=c.execute('SELECT * FROM services WHERE id=?',(integer(d,'service_id'),)).fetchone()
    if not service: raise ValidationError('Serviço inexistente.')
    p=c.execute('SELECT * FROM professionals WHERE id=?',(service['professional_id'],)).fetchone()
    try: start=datetime.strptime(text(d,'start'),'%Y-%m-%dT%H:%M')
    except ValueError: raise ValidationError('Data e horário inválidos.')
    end=start+timedelta(minutes=service['duration'])
    if start<datetime.now(): raise ValidationError('Selecione um horário futuro.')
    if not p['active'] or str(start.weekday()) not in p['weekdays'].split(',') or start.date()!=end.date() or start.strftime('%H:%M')<p['start_time'] or end.strftime('%H:%M')>p['end_time']: raise ValidationError('Fora da disponibilidade do profissional.')
    pet=integer(d,'pet_id'); a,b=start.isoformat(timespec='minutes'),end.isoformat(timespec='minutes')
    if c.execute("SELECT 1 FROM appointments WHERE status!='Cancelado' AND (professional_id=? OR pet_id=?) AND start<? AND end>?",(p['id'],pet,b,a)).fetchone(): raise ValidationError('Conflito: pet ou profissional já tem atendimento neste período.')
    return c.execute('INSERT INTO appointments(pet_id,service_id,professional_id,start,end,price_cents) VALUES(?,?,?,?,?,?)',(pet,service['id'],p['id'],a,b,service['price_cents'])).lastrowid

def sell(c,d):
    pid=integer(d,'product_id'); qty=integer(d,'quantity'); tutor=integer(d,'tutor_id')
    p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
    if not p or not c.execute('UPDATE products SET stock=stock-? WHERE id=? AND stock>=?',(qty,pid,qty)).rowcount: raise ValidationError('Estoque insuficiente.')
    return c.execute('INSERT INTO orders(tutor_id,product_id,quantity,description,total_cents,status,created) VALUES(?,?,?,?,?,?,?)',(tutor,pid,qty,p['name'],p['price_cents']*qty,choice(d,'status',['Pago','Pendente']),datetime.now().isoformat(timespec='seconds'))).lastrowid

def action(c,entity,ident,d):
    if entity=='appointments':
        status=choice(d,'status',['Concluído','Cancelado'])
        a=c.execute('SELECT a.*,p.tutor_id,s.name FROM appointments a JOIN pets p ON p.id=a.pet_id JOIN services s ON s.id=a.service_id WHERE a.id=?',(ident,)).fetchone()
        if not a or a['status']!='Agendado': raise ValidationError('Atendimento já finalizado ou não encontrado.')
        if status=='Concluído':
            c.execute('INSERT INTO orders(tutor_id,appointment_id,description,total_cents,created) VALUES(?,?,?,?,?)',(a['tutor_id'],ident,a['name'],a['price_cents'],datetime.now().isoformat(timespec='seconds')))
        c.execute('UPDATE appointments SET status=? WHERE id=?',(status,ident))
    elif entity=='orders':
        if not c.execute("UPDATE orders SET status='Pago' WHERE id=? AND status='Pendente'",(ident,)).rowcount: raise ValidationError('Pagamento já recebido ou OS inexistente.')
    elif entity=='professionals':
        c.execute('UPDATE professionals SET active=? WHERE id=?',(integer(d,'active',0,1),ident))
    else: raise ValidationError('Ação não permitida.')
