import re
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import abort, current_app, flash, redirect, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename


# ── Segurança de conta ───────────────────────────────────────────────────────
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 8


def validate_password_strength(password):
    """Política de senha: mínimo 8 caracteres, com ao menos uma letra e um
    número. Retorna None se a senha é válida, ou uma mensagem de erro clara
    para mostrar ao usuário."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres."
    if not re.search(r"[A-Za-z]", password):
        return "A senha precisa conter ao menos uma letra."
    if not re.search(r"\d", password):
        return "A senha precisa conter ao menos um número."
    return None


def register_failed_login(user):
    """Incrementa o contador de tentativas falhas e bloqueia temporariamente
    a conta se o limite for atingido. Chamado pela rota de login a cada
    tentativa com senha incorreta."""
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)


def register_successful_login(user):
    """Zera o contador de tentativas falhas e registra o horário do login."""
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()


def lockout_minutes_left(user):
    """Minutos restantes de bloqueio (arredondado para cima), ou 0 se a
    conta não está bloqueada."""
    if not user.locked_until:
        return 0
    remaining = (user.locked_until - datetime.utcnow()).total_seconds()
    if remaining <= 0:
        return 0
    return int(remaining // 60) + 1
# ─────────────────────────────────────────────────────────────────────────────


def slugify(value):
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_-]+", "-", value)
    return re.sub(r"^-+|-+$", "", value) or "loja"


def only_digits(value):
    return re.sub(r"\D+", "", value or "")


def order_code():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def allowed_upload(filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return extension in current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]


def store_upload_prefix(store):
    return f"store-{store.id}"


def ensure_store_upload_dirs(store):
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    for folder in ("branding", "banners", "products"):
        upload_root.joinpath(store_upload_prefix(store), folder).mkdir(parents=True, exist_ok=True)


def save_upload(file_storage, *parts):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_upload(file_storage.filename):
        raise ValueError("Formato de arquivo não permitido. Use JPG, PNG, WEBP ou GIF.")

    filename = secure_filename(file_storage.filename)
    extension = filename.rsplit(".", 1)[-1].lower()
    unique_name = f"{secrets.token_hex(12)}.{extension}"
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target_dir = upload_root.joinpath(*[str(part) for part in parts]).resolve()
    if upload_root not in target_dir.parents and target_dir != upload_root:
        raise ValueError("Destino de upload inválido.")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / unique_name
    file_storage.save(target_path)

    relative_path = target_path.relative_to(upload_root).as_posix()
    return url_for("static", filename=f"uploads/{relative_path}")


def _uploaded_file_path(public_path):
    if not public_path or "/static/uploads/" not in public_path:
        return None
    relative = public_path.split("/static/uploads/", 1)[-1].split("?", 1)[0]
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target_path = upload_root.joinpath(relative).resolve()
    if upload_root not in target_path.parents and target_path != upload_root:
        return None
    return target_path


def delete_uploaded_file(public_path):
    target_path = _uploaded_file_path(public_path)
    if target_path and target_path.is_file():
        target_path.unlink()
        return True
    return False


def delete_upload_folder(*parts):
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target_dir = upload_root.joinpath(*[str(part) for part in parts]).resolve()
    if upload_root not in target_dir.parents and target_dir != upload_root:
        return False
    if not target_dir.exists():
        return False
    for path in sorted(target_dir.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    target_dir.rmdir()
    return True


def superadmin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin():
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def lojista_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.is_superadmin():
            flash("Super admin não possui loja própria.", "warning")
            return redirect(url_for("dashboard.index"))
        if not current_user.store:
            flash("Sua loja ainda não foi configurada.", "warning")
            return redirect(url_for("dashboard.index"))
        return view(*args, **kwargs)

    return wrapped
