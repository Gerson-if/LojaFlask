from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db
from ..models import Store, User
from ..utils import ensure_store_upload_dirs, only_digits, slugify

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("E-mail ou senha inválidos.", "danger")
        elif not user.active:
            flash("Sua conta está suspensa. Fale com o suporte.", "danger")
        else:
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
        if not all([name, store_name, email, password]) or len(password) < 6:
            flash("Preencha os campos obrigatórios e use senha com 6+ caracteres.", "danger")
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
        )
        store = Store(
            owner=user,
            name=store_name,
            slug=slug,
            whatsapp=phone,
            description="",
            city="",
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
