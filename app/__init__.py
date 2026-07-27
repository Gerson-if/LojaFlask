import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config import CONFIG_BY_NAME

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Entre para continuar."


def create_app(config_name=None):
    load_dotenv()

    config_name = config_name or os.getenv("FLASK_ENV") or os.getenv("APP_ENV") or "development"
    app = Flask(__name__, instance_relative_config=True)
    config_class = CONFIG_BY_NAME.get(config_name, CONFIG_BY_NAME["development"])
    app.config.from_object(config_class)
    if hasattr(config_class, "init_app"):
        config_class.init_app(app)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_globals():
        return {"now": datetime.utcnow}

    # ── Subscription context processor ────────────────────────────────────────
    from .subscription import subscription_context_processor
    app.context_processor(subscription_context_processor)
    # ─────────────────────────────────────────────────────────────────────────

    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.storefront import storefront_bp
    from .subscription import subscription_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(storefront_bp)
    app.register_blueprint(subscription_bp)

    # ── Landing page — raiz do site ───────────────────────────────────────────
    # IMPORTANTE: o blueprint do dashboard usa url_prefix="/painel", então não
    # existe mais conflito de URL "/" entre a landing e o painel logado.
    # Usuário autenticado que acessa "/" vai pro painel (dashboard.index).
    # Usuário não autenticado vê a landing page.
    from flask import redirect, url_for
    from flask_login import current_user

    @app.get("/")
    def landing():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return render_template("landing.html")
    # ─────────────────────────────────────────────────────────────────────────

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    register_error_handlers(app)
    register_cli(app)
    return app


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(error):
        return (
            render_template(
                "errors/error.html",
                status_code=403,
                title="Acesso negado",
                message="Você não tem permissão para acessar esta área.",
            ),
            403,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            render_template(
                "errors/error.html",
                status_code=404,
                title="Página não encontrada",
                message="A rota acessada não existe ou foi removida.",
            ),
            404,
        )

    @app.errorhandler(503)
    def store_unavailable(error):
        from .models import Store

        # `error.description` carrega a `Store` quando o 503 vem do bloqueio
        # de inadimplência (ver subscription.require_active_storefront) —
        # assim a página usa a identidade visual daquela loja (logo, cores)
        # em vez de um erro genérico. Em qualquer outro 503 (ex.: falha
        # inesperada do servidor), `description` não é uma Store e a página
        # cai de volta no visual neutro padrão.
        store = error.description if isinstance(error.description, Store) else None
        return (
            render_template("errors/store_unavailable.html", store=store),
            503,
        )

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(error):
        return (
            render_template(
                "errors/error.html",
                status_code=413,
                title="Arquivo muito grande",
                message="O arquivo enviado ultrapassa o limite configurado para uploads.",
            ),
            413,
        )

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            return (
                render_template(
                    "errors/error.html",
                    status_code=error.code or 500,
                    title=error.name or "Erro",
                    message=error.description or "Não foi possível concluir a solicitação.",
                ),
                error.code or 500,
            )
        app.logger.exception("Unhandled exception")
        return (
            render_template(
                "errors/error.html",
                status_code=500,
                title="Algo deu errado",
                message="Não foi possível concluir a operação. Tente novamente em instantes.",
            ),
            500,
        )


def register_cli(app):
    from sqlalchemy import text
    from werkzeug.security import generate_password_hash

    from .models import User

    @app.cli.command("init-db")
    def init_db():
        """Cria tabelas sem migrations e garante o super admin inicial."""
        db.create_all()
        seed_admin()
        print("Banco inicializado com sucesso.")

    @app.cli.command("seed-admin")
    def seed_admin_command():
        """Garante o super admin inicial depois de uma migration."""
        seed_admin()
        print("Super admin verificado com sucesso.")

    @app.cli.command("check-db")
    def check_db():
        """Verifica se a aplicação consegue conectar no banco configurado."""
        db.session.execute(text("SELECT 1"))
        print("Conexão com o banco OK.")

    def seed_admin():
        email = os.getenv("ADMIN_EMAIL", "admin@lojafacil.com").lower()
        if not User.query.filter_by(email=email).first():
            user = User(
                name=os.getenv("ADMIN_NAME", "Super Admin"),
                email=email,
                password_hash=generate_password_hash(
                    os.getenv("ADMIN_PASSWORD", "admin123")
                ),
                phone="",
                role="superadmin",
                active=True,
            )
            db.session.add(user)
            db.session.commit()
