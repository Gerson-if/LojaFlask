# LojaFácil em Flask

Migração do sistema HTML/localStorage para uma aplicação Flask com banco relacional.

## O que foi migrado

- Landing page pública em `/` com apresentação do sistema, login e cadastro.
- Login, cadastro de lojista e super admin.
- Painel do lojista (em `/painel`) com dashboard, produtos, categorias, clientes, pedidos, personalização da loja e área de assinatura.
- Área "Minha assinatura" do lojista: status atual (teste/pago/vencido), datas de início/vencimento e histórico completo de pagamentos.
- Loja pública por slug em `/loja/<slug>`.
- Carrinho em sessão, checkout e registro de pedido no banco.
- Pedido com link pronto para WhatsApp.
- Painel super admin com lojistas, suspensão/reativação, redefinição de senha, gestão de assinatura (com histórico e valor customizável por renovação), pedidos da plataforma e métricas de receita (MRR e receita total recebida).

## Mapa de rotas

| Área | URL base | Observação |
|---|---|---|
| Landing page | `/` | Pública. Usuário autenticado é redirecionado para `/painel`. |
| Autenticação | `/login`, `/cadastro`, `/logout` | Públicas. |
| Painel (lojista/admin) | `/painel/...` | Exige login. Isolado da raiz do site por `url_prefix="/painel"` no blueprint do dashboard — não há mais conflito de rota com a landing page. Inclui `/painel/assinatura` (lojista vê status e histórico de pagamentos), `/painel/financeiro` (margem de lucro e produtos mais vendidos) e `/painel/admin/lojistas/<id>/assinatura/historico` (superadmin vê e gerencia a assinatura de qualquer lojista, inclusive corrigindo a data de vencimento manualmente). |
| Loja pública | `/loja/<slug>/...` | Pública, uma por lojista. |
| Assinatura | `/assinatura-expirada` | Tela de bloqueio quando o trial/assinatura vence. |
| Health check | `/health` | Usado por orquestradores/monitoramento. |

## Banco de dados

O app usa SQLAlchemy e aceita bancos compatíveis via `DATABASE_URL`.

Exemplo MariaDB/MySQL:

```env
DATABASE_URL=mysql+pymysql://lojafacil:senha@localhost/lojafacil?charset=utf8mb4
```

Para desenvolvimento sem MariaDB instalado, deixe `DATABASE_URL` vazio e o app usa SQLite local em `instance/lojafacil.db`.

Tabelas modeladas:

- `users`: lojistas e super admin (`role`: `superadmin` ou `lojista`).
- `stores`: loja de cada lojista, incluindo redes sociais, cores da marca e controle de trial/assinatura (`trial_ends_at`, `subscription_active`, `paid_until`).
- `store_banners`: banners da loja.
- `categories`: categorias por loja.
- `products`: catálogo por loja (preço de custo opcional, preço, preço promocional, estoque, status). Produtos com variações (ver `product_variants`) têm o estoque controlado por elas, não pelo campo `stock` do produto.
- `product_variants`: variações de tamanho/cor de um produto, cada uma com seu próprio estoque e, opcionalmente, seu próprio preço (se vazio, usa o preço do produto). Um produto só passa a ter variações quando o lojista cadastra ao menos uma.
- `product_images`: imagens dos produtos.
- `customers`: clientes por loja (nome, telefone, e-mail, endereço).
- `orders`: pedidos por loja — guarda um snapshot do cliente no momento da compra (`customer_name`, `customer_phone`, `customer_email`, `customer_address`), além de `status` (indexado) e `status_updated_at`, que registra a última mudança de status.
- `order_items`: itens dos pedidos, com snapshot da variação comprada (`variant_id`, `variant_label`) e do custo do produto no momento da venda (`unit_cost`) — usado para calcular margem de lucro real mesmo que o lojista altere o custo depois.
- `order_items`: itens dos pedidos.
- `subscription_payments`: histórico de renovações e suspensões de assinatura de cada loja (quem registrou, período pago, valor, observação). Alimenta tanto a área "Minha assinatura" do lojista quanto o histórico de cada lojista no painel do superadmin.

Esse "snapshot" de dados do cliente em `orders` é intencional: se o cliente depois mudar nome/telefone/e-mail no cadastro, o histórico do pedido continua mostrando os dados de quando a compra foi feita.

## Instalação local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
flask --app run.py init-db
flask --app run.py run
```

Se usar MariaDB, crie antes o banco:

```sql
CREATE DATABASE lojafacil CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lojafacil'@'localhost' IDENTIFIED BY 'senha';
GRANT ALL PRIVILEGES ON lojafacil.* TO 'lojafacil'@'localhost';
FLUSH PRIVILEGES;
```

## Acesso inicial

- E-mail: `admin@lojafacil.com`
- Senha: `admin123`

Troque esses valores no `.env` antes de rodar em produção.

## Deploy com MariaDB

1. Crie o banco MariaDB:

```sql
CREATE DATABASE lojafacil CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lojafacil'@'localhost' IDENTIFIED BY 'senha-forte';
GRANT ALL PRIVILEGES ON lojafacil.* TO 'lojafacil'@'localhost';
FLUSH PRIVILEGES;
```

2. Configure o ambiente:

```powershell
copy deploy.env.example .env
```

Edite `.env` e ajuste `SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL` e `ADMIN_PASSWORD`.

3. Instale dependências e aplique migrations:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app run.py check-db
flask --app run.py db upgrade
flask --app run.py seed-admin
```

4. Inicie em servidor real com Waitress:

```powershell
python serve.py
```

Por padrão ele sobe em `0.0.0.0:8000`. Altere `HOST` e `PORT` no `.env`.

## Deploy Linux com systemd ou proxy reverso

O ponto WSGI de produção é:

```text
wsgi:app
```

Com Gunicorn, se preferir em Linux:

```bash
pip install gunicorn
gunicorn -w 3 -b 127.0.0.1:8000 wsgi:app
```

Use Nginx/Apache como proxy reverso com HTTPS apontando para `127.0.0.1:8000`.

## Migrations — guia rápido

O projeto usa Flask-Migrate (Alembic). O histórico atual de migrations, em ordem:

1. `0a0fb23259f4` — schema inicial (todas as tabelas).
2. `7d3a0b5c8e2f` — redes sociais da loja (`instagram_url`, `facebook_url`, `tiktok_url`) e forma de pagamento do pedido.
3. `a1b2c3d4e5f6` — trial e assinatura (`trial_ends_at`, `subscription_active`).
4. `b2c3d4e5f6a7` — vencimento de assinatura paga (`paid_until`).
5. `c3d4e5f6a7b8` — e-mail do cliente no pedido (`customer_email`) e rastreio de mudança de status (`status_updated_at`, com índice em `status`).
6. `d4e5f6a7b8c9` — tabela `subscription_payments`, histórico de renovações/suspensões de assinatura.
7. `e5f6a7b8c9d0` — `products.cost_price`, tabela `product_variants` (tamanho/cor/estoque/preço), e snapshot de variação/custo em `order_items` (`variant_id`, `variant_label`, `unit_cost`).

Sempre que os modelos em `app/models.py` mudarem, gere uma nova migration em vez de editar o banco manualmente:

```powershell
flask --app run.py db migrate -m "descricao da alteracao"
flask --app run.py db upgrade
```

Boas práticas seguidas neste projeto (mantenha ao criar novas migrations):

- Use `with op.batch_alter_table("tabela", schema=None) as batch_op:` para `add_column`/`drop_column`/índices. Isso garante compatibilidade tanto com SQLite (usado em desenvolvimento) quanto com MariaDB/MySQL (usado em produção).
- Toda migration deve ter `downgrade()` funcional e simétrico ao `upgrade()`.
- Depois de gerar a migration com `db migrate`, sempre revise o arquivo gerado antes de aplicar — o Alembic às vezes não detecta `server_default` ou índices automaticamente.

Em produção, rode somente:

```powershell
flask --app run.py check-db
flask --app run.py db upgrade
flask --app run.py seed-admin
python serve.py
```

## Solução de problemas

**Ao abrir o site, cai direto numa tela de login/cadastro em vez da página de apresentação.**
Esse era um bug de rotas conflitantes corrigido nesta versão: o blueprint do painel registrava a mesma URL `/` que a landing page, e o Flask sempre entregava `/` para a primeira rota cadastrada (o painel, que exige login). A correção foi isolar todo o painel sob `/painel` (`url_prefix="/painel"`), deixando `/` livre e exclusivo para a landing page. Se isso ainda ocorrer, confirme que está rodando esta versão do código e limpe o cache do navegador.

**Erro `OperationalError: no such table` ao abrir o app.**
O banco ainda não foi criado/migrado. Rode `flask --app run.py db upgrade` (ou `init-db` em ambiente novo sem histórico de migrations).

**Erro de conexão recusada com MariaDB.**
Confira se o serviço do MariaDB está no ar e se `DATABASE_URL` no `.env` aponta para host/porta/usuário/senha corretos. `flask --app run.py check-db` testa a conexão isoladamente.

**Upload de imagem falha com erro 413.**
O arquivo passou do limite configurado em `MAX_UPLOAD_MB` (16 MB por padrão). Aumente essa variável no `.env` se precisar de arquivos maiores.

**Quero ver os pedidos de todas as lojas, não só de uma loja.**
Use o super admin e acesse "Pedidos da plataforma" no menu lateral (`/painel/admin/pedidos`). Essa tela tem filtro por status.

**Lojista vencido vê uma página em branco em vez da tela "assine agora".**
Esse era outro bug de template: a tela de bloqueio (`subscription/blocked.html`) usava o bloco `public_content` do layout, mas esse bloco só é renderizado para visitantes não autenticados — e quem vê essa tela está sempre logado (precisa estar autenticado para ter assinatura vencida). O resultado era o painel com sidebar e nenhum conteúdo. Corrigido trocando para o bloco `content`, que é o usado para qualquer usuário autenticado.
