from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin

from . import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("superadmin", "lojista"), nullable=False, default="lojista")
    active = db.Column(db.Boolean, nullable=False, default=True)

    store = db.relationship("Store", back_populates="owner", uselist=False)

    @property
    def is_active(self):
        return self.active

    def is_superadmin(self):
        return self.role == "superadmin"


class Store(TimestampMixin, db.Model):
    __tablename__ = "stores"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    whatsapp = db.Column(db.String(30), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    logo_url = db.Column(db.Text, nullable=True)
    instagram_url = db.Column(db.Text, nullable=True)
    facebook_url = db.Column(db.Text, nullable=True)
    tiktok_url = db.Column(db.Text, nullable=True)
    primary_color = db.Column(db.String(20), nullable=False, default="#4f46e5")
    secondary_color = db.Column(db.String(20), nullable=False, default="#06b6d4")

    # ── Trial / Assinatura ──────────────────────────────────────────────────
    # trial_ends_at: data fim do trial gratuito (definido no cadastro)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    # subscription_active: True enquanto pagamento estiver em dia
    subscription_active = db.Column(db.Boolean, nullable=False, default=False)
    # paid_until: data de vencimento da última assinatura paga (controlado pelo superadmin)
    paid_until = db.Column(db.DateTime, nullable=True)
    # ────────────────────────────────────────────────────────────────────────

    owner = db.relationship("User", back_populates="store")
    banners = db.relationship("StoreBanner", cascade="all, delete-orphan", back_populates="store")
    categories = db.relationship("Category", cascade="all, delete-orphan", back_populates="store")
    products = db.relationship("Product", cascade="all, delete-orphan", back_populates="store")
    customers = db.relationship("Customer", cascade="all, delete-orphan", back_populates="store")
    orders = db.relationship("Order", cascade="all, delete-orphan", back_populates="store")
    subscription_payments = db.relationship(
        "SubscriptionPayment", cascade="all, delete-orphan", back_populates="store",
        order_by="desc(SubscriptionPayment.created_at)",
    )


class StoreBanner(TimestampMixin, db.Model):
    __tablename__ = "store_banners"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)
    image_url = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    store = db.relationship("Store", back_populates="banners")


class Category(TimestampMixin, db.Model):
    __tablename__ = "categories"
    __table_args__ = (db.UniqueConstraint("store_id", "name", name="uq_category_store_name"),)

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    icon = db.Column(db.String(20), nullable=True)

    store = db.relationship("Store", back_populates="categories")
    products = db.relationship("Product", back_populates="category")


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    cost_price = db.Column(db.Numeric(12, 2), nullable=True)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    sale_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(
        db.Enum("ativo", "destaque", "inativo"), nullable=False, default="ativo"
    )

    store = db.relationship("Store", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    images = db.relationship("ProductImage", cascade="all, delete-orphan", back_populates="product")
    variants = db.relationship(
        "ProductVariant", cascade="all, delete-orphan", back_populates="product",
        order_by="ProductVariant.position",
    )

    @property
    def final_price(self):
        return self.sale_price if self.sale_price is not None else self.price

    @property
    def has_variants(self):
        return len(self.variants) > 0

    @property
    def total_stock(self):
        """Estoque total. Com variações, soma o estoque de cada uma;
        sem variações, usa o campo `stock` direto do produto (compatível
        com todo o código existente que já lê `product.stock`)."""
        if self.has_variants:
            return sum(v.stock for v in self.variants)
        return self.stock

    @property
    def profit_margin_amount(self):
        """Margem de lucro em R$ (preço de venda final - custo). None se não
        houver custo cadastrado (não dá para calcular margem sem ele)."""
        if self.cost_price is None:
            return None
        return self.final_price - self.cost_price

    @property
    def profit_margin_percent(self):
        """Margem de lucro em % sobre o preço de venda final. None se não
        houver custo cadastrado ou o preço de venda for zero."""
        if self.cost_price is None or not self.final_price:
            return None
        return (self.final_price - self.cost_price) / self.final_price * 100


class ProductVariant(TimestampMixin, db.Model):
    """Variação de um produto (ex.: tamanho M / cor Azul).

    Produtos sem variações não usam esta tabela — continuam usando
    `Product.stock`/`Product.price` diretamente, sem qualquer mudança de
    comportamento. Um produto só passa a ter variações quando o lojista
    cadastra ao menos uma aqui; nesse caso, o estoque/preço de cada
    combinação tamanho+cor é controlado por linha, e `Product.stock` deixa
    de ser a fonte de verdade (ver `Product.total_stock`).
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        db.UniqueConstraint("product_id", "size", "color", name="uq_variant_product_size_color"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    size = db.Column(db.String(40), nullable=True)
    color = db.Column(db.String(40), nullable=True)
    sku = db.Column(db.String(60), nullable=True)
    # Preço próprio é opcional: se nulo, a variação usa o preço do produto
    # (`Product.final_price`). Permite tanto "todas as variações custam o
    # mesmo" (caso comum) quanto "tamanho P custa diferente de G".
    price = db.Column(db.Numeric(12, 2), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    position = db.Column(db.Integer, nullable=False, default=0)

    product = db.relationship("Product", back_populates="variants")

    @property
    def label(self):
        parts = [p for p in (self.size, self.color) if p]
        return " / ".join(parts) if parts else "Padrão"

    @property
    def final_price(self):
        if self.price is not None:
            return self.price
        return self.product.final_price


class ProductImage(TimestampMixin, db.Model):
    __tablename__ = "product_images"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    image_url = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)

    product = db.relationship("Product", back_populates="images")


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"
    __table_args__ = (db.UniqueConstraint("store_id", "phone", name="uq_customer_store_phone"),)

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)
    name = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(180), nullable=True)
    address = db.Column(db.Text, nullable=True)

    store = db.relationship("Store", back_populates="customers")
    orders = db.relationship("Order", back_populates="customer")


class Order(TimestampMixin, db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    customer_name = db.Column(db.String(140), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False)
    customer_email = db.Column(db.String(180), nullable=True)
    customer_address = db.Column(db.Text, nullable=True)
    payment_method = db.Column(db.String(60), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("Pendente", "Confirmado", "Enviado", "Entregue", "Cancelado"),
        nullable=False,
        default="Pendente",
        index=True,
    )
    status_updated_at = db.Column(db.DateTime, nullable=True)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    store = db.relationship("Store", back_populates="orders")
    customer = db.relationship("Customer", back_populates="orders")
    items = db.relationship("OrderItem", cascade="all, delete-orphan", back_populates="order")


class OrderItem(TimestampMixin, db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=True)
    product_name = db.Column(db.String(180), nullable=False)
    # Snapshot do tamanho/cor escolhidos no momento da compra — preservado
    # mesmo que a variação seja depois renomeada ou excluída do catálogo.
    variant_label = db.Column(db.String(120), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    # Snapshot do preço de custo no momento da venda — usado para calcular a
    # margem de lucro real de cada pedido na seção financeira, mesmo que o
    # lojista altere o custo do produto depois.
    unit_cost = db.Column(db.Numeric(12, 2), nullable=True)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")

    @property
    def profit(self):
        """Lucro deste item de pedido (None se não houver custo registrado)."""
        if self.unit_cost is None:
            return None
        return (self.unit_price - self.unit_cost) * self.quantity


class SubscriptionPayment(TimestampMixin, db.Model):
    """Histórico de renovações/ações de assinatura de uma loja.

    Cada renovação ou suspensão feita pelo superadmin em
    `dashboard.admin_subscription_manage` gera um registro aqui, preservando
    o histórico mesmo que `Store.paid_until` seja sobrescrito depois.
    Isso alimenta tanto a tela "Minha assinatura" do lojista (histórico de
    pagamentos) quanto relatórios financeiros do superadmin.
    """

    __tablename__ = "subscription_payments"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False, index=True)
    action = db.Column(
        db.Enum("renew", "suspend"), nullable=False, default="renew"
    )
    months = db.Column(db.Integer, nullable=True)  # nulo quando action="suspend"
    amount = db.Column(db.Numeric(12, 2), nullable=True)  # valor cobrado nesta renovação
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)
    registered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    note = db.Column(db.String(255), nullable=True)

    store = db.relationship("Store", back_populates="subscription_payments")
    registered_by = db.relationship("User")
