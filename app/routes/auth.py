from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..models import Store, User
from ..subscription import TRIAL_DAYS
from ..utils import (
    ensure_store_upload_dirs,
    lockout_minutes_left,
    only_digits,
    register_failed_login,
    register_successful_login,
    slugify,
    validate_password_strength,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.is_locked():
            minutes = lockout_minutes_left(user)
            flash(
                f"Conta temporariamente bloqueada por excesso de tentativas. "
                f"Tente novamente em {minutes} minuto{'s' if minutes != 1 else ''}.",
                "danger",
            )
        elif not user or not check_password_hash(user.password_hash, password):
            # Mensagem genérica de propósito: não revela se o e-mail existe
            # ou não, dificultando a enumeração de contas cadastradas.
            if user:
                register_failed_login(user)
                db.session.commit()
            flash("E-mail ou senha inválidos.", "danger")
        elif not user.active:
            flash("Sua conta está suspensa. Fale com o suporte.", "danger")
        else:
            register_successful_login(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("dashboard.index"))
    return render_template("auth/login.html")


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = only_digits(request.form.get("phone"))
        store_name = request.form.get("store_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not all([name, store_name, email, password]):
            flash("Preencha todos os campos obrigatórios.", "danger")
            return render_template("auth/register.html")

        password_error = validate_password_strength(password)
        if password_error:
            flash(password_error, "danger")
            return render_template("auth/register.html")

        if password != password_confirm:
            flash("As senhas não coincidem.", "danger")
            return render_template("auth/register.html")

        base_slug = slugify(store_name)
        slug = base_slug
        suffix = 2
        while Store.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        user = User(
            name=name,
            phone=phone,
            email=email,
            password_hash=generate_password_hash(password),
            role="lojista",
            active=True,
            password_changed_at=datetime.utcnow(),
        )
        store = Store(
            owner=user,
            name=store_name,
            slug=slug,
            whatsapp=phone,
            description="",
            city="",
            # ── Trial: 14 dias a partir do cadastro ──────────────────────
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS),
            subscription_active=False,
            # ─────────────────────────────────────────────────────────────
        )
        db.session.add_all([user, store])
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Este e-mail já está cadastrado.", "danger")
            return render_template("auth/register.html")
        ensure_store_upload_dirs(store)
        login_user(user)
        return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Você saiu da sua conta.", "success")
    return redirect(url_for("auth.login"))
