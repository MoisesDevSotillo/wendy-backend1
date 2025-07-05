from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.rating_models import db, Rating, UserRatingStats
from src.models.wendy_models import User, Order
from datetime import datetime
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)

ratings_bp = Blueprint('ratings', __name__)

@ratings_bp.route('/ratings', methods=['POST'])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=5, per="user")
@validate_json_input(
    required_fields=['rated_id', 'rating', 'rating_type'],
    optional_fields=['order_id', 'comment']
)
@secure_headers()
def create_rating():
    """Criar uma nova avaliação"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Sanitizar dados de entrada
        rated_id = SecurityValidator.sanitize_int(data.get('rated_id'))
        rating = SecurityValidator.sanitize_int(data.get('rating'))
        order_id = SecurityValidator.sanitize_int(data.get('order_id'))
        rating_type = SecurityValidator.sanitize_string(data.get('rating_type'), max_length=50)
        comment = SecurityValidator.sanitize_string(data.get('comment', ''), max_length=500)
        
        # Validações de segurança
        if not rated_id or rated_id <= 0:
            SecurityLogger.log_security_event("invalid_rated_id", 
                                            {"user_id": user_id, "rated_id": data.get('rated_id')})
            return jsonify({'error': 'ID do usuário avaliado inválido'}), 400
            
        if not rating or rating < 1 or rating > 5:
            SecurityLogger.log_security_event("invalid_rating_value", 
                                            {"user_id": user_id, "rating": data.get('rating')})
            return jsonify({'error': 'Rating deve ser um número inteiro entre 1 e 5'}), 400
        
        if user_id == rated_id:
            SecurityLogger.log_security_event("self_rating_attempt", 
                                            {"user_id": user_id})
            return jsonify({'error': 'Não é possível avaliar a si mesmo'}), 400
        
        # Verificar se os usuários existem
        rater = User.query.get(user_id)
        rated = User.query.get(rated_id)
        
        if not rater:
            SecurityLogger.log_security_event("rater_not_found", 
                                            {"user_id": user_id})
            return jsonify({'error': 'Usuário avaliador não encontrado'}), 404
        if not rated:
            SecurityLogger.log_security_event("rated_user_not_found", 
                                            {"user_id": user_id, "rated_id": rated_id})
            return jsonify({'error': 'Usuário avaliado não encontrado'}), 404
        
        # Verificar se já existe avaliação para este pedido (se order_id fornecido)
        if order_id:
            # Verificar se o pedido existe e se o usuário tem permissão para avaliá-lo
            order = Order.query.get(order_id)
            if not order:
                SecurityLogger.log_security_event("order_not_found_for_rating", 
                                                {"user_id": user_id, "order_id": order_id})
                return jsonify({'error': 'Pedido não encontrado'}), 404
            
            # Verificar se o usuário está relacionado ao pedido
            if user_id not in [order.customer_id, order.deliverer_id] and order.store.owner_id != user_id:
                SecurityLogger.log_security_event("unauthorized_rating_attempt", 
                                                {"user_id": user_id, "order_id": order_id})
                return jsonify({'error': 'Você não tem permissão para avaliar este pedido'}), 403
            
            existing_rating = Rating.query.filter_by(
                rater_id=user_id,
                rated_id=rated_id,
                order_id=order_id
            ).first()
            
            if existing_rating:
                SecurityLogger.log_security_event("duplicate_rating_attempt", 
                                                {"user_id": user_id, "order_id": order_id, "rated_id": rated_id})
                return jsonify({'error': 'Já existe uma avaliação para este pedido'}), 400
        
        # Criar nova avaliação
        rating_obj = Rating(
            rater_id=user_id,
            rated_id=rated_id,
            order_id=order_id,
            rating=rating,
            comment=comment,
            rating_type=rating_type,
            created_at=datetime.utcnow()
        )
        
        db.session.add(rating_obj)
        db.session.commit()
        
        # Atualizar estatísticas do usuário avaliado
        update_user_rating_stats(rated_id)
        
        SecurityLogger.log_security_event("rating_created", 
                                        {"user_id": user_id, "rating_id": rating_obj.id, "rated_id": rated_id})
        
        return jsonify({
            'message': 'Avaliação criada com sucesso',
            'rating': rating_obj.to_dict()
        }), 201
        
    except Exception as e:
        SecurityLogger.log_security_event("rating_creation_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({'error': 'Erro interno do servidor'}), 500

@ratings_bp.route('/ratings/user/<int:user_id>', methods=['GET'])
@rate_limit(max_requests=30, window_minutes=1, per="ip")
@secure_headers()
def get_user_ratings(user_id):
    """Obter avaliações de um usuário"""
    try:
        sanitized_user_id = SecurityValidator.sanitize_int(user_id)
        if sanitized_user_id is None or sanitized_user_id <= 0:
            return jsonify({'error': 'ID do usuário inválido'}), 400
        
        user = User.query.get(sanitized_user_id)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        # Obter avaliações recebidas pelo usuário
        ratings = Rating.query.filter_by(rated_id=sanitized_user_id).order_by(Rating.created_at.desc()).all()
        
        # Obter estatísticas
        stats = UserRatingStats.query.filter_by(user_id=sanitized_user_id).first()
        
        return jsonify({
            'user_id': sanitized_user_id,
            'ratings': [rating.to_dict() for rating in ratings],
            'stats': stats.to_dict() if stats else None
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_user_ratings_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({'error': 'Erro interno do servidor'}), 500

@ratings_bp.route('/ratings/order/<int:order_id>', methods=['GET'])
@jwt_required()
@rate_limit(max_requests=20, window_minutes=1, per="user")
@secure_headers()
def get_order_ratings(order_id):
    """Obter avaliações de um pedido"""
    try:
        user_id = get_jwt_identity()
        sanitized_order_id = SecurityValidator.sanitize_int(order_id)
        
        if sanitized_order_id is None or sanitized_order_id <= 0:
            return jsonify({'error': 'ID do pedido inválido'}), 400
        
        order = Order.query.get(sanitized_order_id)
        if not order:
            return jsonify({'error': 'Pedido não encontrado'}), 404
        
        # Verificar se o usuário tem permissão para ver as avaliações do pedido
        if user_id not in [order.customer_id, order.deliverer_id] and order.store.owner_id != user_id:
            SecurityLogger.log_security_event("unauthorized_order_ratings_access", 
                                            {"user_id": user_id, "order_id": sanitized_order_id})
            return jsonify({'error': 'Você não tem permissão para ver as avaliações deste pedido'}), 403
        
        ratings = Rating.query.filter_by(order_id=sanitized_order_id).all()
        
        return jsonify({
            'order_id': sanitized_order_id,
            'ratings': [rating.to_dict() for rating in ratings]
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_order_ratings_error", 
                                        {"user_id": user_id, "order_id": order_id, "error": str(e)})
        return jsonify({'error': 'Erro interno do servidor'}), 500

def update_user_rating_stats(user_id):
    """Atualizar estatísticas de avaliação do usuário"""
    try:
        ratings = Rating.query.filter_by(rated_id=user_id).all()
        
        if not ratings:
            return
        
        total_ratings = len(ratings)
        average_rating = sum(r.rating for r in ratings) / total_ratings
        
        # Contar por estrelas
        rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating in ratings:
            rating_counts[rating.rating] += 1
        
        # Atualizar ou criar estatísticas
        stats = UserRatingStats.query.filter_by(user_id=user_id).first()
        if not stats:
            stats = UserRatingStats(user_id=user_id)
            db.session.add(stats)
        
        stats.total_ratings = total_ratings
        stats.average_rating = round(average_rating, 2)
        stats.five_star_count = rating_counts[5]
        stats.four_star_count = rating_counts[4]
        stats.three_star_count = rating_counts[3]
        stats.two_star_count = rating_counts[2]
        stats.one_star_count = rating_counts[1]
        stats.updated_at = datetime.utcnow()
        
        db.session.commit()
        
    except Exception as e:
        SecurityLogger.log_security_event("update_rating_stats_error", 
                                        {"user_id": user_id, "error": str(e)})
        db.session.rollback()

