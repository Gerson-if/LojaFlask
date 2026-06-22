import re
import secrets
import string
from functools import wraps
from pathlib import Path

from flask import abort, current_app, flash, redirect, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename


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
