from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
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
    ProductVariant,
    Store,
    StoreBanner,
    SubscriptionPayment,
    User,
)
from ..subscription import require_active_subscription
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

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/painel")


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
# Index — superadmin e lojista (sem bloqueio de assinatura aqui; lojista com
# acesso expirado é redirecionado para subscription.blocked, mais abaixo)
# ---------------------------------------------------------------------------

@dashboard_bp.route("")
@login_required
def index():
    if current_user.is_superadmin():
        from ..subscription import PLAN_PRICE_MONTHLY, store_access_status

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

        # ── Métricas de assinatura/receita ──────────────────────────────
        trial_count = paid_count = expired_count = none_count = 0
        for store in stores_query:
            mode = store_access_status(store)["mode"]
            if mode == "trial":
                trial_count += 1
            elif mode == "paid":
                paid_count += 1
            elif mode == "expired":
                expired_count += 1
            else:
                none_count += 1

        mrr = Decimal(str(PLAN_PRICE_MONTHLY)) * paid_count
        total_revenue = db.session.query(
            db.func.coalesce(db.func.sum(SubscriptionPayment.amount), 0)
        ).filter(SubscriptionPayment.action == "renew").scalar() or Decimal("0.00")

        recent_payments = (
            SubscriptionPayment.query.filter_by(action="renew")
            .order_by(SubscriptionPayment.created_at.desc())
            .limit(8)
            .all()
        )

        # Segmentos do donut chart de status de assinatura (SVG, sem libs JS).
        # Circunferência do círculo usado no template (raio 60): 2*pi*60 ≈ 377.
        CIRCUMFERENCE = 377.0
        donut_data = [
            ("paid", paid_count, "#22c55e"),
            ("trial", trial_count, "#f59e0b"),
            ("expired", expired_count, "#ef4444"),
            ("none", none_count, "#cbd5e1"),
        ]
        total_for_donut = sum(count for _, count, _ in donut_data) or 1
        donut_segments = []
        offset_acc = 0.0
        for label, count, color in donut_data:
            if count <= 0:
                continue
            fraction = count / total_for_donut
            dash = fraction * CIRCUMFERENCE
            donut_segments.append({
                "label": label,
                "count": count,
                "color": color,
                "dash": round(dash, 2),
                "gap": round(CIRCUMFERENCE - dash, 2),
                "offset": round(-offset_acc, 2),
            })
            offset_acc += dash
        # ─────────────────────────────────────────────────────────────────

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
            trial_count=trial_count,
            paid_count=paid_count,
            expired_count=expired_count,
            none_count=none_count,
            mrr=mrr,
            total_revenue=total_revenue,
            recent_payments=recent_payments,
            donut_segments=donut_segments,
            total_for_donut=total_for_donut,
        )

    store = current_user.store
    if not store:
        flash("Sua loja ainda não foi configurada. Complete o cadastro para começar.", "warning")
        stats = {"products": 0, "orders": 0, "customers": 0, "revenue": Decimal("0.00")}
        return render_template("dashboard/index.html", store=None, orders=[], stats=stats)

    # Lojista com assinatura expirada (trial encerrado e sem pagamento) →
    # redireciona para a página de bloqueio
    from ..subscription import store_has_access
    if not store_has_access(store):
        return redirect(url_for("subscription.blocked"))

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
@require_active_subscription
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

    return render_template(
        "dashboard/products.html",
        products=query.order_by(Product.created_at.desc()).all(),
        categories=Category.query.filter_by(store_id=store.id).order_by(Category.name).all(),
        selected_product=selected_product,
    )


@dashboard_bp.route("/produtos/novo", methods=["GET", "POST"])
@login_required
@lojista_required
@require_active_subscription
def product_new():
    return product_form()


@dashboard_bp.route("/produtos/<int:product_id>/editar", methods=["GET", "POST"])
@login_required
@lojista_required
@require_active_subscription
def product_edit(product_id):
    product = Product.query.filter_by(
        id=product_id, store_id=current_user.store.id
    ).first_or_404()

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

        try:
            target.cost_price = (
                _money_from_form(data.get("cost_price")) if data.get("cost_price") else None
            )
            target.price = _money_from_form(data.get("price"))
            target.sale_price = (
                _money_from_form(data.get("sale_price")) if data.get("sale_price") else None
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

        # Variações (tamanho/cor) — listas paralelas indexadas pela mesma
        # posição: variant_id[i] (vazio = nova linha), variant_size[i],
        # variant_color[i], variant_stock[i], variant_price[i] (opcional).
        variant_ids = data.getlist("variant_id[]")
        variant_sizes = data.getlist("variant_size[]")
        variant_colors = data.getlist("variant_color[]")
        variant_stocks = data.getlist("variant_stock[]")
        variant_prices = data.getlist("variant_price[]")

        has_variant_rows = any(
            (variant_sizes[i].strip() if i < len(variant_sizes) else "")
            or (variant_colors[i].strip() if i < len(variant_colors) else "")
            for i in range(len(variant_ids))
        )

        # O campo de estoque do produto vem desabilitado no formulário quando
        # há variações (controle passa a ser por variação) — nesse caso o
        # navegador não envia o campo, então não sobrescrevemos o valor atual.
        if has_variant_rows:
            if not product:
                target.stock = 0
            # produto existente: mantém target.stock como está; total_stock
            # passa a refletir a soma das variações de qualquer forma.
        else:
            target.stock = max(0, data.get("stock", type=int) or 0)

        target.status = (
            data.get("status")
            if data.get("status") in {"ativo", "destaque", "inativo"}
            else "ativo"
        )

        if not target.name:
            flash("Informe o nome do produto.", "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

        if not product:
            db.session.add(target)
            db.session.flush()

        # Sincroniza variações: atualiza as existentes (por variant_id),
        # cria as novas (variant_id vazio) e remove as que não vieram mais
        # no formulário (lojista apagou a linha na tela). Usa uma query
        # direta por product_id em vez de depender do estado em memória de
        # `target.variants`, que pode não estar carregado nesse ponto.
        try:
            existing_variants_by_id = {
                v.id: v for v in ProductVariant.query.filter_by(product_id=target.id).all()
            }
            kept_variant_ids = set()
            for i in range(len(variant_ids)):
                size = (variant_sizes[i].strip() if i < len(variant_sizes) else "") or None
                color = (variant_colors[i].strip() if i < len(variant_colors) else "") or None
                if not size and not color:
                    continue  # linha vazia (sobrou no form sem dados) — ignora
                stock_raw = variant_stocks[i] if i < len(variant_stocks) else "0"
                try:
                    stock_value = max(0, int(stock_raw or 0))
                except ValueError:
                    stock_value = 0
                price_raw = variant_prices[i].strip() if i < len(variant_prices) else ""
                price_value = _money_from_form(price_raw) if price_raw else None

                existing_id_raw = variant_ids[i].strip() if i < len(variant_ids) else ""
                existing_id = int(existing_id_raw) if existing_id_raw.isdigit() else None
                variant = existing_variants_by_id.get(existing_id) if existing_id else None

                if variant:
                    variant.size = size
                    variant.color = color
                    variant.stock = stock_value
                    variant.price = price_value
                    kept_variant_ids.add(variant.id)
                else:
                    db.session.add(ProductVariant(
                        product_id=target.id, size=size, color=color,
                        stock=stock_value, price=price_value, position=i,
                    ))

            # Remove variações que existiam antes mas não vieram no form
            for variant_id, variant in existing_variants_by_id.items():
                if variant_id not in kept_variant_ids:
                    db.session.delete(variant)
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
            if product:
                return redirect(url_for("dashboard.products", edit=product.id))
            return redirect(url_for("dashboard.product_new"))

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

    return render_template("dashboard/product_form.html", product=product, categories=categories)


@dashboard_bp.route("/produtos/<int:product_id>/excluir", methods=["POST"])
@login_required
@lojista_required
@require_active_subscription
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
@require_active_subscription
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
@require_active_subscription
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
@require_active_subscription
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
@require_active_subscription
def order_detail(order_id):
    order = Order.query.filter_by(
        id=order_id, store_id=current_user.store.id
    ).first_or_404()
    if request.method == "POST":
        status = request.form.get("status", order.status)
        new_status = (
            status
            if status in {"Pendente", "Confirmado", "Enviado", "Entregue", "Cancelado"}
            else order.status
        )
        if new_status != order.status:
            order.status = new_status
            order.status_updated_at = datetime.utcnow()
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
@require_active_subscription
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
        digits = only_digits(q)
        if digits:
            query = query.filter(
                or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{digits}%"))
            )
        else:
            query = query.filter(Customer.name.ilike(f"%{q}%"))
    return render_template(
        "dashboard/customers.html",
        customers=query.order_by(Customer.name).all(),
    )


@dashboard_bp.route("/clientes/<int:customer_id>/excluir", methods=["POST"])
@login_required
@lojista_required
@require_active_subscription
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
@require_active_subscription
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
@require_active_subscription
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
@require_active_subscription
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
# Financeiro (lojista) — margem de lucro com base em preço de custo/venda
# ---------------------------------------------------------------------------

@dashboard_bp.route("/financeiro")
@login_required
@lojista_required
@require_active_subscription
def finance():
    store = current_user.store
    period_days = request.args.get("period", "30")
    try:
        period_days = int(period_days)
    except ValueError:
        period_days = 30
    period_days = period_days if period_days in (7, 30, 90, 365) else 30

    since = datetime.utcnow() - timedelta(days=period_days)

    orders = (
        Order.query.filter(
            Order.store_id == store.id,
            Order.status != "Cancelado",
            Order.created_at >= since,
        )
        .all()
    )
    order_ids = [o.id for o in orders]
    items = OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).all() if order_ids else []

    revenue = sum((item.subtotal for item in items), Decimal("0.00"))
    cost_total = Decimal("0.00")
    items_missing_cost = 0
    product_breakdown = {}  # product_id -> {"name", "qty", "revenue", "cost"}

    for item in items:
        # Prioriza o custo registrado no momento da venda (`unit_cost`); se
        # o item é antigo (vendido antes desta funcionalidade existir) e não
        # tem snapshot, cai para o custo atual cadastrado no produto — é uma
        # aproximação, sinalizada na UI via `items_missing_cost`.
        unit_cost = item.unit_cost
        if unit_cost is None and item.product is not None:
            unit_cost = item.product.cost_price
        if unit_cost is None:
            items_missing_cost += 1
            item_cost_total = None
        else:
            item_cost_total = unit_cost * item.quantity
            cost_total += item_cost_total

        key = item.product_id or f"deleted-{item.product_name}"
        row = product_breakdown.setdefault(
            key, {"name": item.product_name, "qty": 0, "revenue": Decimal("0.00"), "cost": Decimal("0.00"), "has_cost": True}
        )
        row["qty"] += item.quantity
        row["revenue"] += item.subtotal
        if item_cost_total is not None:
            row["cost"] += item_cost_total
        else:
            row["has_cost"] = False

    profit_total = revenue - cost_total
    margin_percent = (profit_total / revenue * 100) if revenue else None

    ranking = []
    for row in product_breakdown.values():
        profit = (row["revenue"] - row["cost"]) if row["has_cost"] else None
        margin = (profit / row["revenue"] * 100) if (profit is not None and row["revenue"]) else None
        ranking.append({**row, "profit": profit, "margin": margin})
    ranking.sort(key=lambda r: r["revenue"], reverse=True)

    products_without_cost = Product.query.filter_by(store_id=store.id, cost_price=None).count()

    return render_template(
        "dashboard/finance.html",
        period_days=period_days,
        revenue=revenue,
        cost_total=cost_total,
        profit_total=profit_total,
        margin_percent=margin_percent,
        items_missing_cost=items_missing_cost,
        ranking=ranking[:15],
        products_without_cost=products_without_cost,
        orders_count=len(orders),
    )


# ---------------------------------------------------------------------------
# Segurança da conta (lojista) — sem @require_active_subscription de
# propósito: o lojista precisa conseguir proteger a própria conta mesmo com
# acesso vencido (ex.: trocar senha após suspeitar de acesso indevido).
# ---------------------------------------------------------------------------

@dashboard_bp.route("/seguranca", methods=["GET", "POST"])
@login_required
@lojista_required
def security():
    from werkzeug.security import check_password_hash, generate_password_hash

    from ..utils import validate_password_strength

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        new_password_confirm = request.form.get("new_password_confirm", "")

        if not check_password_hash(current_user.password_hash, current_password):
            flash("Senha atual incorreta.", "danger")
        else:
            password_error = validate_password_strength(new_password)
            if password_error:
                flash(password_error, "danger")
            elif new_password != new_password_confirm:
                flash("As senhas não coincidem.", "danger")
            else:
                current_user.password_hash = generate_password_hash(new_password)
                current_user.password_changed_at = datetime.utcnow()
                db.session.commit()
                flash("Senha atualizada com sucesso.", "success")
                return redirect(url_for("dashboard.security"))

    return render_template(
        "dashboard/security.html",
        last_login_at=current_user.last_login_at,
        password_changed_at=current_user.password_changed_at,
    )


# ---------------------------------------------------------------------------
# Minha assinatura (lojista) — sem @require_active_subscription de propósito:
# o lojista precisa conseguir ver e renovar mesmo com acesso vencido.
# ---------------------------------------------------------------------------

@dashboard_bp.route("/assinatura")
@login_required
@lojista_required
def my_subscription():
    from ..subscription import PLAN_PRICE_MONTHLY, TRIAL_DAYS, store_access_status

    store = current_user.store
    status = store_access_status(store)
    payments = (
        SubscriptionPayment.query.filter_by(store_id=store.id)
        .order_by(SubscriptionPayment.created_at.desc())
        .all()
    )
    support_admin = (
        User.query.filter_by(role="superadmin", active=True)
        .filter(User.phone.isnot(None), User.phone != "")
        .first()
    )

    # Percentual do ciclo atual já decorrido, para a barra de progresso.
    # Trial: ciclo de TRIAL_DAYS dias. Pago: usa o período da renovação mais
    # recente (se houver) como referência de duração do ciclo; sem esse
    # histórico, assume 30 dias como aproximação razoável.
    progress_percent = None
    if status["mode"] == "trial" and status["days_left"] is not None:
        days_used = max(0, TRIAL_DAYS - status["days_left"])
        progress_percent = min(100, round(days_used / TRIAL_DAYS * 100))
    elif status["mode"] == "paid" and status["days_left"] is not None:
        last_renew = next((p for p in payments if p.action == "renew" and p.period_start and p.period_end), None)
        cycle_days = max((last_renew.period_end - last_renew.period_start).days, 1) if last_renew else 30
        days_used = max(0, cycle_days - status["days_left"])
        progress_percent = min(100, round(days_used / cycle_days * 100))

    return render_template(
        "dashboard/my_subscription.html",
        store=store,
        status=status,
        payments=payments,
        price=PLAN_PRICE_MONTHLY,
        trial_days=TRIAL_DAYS,
        progress_percent=progress_percent,
        support_phone=only_digits(support_admin.phone) if support_admin else None,
    )


# ---------------------------------------------------------------------------
# Admin — Lojistas (superadmin only, sem restrição de assinatura)
# ---------------------------------------------------------------------------

@dashboard_bp.route("/admin/lojistas")
@login_required
@superadmin_required
def admin_users():
    from ..subscription import store_access_status

    q = request.args.get("q", "").strip()
    account_filter = request.args.get("account", "")  # "active" | "suspended" | ""
    sub_filter = request.args.get("sub", "")  # "trial" | "paid" | "expired" | "none" | ""

    query = User.query.filter_by(role="lojista")
    if q:
        query = query.filter(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    if account_filter == "active":
        query = query.filter_by(active=True)
    elif account_filter == "suspended":
        query = query.filter_by(active=False)

    all_users = query.order_by(User.created_at.desc()).all()

    # Resumo geral (sobre TODOS os lojistas, não só o resultado filtrado) —
    # usado nos cards de contagem no topo da página.
    summary = {"active": 0, "suspended": 0, "trial": 0, "paid": 0, "expired": 0, "none": 0}
    rows = []
    for user in User.query.filter_by(role="lojista").all():
        status = store_access_status(user.store)
        summary["active" if user.active else "suspended"] += 1
        summary[status["mode"]] += 1

    for user in all_users:
        status = store_access_status(user.store)
        if sub_filter and status["mode"] != sub_filter:
            continue
        rows.append((user, status))

    return render_template(
        "admin/users.html",
        rows=rows,
        summary=summary,
        total_lojistas=summary["active"] + summary["suspended"],
        account_filter=account_filter,
        sub_filter=sub_filter,
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


@dashboard_bp.route("/admin/lojistas/<int:user_id>/desbloquear", methods=["POST"])
@login_required
@superadmin_required
def admin_unlock_user(user_id):
    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    flash(f"Conta de {user.name} desbloqueada.", "success")
    return redirect(request.referrer or url_for("dashboard.admin_users"))


@dashboard_bp.route("/admin/lojistas/<int:user_id>/senha", methods=["POST"])
@login_required
@superadmin_required
def admin_user_password(user_id):
    from ..utils import validate_password_strength

    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    password = request.form.get("password", "")
    password_error = validate_password_strength(password)
    if password_error:
        flash(password_error, "danger")
    else:
        user.password_hash = generate_password_hash(password)
        user.password_changed_at = datetime.utcnow()
        # Redefinir a senha é uma ação administrativa legítima — libera
        # qualquer bloqueio por tentativas anteriores, já que o lojista vai
        # receber a senha nova diretamente do superadmin.
        user.failed_login_attempts = 0
        user.locked_until = None
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


# ---------------------------------------------------------------------------
# Admin — Gerenciamento de Assinatura (superadmin only)
# ---------------------------------------------------------------------------

@dashboard_bp.route("/admin/lojistas/<int:user_id>/assinatura", methods=["POST"])
@login_required
@superadmin_required
def admin_subscription_manage(user_id):
    """
    Ação do superadmin sobre a assinatura de um lojista.
    Campo 'action' no form pode ser:
      - 'renew_1'  → renova por 1 mês a partir de hoje (ou de paid_until se ainda ativo)
      - 'renew_3'  → renova por 3 meses
      - 'renew_12' → renova por 12 meses
      - 'set_date' → define/corrige manualmente a data de vencimento (campo 'paid_until')
      - 'suspend'  → suspende imediatamente
    Campo opcional 'amount': valor cobrado nesta renovação (padrão = preço
    mensal vigente x número de meses). Campo opcional 'note': observação
    livre sobre o pagamento (ex.: forma de pagamento, referência do PIX).
    """
    from ..subscription import PLAN_PRICE_MONTHLY, as_aware

    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    store = user.store
    if not store:
        flash("Este lojista não possui loja cadastrada.", "warning")
        return redirect(url_for("dashboard.admin_users"))

    action = request.form.get("action", "")
    note = request.form.get("note", "").strip() or None

    MONTH_MAP = {"renew_1": 1, "renew_3": 3, "renew_12": 12}

    if action in MONTH_MAP:
        months = MONTH_MAP[action]
        now = datetime.now(timezone.utc)

        # Ponto de partida: se já tem paid_until no futuro, prolonga a partir dele
        current_paid_until = as_aware(store.paid_until)
        base = current_paid_until if current_paid_until and current_paid_until > now else now

        period_start = base
        period_end = base + timedelta(days=30 * months)

        amount_raw = request.form.get("amount", "").strip().replace(",", ".")
        try:
            amount = Decimal(amount_raw) if amount_raw else Decimal("0")
            if amount <= 0:
                amount = Decimal(str(PLAN_PRICE_MONTHLY)) * months
        except InvalidOperation:
            amount = Decimal(str(PLAN_PRICE_MONTHLY)) * months
        amount = amount.quantize(Decimal("0.01"))

        store.paid_until = period_end.replace(tzinfo=None)
        store.subscription_active = True
        db.session.add(
            SubscriptionPayment(
                store_id=store.id,
                action="renew",
                months=months,
                amount=amount,
                period_start=period_start.replace(tzinfo=None),
                period_end=period_end.replace(tzinfo=None),
                registered_by_id=current_user.id,
                note=note,
            )
        )
        db.session.commit()
        flash(
            f"Assinatura de {user.name} renovada por {months} mês(es). "
            f"Vence em {store.paid_until.strftime('%d/%m/%Y')}.",
            "success",
        )

    elif action == "set_date":
        date_raw = request.form.get("paid_until", "").strip()
        if not date_raw:
            flash("Informe uma data de vencimento válida.", "danger")
            return redirect(request.referrer or url_for("dashboard.admin_users"))
        try:
            new_date = datetime.strptime(date_raw, "%Y-%m-%d")
        except ValueError:
            flash("Data inválida. Use o seletor de data do formulário.", "danger")
            return redirect(request.referrer or url_for("dashboard.admin_users"))

        old_paid_until = store.paid_until
        # Fim do dia escolhido, para a loja continuar ativa até o fim daquela data
        new_date = new_date.replace(hour=23, minute=59, second=59)
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

        store.paid_until = new_date
        store.subscription_active = new_date >= now_naive

        note_text = note or "Data de vencimento ajustada manualmente pelo superadmin"
        if old_paid_until:
            note_text += f" (era {old_paid_until.strftime('%d/%m/%Y')})"
        db.session.add(
            SubscriptionPayment(
                store_id=store.id,
                action="renew",
                months=None,
                amount=None,
                period_start=now_naive,
                period_end=new_date,
                registered_by_id=current_user.id,
                note=note_text,
            )
        )
        db.session.commit()
        flash(
            f"Data de vencimento de {user.name} ajustada para {new_date.strftime('%d/%m/%Y')}.",
            "success",
        )

    elif action == "suspend":
        store.subscription_active = False
        db.session.add(
            SubscriptionPayment(
                store_id=store.id,
                action="suspend",
                registered_by_id=current_user.id,
                note=note,
            )
        )
        db.session.commit()
        flash(f"Assinatura de {user.name} suspensa imediatamente.", "warning")

    else:
        flash("Ação inválida.", "danger")

    return redirect(request.referrer or url_for("dashboard.admin_users"))


@dashboard_bp.route("/admin/lojistas/<int:user_id>/assinatura/historico")
@login_required
@superadmin_required
def admin_subscription_detail(user_id):
    """Histórico completo de assinatura de um lojista — usado pelo superadmin
    para auditar renovações/suspensões e ver o status atual em detalhe."""
    from ..subscription import store_access_status, PLAN_PRICE_MONTHLY

    user = User.query.filter_by(id=user_id, role="lojista").first_or_404()
    store = user.store
    if not store:
        flash("Este lojista não possui loja cadastrada.", "warning")
        return redirect(url_for("dashboard.admin_users"))

    payments = (
        SubscriptionPayment.query.filter_by(store_id=store.id)
        .order_by(SubscriptionPayment.created_at.desc())
        .all()
    )
    total_paid = sum((p.amount or Decimal("0.00")) for p in payments if p.action == "renew")

    return render_template(
        "admin/subscription_detail.html",
        user=user,
        store=store,
        status=store_access_status(store),
        payments=payments,
        total_paid=total_paid,
        price=PLAN_PRICE_MONTHLY,
    )
