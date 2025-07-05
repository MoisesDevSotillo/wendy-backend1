from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, Deliverer, User, DeliveryRequest, Order
from datetime import datetime, timedelta
import random
import string
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)

deliverers_bp = Blueprint('deliverers', __name__)

@deliverers_bp.route("/toggle-online", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=1, per="user")
@secure_headers()
def toggle_online():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/deliverers/toggle-online", "method": "POST"})
            return jsonify({"error": "Acesso negado"}), 403
        
        deliverer = Deliverer.query.filter_by(user_id=user_id).first()
        
        if not deliverer:
            SecurityLogger.log_security_event("deliverer_profile_not_found", 
                                                {"user_id": user_id, "route": "/deliverers/toggle-online", "method": "POST"})
            return jsonify({"error": "Perfil de entregador não encontrado"}), 404
        
        if not deliverer.is_approved:
            SecurityLogger.log_security_event("deliverer_not_approved", 
                                                {"user_id": user_id, "route": "/deliverers/toggle-online", "method": "POST"})
            return jsonify({"error": "Entregador não aprovado"}), 403
        
        # Alternar status online/offline
        deliverer.is_online = not deliverer.is_online
        db.session.commit()
        
        SecurityLogger.log_security_event("deliverer_status_toggle", 
                                        {"user_id": user_id, "is_online": deliverer.is_online})
        
        return jsonify({
            "message": f"Status alterado para {"online" if deliverer.is_online else "offline"}",
            "is_online": deliverer.is_online
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route("/stats", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_deliverer_stats():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/deliverers/stats", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        deliverer = Deliverer.query.filter_by(user_id=user_id).first()
        
        if not deliverer:
            SecurityLogger.log_security_event("deliverer_profile_not_found", 
                                                {"user_id": user_id, "route": "/deliverers/stats", "method": "GET"})
            return jsonify({"error": "Perfil de entregador não encontrado"}), 404
        
        # Estatísticas de hoje
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_deliveries = Order.query.filter(
            Order.deliverer_id == user_id,
            Order.status == "delivered",
            Order.updated_at >= today
        ).all()
        
        daily_earnings = sum(order.delivery_fee for order in daily_deliveries)
        
        # Estatísticas da semana
        week_start = today - timedelta(days=today.weekday())
        weekly_deliveries = Order.query.filter(
            Order.deliverer_id == user_id,
            Order.status == "delivered",
            Order.updated_at >= week_start
        ).all()
        
        weekly_earnings = sum(order.delivery_fee for order in weekly_deliveries)
        
        # Estatísticas do mês
        month_start = today.replace(day=1)
        monthly_deliveries = Order.query.filter(
            Order.deliverer_id == user_id,
            Order.status == "delivered",
            Order.updated_at >= month_start
        ).all()
        
        monthly_earnings = sum(order.delivery_fee for order in monthly_deliveries)
        
        # Pedidos ativos
        active_orders = Order.query.filter(
            Order.deliverer_id == user_id,
            Order.status.in_(["delivering"])
        ).count()
        
        return jsonify({
            "daily": {
                "deliveries": len(daily_deliveries),
                "earnings": daily_earnings
            },
            "weekly": {
                "deliveries": len(weekly_deliveries),
                "earnings": weekly_earnings
            },
            "monthly": {
                "deliveries": len(monthly_deliveries),
                "earnings": monthly_earnings
            },
            "active_orders": active_orders,
            "total_deliveries": deliverer.total_deliveries,
            "rating": deliverer.rating,
            "is_online": deliverer.is_online
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route("/delivery-history", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_delivery_history():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/deliverers/delivery-history", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        page = int(SecurityValidator.sanitize_string(request.args.get("page", "1")))
        per_page = int(SecurityValidator.sanitize_string(request.args.get("per_page", "20")))
        
        if page <= 0 or per_page <= 0:
            return jsonify({"error": "Parâmetros de paginação inválidos"}), 400

        orders = Order.query.filter_by(deliverer_id=user_id).order_by(
            Order.updated_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            "orders": [order.to_dict() for order in orders.items],
            "total": orders.total,
            "pages": orders.pages,
            "current_page": page
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route("/delivery-requests", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["pickup_address", "delivery_address", "item_description"],
    optional_fields=["payment_method"]
)
@secure_headers()
def create_delivery_request():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "client":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/deliverers/delivery-requests", "method": "POST"})
            return jsonify({"error": "Acesso negado"}), 403
        
        data = request.get_json()
        
        # Validar e sanitizar dados
        pickup_address = SecurityValidator.sanitize_string(data["pickup_address"], 200)
        delivery_address = SecurityValidator.sanitize_string(data["delivery_address"], 200)
        item_description = SecurityValidator.sanitize_string(data["item_description"], 500)
        payment_method = SecurityValidator.sanitize_string(data.get("payment_method", "pix"), 50)

        if not pickup_address or not delivery_address or not item_description:
            return jsonify({"error": "Campos obrigatórios inválidos ou vazios"}), 400

        allowed_payment_methods = ["credit_card", "debit_card", "cash", "pix"]
        if payment_method not in allowed_payment_methods:
            return jsonify({"error": "Método de pagamento inválido"}), 400
        
        # Calcular estimativa de preço e tempo (simulado)
        estimated_price = round(random.uniform(8.0, 25.0), 2)
        estimated_time = random.randint(20, 60)
        
        delivery_request = DeliveryRequest(
            client_id=user_id,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            item_description=item_description,
            estimated_price=estimated_price,
            estimated_time=estimated_time,
            payment_method=payment_method
        )
        
        db.session.add(delivery_request)
        db.session.commit()
        
        SecurityLogger.log_security_event("delivery_request_created", {"user_id": user_id, "request_id": delivery_request.id})

        return jsonify({
            "message": "Solicitação de entrega criada com sucesso",
            "delivery_request": delivery_request.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route("/delivery-requests/available", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_available_delivery_requests():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/deliverers/delivery-requests/available", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        deliverer = Deliverer.query.filter_by(user_id=user_id).first()
        
        if not deliverer or not deliverer.is_online:
            SecurityLogger.log_security_event("deliverer_offline_or_not_found", 
                                                {"user_id": user_id, "route": "/deliverers/delivery-requests/available", "method": "GET"})
            return jsonify({"error": "Entregador deve estar online"}), 403
        
        # Buscar solicitações pendentes
        requests = DeliveryRequest.query.filter_by(
            status="pending",
            deliverer_id=None
        ).order_by(DeliveryRequest.created_at.desc()).all()
        
        return jsonify({
            "delivery_requests": [req.to_dict() for req in requests],
            "total": len(requests)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route('/delivery-requests/<int:request_id>/accept', methods=['POST'])
@jwt_required()
def accept_delivery_request(request_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != 'deliverer':
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverer = Deliverer.query.filter_by(user_id=user_id).first()
        
        if not deliverer or not deliverer.is_online:
            return jsonify({'error': 'Entregador deve estar online'}), 403
        
        delivery_request = DeliveryRequest.query.get(request_id)
        
        if not delivery_request:
            return jsonify({'error': 'Solicitação não encontrada'}), 404
        
        if delivery_request.status != 'pending':
            return jsonify({'error': 'Solicitação não está disponível'}), 400
        
        if delivery_request.deliverer_id:
            return jsonify({'error': 'Solicitação já foi aceita'}), 400
        
        delivery_request.deliverer_id = user_id
        delivery_request.status = 'accepted'
        
        db.session.commit()
        
        return jsonify({
            'message': 'Solicitação aceita com sucesso',
            'delivery_request': delivery_request.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route("/delivery-requests/<int:request_id>/status", methods=["PUT"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["status"]
)
@secure_headers()
def update_delivery_request_status(request_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": f"/deliverers/delivery-requests/{request_id}/status", "method": "PUT"})
            return jsonify({"error": "Acesso negado"}), 403
        
        sanitized_request_id = SecurityValidator.sanitize_int(request_id)
        if sanitized_request_id is None or sanitized_request_id <= 0:
            return jsonify({"error": "ID da solicitação inválido"}), 400

        delivery_request = DeliveryRequest.query.filter_by(
            id=sanitized_request_id,
            deliverer_id=user_id
        ).first()
        
        if not delivery_request:
            SecurityLogger.log_security_event("delivery_request_not_found", 
                                                {"user_id": user_id, "request_id": sanitized_request_id, "route": f"/deliverers/delivery-requests/{request_id}/status", "method": "PUT"})
            return jsonify({"error": "Solicitação não encontrada ou você não é o entregador responsável"}), 404
        
        data = request.get_json()
        new_status = SecurityValidator.sanitize_string(data.get("status"), 50)
        
        if not new_status:
            return jsonify({"error": "Status é obrigatório"}), 400
        
        # Validar transições de status
        valid_transitions = {
            "accepted": ["picked_up", "cancelled"],
            "picked_up": ["delivered"],
            "delivered": [],
            "cancelled": []
        }
        
        current_transitions = valid_transitions.get(delivery_request.status, [])
        
        if new_status not in current_transitions:
            SecurityLogger.log_security_event("invalid_status_transition", 
                                                {"user_id": user_id, "request_id": sanitized_request_id, "current_status": delivery_request.status, "new_status": new_status})
            return jsonify({"error": f"Transição inválida de {delivery_request.status} para {new_status}"}), 400
        
        delivery_request.status = new_status
        
        # Se entregue, atualizar estatísticas do entregador
        if new_status == "delivered":
            deliverer = Deliverer.query.filter_by(user_id=user_id).first()
            if deliverer:
                deliverer.total_deliveries += 1
        
        db.session.commit()
        
        SecurityLogger.log_security_event("delivery_status_updated", 
                                        {"user_id": user_id, "request_id": sanitized_request_id, "new_status": new_status})

        return jsonify({
            "message": "Status atualizado com sucesso",
            "delivery_request": delivery_request.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@deliverers_bp.route("/my-delivery-requests", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_my_delivery_requests():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            SecurityLogger.log_security_event("user_not_found", 
                                            {"user_id": user_id, "route": "/deliverers/my-delivery-requests", "method": "GET"})
            return jsonify({"error": "Usuário não encontrado"}), 404
        
        if user.user_type == "client":
            requests = DeliveryRequest.query.filter_by(client_id=user_id).order_by(
                DeliveryRequest.created_at.desc()
            ).all()
        elif user.user_type == "deliverer":
            requests = DeliveryRequest.query.filter_by(deliverer_id=user_id).order_by(
                DeliveryRequest.created_at.desc()
            ).all()
        else:
            SecurityLogger.log_security_event("invalid_user_type_access", 
                                                {"user_id": user_id, "user_type": user.user_type, "route": "/deliverers/my-delivery-requests", "method": "GET"})
            return jsonify({"error": "Tipo de usuário inválido"}), 403
        
        return jsonify({
            "delivery_requests": [req.to_dict() for req in requests],
            "total": len(requests)
        }), 200
        
    except Exception as e:
        SecurityLogger.log_error("get_my_delivery_requests_error", {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

