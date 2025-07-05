from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, Order, Product, Store, User
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)

reports_bp = Blueprint("reports", __name__)

@reports_bp.route("/sales-by-store", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=20, window_minutes=5, per="user")
@secure_headers()
def get_sales_by_store():
    """Relatório de vendas por loja"""
    try:
        user_id = get_jwt_identity()
        
        # Verificar se o usuário é admin ou lojista
        user = User.query.get(user_id)
        if not user:
            SecurityLogger.log_security_event("user_not_found_for_sales_report", 
                                            {"user_id": user_id})
            return jsonify({"error": "Usuário não encontrado"}), 404
        
        if user.user_type not in ["admin", "store_owner"]:
            SecurityLogger.log_security_event("unauthorized_sales_report_access", 
                                            {"user_id": user_id, "user_type": user.user_type})
            return jsonify({"error": "Acesso negado"}), 403
        
        # Parâmetros de filtro opcionais
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        store_id = request.args.get('store_id')
        
        # Sanitizar parâmetros
        if start_date:
            start_date = SecurityValidator.sanitize_string(start_date, max_length=10)
        if end_date:
            end_date = SecurityValidator.sanitize_string(end_date, max_length=10)
        if store_id:
            store_id = SecurityValidator.sanitize_int(store_id)
        
        # Query base
        query = db.session.query(
            Store.id,
            Store.name,
            func.count(Order.id).label('total_orders'),
            func.sum(Order.total_amount).label('total_revenue'),
            func.avg(Order.total_amount).label('average_order_value')
        ).join(Order, Store.id == Order.store_id).filter(Order.status == 'delivered')
        
        # Filtros de data
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Order.created_at >= start_date_obj)
            except ValueError:
                return jsonify({"error": "Formato de data inicial inválido (use YYYY-MM-DD)"}), 400
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Order.created_at < end_date_obj)
            except ValueError:
                return jsonify({"error": "Formato de data final inválido (use YYYY-MM-DD)"}), 400
        
        # Se for lojista, filtrar apenas suas lojas
        if user.user_type == "store_owner":
            user_stores = Store.query.filter_by(owner_id=user_id).all()
            store_ids = [store.id for store in user_stores]
            if not store_ids:
                return jsonify({"sales_by_store": []}), 200
            query = query.filter(Store.id.in_(store_ids))
        elif store_id:
            query = query.filter(Store.id == store_id)
        
        # Agrupar por loja
        query = query.group_by(Store.id, Store.name).order_by(func.sum(Order.total_amount).desc())
        
        results = query.all()
        
        sales_data = []
        for result in results:
            sales_data.append({
                "store_id": result.id,
                "store_name": result.name,
                "total_orders": result.total_orders,
                "total_revenue": float(result.total_revenue) if result.total_revenue else 0,
                "average_order_value": float(result.average_order_value) if result.average_order_value else 0
            })
        
        SecurityLogger.log_security_event("sales_report_accessed", 
                                        {"user_id": user_id, "stores_count": len(sales_data)})
        
        return jsonify({"sales_by_store": sales_data}), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("sales_report_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@reports_bp.route("/deliverer-performance", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=20, window_minutes=5, per="user")
@secure_headers()
def get_deliverer_performance():
    """Relatório de performance de entregadores"""
    try:
        user_id = get_jwt_identity()
        
        # Verificar se o usuário é admin
        user = User.query.get(user_id)
        if not user or user.user_type != "admin":
            SecurityLogger.log_security_event("unauthorized_deliverer_report_access", 
                                            {"user_id": user_id, "user_type": user.user_type if user else None})
            return jsonify({"error": "Acesso negado"}), 403
        
        # Parâmetros de filtro opcionais
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Query para performance de entregadores
        query = db.session.query(
            User.id,
            User.name,
            func.count(Order.id).label('total_deliveries'),
            func.avg(Order.delivery_time).label('average_delivery_time'),
            func.sum(Order.delivery_fee).label('total_delivery_fees')
        ).join(Order, User.id == Order.deliverer_id).filter(
            User.user_type == 'deliverer',
            Order.status == 'delivered'
        )
        
        # Filtros de data
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Order.created_at >= start_date_obj)
            except ValueError:
                return jsonify({"error": "Formato de data inicial inválido (use YYYY-MM-DD)"}), 400
        
        if end_date:
            try:
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Order.created_at < end_date_obj)
            except ValueError:
                return jsonify({"error": "Formato de data final inválido (use YYYY-MM-DD)"}), 400
        
        # Agrupar por entregador
        query = query.group_by(User.id, User.name).order_by(func.count(Order.id).desc())
        
        results = query.all()
        
        performance_data = []
        for result in results:
            performance_data.append({
                "deliverer_id": result.id,
                "deliverer_name": result.name,
                "total_deliveries": result.total_deliveries,
                "average_delivery_time": float(result.average_delivery_time) if result.average_delivery_time else 0,
                "total_delivery_fees": float(result.total_delivery_fees) if result.total_delivery_fees else 0
            })
        
        SecurityLogger.log_security_event("deliverer_report_accessed", 
                                        {"user_id": user_id, "deliverers_count": len(performance_data)})
        
        return jsonify({"deliverer_performance": performance_data}), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("deliverer_report_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@reports_bp.route("/admin-dashboard-stats", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_admin_dashboard_stats():
    """Estatísticas do dashboard do administrador"""
    try:
        user_id = get_jwt_identity()
        
        # Verificar se o usuário é admin
        user = User.query.get(user_id)
        if not user or user.user_type != "admin":
            SecurityLogger.log_security_event("unauthorized_admin_stats_access", 
                                            {"user_id": user_id, "user_type": user.user_type if user else None})
            return jsonify({"error": "Acesso negado"}), 403
        
        # Estatísticas gerais
        total_users = User.query.count()
        total_stores = Store.query.count()
        active_stores = Store.query.filter_by(approval_status='approved').count()
        total_orders = Order.query.count()
        
        # Estatísticas do mês atual
        current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_orders = Order.query.filter(Order.created_at >= current_month_start).count()
        monthly_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.created_at >= current_month_start,
            Order.status == 'delivered'
        ).scalar() or 0
        
        # Estatísticas de hoje
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = Order.query.filter(Order.created_at >= today_start).count()
        today_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.created_at >= today_start,
            Order.status == 'delivered'
        ).scalar() or 0
        
        # Pedidos por status
        orders_by_status = {}
        status_counts = db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
        for status, count in status_counts:
            orders_by_status[status] = count
        
        # Top 5 lojas por receita (último mês)
        last_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1)
        top_stores = db.session.query(
            Store.name,
            func.sum(Order.total_amount).label('revenue')
        ).join(Order, Store.id == Order.store_id).filter(
            Order.created_at >= last_month_start,
            Order.status == 'delivered'
        ).group_by(Store.id, Store.name).order_by(func.sum(Order.total_amount).desc()).limit(5).all()
        
        top_stores_data = [{"name": store.name, "revenue": float(store.revenue)} for store in top_stores]
        
        stats = {
            "general": {
                "total_users": total_users,
                "total_stores": total_stores,
                "active_stores": active_stores,
                "total_orders": total_orders
            },
            "monthly": {
                "orders": monthly_orders,
                "revenue": float(monthly_revenue)
            },
            "today": {
                "orders": today_orders,
                "revenue": float(today_revenue)
            },
            "orders_by_status": orders_by_status,
            "top_stores_last_month": top_stores_data
        }
        
        SecurityLogger.log_security_event("admin_stats_accessed", 
                                        {"user_id": user_id})
        
        return jsonify(stats), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("admin_stats_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

