from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Rating(db.Model):
    __tablename__ = 'ratings'
    
    id = db.Column(db.Integer, primary_key=True)
    rater_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Quem avalia
    rated_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Quem é avaliado
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)  # Pedido relacionado (opcional)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 estrelas
    comment = db.Column(db.Text, nullable=True)  # Comentário opcional
    rating_type = db.Column(db.String(50), nullable=False)  # 'delivery', 'service', 'product'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    rater = db.relationship('User', foreign_keys=[rater_id], backref='ratings_given')
    rated = db.relationship('User', foreign_keys=[rated_id], backref='ratings_received')
    order = db.relationship('Order', backref='ratings')
    
    def to_dict(self):
        return {
            'id': self.id,
            'rater_id': self.rater_id,
            'rated_id': self.rated_id,
            'order_id': self.order_id,
            'rating': self.rating,
            'comment': self.comment,
            'rating_type': self.rating_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'rater_name': self.rater.name if self.rater else None,
            'rated_name': self.rated.name if self.rated else None
        }

class UserRatingStats(db.Model):
    __tablename__ = 'user_rating_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    total_ratings = db.Column(db.Integer, default=0)
    average_rating = db.Column(db.Float, default=0.0)
    five_star_count = db.Column(db.Integer, default=0)
    four_star_count = db.Column(db.Integer, default=0)
    three_star_count = db.Column(db.Integer, default=0)
    two_star_count = db.Column(db.Integer, default=0)
    one_star_count = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento
    user = db.relationship('User', backref='rating_stats')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'total_ratings': self.total_ratings,
            'average_rating': round(self.average_rating, 1),
            'five_star_count': self.five_star_count,
            'four_star_count': self.four_star_count,
            'three_star_count': self.three_star_count,
            'two_star_count': self.two_star_count,
            'one_star_count': self.one_star_count,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def update_stats(self):
        """Atualiza as estatísticas baseado nas avaliações recebidas"""
        ratings = Rating.query.filter_by(rated_id=self.user_id).all()
        
        if not ratings:
            self.total_ratings = 0
            self.average_rating = 0.0
            self.five_star_count = 0
            self.four_star_count = 0
            self.three_star_count = 0
            self.two_star_count = 0
            self.one_star_count = 0
            return
        
        self.total_ratings = len(ratings)
        total_score = sum(rating.rating for rating in ratings)
        self.average_rating = total_score / self.total_ratings
        
        # Contar por estrelas
        star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating in ratings:
            star_counts[rating.rating] += 1
        
        self.one_star_count = star_counts[1]
        self.two_star_count = star_counts[2]
        self.three_star_count = star_counts[3]
        self.four_star_count = star_counts[4]
        self.five_star_count = star_counts[5]

