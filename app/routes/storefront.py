from decimal import Decimal
from urllib.parse import quote

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import Customer, Order, OrderItem, Product, Store
from ..utils import only_digits, order_code

storefront_bp = Blueprint("storefront", __name__)


def cart_key(store_id):
    return f"cart_{store_id}"


def current_cart(store_id):
    key = cart_key(store_id)
    cart = session.get(key)
    if not isinstance(cart, dict):
        cart = {}

    cleaned = {}
    for product_id, quantity in cart.items():
        try:
            product_id = str(int(product_id))
            quantity = int(quantity)
        except (TypeError, ValueError):
            continue
        if quantity > 0:
            cleaned[product_id] = quantity

    if cleaned != cart:
        session[key] = cleaned
        session.modified = True
    else:
        session.setdefault(key, cleaned)
    return session[key]


def cart_count(cart):
    return sum(max(0, int(quantity)) for quantity in cart.values())


def wants_json():
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


def active_store_or_404(slug):
    store = Store.query.filter_by(slug=slug).first_or_404()
    if not store.owner or not store.owner.active:
        abort(403)
    return store


def cart_items_for(store):
    cart = current_cart(store.id)
    product_ids = [int(product_id) for product_id in cart.keys()]
    products = (
        Product.query.filter(
            Product.store_id == store.id,
            Product.status != "inativo",
            Product.id.in_(product_ids or [0]),
        )
        .order_by(Product.name)
        .all()
    )
    valid_ids = {str(product.id) for product in products}
    items = []
    changed = False
    for product in products:
        quantity = max(0, min(int(cart.get(str(product.id), 0)), max(product.stock, 0)))
        if quantity > 0:
            items.append((product, quantity))
            if quantity != int(cart.get(str(product.id), 0)):
                cart[str(product.id)] = quantity
                changed = True

    for product_id in list(cart.keys()):
        if product_id not in valid_ids or int(cart.get(product_id, 0)) <= 0:
            cart.pop(product_id, None)
            changed = True

    if changed:
        session.modified = True
    return items


def cart_total(items):
    return sum((product.final_price or Decimal("0.00")) * qty for product, qty in items)


@storefront_bp.route("/loja/<slug>")
def store(slug):
    store = active_store_or_404(slug)
    category_id = request.args.get("categoria", type=int)
    products = Product.query.filter_by(store_id=store.id).filter(Product.status != "inativo")
    if category_id:
        products = products.filter_by(category_id=category_id)
    cart = current_cart(store.id)
    return render_template(
        "storefront/store.html",
        store=store,
        products=products.order_by(Product.status.desc(), Product.name).all(),
        cart_count=cart_count(cart),
        selected_category_id=category_id,
    )


@storefront_bp.route("/loja/<slug>/produto/<int:product_id>")
def product_detail(slug, product_id):
    store = active_store_or_404(slug)
    product = Product.query.filter(
        Product.id == product_id,
        Product.store_id == store.id,
        Product.status != "inativo",
    ).first_or_404()

    related_query = Product.query.filter(
        Product.store_id == store.id,
        Product.id != product.id,
        Product.status != "inativo",
    )
    related = []
    if product.category_id:
        related = (
            related_query.filter(Product.category_id == product.category_id)
            .order_by(Product.status.desc(), Product.name)
            .limit(4)
            .all()
        )
    if len(related) < 4:
        related_ids = [item.id for item in related]
        related.extend(
            related_query.filter(~Product.id.in_(related_ids or [0]))
            .order_by(Product.status.desc(), Product.name)
            .limit(4 - len(related))
            .all()
        )

    return render_template(
        "storefront/product_detail.html",
        store=store,
        product=product,
        related_products=related,
        cart_count=cart_count(current_cart(store.id)),
    )


@storefront_bp.route("/loja/<slug>/carrinho/adicionar/<int:product_id>", methods=["POST"])
def cart_add(slug, product_id):
    store = active_store_or_404(slug)
    product = Product.query.filter(
        Product.id == product_id,
        Product.store_id == store.id,
        Product.status != "inativo",
    ).first_or_404()
    cart = current_cart(store.id)
    requested_quantity = max(1, request.form.get("quantity", type=int) or 1)

    if product.stock <= 0:
        if wants_json():
            return jsonify({"ok": False, "message": "Produto sem estoque."}), 400
        return redirect(request.referrer or url_for("storefront.store", slug=slug))

    product_key = str(product.id)
    cart[product_key] = min(product.stock, int(cart.get(product_key, 0)) + requested_quantity)
    session.modified = True

    if wants_json():
        return jsonify(
            {
                "ok": True,
                "message": "Produto adicionado ao carrinho.",
                "cart_count": cart_count(cart),
                "line_quantity": cart[product_key],
            }
        )
    return redirect(request.referrer or url_for("storefront.store", slug=slug))


@storefront_bp.route("/loja/<slug>/carrinho", methods=["GET", "POST"])
def cart(slug):
    store = active_store_or_404(slug)
    cart = current_cart(store.id)
    items = cart_items_for(store)
    if request.method == "POST":
        for product, _qty in items:
            qty = request.form.get(f"qty_{product.id}", type=int) or 0
            if qty <= 0:
                cart.pop(str(product.id), None)
            else:
                cart[str(product.id)] = min(qty, product.stock)
        session.modified = True
        return redirect(url_for("storefront.cart", slug=slug))
    return render_template(
        "storefront/cart.html",
        store=store,
        items=items,
        total=cart_total(items),
        cart_count=cart_count(cart),
    )


@storefront_bp.route("/loja/<slug>/checkout", methods=["GET", "POST"])
def checkout(slug):
    store = active_store_or_404(slug)
    cart = current_cart(store.id)
    items = cart_items_for(store)
    if not items:
        return redirect(url_for("storefront.store", slug=slug))
    total = cart_total(items)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = only_digits(request.form.get("phone"))
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()
        if not name or not phone:
            return render_template(
                "storefront/checkout.html",
                store=store,
                items=items,
                total=total,
                error="Informe nome e WhatsApp.",
                cart_count=cart_count(cart),
            )
        customer = Customer.query.filter_by(store_id=store.id, phone=phone).first()
        if not customer:
            customer = Customer(store_id=store.id, name=name, phone=phone)
            db.session.add(customer)
        customer.name = name
        customer.address = address
        code = order_code()
        while Order.query.filter_by(code=code).first():
            code = order_code()
        order = Order(
            code=code,
            store_id=store.id,
            customer=customer,
            customer_name=name,
            customer_phone=phone,
            customer_address=address,
            notes=notes,
            total=total,
        )
        for product, qty in items:
            order.items.append(
                OrderItem(
                    product=product,
                    product_name=product.name,
                    quantity=qty,
                    unit_price=product.final_price,
                    subtotal=product.final_price * qty,
                )
            )
            product.stock = max(0, product.stock - qty)
        db.session.add(order)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return (
                render_template(
                    "storefront/checkout.html",
                    store=store,
                    items=items,
                    total=total,
                    error="Não foi possível registrar o pedido. Tente novamente.",
                    cart_count=cart_count(cart),
                ),
                500,
            )
        session.pop(cart_key(store.id), None)
        message = [
            f"*Novo Pedido - {store.name}*",
            "",
            f"*Pedido:* #{order.code}",
            f"*Cliente:* {name}",
            f"*WhatsApp:* {phone}",
        ]
        if address:
            message.append(f"*Endereço:* {address}")
        message.extend(["", "*Itens:*"])
        for item in order.items:
            message.append(f"- {item.product_name} x{item.quantity} = R$ {item.subtotal:.2f}")
        message.append(f"\n*Total: R$ {order.total:.2f}*")
        if notes:
            message.append(f"\n*Obs:* {notes}")
        whatsapp_url = (
            f"https://wa.me/{store.whatsapp}?text={quote(chr(10).join(message))}"
            if store.whatsapp
            else None
        )
        return render_template(
            "storefront/success.html",
            store=store,
            order=order,
            whatsapp_url=whatsapp_url,
        )
    return render_template(
        "storefront/checkout.html",
        store=store,
        items=items,
        total=total,
        cart_count=cart_count(cart),
    )
