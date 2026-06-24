from datetime import datetime
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
    OrderItem,
    Product,
    ProductImage,
    Store,
    StoreBanner,
    User,
)
from ..utils import (
    delete_upload_folder,
    delete_uploaded_file,
    ensure_store_upload_dirs,
    lojista_required,
    only_digits,
    save_upload,
    store_upload_prefix,
    superadmin_required,
)

dashboard_bp = Blueprint("dashboard", __name__)


def _month_labels(months=6):
    today = datetime.utcnow()
    labels = []
    for offset in range(months - 1, -1, -1):
        month = today.month - offset
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        labels.append((year, month, f"{month:02d}/{str(year)[-2:]}"))
    return labels


def _monthly_order_chart(orders, months=6):
    labels = _month_labels(months)
    rows = []
    for year, month, label in labels:
        month_orders = [
            order for order in orders if order.created_at.year == year and order.created_at.month == month
        ]
        revenue = sum((order.total or Decimal("0.00")) for order in month_orders)
        rows.append({"label": label, "count": len(month_orders), "revenue": revenue})
    max_count = max([row["count"] for row in rows] or [1]) or 1
    max_revenue = max([row["revenue"] for row in rows] or [Decimal("1.00")]) or Decimal("1.00")
    for row in rows:
        row["count_percent"] = int((row["count"] / max_count) * 100) if max_count else 0
        row["revenue_percent"] = int((row["revenue"] / max_revenue) * 100) if max_revenue else 0
    return rows


def _monthly_creation_chart(items, months=6):
    labels = _month_labels(months)
    rows = []
    for year, month, label in labels:
        count = len([item for item in items if item.created_at.year == year and item.created_at.month == month])
        rows.append({"label": label, "count": count})
    max_count = max([row["count"] for row in rows] or [1]) or 1
    for row in rows:
        row["count_percent"] = int((row["count"] / max_count) * 100) if max_count else 0
    return rows


def _money_from_form(value, default="0"):
    try:
        money = Decimal(value or default)
    except (InvalidOperation, ValueError):
        raise ValueError("Informe valores monetários válidos.")
    if money < 0:
        raise ValueError("Valores monetários não podem ser negativos.")
    return money.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

@dashboard_bp.route("/")
@login_required
def index():
    if current_user.is_superadmin():
        lojistas = User.query.filter_by(role="lojista").order_by(User.created_at.desc()).all()
        stores_query = Store.query.order_by(Store.created_at.desc()).all()
        products_total = Product.query.count()
        customers_total = Customer.query.count()
        active_users = len([user for user in lojistas if user.active])
        suspended_users = len(lojistas) - active_users
        top_stores = sorted(
            stores_query,
            key=lambda store: (len(store.products), len(store.customers)),
            reverse=True,
        )[:5]
        chart_rows = _monthly_creation_chart(stores_query)
        return render_template(
            "admin/index.html",
            users=len(lojistas),
            stores=len(stores_query),
            products_total=products_total,
            customers_total=customers_total,
            active_users=active_users,
            suspended_users=suspended_users,
            top_stores=top_stores,
            chart_rows=chart_rows,
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
    all_orders = Order.query.filter_by(store_id=store.id).order_by(Order.created_at.desc()).all()
    low_stock = (
        Product.query.filter(Product.store_id == store.id, Product.stock <= 5)
        .order_by(Product.stock.asc(), Product.name)
        .limit(5)
        .all()
    )
    stats = {
        "products": Product.query.filter_by(store_id=store.id).count(),
        "orders": len(all_orders),
        "customers": Customer.query.filter_by(store_id=store.id).count(),
        "revenue": db.session.query(db.func.coalesce(db.func.sum(Order.total), 0))
        .filter(Order.store_id == store.id, Order.status == "Entregue")
        .scalar(),
        "pending_orders": len([order for order in all_orders if order.status == "Pendente"]),
        "active_products": Product.query.filter_by(store_id=store.id).filter(Product.status != "inativo").count(),
    }
    status_rows = []
    for status in ["Pendente", "Confirmado", "Enviado", "Entregue", "Cancelado"]:
        count = len([order for order in all_orders if order.status == status])
        status_rows.append({"label": status, "count": count})
    max_status = max([row["count"] for row in status_rows] or [1]) or 1
    for row in status_rows:
        row["percent"] = int((row["count"] / max_status) * 100) if max_status else 0
    return render_template(
        "dashboard/index.html",
        store=store,
        orders=orders,
        stats=stats,
        chart_rows=_monthly_order_chart(all_orders),
        status_rows=status_rows,
        low_stock=low_stock,
    )


# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------

@dashboard_bp.route("/produtos")
@login_required
@lojista_required
def products():
    store = current_user.store
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category_id", type=int)
    selected_product_id = request.args.get("edit", type=int)

    query = Product.query.filter_by(store_id=store.id)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category_id:
        query = query.filter_by(category_id=category_id)

    selected_product = None
    if selected_product_id:
        selected_product = Product.query.filter_by(
            id=selected_product_id, store_id=store.id
        ).first()
        # Se o produto não existe ou não pertence à loja, ignora silenciosamente
        # (não lança 404 para não quebrar a página de listagem)

    return render_template(
        "dashboard/products.html",
        products=query.order_by(Product.created_at.desc()).all(),
        categories=Category.query.filter_by(store_id=store.id).order_by(Category.name).all(),
        selected_product=selected_product,
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
    product = Product.query.filter_by(
        id=product_id, store_id=current_user.store.id
    ).first_or_404()

    # GET: redireciona para o drawer na listagem em vez de abrir página separada
    if request.method == "GET":
        return redirect(url_for(
            "dashboard.products",
            edit=product_id,
            q=request.args.get("q", ""),
            category_id=request.args.get("category_id", ""),
        ))

    return product_form(product)


def product_form(product=None):
    store = current_user.store
    ensure_store_upload_dirs(store)
    categories = Category.query.filter_by(store_id=store.id).order_by(Category.name).all()

    if request.method == "POST":
        data = request.form
        target = product or Product(store_id=store.id)
        target.name = data.get("name", "").strip()
        target.description = data.get("description", "").strip()
        target.category_id = data.get("category_id", type=int) or None

        # Validação de preços
        try:
            target.price = _money_from_form(data.get("price"))
            target.sale_price = (
                _money_from_form(data.get("sale_price")) if data.get("sale_price") else None
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

        target.stock = max(0, data.get("stock", type=int) or 0)
        target.status = (
            data.get("status")
            if data.get("status") in {"ativo", "destaque", "inativo"}
            else "ativo"
        )

        # Validação do nome
        if not target.name:
            flash("Informe o nome do produto.", "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

        if not product:
            db.session.add(target)
            db.session.flush()

        # Upload de imagens
        image_paths = []
        try:
            for file_storage in request.files.getlist("image_files"):
                saved_path = save_upload(file_storage, store_upload_prefix(store), "products")
                if saved_path:
                    image_paths.append(saved_path)
        except ValueError as exc:
            for image_path in image_paths:
                delete_uploaded_file(image_path)
            db.session.rollback()
            flash(str(exc), "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

        old_image_paths = [image.image_url for image in target.images]
        if image_paths:
            target.images.clear()
            for position, image_url in enumerate(image_paths):
                target.images.append(ProductImage(image_url=image_url, position=position))

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            for image_path in image_paths:
                delete_uploaded_file(image_path)
            flash("Não foi possível salvar o produto. Revise os dados e tente novamente.", "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

        if image_paths:
            for image_url in old_image_paths:
                delete_uploaded_file(image_url)

        flash("Produto salvo.", "success")
        return redirect(url_for("dashboard.products"))

    # GET — página de criação de novo produto
    return render_template("dashboard/product_form.html", product=product, categories=categories)


@dashboard_bp.route("/produtos/<int:product_id>/excluir", methods=["POST"])
@login_required
@lojista_required
def product_delete(product_id):
    product = Product.query.filter_by(
        id=product_id, store_id=current_user.store.id
    ).first_or_404()
    image_paths = [image.image_url for image in product.images]
    OrderItem.query.filter_by(product_id=product.id).update({"product_id": None})
    db.session.delete(product)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível excluir o produto agora.", "danger")
        return redirect(url_for("dashboard.products"))
    for image_path in image_paths:
        delete_uploaded_file(image_path)
    flash("Produto excluído.", "success")
    return redirect(url_for("dashboard.products"))


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------

@dashboard_bp.route("/categorias", methods=["GET", "POST"])
@login_required
@lojista_required
def categories():
    store = current_user.store
    if request.method == "POST":
        category_id = request.form.get("id", type=int)
        category = (
            Category.query.filter_by(id=category_id, store_id=store.id).first()
            if category_id
            else Category(store_id=store.id)
        )
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
    category = Category.query.filter_by(
        id=category_id, store_id=current_user.store.id
    ).first_or_404()
    Product.query.filter_by(category_id=category.id).update({"category_id": None})
    db.session.delete(category)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível excluir a categoria agora.", "danger")
        return redirect(url_for("dashboard.categories"))
    flash("Categoria excluída e produtos desvinculados.", "success")
    return redirect(url_for("dashboard.categories"))


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------

@dashboard_bp.route("/pedidos")
@login_required
@lojista_required
def orders():
    status = request.args.get("status", "")
    query = Order.query.filter_by(store_id=current_user.store.id)
    if status:
        query = query.filter_by(status=status)
    return render_template(
        "dashboard/orders.html",
        orders=query.order_by(Order.created_at.desc()).all(),
    )


@dashboard_bp.route("/pedidos/<int:order_id>", methods=["GET", "POST"])
@login_required
@lojista_required
def order_detail(order_id):
    order = Order.query.filter_by(
        id=order_id, store_id=current_user.store.id
    ).first_or_404()
    if request.method == "POST":
        status = request.form.get("status", order.status)
        order.status = (
            status
            if status in {"Pendente", "Confirmado", "Enviado", "Entregue", "Cancelado"}
            else order.status
        )
        db.session.commit()
        flash("Status atualizado.", "success")
        return redirect(url_for("dashboard.order_detail", order_id=order.id))
    return render_template("dashboard/order_detail.html", order=order)


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------

@dashboard_bp.route("/clientes", methods=["GET", "POST"])
@login_required
@lojista_required
def customers():
    store = current_user.store
    if request.method == "POST":
        customer_id = request.form.get("id", type=int)
        customer = (
            Customer.query.filter_by(id=customer_id, store_id=store.id).first()
            if customer_id
            else Customer(store_id=store.id)
        )
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
    return render_template(
        "dashboard/customers.html",
        customers=query.order_by(Customer.name).all(),
    )


@dashboard_bp.route("/clientes/<int:customer_id>/excluir", methods=["POST"])
@login_required
@lojista_required
def customer_delete(customer_id):
    customer = Customer.query.filter_by(
        id=customer_id, store_id=current_user.store.id
    ).first_or_404()
    Order.query.filter_by(customer_id=customer.id).update({"customer_id": None})
    db.session.delete(customer)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível excluir o cliente agora.", "danger")
        return redirect(url_for("dashboard.customers"))
    flash("Cliente excluído.", "success")
    return redirect(url_for("dashboard.customers"))


# ---------------------------------------------------------------------------
# Loja / Configurações
# ---------------------------------------------------------------------------

@dashboard_bp.route("/loja/configuracoes", methods=["GET", "POST"])
@login_required
@lojista_required
def store_settings():
    store = current_user.store
    ensure_store_upload_dirs(store)
    if request.method == "POST":
        store.name = request.form.get("name", "").strip()
        store.description = request.form.get("description", "").strip()
        store.whatsapp = only_digits(request.form.get("whatsapp"))
        store.city = request.form.get("city", "").strip()
        store.instagram_url = request.form.get("instagram_url", "").strip()
        store.facebook_url = request.form.get("facebook_url", "").strip()
        store.tiktok_url = request.form.get("tiktok_url", "").strip()
        try:
            uploaded_logo = save_upload(
                request.files.get("logo_file"), store_upload_prefix(store), "branding"
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template("dashboard/store_settings.html", store=store)
        old_logo_url = store.logo_url
        if uploaded_logo:
            store.logo_url = uploaded_logo
        store.primary_color = request.form.get("primary_color") or "#4f46e5"
        store.secondary_color = request.form.get("secondary_color") or "#06b6d4"
        banner_paths = []
        try:
            for file_storage in request.files.getlist("banner_files"):
                saved_path = save_upload(file_storage, store_upload_prefix(store), "banners")
                if saved_path:
                    banner_paths.append(saved_path)
        except ValueError as exc:
            for banner_path in banner_paths:
                delete_uploaded_file(banner_path)
            if uploaded_logo and uploaded_logo != old_logo_url:
                delete_uploaded_file(uploaded_logo)
            db.session.rollback()
            flash(str(exc), "danger")
            return render_template("dashboard/store_settings.html", store=store)
        old_banner_paths = [banner.image_url for banner in store.banners]
        if banner_paths:
            store.banners.clear()
            for position, image_url in enumerate(banner_paths):
                store.banners.append(StoreBanner(image_url=image_url, position=position))
        if not store.name:
            flash("Informe o nome da loja.", "danger")
            return render_template("dashboard/store_settings.html", store=store)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if uploaded_logo and uploaded_logo != old_logo_url:
                delete_uploaded_file(uploaded_logo)
            for banner_path in banner_paths:
                delete_uploaded_file(banner_path)
            flash("Não foi possível salvar as configurações. Revise os dados e tente novamente.", "danger")
            return render_template("dashboard/store_settings.html", store=store)
        if uploaded_logo and old_logo_url:
            delete_uploaded_file(old_logo_url)
        if banner_paths:
            for banner_path in old_banner_paths:
                delete_uploaded_file(banner_path)
        flash("Configurações salvas.", "success")
        return redirect(url_for("dashboard.store_settings"))
    return render_template("dashboard/store_settings.html", store=store)


@dashboard_bp.route("/loja/logo/excluir", methods=["POST"])
@login_required
@lojista_required
def store_logo_delete():
    store = current_user.store
    logo_url = store.logo_url
    store.logo_url = None
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível remover a logo agora.", "danger")
        return redirect(url_for("dashboard.store_settings"))
    delete_uploaded_file(logo_url)
    flash("Logo removida.", "success")
    return redirect(url_for("dashboard.store_settings"))


@dashboard_bp.route("/loja/banners/<int:banner_id>/excluir", methods=["POST"])
@login_required
@lojista_required
def store_banner_delete(banner_id):
    banner = StoreBanner.query.filter_by(
        id=banner_id, store_id=current_user.store.id
    ).first_or_404()
    banner_url = banner.image_url
    db.session.delete(banner)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível remover o banner agora.", "danger")
        return redirect(url_for("dashboard.store_settings"))
    delete_uploaded_file(banner_url)
    flash("Banner removido.", "success")
    return redirect(url_for("dashboard.store_settings"))


# ---------------------------------------------------------------------------
# Admin — Lojistas
# ---------------------------------------------------------------------------

@dashboard_bp.route("/admin/lojistas")
@login_required
@superadmin_required
def admin_users():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role="lojista")
    if q:
        query = query.filter(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    return render_template(
        "admin/users.html",
        users=query.order_by(User.created_at.desc()).all(),
    )


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


@dashboard_bp.route("/admin/lojistas/<int:user_id>/excluir", methods=["POST"])
@login_required
@superadmin_required
def admin_user_delete(user_id):
    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    store = user.store
    upload_prefix = store_upload_prefix(store) if store else None
    if store:
        db.session.delete(store)
    db.session.delete(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Não foi possível excluir o lojista agora.", "danger")
        return redirect(url_for("dashboard.admin_users"))
    if upload_prefix:
        delete_upload_folder(upload_prefix)
    flash("Lojista excluído.", "success")
    return redirect(url_for("dashboard.admin_users"))


@dashboard_bp.route("/admin/pedidos")
@login_required
@superadmin_required
def admin_orders():
    return render_template(
        "admin/orders.html",
        orders=Order.query.order_by(Order.created_at.desc()).all(),
    )