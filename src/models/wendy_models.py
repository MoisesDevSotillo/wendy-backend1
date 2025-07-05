from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    user_type = db.Column(db.String(20), nullable=False)  # 'client', 'store', 'deliverer', 'admin'
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=True)  # Clientes são aprovados automaticamente
    approval_status = db.Column(db.String(20), default='approved')  # 'pending', 'approved', 'rejected'
    rejection_reason = db.Column(db.Text)  # Motivo da rejeição, se aplicável
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'phone': self.phone,
            'user_type': self.user_type,
            'is_active': self.is_active,
            'is_approved': self.is_approved,
            'approval_status': self.approval_status,
            'rejection_reason': self.rejection_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Store(db.Model):
    __tablename__ = 'stores'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    category = db.Column(db.String(50))  # Manter por compatibilidade
    cnpj = db.Column(db.String(20))
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(10))
    is_approved = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    rejection_reason = db.Column(db.Text)  # Motivo da rejeição, se aplicável
    is_active = db.Column(db.Boolean, default=True)
    minimum_order_value = db.Column(db.Float)  # Valor mínimo personalizado (se permitido)
    custom_delivery_fee_per_km = db.Column(db.Float)  # Taxa personalizada (se permitido)
    uses_platform_defaults = db.Column(db.Boolean, default=True)  # Usar configurações da plataforma
    is_privileged = db.Column(db.Boolean, default=False)  # Privilégio na busca de produtos
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    user = db.relationship('User', backref='store')
    products = db.relationship('Product', backref='store', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'cnpj': self.cnpj,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'zip_code': self.zip_code,
            'is_approved': self.is_approved,
            'approval_status': self.approval_status,
            'rejection_reason': self.rejection_reason,
            'is_active': self.is_active,
            'is_privileged': self.is_privileged,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    subcategory_id = db.Column(db.Integer, db.ForeignKey('subcategories.id'))
    category = db.Column(db.String(50))  # Manter por compatibilidade
    stock_quantity = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'store_id': self.store_id,
            'store_name': self.store.name if self.store else None,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'category': self.category,
            'stock_quantity': self.stock_quantity,
            'is_active': self.is_active,
            'image_url': self.image_url,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    deliverer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, preparing, ready, delivering, delivered, cancelled
    total_amount = db.Column(db.Float, nullable=False)
    delivery_fee = db.Column(db.Float, default=5.0)
    payment_method = db.Column(db.String(20))  # pix, card, cash
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, failed
    delivery_address = db.Column(db.String(255))
    delivery_city = db.Column(db.String(100))
    delivery_state = db.Column(db.String(50))
    delivery_zip_code = db.Column(db.String(10))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    client = db.relationship('User', foreign_keys=[client_id], backref='client_orders')
    deliverer = db.relationship('User', foreign_keys=[deliverer_id], backref='deliverer_orders')
    store_rel = db.relationship('Store', backref='orders')
    items = db.relationship('OrderItem', backref='order', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'store_id': self.store_id,
            'deliverer_id': self.deliverer_id,
            'order_number': self.order_number,
            'status': self.status,
            'total_amount': self.total_amount,
            'delivery_fee': self.delivery_fee,
            'payment_method': self.payment_method,
            'payment_status': self.payment_status,
            'delivery_address': self.delivery_address,
            'delivery_city': self.delivery_city,
            'delivery_state': self.delivery_state,
            'delivery_zip_code': self.delivery_zip_code,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'client_name': self.client.name if self.client else None,
            'store_name': self.store_rel.name if self.store_rel else None,
            'deliverer_name': self.deliverer.name if self.deliverer else None,
            'items': [item.to_dict() for item in self.items]
        }

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    # Relacionamentos
    product = db.relationship('Product', backref='order_items')
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'unit_price': self.unit_price,
            'total_price': self.total_price,
            'product_name': self.product.name if self.product else None
        }

class Deliverer(db.Model):
    __tablename__ = 'deliverers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    cpf = db.Column(db.String(15))
    vehicle_type = db.Column(db.String(20))  # motorcycle, bicycle, car
    vehicle_plate = db.Column(db.String(10))
    is_online = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    rejection_reason = db.Column(db.Text)  # Motivo da rejeição, se aplicável
    rating = db.Column(db.Float, default=5.0)
    total_deliveries = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    user = db.relationship('User', backref='deliverer_profile')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'cpf': self.cpf,
            'vehicle_type': self.vehicle_type,
            'vehicle_plate': self.vehicle_plate,
            'is_online': self.is_online,
            'is_approved': self.is_approved,
            'approval_status': self.approval_status,
            'rejection_reason': self.rejection_reason,
            'rating': self.rating,
            'total_deliveries': self.total_deliveries,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_name': self.user.name if self.user else None,
            'user_phone': self.user.phone if self.user else None
        }

class DeliveryRequest(db.Model):
    __tablename__ = 'delivery_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    deliverer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    pickup_address = db.Column(db.String(255), nullable=False)
    delivery_address = db.Column(db.String(255), nullable=False)
    item_description = db.Column(db.String(255))
    estimated_price = db.Column(db.Float)
    estimated_time = db.Column(db.Integer)  # em minutos
    payment_method = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')  # pending, accepted, picked_up, delivered, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    client = db.relationship('User', foreign_keys=[client_id], backref='delivery_requests')
    deliverer = db.relationship('User', foreign_keys=[deliverer_id], backref='assigned_deliveries')
    
    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id,
            'deliverer_id': self.deliverer_id,
            'pickup_address': self.pickup_address,
            'delivery_address': self.delivery_address,
            'item_description': self.item_description,
            'estimated_price': self.estimated_price,
            'estimated_time': self.estimated_time,
            'payment_method': self.payment_method,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'client_name': self.client.name if self.client else None,
            'deliverer_name': self.deliverer.name if self.deliverer else None
        }


class AllowedCity(db.Model):
    __tablename__ = 'allowed_cities'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    delivery_fee_per_km = db.Column(db.Float, default=2.0)  # Taxa por km
    minimum_order_value = db.Column(db.Float, default=30.0)  # Pedido mínimo
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'is_active': self.is_active,
            'delivery_fee_per_km': self.delivery_fee_per_km,
            'minimum_order_value': self.minimum_order_value,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class PlatformSettings(db.Model):
    __tablename__ = 'platform_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'setting_key': self.setting_key,
            'setting_value': self.setting_value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))  # Nome do ícone (ex: 'pizza', 'burger')
    color = db.Column(db.String(7), default='#66CCFF')  # Cor em hex
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    subcategories = db.relationship('Subcategory', backref='category', lazy=True, cascade='all, delete-orphan')
    stores = db.relationship('Store', backref='category_ref', lazy=True)
    products = db.relationship('Product', backref='category_ref', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'color': self.color,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'subcategories': [sub.to_dict() for sub in self.subcategories if sub.is_active]
        }

class Subcategory(db.Model):
    __tablename__ = 'subcategories'
    
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    products = db.relationship('Product', backref='subcategory_ref', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

