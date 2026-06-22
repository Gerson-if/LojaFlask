from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .. import db
from ..models import (
    Category,
    Customer,
    Order,
    Product,
    ProductImage,
    Store,
    StoreBanner,
    User,
)
from ..utils import lojista_required, only_digits, save_upload, superadmin_required

dashboard_bp = Blueprint("dashboard", __name__)


def _money_from_form(value, default="0"):
    try:
        money = Decimal(value or default)
    except (InvalidOperation, ValueError):
        raise ValueError("Informe valores monetários válidos.")
    if money < 0:
        raise ValueError("Valores monetários não podem ser negativos.")
    return money.quantize(Decimal("0.01"))


@dashboard_bp.route("/")
@login_required
def index():
    if current_user.is_superadmin():
        users = User.query.filter_by(role="lojista").count()
        stores = Store.query.count()
        orders = Order.query.count()
        revenue = db.session.query(db.func.coalesce(db.func.sum(Order.total), 0)).filter(
            Order.status == "Entregue"
        ).scalar()
        return render_template(
            "admin/index.html", users=users, stores=stores, orders=orders, revenue=revenue
        )

    store = current_user.store
    if not store:
        flash("Sua loja ainda não foi configurada. Complete o cadastro para começar.", "warning")
        stats = {"products": 0, "orders": 0, "customers": 0, "revenue": Decimal("0.00")}
        return render_template("dashboard/index.html", store=None, orders=[], stats=stats)

    orders = (
        Order.query.filter_by(store_id=store.id)
        .order_by(Order.created_at.desc())
        .limit(8)
        .all()
    )
    stats = {
        "products": Product.query.filter_by(store_id=store.id).count(),
        "orders": Order.query.filter_by(store_id=store.id).count(),
        "customers": Customer.query.filter_by(store_id=store.id).count(),
        "revenue": db.session.query(db.func.coalesce(db.func.sum(Order.total), 0))
        .filter(Order.store_id == store.id, Order.status == "Entregue")
        .scalar(),
    }
    return render_template("dashboard/index.html", store=store, orders=orders, stats=stats)


@dashboard_bp.route("/produtos")
@login_required
@lojista_required
def products():
    store = current_user.store
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category_id", type=int)
    query = Product.query.filter_by(store_id=store.id)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category_id:
        query = query.filter_by(category_id=category_id)
    return render_template(
        "dashboard/products.html",
        products=query.order_by(Product.created_at.desc()).all(),
        categories=Category.query.filter_by(store_id=store.id).order_by(Category.name).all(),
    )


@dashboard_bp.route("/produtos/novo", methods=["GET", "POST"])
@login_required
@lojista_required
def product_new():
    return product_form()


@dashboard_bp.route("/produtos/<int:product_id>/editar", methods=["GET", "POST"])
@login_required
@lojista_required
def product_edit(product_id):
    product = Product.query.filter_by(id=product_id, store_id=current_user.store.id).first_or_404()
    return product_form(product)


def product_form(product=None):
    store = current_user.store
    categories = Category.query.filter_by(store_id=store.id).order_by(Category.name).all()
    if request.method == "POST":
        data = request.form
        target = product or Product(store_id=store.id)
        target.name = data.get("name", "").strip()
        target.description = data.get("description", "").strip()
        target.category_id = data.get("category_id", type=int) or None
        try:
            target.price = _money_from_form(data.get("price"))
            target.sale_price = (
                _money_from_form(data.get("sale_price")) if data.get("sale_price") else None
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(
                "dashboard/product_form.html", product=target, categories=categories
            )
        target.stock = max(0, data.get("stock", type=int) or 0)
        target.status = data.get("status") if data.get("status") in {"ativo", "destaque", "inativo"} else "ativo"
        if not target.name:
            flash("Informe o nome do produto.", "danger")
        else:
            if not product:
                db.session.add(target)
                db.session.flush()
            image_paths = []
            try:
                for file_storage in request.files.getlist("image_files"):
                    saved_path = save_upload(file_storage, f"store-{store.id}", "products")
                    if saved_path:
                        image_paths.append(saved_path)
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "danger")
                return render_template(
                    "dashboard/product_form.html", product=target, categories=categories
                )
            if image_paths:
                target.images.clear()
                for position, image_url in enumerate(image_paths):
                    target.images.append(ProductImage(image_url=image_url, position=position))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar o produto. Revise os dados e tente novamente.", "danger")
                return render_template(
                    "dashboard/product_form.html", product=target, categories=categories
                )
            flash("Produto salvo.", "success")
            return redirect(url_for("dashboard.products"))
    return render_template("dashboard/product_form.html", product=product, categories=categories)


@dashboard_bp.route("/produtos/<int:product_id>/excluir", methods=["POST"])
@login_required
@lojista_required
def product_delete(product_id):
    product = Product.query.filter_by(id=product_id, store_id=current_user.store.id).first_or_404()
    db.session.delete(product)
    db.session.commit()
    flash("Produto excluído.", "success")
    return redirect(url_for("dashboard.products"))


@dashboard_bp.route("/categorias", methods=["GET", "POST"])
@login_required
@lojista_required
def categories():
    store = current_user.store
    if request.method == "POST":
        category_id = request.form.get("id", type=int)
        category = Category.query.filter_by(id=category_id, store_id=store.id).first() if category_id else Category(store_id=store.id)
        category.name = request.form.get("name", "").strip()
        category.icon = request.form.get("icon", "").strip()
        if not category.name:
            flash("Informe o nome da categoria.", "danger")
        else:
            db.session.add(category)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Já existe uma categoria com esse nome.", "danger")
                return redirect(url_for("dashboard.categories"))
            flash("Categoria salva.", "success")
            return redirect(url_for("dashboard.categories"))
    return render_template(
        "dashboard/categories.html",
        categories=Category.query.filter_by(store_id=store.id).order_by(Category.name).all(),
    )


@dashboard_bp.route("/categorias/<int:category_id>/excluir", methods=["POST"])
@login_required
@lojista_required
def category_delete(category_id):
    category = Category.query.filter_by(id=category_id, store_id=current_user.store.id).first_or_404()
    Product.query.filter_by(category_id=category.id).update({"category_id": None})
    db.session.delete(category)
    db.session.commit()
    flash("Categoria excluída e produtos desvinculados.", "success")
    return redirect(url_for("dashboard.categories"))


@dashboard_bp.route("/pedidos")
@login_required
@lojista_required
def orders():
    status = request.args.get("status", "")
    query = Order.query.filter_by(store_id=current_user.store.id)
    if status:
        query = query.filter_by(status=status)
    return render_template("dashboard/orders.html", orders=query.order_by(Order.created_at.desc()).all())


@dashboard_bp.route("/pedidos/<int:order_id>", methods=["GET", "POST"])
@login_required
@lojista_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, store_id=current_user.store.id).first_or_404()
    if request.method == "POST":
        status = request.form.get("status", order.status)
        order.status = status if status in {"Pendente", "Confirmado", "Enviado", "Entregue", "Cancelado"} else order.status
        db.session.commit()
        flash("Status atualizado.", "success")
        return redirect(url_for("dashboard.order_detail", order_id=order.id))
    return render_template("dashboard/order_detail.html", order=order)


@dashboard_bp.route("/clientes", methods=["GET", "POST"])
@login_required
@lojista_required
def customers():
    store = current_user.store
    if request.method == "POST":
        customer_id = request.form.get("id", type=int)
        customer = Customer.query.filter_by(id=customer_id, store_id=store.id).first() if customer_id else Customer(store_id=store.id)
        customer.name = request.form.get("name", "").strip()
        customer.phone = only_digits(request.form.get("phone"))
        customer.email = request.form.get("email", "").strip()
        customer.address = request.form.get("address", "").strip()
        if not customer.name or not customer.phone:
            flash("Informe nome e telefone.", "danger")
        else:
            db.session.add(customer)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Já existe um cliente com esse WhatsApp.", "danger")
                return redirect(url_for("dashboard.customers"))
            flash("Cliente salvo.", "success")
            return redirect(url_for("dashboard.customers"))
    q = request.args.get("q", "").strip()
    query = Customer.query.filter_by(store_id=store.id)
    if q:
        query = query.filter(Customer.name.ilike(f"%{q}%"))
    return render_template("dashboard/customers.html", customers=query.order_by(Customer.name).all())


@dashboard_bp.route("/clientes/<int:customer_id>/excluir", methods=["POST"])
@login_required
@lojista_required
def customer_delete(customer_id):
    customer = Customer.query.filter_by(id=customer_id, store_id=current_user.store.id).first_or_404()
    db.session.delete(customer)
    db.session.commit()
    flash("Cliente excluído.", "success")
    return redirect(url_for("dashboard.customers"))


@dashboard_bp.route("/loja/configuracoes", methods=["GET", "POST"])
@login_required
@lojista_required
def store_settings():
    store = current_user.store
    if request.method == "POST":
        store.name = request.form.get("name", "").strip()
        store.description = request.form.get("description", "").strip()
        store.whatsapp = only_digits(request.form.get("whatsapp"))
        store.city = request.form.get("city", "").strip()
        try:
            uploaded_logo = save_upload(request.files.get("logo_file"), f"store-{store.id}", "branding")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template("dashboard/store_settings.html", store=store)
        if uploaded_logo:
            store.logo_url = uploaded_logo
        store.primary_color = request.form.get("primary_color") or "#4f46e5"
        store.secondary_color = request.form.get("secondary_color") or "#06b6d4"
        banner_paths = []
        try:
            for file_storage in request.files.getlist("banner_files"):
                saved_path = save_upload(file_storage, f"store-{store.id}", "banners")
                if saved_path:
                    banner_paths.append(saved_path)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template("dashboard/store_settings.html", store=store)
        if banner_paths:
            store.banners.clear()
            for position, image_url in enumerate(banner_paths):
                store.banners.append(StoreBanner(image_url=image_url, position=position))
        if not store.name:
            flash("Informe o nome da loja.", "danger")
            return render_template("dashboard/store_settings.html", store=store)
        db.session.commit()
        flash("Configurações salvas.", "success")
        return redirect(url_for("dashboard.store_settings"))
    return render_template("dashboard/store_settings.html", store=store)


@dashboard_bp.route("/admin/lojistas")
@login_required
@superadmin_required
def admin_users():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role="lojista")
    if q:
        query = query.filter(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    return render_template("admin/users.html", users=query.order_by(User.created_at.desc()).all())


@dashboard_bp.route("/admin/lojistas/<int:user_id>/toggle", methods=["POST"])
@login_required
@superadmin_required
def admin_user_toggle(user_id):
    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    user.active = not user.active
    db.session.commit()
    flash("Status do lojista atualizado.", "success")
    return redirect(url_for("dashboard.admin_users"))


@dashboard_bp.route("/admin/lojistas/<int:user_id>/senha", methods=["POST"])
@login_required
@superadmin_required
def admin_user_password(user_id):
    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    password = request.form.get("password", "")
    if len(password) < 6:
        flash("Senha deve ter pelo menos 6 caracteres.", "danger")
    else:
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash("Senha atualizada.", "success")
    return redirect(url_for("dashboard.admin_users"))


@dashboard_bp.route("/admin/pedidos")
@login_required
@superadmin_required
def admin_orders():
    return render_template("admin/orders.html", orders=Order.query.order_by(Order.created_at.desc()).all())
