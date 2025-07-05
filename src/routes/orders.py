from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, Order, OrderItem, Product, Store, User
from datetime import datetime
import random
import string
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)

orders_bp = Blueprint("orders", __name__)

def generate_order_number():
    """Gerar número único do pedido"""
    return ''.join(random.choices(string.digits, k=6))

@orders_bp.route("/", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["store_id", "items", "delivery_address", "payment_method"],
    optional_fields=["delivery_fee", "delivery_city", "delivery_state", "delivery_zip_code", "notes"]
)
@secure_headers()
def create_order():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "client":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/orders", "method": "POST"})
            return jsonify({"error": "Acesso negado"}), 403
        
        data = request.get_json()
        
        # Validar store_id
        store_id = SecurityValidator.sanitize_string(str(data["store_id"])) # Sanitiza para int
        if not store_id.isdigit():
            return jsonify({"error": "ID da loja inválido"}), 400
        store_id = int(store_id)

        # Verificar se a loja existe e está ativa
        store = Store.query.filter_by(id=store_id, is_approved=True, is_active=True).first()
        if not store:
            return jsonify({"error": "Loja não encontrada ou inativa"}), 404
        
        # Validar itens do pedido
        if not data["items"] or not isinstance(data["items"], list):
            return jsonify({"error": "Pedido deve conter uma lista de itens"}), 400
        
        if not data["items"]:
            return jsonify({"error": "Pedido deve conter pelo menos um item"}), 400
        
        # Validar delivery_address
        delivery_address = SecurityValidator.sanitize_string(data["delivery_address"], 200)
        if not delivery_address:
            return jsonify({"error": "Endereço de entrega inválido"}), 400

        # Validar payment_method
        payment_method = SecurityValidator.sanitize_string(data["payment_method"], 50)
        allowed_payment_methods = ["credit_card", "debit_card", "cash", "pix"]
        if payment_method not in allowed_payment_methods:
            return jsonify({"error": "Método de pagamento inválido"}), 400

        # Calcular total do pedido e validar produtos
        total_amount = 0
        order_items = []
        
        for item_data in data["items"]:
            # Validar product_id e quantity
            product_id = SecurityValidator.sanitize_string(str(item_data.get("product_id")))
            quantity = SecurityValidator.sanitize_string(str(item_data.get("quantity")))

            if not product_id.isdigit() or not quantity.isdigit():
                return jsonify({"error": "ID do produto ou quantidade inválidos"}), 400
            
            product_id = int(product_id)
            quantity = int(quantity)

            if quantity <= 0:
                return jsonify({"error": "Quantidade do produto deve ser positiva"}), 400

            product = Product.query.filter_by(
                id=product_id, 
                store_id=store_id,
                is_active=True
            ).first()
            
            if not product:
                return jsonify({"error": f"Produto {product_id} não encontrado na loja {store_id}"}), 404
            
            if product.stock_quantity < quantity:
                return jsonify({"error": f"Estoque insuficiente para {product.name}. Disponível: {product.stock_quantity}"}), 400
            
            item_total = product.price * quantity
            total_amount += item_total
            
            order_items.append({
                "product": product,
                "quantity": quantity,
                "unit_price": product.price,
                "total_price": item_total
            })
        
        # Sanitizar campos opcionais
        delivery_fee = float(SecurityValidator.sanitize_string(str(data.get("delivery_fee", 0.0))))
        delivery_city = SecurityValidator.sanitize_string(data.get("delivery_city", ""), 50)
        delivery_state = SecurityValidator.sanitize_string(data.get("delivery_state", ""), 2)
        delivery_zip_code = SecurityValidator.sanitize_string(data.get("delivery_zip_code", ""), 10)
        notes = SecurityValidator.sanitize_string(data.get("notes", ""), 500)

        # Gerar número único do pedido
        order_number = generate_order_number()
        while Order.query.filter_by(order_number=order_number).first():
            order_number = generate_order_number()
        
        order = Order(
            client_id=user_id,
            store_id=store_id,
            order_number=order_number,
            total_amount=total_amount,
            delivery_fee=delivery_fee,
            payment_method=payment_method,
            delivery_address=delivery_address,
            delivery_city=delivery_city,
            delivery_state=delivery_state,
            delivery_zip_code=delivery_zip_code,
            notes=notes
        )
        
        db.session.add(order)
        db.session.flush()  # Para obter o ID do pedido
        
        # Criar itens do pedido e atualizar estoque
        for item_data in order_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data["product"].id,
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                total_price=item_data["total_price"]
            )
            db.session.add(order_item)
            
            # Atualizar estoque
            item_data["product"].stock_quantity -= item_data["quantity"]
        
        db.session.commit()
        
        SecurityLogger.log_security_event("order_create_success", {"user_id": user_id, "order_id": order.id})
        
        return jsonify({
            "message": "Pedido criado com sucesso",
            "order": order.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("order_create_error", {"error": str(e), "user_id": user_id, "data": data})
        return jsonify({"error": "Erro interno do servidor"}), 500

@orders_bp.route("/my-orders", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_my_orders():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/orders/my-orders", "method": "GET"})
            return jsonify({"error": "Usuário não encontrado"}), 404
        
        if user.user_type == "client":
            orders = Order.query.filter_by(client_id=user_id).order_by(Order.created_at.desc()).all()
        elif user.user_type == "store":
            store = Store.query.filter_by(user_id=user_id).first()
            if not store:
                SecurityLogger.log_security_event("store_not_found", 
                                                {"user_id": user_id, "route": "/orders/my-orders", "method": "GET"})
                return jsonify({"error": "Loja não encontrada"}), 404
            orders = Order.query.filter_by(store_id=store.id).order_by(Order.created_at.desc()).all()
        elif user.user_type == "deliverer":
            orders = Order.query.filter_by(deliverer_id=user_id).order_by(Order.created_at.desc()).all()
        else:
            SecurityLogger.log_security_event("invalid_user_type", 
                                            {"user_id": user_id, "user_type": user.user_type, "route": "/orders/my-orders", "method": "GET"})
            return jsonify({"error": "Tipo de usuário inválido"}), 403
        
        return jsonify({
            "orders": [order.to_dict() for order in orders],
            "total": len(orders)
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_my_orders_error", {"error": str(e), "user_id": user_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@orders_bp.route("/<int:order_id>", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_order(order_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        # Sanitizar order_id
        order_id = int(SecurityValidator.sanitize_string(str(order_id)))

        order = Order.query.get(order_id)
        
        if not order:
            return jsonify({"error": "Pedido não encontrado"}), 404
        
        # Verificar permissão de acesso
        has_access = False
        if user.user_type == "client" and order.client_id == user_id:
            has_access = True
        elif user.user_type == "store":
            store = Store.query.filter_by(user_id=user_id).first()
            if store and order.store_id == store.id:
                has_access = True
        elif user.user_type == "deliverer" and order.deliverer_id == user_id:
            has_access = True
        elif user.user_type == "admin":
            has_access = True
        
        if not has_access:
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": f"/orders/{order_id}", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        return jsonify(order.to_dict()), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_order_error", {"error": str(e), "user_id": user_id, "order_id": order_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@orders_bp.route("/<int:order_id>/status", methods=["PUT"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["status"]
)
@secure_headers()
def update_order_status(order_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        # Sanitizar order_id
        order_id = int(SecurityValidator.sanitize_string(str(order_id)))

        order = Order.query.get(order_id)
        
        if not order:
            return jsonify({"error": "Pedido não encontrado"}), 404
        
        data = request.get_json()
        new_status = SecurityValidator.sanitize_string(data.get("status"), 50)
        
        if not new_status:
            return jsonify({"error": "Status é obrigatório"}), 400
        
        # Verificar permissão e status válidos
        valid_transitions = {
            "store": {
                "pending": ["accepted", "cancelled"],
                "accepted": ["preparing"],
                "preparing": ["ready"]
            },
            "deliverer": {
                "ready": ["delivering"],
                "delivering": ["delivered"]
            },
            "admin": {
                "pending": ["accepted", "cancelled"],
                "accepted": ["preparing", "cancelled"],
                "preparing": ["ready", "cancelled"],
                "ready": ["delivering", "cancelled"],
                "delivering": ["delivered", "cancelled"]
            }
        }
        
        has_permission = False
        
        if user.user_type == "store":
            store = Store.query.filter_by(user_id=user_id).first()
            if store and order.store_id == store.id:
                has_permission = True
        elif user.user_type == "deliverer" and order.deliverer_id == user_id:
            has_permission = True
        elif user.user_type == "admin":
            has_permission = True
        
        if not has_permission:
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": f"/orders/{order_id}/status", "method": "PUT"})
            return jsonify({"error": "Acesso negado"}), 403
        
        # Verificar se a transição é válida
        user_transitions = valid_transitions.get(user.user_type, {})
        current_status_transitions = user_transitions.get(order.status, [])
        
        if new_status not in current_status_transitions:
            SecurityLogger.log_security_event("invalid_status_transition", 
                                            {"user_id": user_id, "order_id": order_id, "current_status": order.status, "new_status": new_status})
            return jsonify({"error": f"Transição de {order.status} para {new_status} não permitida"}), 400
        
        order.status = new_status
        order.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        SecurityLogger.log_security_event("order_status_update_success", {"user_id": user_id, "order_id": order.id, "new_status": new_status})
        
        return jsonify({
            "message": "Status do pedido atualizado com sucesso",
            "order": order.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("update_order_status_error", {"error": str(e), "user_id": user_id, "order_id": order_id, "data": data})
        return jsonify({"error": "Erro interno do servidor"}), 500

@orders_bp.route("/available", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_available_orders():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/orders/available", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        # Buscar pedidos prontos para entrega
        orders = Order.query.filter_by(status="ready", deliverer_id=None).order_by(Order.created_at.desc()).all()
        
        return jsonify({
            "orders": [order.to_dict() for order in orders],
            "total": len(orders)
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_available_orders_error", {"error": str(e), "user_id": user_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@orders_bp.route("/<int:order_id>/accept", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=1, per="user")
@secure_headers()
def accept_delivery(order_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "deliverer":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": f"/orders/{order_id}/accept", "method": "POST"})
            return jsonify({"error": "Acesso negado"}), 403
        
        # Sanitizar order_id
        order_id = int(SecurityValidator.sanitize_string(str(order_id)))

        order = Order.query.get(order_id)
        
        if not order:
            return jsonify({"error": "Pedido não encontrado"}), 404
        
        if order.status != "ready":
            SecurityLogger.log_security_event("invalid_order_status_for_accept", 
                                            {"user_id": user_id, "order_id": order_id, "current_status": order.status})
            return jsonify({"error": "Pedido não está disponível para entrega"}), 400
        
        if order.deliverer_id:
            SecurityLogger.log_security_event("order_already_accepted", 
                                            {"user_id": user_id, "order_id": order_id, "deliverer_id": order.deliverer_id})
            return jsonify({"error": "Pedido já foi aceito por outro entregador"}), 400
        
        order.deliverer_id = user_id
        order.status = "delivering"
        order.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        SecurityLogger.log_security_event("delivery_accepted_success", {"user_id": user_id, "order_id": order.id})
        
        return jsonify({
            "message": "Entrega aceita com sucesso",
            "order": order.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("accept_delivery_error", {"error": str(e), "user_id": user_id, "order_id": order_id})
        return jsonify({"error": "Erro interno do servidor"}), 500


