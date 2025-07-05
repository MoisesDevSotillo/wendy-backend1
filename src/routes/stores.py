from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, Store, User, Product, Category, AllowedCity
from sqlalchemy import or_
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)
from datetime import datetime

stores_bp = Blueprint("stores", __name__)

@stores_bp.route("/", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_stores():
    try:
        # Parâmetros de filtro
        category_name = request.args.get("category")
        city_name = request.args.get("city")
        search = request.args.get("search")
        approved_only = request.args.get("approved_only", "true").lower() == "true"
        
        query = Store.query
        
        if approved_only:
            query = query.filter(Store.is_approved == True, Store.is_active == True)
        
        if category_name:
            category = Category.query.filter_by(name=category_name).first()
            if category:
                query = query.filter(Store.category_id == category.id)
            else:
                return jsonify({"stores": [], "total": 0}), 200 # Categoria não encontrada
        
        if city_name:
            allowed_city = AllowedCity.query.filter_by(name=city_name.lower()).first()
            if allowed_city:
                query = query.filter(Store.city == city_name.lower())
            else:
                return jsonify({"stores": [], "total": 0}), 200 # Cidade não encontrada
        
        if search:
            search_term = f"%{SecurityValidator.sanitize_string(search)}%"
            query = query.filter(
                or_(
                    Store.name.ilike(search_term),
                    Store.description.ilike(search_term)
                )
            )
        
        # Ordenar por privilégio primeiro, depois por nome
        stores = query.order_by(Store.is_privileged.desc(), Store.name.asc()).all()
        
        return jsonify({
            "stores": [store.to_dict() for store in stores],
            "total": len(stores)
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_stores_error", {"error": str(e), "query_params": request.args.to_dict()})
        return jsonify({"error": "Erro interno do servidor"}), 500

@stores_bp.route("/<int:store_id>", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_store(store_id):
    try:
        # Sanitizar store_id
        store_id = int(SecurityValidator.sanitize_string(str(store_id)))
        
        store = Store.query.get(store_id)
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        # Buscar produtos da loja
        products = Product.query.filter_by(store_id=store_id, is_active=True).all()
        
        store_data = store.to_dict()
        store_data["products"] = [product.to_dict() for product in products]
        
        return jsonify(store_data), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_store_error", {"error": str(e), "store_id": store_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@stores_bp.route("/my-store", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_my_store():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/stores/my-store", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        return jsonify(store.to_dict()), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_my_store_error", {"error": str(e), "user_id": user_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@stores_bp.route("/my-store", methods=["PUT"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=5, per="user")
@validate_json_input(
    optional_fields=[
        "name", "description", "category_id", "address", "city", "state", "zip_code", "phone"
    ]
)
@secure_headers()
def update_my_store():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/stores/my-store", "method": "PUT"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        data = request.get_json()
        
        # Atualizar campos permitidos com sanitização e validação
        if "name" in data:
            store.name = SecurityValidator.sanitize_string(data["name"], 100)
        if "description" in data:
            store.description = SecurityValidator.sanitize_string(data["description"], 500)
        if "category_id" in data:
            category_id = SecurityValidator.sanitize_string(str(data["category_id"])) # Sanitiza para int
            if not category_id.isdigit():
                return jsonify({"error": "ID da categoria inválido"}), 400
            category = Category.query.get(int(category_id))
            if not category:
                return jsonify({"error": "Categoria não encontrada"}), 404
            store.category_id = int(category_id)
        if "address" in data:
            store.address = SecurityValidator.sanitize_string(data["address"], 200)
        if "city" in data:
            store.city = SecurityValidator.sanitize_string(data["city"], 50)
        if "state" in data:
            store.state = SecurityValidator.sanitize_string(data["state"], 2)
        if "zip_code" in data:
            zip_code = SecurityValidator.sanitize_string(data["zip_code"], 10)
            if not SecurityValidator.validate_zip_code(zip_code):
                return jsonify({"error": "CEP inválido"}), 400
            store.zip_code = zip_code
        if "phone" in data:
            phone = SecurityValidator.sanitize_string(data["phone"], 20)
            if not SecurityValidator.validate_phone(phone):
                return jsonify({"error": "Telefone inválido"}), 400
            store.phone = phone
        
        db.session.commit()
        
        SecurityLogger.log_security_event("store_update_success", {"user_id": user_id, "store_id": store.id})
        
        return jsonify({
            "message": "Loja atualizada com sucesso",
            "store": store.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("update_my_store_error", {"error": str(e), "user_id": user_id, "data": request.get_json()})
        return jsonify({"error": "Erro interno do servidor"}), 500

@stores_bp.route("/categories", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_categories():
    try:
        # Buscar categorias ativas e aprovadas
        categories = Category.query.filter_by(is_active=True).all()
        
        return jsonify({
            "categories": [cat.to_dict() for cat in categories]
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_categories_error", {"error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@stores_bp.route("/stats", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_store_stats():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/stores/stats", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        # Estatísticas da loja
        from src.models.wendy_models import Order, OrderItem
        
        total_products = Product.query.filter_by(store_id=store.id).count()
        active_products = Product.query.filter_by(store_id=store.id, is_active=True).count()
        out_of_stock = Product.query.filter_by(store_id=store.id, stock_quantity=0).count()
        
        total_orders = Order.query.filter_by(store_id=store.id).count()
        pending_orders = Order.query.filter_by(store_id=store.id, status="pending").count()
        
        # Vendas do mês atual
        current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_orders = Order.query.filter(
            Order.store_id == store.id,
            Order.created_at >= current_month,
            Order.status.in_(["delivered", "ready", "preparing"])
        ).all()
        
        monthly_revenue = sum(order.total_amount for order in monthly_orders)
        
        # Vendas de hoje
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_orders = Order.query.filter(
            Order.store_id == store.id,
            Order.created_at >= today,
            Order.status.in_(["delivered", "ready", "preparing"])
        ).all()
        
        daily_revenue = sum(order.total_amount for order in daily_orders)
        
        return jsonify({
            "products": {
                "total": total_products,
                "active": active_products,
                "out_of_stock": out_of_stock
            },
            "orders": {
                "total": total_orders,
                "pending": pending_orders
            },
            "revenue": {
                "daily": daily_revenue,
                "monthly": monthly_revenue
            }
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_store_stats_error", {"error": str(e), "user_id": user_id})
        return jsonify({"error": "Erro interno do servidor"}), 500


