from decimal import Decimal
from math import ceil
from urllib.parse import quote

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from .. import db
from ..models import Category, Customer, Order, OrderItem, Product, Store
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
    search_query = request.args.get("q", "").strip()
    sort = request.args.get("sort", "recentes").strip()
    if sort not in {"recentes", "nome", "menor_preco", "maior_preco"}:
        sort = "recentes"
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = 12
    products = Product.query.filter_by(store_id=store.id).filter(Product.status != "inativo")
    if category_id:
        products = products.filter_by(category_id=category_id)
    if search_query:
        term = f"%{search_query}%"
        products = products.filter(or_(Product.name.ilike(term), Product.description.ilike(term)))

    price_expression = func.coalesce(Product.sale_price, Product.price)
    if sort == "nome":
        ordered_products = products.order_by(Product.name.asc(), Product.created_at.desc())
    elif sort == "menor_preco":
        ordered_products = products.order_by(price_expression.asc(), Product.name.asc())
    elif sort == "maior_preco":
        ordered_products = products.order_by(price_expression.desc(), Product.name.asc())
    else:
        ordered_products = products.order_by(Product.status.desc(), Product.created_at.desc(), Product.name.asc())

    total_products = ordered_products.count()
    total_pages = max(1, ceil(total_products / per_page)) if total_products else 1
    if page > total_pages:
        page = total_pages
    product_items = ordered_products.offset((page - 1) * per_page).limit(per_page).all()
    featured_product = product_items[0] if product_items else ordered_products.limit(1).first()
    categories = Category.query.filter_by(store_id=store.id).order_by(Category.name).all()
    cart = current_cart(store.id)
    return render_template(
        "storefront/store.html",
        store=store,
        products=product_items,
        featured_product=featured_product,
        cart_count=cart_count(cart),
        selected_category_id=category_id,
        categories=categories,
        search_query=search_query,
        sort=sort,
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total_products,
            "pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "next_num": page + 1,
            "prev_num": page - 1,
        },
    )


@storefront_bp.route("/loja/<slug>/produto/<int:product_id>")
def product_detail(slug, product_id):
    store = active_store_or_404(slug)
    product = Product.query.filter(
        Product.id == product_id,
        Product.store_id == store.id,
        Product.status != "inativo",
    ).first_or_404()
    categories = Category.query.filter_by(store_id=store.id).order_by(Category.name).all()
    search_query = request.args.get("q", "").strip()
    selected_category_id = request.args.get("categoria", type=int) or product.category_id
    sort = request.args.get("sort", "recentes").strip()

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
        categories=categories,
        selected_category_id=selected_category_id,
        search_query=search_query,
        sort=sort,
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


@storefront_bp.route("/loja/<slug>/carrinho/atualizar", methods=["POST"])
def cart_update(slug):
    """Atualiza ou remove um item do carrinho via fetch (sem reload de página).

    Espera `product_id` e `quantity` (form-encoded). quantity <= 0 remove o item.
    Sempre responde em JSON: usado pela tela /carrinho para refletir a mudança
    ao vivo (badge do header, subtotal da linha e total do pedido).
    """
    store = active_store_or_404(slug)
    product_id = request.form.get("product_id", type=int)
    quantity = request.form.get("quantity", type=int)

    if product_id is None or quantity is None:
        return jsonify({"ok": False, "message": "Requisição inválida."}), 400

    product = Product.query.filter(
        Product.id == product_id,
        Product.store_id == store.id,
    ).first()
    if not product:
        return jsonify({"ok": False, "message": "Produto não encontrado."}), 404

    cart = current_cart(store.id)
    product_key = str(product.id)

    if quantity <= 0:
        cart.pop(product_key, None)
        line_quantity = 0
    else:
        line_quantity = min(quantity, max(product.stock, 0))
        if line_quantity <= 0:
            cart.pop(product_key, None)
            line_quantity = 0
        else:
            cart[product_key] = line_quantity
    session.modified = True

    items = cart_items_for(store)
    total = cart_total(items)

    return jsonify(
        {
            "ok": True,
            "cart_count": cart_count(cart),
            "line_quantity": line_quantity,
            "removed": line_quantity <= 0,
            "total": float(total),
        }
    )


@storefront_bp.route("/loja/<slug>/carrinho", methods=["GET", "POST"])
def cart(slug):
    store = active_store_or_404(slug)
    cart = current_cart(store.id)
    items = cart_items_for(store)
    if request.method == "POST":
        # Fallback sem JavaScript: o formulário antigo (recarrega a página)
        # continua funcionando para quem desabilitar o JS no navegador.
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


def _build_structured_address(form):
    """Monta um endereço de texto único a partir dos campos estruturados do
    checkout, mantendo compatibilidade com a coluna `address` já existente
    em Customer/Order (texto livre), sem exigir migração de banco agora.
    """
    street = form.get("street", "").strip()
    number = form.get("number", "").strip()
    complement = form.get("complement", "").strip()
    neighborhood = form.get("neighborhood", "").strip()
    city = form.get("city", "").strip()
    state = form.get("state", "").strip().upper()
    zip_code = only_digits(form.get("zip_code", ""))

    line1 = ", ".join(part for part in [street, number] if part)
    line2 = " - ".join(part for part in [neighborhood, complement] if part)
    line3 = "/".join(part for part in [city, state] if part)

    pieces = [piece for piece in [line1, line2, line3] if piece]
    if zip_code:
        pieces.append(f"CEP {zip_code}")
    return ", ".join(pieces)


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
        email = request.form.get("email", "").strip()
        payment_method = request.form.get("payment_method", "").strip()
        notes = request.form.get("notes", "").strip()
        address = _build_structured_address(request.form)

        form_data = request.form

        if not name or not phone or not email or not payment_method:
            return render_template(
                "storefront/checkout.html",
                store=store,
                items=items,
                total=total,
                error="Informe nome, WhatsApp, e-mail e forma de pagamento.",
                cart_count=cart_count(cart),
                form_data=form_data,
            )

        # `Customer`/`Order` ainda não têm coluna própria de e-mail neste
        # banco. Para não perder o dado, ele vai junto das observações até
        # que uma migração adicione `email` em Customer/Order.
        notes_with_email = f"E-mail: {email}" + (f"\n{notes}" if notes else "")

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
            payment_method=payment_method,
            notes=notes_with_email,
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
                    form_data=form_data,
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
            f"*E-mail:* {email}",
        ]
        if address:
            message.append(f"*Endereço:* {address}")
        message.append(f"*Pagamento:* {payment_method}")
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
