# PetCare — edição para equipe de testes

Aplicação local em português para gestão de petshop e clínica veterinária, com banco SQLite, interface responsiva e integração Stripe em **modo de teste**.

## Iniciar no Windows

1. Instale Python 3.12 ou superior.
2. Abra esta pasta no terminal.
3. Execute `python app.py` ou `py app.py`.
4. Acesse `http://127.0.0.1:5000`.
5. Entre com `admin@gmail.com` e a senha `pet123` na primeira inicialização.

Se a porta 5000 já estiver em uso, abra outro PowerShell e defina `$env:PORT='5001'` antes de executar `python app.py`; depois acesse `http://127.0.0.1:5001`. Mantenha apenas uma instância usando cada arquivo de banco de dados.

A senha inicial também pode ser definida antes da primeira execução pela variável `PETSHOP_ADMIN_PASSWORD`. A configuração não altera uma conta já criada. O login simples existe para o teste local: troque a senha em **Equipe → Editar** antes de publicar. Bancos já existentes não têm contas nem senhas redefinidas. O sistema atende apenas a própria máquina (`127.0.0.1`); não está publicado nem configurado para acesso por outros computadores.

## Catálogo de testes

Na primeira inicialização, o sistema inclui 20 produtos demonstrativos em alimentação, petiscos, higiene, brinquedos, passeio, acessórios e transporte: rações, sachês, biscoitos, petisco dental, areia, tapetes, shampoo, escovas, brinquedos, coleira, guia, comedouro, bebedouro, caixa de transporte, arranhador e saquinhos higiênicos.

Os preços e quantidades são **ilustrativos**. A lista aparece em **Petshop → Produtos** e pode ser editada pela equipe. O catálogo é inserido uma única vez; reiniciar o servidor não repõe itens excluídos nem altera preços ou estoque existentes. O banco do usuário não está incluído neste pacote.

## O que a equipe pode avaliar

- Cadastro de tutores e pets, profissionais, serviços e produtos.
- Agenda com validação de disponibilidade, expediente e conflitos.
- Prontuários veterinários.
- Vendas com total calculado no servidor, baixa automática do estoque e bloqueio de quantidade acima do saldo.
- Compras e ajustes de estoque.
- Financeiro de vendas e ordens de serviço.
- Usuários com perfis administrador e atendente.
- Checkout Stripe em ambiente de teste. A confirmação automática local requer o app e o Stripe CLI ativos, encaminhando os webhooks para `/api/stripe/webhook`.

## Stripe

Esta edição aceita somente chaves `sk_test_` e é própria para homologação. Não use dados reais de clientes nem faça cobrança real com o pacote de testes. Guarde chaves e segredos no ambiente local; nunca os inclua neste ZIP ou compartilhe no chat. Para receber dinheiro real em produção, será preciso preparar implantação HTTPS, configurar as credenciais ativas e registrar o webhook de produção.

## Testes automatizados

Execute na pasta:

```powershell
python -m unittest discover -s tests -v
```

A suíte contém **77 testes automatizados** cobrindo validações, cadastro/edição/exclusão, agenda, permissões, sessão, estoque, vendas, transações, Checkout e webhooks Stripe/Pix simulados. Também foram percorridas no navegador, em ambiente isolado, as telas dos módulos Petshop e Clínica. Testes HTTP adicionais validam login, CSRF, dados protegidos, cadastro, venda, cálculo do total e rejeição de venda acima do estoque. A confirmação Stripe foi simulada; nenhum pagamento real foi realizado.

## Dados e segurança

Os dados ficam em `petshop_pro.db`, criado ao iniciar. Faça backup com o servidor parado. Senhas usam PBKDF2 com salt; sessões usam cookies HttpOnly e SameSite e as escritas autenticadas exigem token CSRF. O SQLite usa transações para manter juntas as mudanças da venda e do estoque.

A integração local não equivale a uma implantação de produção. O servidor é local, sessões se encerram ao reiniciar, e ainda são necessários HTTPS, política de backups, controle de tentativas de login, revisão de permissões e configuração de webhook público antes do uso comercial.
