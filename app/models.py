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
    primary_color = db.Column(db.String(20), nullable=False, default="#4f46e5")
    secondary_color = db.Column(db.String(20), nullable=False, default="#06b6d4")

    owner = db.relationship("User", back_populates="store")
    banners = db.relationship("StoreBanner", cascade="all, delete-orphan", back_populates="store")
    categories = db.relationship("Category", cascade="all, delete-orphan", back_populates="store")
    products = db.relationship("Product", cascade="all, delete-orphan", back_populates="store")
    customers = db.relationship("Customer", cascade="all, delete-orphan", back_populates="store")
    orders = db.relationship("Order", cascade="all, delete-orphan", back_populates="store")


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
    price = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    sale_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(
        db.Enum("ativo", "destaque", "inativo"), nullable=False, default="ativo"
    )

    store = db.relationship("Store", back_populates="products")
    category = db.relationship("Category", back_populates="products")
    images = db.relationship("ProductImage", cascade="all, delete-orphan", back_populates="product")

    @property
    def final_price(self):
        return self.sale_price if self.sale_price is not None else self.price


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
    customer_address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("Pendente", "Confirmado", "Enviado", "Entregue", "Cancelado"),
        nullable=False,
        default="Pendente",
    )
    total = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    store = db.relationship("Store", back_populates="orders")
    customer = db.relationship("Customer", back_populates="orders")
    items = db.relationship("OrderItem", cascade="all, delete-orphan", back_populates="order")


class OrderItem(TimestampMixin, db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    product_name = db.Column(db.String(180), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")
