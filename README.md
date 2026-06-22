# LojaFácil em Flask

Migração do sistema HTML/localStorage para uma aplicação Flask com banco relacional.

## O que foi migrado

- Login, cadastro de lojista e super admin.
- Painel do lojista com dashboard, produtos, categorias, clientes, pedidos e personalização da loja.
- Loja pública por slug em `/loja/<slug>`.
- Carrinho em sessão, checkout e registro de pedido no banco.
- Pedido com link pronto para WhatsApp.
- Painel super admin com lojistas, suspensão/reativação, redefinição de senha e pedidos da plataforma.

## Banco de dados

O app usa SQLAlchemy e aceita bancos compatíveis via `DATABASE_URL`.

Exemplo MariaDB/MySQL:

```env
DATABASE_URL=mysql+pymysql://lojafacil:senha@localhost/lojafacil?charset=utf8mb4
```

Para desenvolvimento sem MariaDB instalado, deixe `DATABASE_URL` vazio e o app usa SQLite local em `instance/lojafacil.db`.

Tabelas modeladas:

- `users`: lojistas e super admin.
- `stores`: loja de cada lojista.
- `store_banners`: banners da loja.
- `categories`: categorias por loja.
- `products`: catálogo por loja.
- `product_images`: imagens dos produtos.
- `customers`: clientes por loja.
- `orders`: pedidos por loja.
- `order_items`: itens dos pedidos.

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

## Rotina segura de atualização

Sempre que os modelos mudarem:

```powershell
flask --app run.py db migrate -m "descricao da alteracao"
flask --app run.py db upgrade
```

Em produção, rode somente:

```powershell
flask --app run.py check-db
flask --app run.py db upgrade
flask --app run.py seed-admin
python serve.py
```
# LojaFlask
