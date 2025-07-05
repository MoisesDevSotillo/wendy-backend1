from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from src.models.wendy_models import db

class DelivererLocation(db.Model):
    __tablename__ = 'deliverer_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    deliverer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy = db.Column(db.Float)  # Precisão em metros
    speed = db.Column(db.Float)  # Velocidade em km/h
    heading = db.Column(db.Float)  # Direção em graus
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    deliverer = db.relationship('User', backref='locations')
    
    def to_dict(self):
        return {
            'id': self.id,
            'deliverer_id': self.deliverer_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'accuracy': self.accuracy,
            'speed': self.speed,
            'heading': self.heading,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'deliverer_name': self.deliverer.name if self.deliverer else None
        }

class OrderTracking(db.Model):
    __tablename__ = 'order_tracking'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    deliverer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50))  # 'pickup', 'in_transit', 'delivered'
    estimated_arrival = db.Column(db.DateTime)
    distance_remaining = db.Column(db.Float)  # Distância restante em km
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    order = db.relationship('Order', backref='tracking_points')
    deliverer = db.relationship('User', backref='tracking_history')
    
    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'deliverer_id': self.deliverer_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'status': self.status,
            'estimated_arrival': self.estimated_arrival.isoformat() if self.estimated_arrival else None,
            'distance_remaining': self.distance_remaining,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class GeofenceArea(db.Model):
    __tablename__ = 'geofence_areas'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    center_latitude = db.Column(db.Float, nullable=False)
    center_longitude = db.Column(db.Float, nullable=False)
    radius = db.Column(db.Float, nullable=False)  # Raio em metros
    area_type = db.Column(db.String(50))  # 'store', 'delivery_zone', 'restricted'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'center_latitude': self.center_latitude,
            'center_longitude': self.center_longitude,
            'radius': self.radius,
            'area_type': self.area_type,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

