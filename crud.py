"""Atomic editing/deletion, including reversal of stock effects."""
from domain import create, ValidationError, text, choice, money, integer
from database import password_hash
import re
TABLES={'tutors','pets','professionals','services','appointments','records','products','orders','stock_movements','users'}

def get(c,entity,ident):
    if entity not in TABLES: raise ValidationError('Registro inválido.')
    row=c.execute(f'SELECT * FROM {entity} WHERE id=?',(ident,)).fetchone()
    if not row: raise ValidationError('Registro não encontrado.')
    return dict(row)

def tutor_for_pet(c,d,user):
    """A pet can reuse a tutor, or register one inline; never deduplicate by name."""
    data={k:d.get('tutor_'+k,'') for k in ('name','phone','email')}
    if d.get('tutor_id'):
        ident=integer(d,'tutor_id'); old=get(c,'tutors',ident)
        if data['name']: update(c,'tutors',ident,data,user)
        return ident
    return create(c,'tutors',data,user)

def protect_admin(c,old,user,new_role=None):
    if user['role']!='admin': raise ValidationError('Somente administrador pode gerenciar a equipe.')
    if old['id']==user['id'] and new_role!='admin': raise ValidationError('Não é possível excluir ou remover seu próprio acesso de administrador.')
    if old['role']=='admin' and new_role!='admin' and c.execute("SELECT count(*) FROM users WHERE role='admin'").fetchone()[0]<=1: raise ValidationError('Mantenha ao menos um administrador.')

def stock(c,pid,delta):
    if not c.execute('UPDATE products SET stock=stock+? WHERE id=? AND stock+?>=0',(delta,pid,delta)).rowcount: raise ValidationError('Não há estoque suficiente para reverter esta movimentação.')

def update(c,entity,ident,d,user):
    old=get(c,entity,ident);d=dict(d)
    if entity=='users':
        role=choice(d,'role',['admin','atendente']);protect_admin(c,old,user,role)
        email=text(d,'email').lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValidationError('E-mail inválido.')
        values=dict(name=text(d,'name'),email=email,role=role)
        if d.get('password'):
            if len(text(d,'password'))<10: raise ValidationError('Senha deve ter pelo menos 10 caracteres.')
            values['password']=password_hash(d['password'])
    elif entity=='orders' and old['appointment_id']:
        values=dict(description=text(d,'description'),tutor_id=integer(d,'tutor_id'),total_cents=money(d),status=choice(d,'status',['Pago','Pendente']))
    else:
        if entity=='pets' and 'tutor_name' in d:d['tutor_id']=str(tutor_for_pet(c,d,user))
        if entity=='orders': stock(c,old['product_id'],old['quantity'])
        if entity=='stock_movements': stock(c,old['product_id'],-old['quantity'])
        if entity=='appointments':c.execute("UPDATE appointments SET status='Cancelado' WHERE id=?",(ident,))
        temp=create(c,entity,d,user)
        values=get(c,entity,temp);values.pop('id')
        c.execute(f'DELETE FROM {entity} WHERE id=?',(temp,))
        if entity in ('orders','stock_movements'):values['created']=old['created']
        if entity=='records':values['author_id']=old['author_id']
        if entity=='appointments':
            values['status']=old['status']
            c.execute('UPDATE orders SET tutor_id=(SELECT tutor_id FROM pets WHERE id=?),total_cents=?,description=(SELECT name FROM services WHERE id=?) WHERE appointment_id=?',(values['pet_id'],values['price_cents'],values['service_id'],ident))
    if entity=='professionals' and values['kind']!=old['kind'] and (c.execute('SELECT 1 FROM services WHERE professional_id=?',(ident,)).fetchone() or c.execute('SELECT 1 FROM records WHERE professional_id=?',(ident,)).fetchone()):raise ValidationError('Profissional vinculado: não altere o tipo.')
    if entity=='services' and values['category']!=old['category'] and c.execute('SELECT 1 FROM appointments WHERE service_id=?',(ident,)).fetchone():raise ValidationError('Serviço com agendamentos: não altere a categoria.')
    assignments=','.join(k+'=?' for k in values)
    c.execute(f'UPDATE {entity} SET {assignments} WHERE id=?',list(values.values())+[ident])

def delete(c,entity,ident,user):
    old=get(c,entity,ident)
    if entity=='orders':
        c.execute('DELETE FROM stripe_payments WHERE order_id=?',(ident,))
    if entity=='users':protect_admin(c,old,user)
    if entity=='orders' and old['product_id']:stock(c,old['product_id'],old['quantity'])
    if entity=='orders' and old['appointment_id']:
        c.execute("UPDATE appointments SET status='Agendado' WHERE id=?",(old['appointment_id'],))
    if entity=='stock_movements':stock(c,old['product_id'],-old['quantity'])
    if entity=='appointments':c.execute('DELETE FROM orders WHERE appointment_id=?',(ident,))
    # Foreign keys deliberately block deleting a master record used in history.
    c.execute(f'DELETE FROM {entity} WHERE id=?',(ident,))
