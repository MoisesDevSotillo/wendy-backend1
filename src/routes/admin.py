from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, User, Store, Deliverer, Order, Product, AllowedCity, PlatformSettings, Category, Subcategory
from datetime import datetime, timedelta
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__)

def admin_required():
    """Decorator para verificar se o usuário é admin"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return user and user.user_type == 'admin'

@admin_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Estatísticas gerais
        total_stores = Store.query.count()
        active_stores = Store.query.filter_by(is_approved=True, is_active=True).count()
        pending_stores = Store.query.filter_by(is_approved=False, is_active=True).count()
        
        total_deliverers = Deliverer.query.count()
        active_deliverers = Deliverer.query.filter_by(is_approved=True).count()
        online_deliverers = Deliverer.query.filter_by(is_approved=True, is_online=True).count()
        
        total_orders = Order.query.count()
        
        # Receita total
        total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.status == 'delivered'
        ).scalar() or 0
        
        # Receita do mês atual
        current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.status == 'delivered',
            Order.updated_at >= current_month
        ).scalar() or 0
        
        # Pedidos do mês
        monthly_orders = Order.query.filter(
            Order.created_at >= current_month
        ).count()
        
        return jsonify({
            'stores': {
                'total': total_stores,
                'active': active_stores,
                'pending': pending_stores
            },
            'deliverers': {
                'total': total_deliverers,
                'active': active_deliverers,
                'online': online_deliverers
            },
            'orders': {
                'total': total_orders,
                'monthly': monthly_orders
            },
            'revenue': {
                'total': total_revenue,
                'monthly': monthly_revenue
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/pending', methods=['GET'])
@jwt_required()
def get_pending_stores():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        stores = Store.query.filter_by(is_approved=False, is_active=True).order_by(
            Store.created_at.desc()
        ).all()
        
        stores_data = []
        for store in stores:
            store_dict = store.to_dict()
            store_dict['owner_name'] = store.user.name if store.user else None
            store_dict['owner_email'] = store.user.email if store.user else None
            stores_data.append(store_dict)
        
        return jsonify({
            'stores': stores_data,
            'total': len(stores_data)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/<int:store_id>/approve', methods=['POST'])
@jwt_required()
def approve_store(store_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        store = Store.query.get(store_id)
        
        if not store:
            return jsonify({'error': 'Loja não encontrada'}), 404
        
        # Aprovar loja
        store.is_approved = True
        store.approval_status = 'approved'
        store.rejection_reason = None
        
        # Aprovar usuário também
        store.user.is_approved = True
        store.user.approval_status = 'approved'
        store.user.rejection_reason = None
        
        db.session.commit()
        
        return jsonify({
            'message': 'Loja aprovada com sucesso',
            'store': store.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/<int:store_id>/reject', methods=['POST'])
@jwt_required()
def reject_store(store_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        store = Store.query.get(store_id)
        
        if not store:
            return jsonify({'error': 'Loja não encontrada'}), 404
        
        data = request.get_json()
        reason = data.get('reason', 'Não especificado')
        
        # Rejeitar loja
        store.is_approved = False
        store.approval_status = 'rejected'
        store.rejection_reason = reason
        store.is_active = False
        
        # Rejeitar usuário também
        store.user.is_approved = False
        store.user.approval_status = 'rejected'
        store.user.rejection_reason = reason
        store.user.is_active = False
        
        db.session.commit()
        
        return jsonify({
            'message': 'Loja rejeitada com sucesso',
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/deliverers/pending', methods=['GET'])
@jwt_required()
def get_pending_deliverers():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverers = Deliverer.query.filter_by(is_approved=False).order_by(
            Deliverer.created_at.desc()
        ).all()
        
        return jsonify({
            'deliverers': [deliverer.to_dict() for deliverer in deliverers],
            'total': len(deliverers)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/deliverers/<int:deliverer_id>/approve', methods=['POST'])
@jwt_required()
def approve_deliverer(deliverer_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverer = Deliverer.query.get(deliverer_id)
        
        if not deliverer:
            return jsonify({'error': 'Entregador não encontrado'}), 404
        
        # Aprovar entregador
        deliverer.is_approved = True
        deliverer.approval_status = 'approved'
        deliverer.rejection_reason = None
        
        # Aprovar usuário também
        deliverer.user.is_approved = True
        deliverer.user.approval_status = 'approved'
        deliverer.user.rejection_reason = None
        
        db.session.commit()
        
        return jsonify({
            'message': 'Entregador aprovado com sucesso',
            'deliverer': deliverer.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/deliverers/<int:deliverer_id>/reject', methods=['POST'])
@jwt_required()
def reject_deliverer(deliverer_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverer = Deliverer.query.get(deliverer_id)
        
        if not deliverer:
            return jsonify({'error': 'Entregador não encontrado'}), 404
        
        data = request.get_json()
        reason = data.get('reason', 'Não especificado')
        
        # Rejeitar entregador
        deliverer.is_approved = False
        deliverer.approval_status = 'rejected'
        deliverer.rejection_reason = reason
        
        # Rejeitar usuário também
        deliverer.user.is_approved = False
        deliverer.user.approval_status = 'rejected'
        deliverer.user.rejection_reason = reason
        deliverer.user.is_active = False
        
        db.session.commit()
        
        return jsonify({
            'message': 'Entregador rejeitado com sucesso',
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores', methods=['GET'])
@jwt_required()
def get_all_stores():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status = request.args.get('status')  # 'approved', 'pending', 'rejected'
        
        query = Store.query
        
        if status == 'approved':
            query = query.filter_by(is_approved=True, is_active=True)
        elif status == 'pending':
            query = query.filter_by(is_approved=False, is_active=True)
        elif status == 'rejected':
            query = query.filter_by(is_active=False)
        
        stores = query.order_by(Store.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        stores_data = []
        for store in stores.items:
            store_dict = store.to_dict()
            store_dict['owner_name'] = store.user.name if store.user else None
            store_dict['owner_email'] = store.user.email if store.user else None
            stores_data.append(store_dict)
        
        return jsonify({
            'stores': stores_data,
            'total': stores.total,
            'pages': stores.pages,
            'current_page': page
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/deliverers', methods=['GET'])
@jwt_required()
def get_all_deliverers():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status = request.args.get('status')  # 'approved', 'pending'
        
        query = Deliverer.query
        
        if status == 'approved':
            query = query.filter_by(is_approved=True)
        elif status == 'pending':
            query = query.filter_by(is_approved=False)
        
        deliverers = query.order_by(Deliverer.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'deliverers': [deliverer.to_dict() for deliverer in deliverers.items],
            'total': deliverers.total,
            'pages': deliverers.pages,
            'current_page': page
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/orders', methods=['GET'])
@jwt_required()
def get_all_orders():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status = request.args.get('status')
        
        query = Order.query
        
        if status:
            query = query.filter_by(status=status)
        
        orders = query.order_by(Order.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'orders': [order.to_dict() for order in orders.items],
            'total': orders.total,
            'pages': orders.pages,
            'current_page': page
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/reports/revenue', methods=['GET'])
@jwt_required()
def get_revenue_report():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Relatório de receita dos últimos 30 dias
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        daily_revenue = db.session.query(
            func.date(Order.updated_at).label('date'),
            func.sum(Order.total_amount).label('revenue'),
            func.count(Order.id).label('orders')
        ).filter(
            Order.status == 'delivered',
            Order.updated_at >= thirty_days_ago
        ).group_by(func.date(Order.updated_at)).all()
        
        revenue_data = []
        for day in daily_revenue:
            revenue_data.append({
                'date': day.date.isoformat(),
                'revenue': float(day.revenue),
                'orders': day.orders
            })
        
        return jsonify({
            'daily_revenue': revenue_data,
            'period': '30_days'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# Rotas para exclusão de cadastros

@admin_bp.route('/users/<int:user_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        if user.user_type == 'admin':
            return jsonify({'error': 'Não é possível excluir administradores'}), 403
        
        data = request.get_json()
        reason = data.get('reason', 'Violação dos termos de uso')
        
        # Excluir registros relacionados primeiro
        if user.user_type == 'store' and user.store:
            # Desativar produtos da loja
            for product in user.store.products:
                product.is_active = False
            
            # Cancelar pedidos pendentes
            pending_orders = Order.query.filter_by(store_id=user.store.id, status='pending').all()
            for order in pending_orders:
                order.status = 'cancelled'
            
            db.session.delete(user.store)
        
        elif user.user_type == 'deliverer' and user.deliverer_profile:
            # Cancelar entregas pendentes
            pending_deliveries = Order.query.filter_by(deliverer_id=user.id).filter(
                Order.status.in_(['accepted', 'preparing', 'ready', 'delivering'])
            ).all()
            for order in pending_deliveries:
                order.deliverer_id = None
                order.status = 'pending'
            
            db.session.delete(user.deliverer_profile)
        
        # Excluir o usuário
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'message': f'Usuário {user.name} excluído com sucesso',
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/<int:store_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_store(store_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        store = Store.query.get(store_id)
        
        if not store:
            return jsonify({'error': 'Loja não encontrada'}), 404
        
        data = request.get_json()
        reason = data.get('reason', 'Violação dos termos de uso')
        
        # Desativar produtos da loja
        for product in store.products:
            product.is_active = False
        
        # Cancelar pedidos pendentes
        pending_orders = Order.query.filter_by(store_id=store.id, status='pending').all()
        for order in pending_orders:
            order.status = 'cancelled'
        
        # Excluir a loja e o usuário
        user = store.user
        db.session.delete(store)
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'message': f'Loja {store.name} excluída com sucesso',
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/deliverers/<int:deliverer_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_deliverer(deliverer_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverer = Deliverer.query.get(deliverer_id)
        
        if not deliverer:
            return jsonify({'error': 'Entregador não encontrado'}), 404
        
        data = request.get_json()
        reason = data.get('reason', 'Violação dos termos de uso')
        
        # Cancelar entregas pendentes
        pending_deliveries = Order.query.filter_by(deliverer_id=deliverer.user_id).filter(
            Order.status.in_(['accepted', 'preparing', 'ready', 'delivering'])
        ).all()
        for order in pending_deliveries:
            order.deliverer_id = None
            order.status = 'pending'
        
        # Excluir o entregador e o usuário
        user = deliverer.user
        db.session.delete(deliverer)
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            'message': f'Entregador {user.name} excluído com sucesso',
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Rotas para reativar usuários rejeitados

@admin_bp.route('/stores/<int:store_id>/reactivate', methods=['POST'])
@jwt_required()
def reactivate_store(store_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        store = Store.query.get(store_id)
        
        if not store:
            return jsonify({'error': 'Loja não encontrada'}), 404
        
        # Reativar loja
        store.is_active = True
        store.is_approved = False
        store.approval_status = 'pending'
        store.rejection_reason = None
        
        # Reativar usuário
        store.user.is_active = True
        store.user.is_approved = False
        store.user.approval_status = 'pending'
        store.user.rejection_reason = None
        
        db.session.commit()
        
        return jsonify({
            'message': 'Loja reativada e colocada em análise novamente',
            'store': store.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/deliverers/<int:deliverer_id>/reactivate', methods=['POST'])
@jwt_required()
def reactivate_deliverer(deliverer_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverer = Deliverer.query.get(deliverer_id)
        
        if not deliverer:
            return jsonify({'error': 'Entregador não encontrado'}), 404
        
        # Reativar entregador
        deliverer.is_approved = False
        deliverer.approval_status = 'pending'
        deliverer.rejection_reason = None
        
        # Reativar usuário
        deliverer.user.is_active = True
        deliverer.user.is_approved = False
        deliverer.user.approval_status = 'pending'
        deliverer.user.rejection_reason = None
        
        db.session.commit()
        
        return jsonify({
            'message': 'Entregador reativado e colocado em análise novamente',
            'deliverer': deliverer.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# Rotas para gerenciar cidades permitidas

@admin_bp.route('/cities', methods=['GET'])
@jwt_required()
def get_allowed_cities():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        cities = AllowedCity.query.order_by(AllowedCity.name).all()
        
        return jsonify({
            'cities': [city.to_dict() for city in cities],
            'total': len(cities)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/cities', methods=['POST'])
@jwt_required()
def add_allowed_city():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Validar dados obrigatórios
        required_fields = ['name', 'state']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        # Verificar se cidade já existe
        existing_city = AllowedCity.query.filter_by(
            name=data['name'], 
            state=data['state']
        ).first()
        
        if existing_city:
            return jsonify({'error': 'Cidade já cadastrada'}), 400
        
        # Criar nova cidade
        city = AllowedCity(
            name=data['name'],
            state=data['state'],
            delivery_fee_per_km=data.get('delivery_fee_per_km', 2.0),
            minimum_order_value=data.get('minimum_order_value', 30.0),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(city)
        db.session.commit()
        
        return jsonify({
            'message': 'Cidade adicionada com sucesso',
            'city': city.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/cities/<int:city_id>', methods=['PUT'])
@jwt_required()
def update_allowed_city(city_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        city = AllowedCity.query.get(city_id)
        
        if not city:
            return jsonify({'error': 'Cidade não encontrada'}), 404
        
        data = request.get_json()
        
        # Atualizar campos
        if 'name' in data:
            city.name = data['name']
        if 'state' in data:
            city.state = data['state']
        if 'delivery_fee_per_km' in data:
            city.delivery_fee_per_km = data['delivery_fee_per_km']
        if 'minimum_order_value' in data:
            city.minimum_order_value = data['minimum_order_value']
        if 'is_active' in data:
            city.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Cidade atualizada com sucesso',
            'city': city.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/cities/<int:city_id>', methods=['DELETE'])
@jwt_required()
def delete_allowed_city(city_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        city = AllowedCity.query.get(city_id)
        
        if not city:
            return jsonify({'error': 'Cidade não encontrada'}), 404
        
        db.session.delete(city)
        db.session.commit()
        
        return jsonify({
            'message': f'Cidade {city.name} removida com sucesso'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Rota pública para verificar cidades disponíveis
@admin_bp.route('/cities/available', methods=['GET'])
def get_available_cities():
    try:
        cities = AllowedCity.query.filter_by(is_active=True).order_by(AllowedCity.name).all()
        
        return jsonify({
            'cities': [city.to_dict() for city in cities],
            'total': len(cities)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Rotas para configurações da plataforma

@admin_bp.route('/settings', methods=['GET'])
@jwt_required()
def get_platform_settings():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        settings = PlatformSettings.query.all()
        
        settings_dict = {}
        for setting in settings:
            settings_dict[setting.setting_key] = {
                'value': setting.setting_value,
                'description': setting.description,
                'updated_at': setting.updated_at.isoformat() if setting.updated_at else None
            }
        
        return jsonify({
            'settings': settings_dict
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/settings', methods=['POST'])
@jwt_required()
def update_platform_settings():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        for key, value in data.items():
            setting = PlatformSettings.query.filter_by(setting_key=key).first()
            
            if setting:
                setting.setting_value = str(value)
                setting.updated_at = datetime.utcnow()
            else:
                setting = PlatformSettings(
                    setting_key=key,
                    setting_value=str(value)
                )
                db.session.add(setting)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Configurações atualizadas com sucesso'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# Rotas para gerenciar categorias

@admin_bp.route('/categories', methods=['GET'])
def get_categories():
    try:
        categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order, Category.name).all()
        
        return jsonify({
            'categories': [category.to_dict() for category in categories],
            'total': len(categories)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/categories/admin', methods=['GET'])
@jwt_required()
def get_all_categories():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        categories = Category.query.order_by(Category.sort_order, Category.name).all()
        
        return jsonify({
            'categories': [category.to_dict() for category in categories],
            'total': len(categories)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/categories', methods=['POST'])
@jwt_required()
def create_category():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Validar dados obrigatórios
        if 'name' not in data or not data['name']:
            return jsonify({'error': 'Nome da categoria é obrigatório'}), 400
        
        # Verificar se categoria já existe
        existing_category = Category.query.filter_by(name=data['name']).first()
        if existing_category:
            return jsonify({'error': 'Categoria já existe'}), 400
        
        # Criar nova categoria
        category = Category(
            name=data['name'],
            description=data.get('description', ''),
            icon=data.get('icon', ''),
            color=data.get('color', '#66CCFF'),
            sort_order=data.get('sort_order', 0)
        )
        
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'message': 'Categoria criada com sucesso',
            'category': category.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/categories/<int:category_id>', methods=['PUT'])
@jwt_required()
def update_category(category_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        category = Category.query.get(category_id)
        if not category:
            return jsonify({'error': 'Categoria não encontrada'}), 404
        
        data = request.get_json()
        
        # Atualizar campos
        if 'name' in data:
            category.name = data['name']
        if 'description' in data:
            category.description = data['description']
        if 'icon' in data:
            category.icon = data['icon']
        if 'color' in data:
            category.color = data['color']
        if 'sort_order' in data:
            category.sort_order = data['sort_order']
        if 'is_active' in data:
            category.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Categoria atualizada com sucesso',
            'category': category.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/categories/<int:category_id>', methods=['DELETE'])
@jwt_required()
def delete_category(category_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        category = Category.query.get(category_id)
        if not category:
            return jsonify({'error': 'Categoria não encontrada'}), 404
        
        # Verificar se há produtos ou lojas usando esta categoria
        products_count = Product.query.filter_by(category_id=category_id).count()
        stores_count = Store.query.filter_by(category_id=category_id).count()
        
        if products_count > 0 or stores_count > 0:
            return jsonify({'error': f'Não é possível excluir categoria. Há {products_count} produtos e {stores_count} lojas usando esta categoria'}), 400
        
        db.session.delete(category)
        db.session.commit()
        
        return jsonify({
            'message': f'Categoria {category.name} excluída com sucesso'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Rotas para gerenciar subcategorias

@admin_bp.route('/categories/<int:category_id>/subcategories', methods=['GET'])
def get_subcategories(category_id):
    try:
        subcategories = Subcategory.query.filter_by(
            category_id=category_id, 
            is_active=True
        ).order_by(Subcategory.sort_order, Subcategory.name).all()
        
        return jsonify({
            'subcategories': [sub.to_dict() for sub in subcategories],
            'total': len(subcategories)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/subcategories', methods=['POST'])
@jwt_required()
def create_subcategory():
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Validar dados obrigatórios
        required_fields = ['category_id', 'name']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        # Verificar se categoria existe
        category = Category.query.get(data['category_id'])
        if not category:
            return jsonify({'error': 'Categoria não encontrada'}), 404
        
        # Verificar se subcategoria já existe na categoria
        existing_sub = Subcategory.query.filter_by(
            category_id=data['category_id'],
            name=data['name']
        ).first()
        if existing_sub:
            return jsonify({'error': 'Subcategoria já existe nesta categoria'}), 400
        
        # Criar nova subcategoria
        subcategory = Subcategory(
            category_id=data['category_id'],
            name=data['name'],
            description=data.get('description', ''),
            sort_order=data.get('sort_order', 0)
        )
        
        db.session.add(subcategory)
        db.session.commit()
        
        return jsonify({
            'message': 'Subcategoria criada com sucesso',
            'subcategory': subcategory.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/subcategories/<int:subcategory_id>', methods=['PUT'])
@jwt_required()
def update_subcategory(subcategory_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        subcategory = Subcategory.query.get(subcategory_id)
        if not subcategory:
            return jsonify({'error': 'Subcategoria não encontrada'}), 404
        
        data = request.get_json()
        
        # Atualizar campos
        if 'name' in data:
            subcategory.name = data['name']
        if 'description' in data:
            subcategory.description = data['description']
        if 'sort_order' in data:
            subcategory.sort_order = data['sort_order']
        if 'is_active' in data:
            subcategory.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Subcategoria atualizada com sucesso',
            'subcategory': subcategory.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/subcategories/<int:subcategory_id>', methods=['DELETE'])
@jwt_required()
def delete_subcategory(subcategory_id):
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        subcategory = Subcategory.query.get(subcategory_id)
        if not subcategory:
            return jsonify({'error': 'Subcategoria não encontrada'}), 404
        
        # Verificar se há produtos usando esta subcategoria
        products_count = Product.query.filter_by(subcategory_id=subcategory_id).count()
        
        if products_count > 0:
            return jsonify({'error': f'Não é possível excluir subcategoria. Há {products_count} produtos usando esta subcategoria'}), 400
        
        db.session.delete(subcategory)
        db.session.commit()
        
        return jsonify({
            'message': f'Subcategoria {subcategory.name} excluída com sucesso'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# Função para inicializar configurações padrão
def initialize_default_settings():
    """Inicializa configurações padrão da plataforma se não existirem"""
    default_settings = {
        'platform_commission_percentage': '5.0',  # Taxa da plataforma (%)
        'default_delivery_fee_per_km': '2.0',     # Taxa de entrega por km
        'minimum_delivery_fee': '5.0',            # Taxa mínima de entrega
        'maximum_delivery_distance': '10.0',      # Distância máxima de entrega (km)
        'default_minimum_order_value': '30.0',    # Valor mínimo de pedido padrão
        'allow_store_set_minimum': 'false',       # Permitir loja definir mínimo
        'allow_store_set_delivery_fee': 'false',  # Permitir loja definir taxa entrega
        'platform_name': 'Wendy',
        'support_email': 'suporte@wendy.com',
        'support_phone': '(11) 99999-9999'
    }
    
    for key, value in default_settings.items():
        existing_setting = PlatformSettings.query.filter_by(setting_key=key).first()
        if not existing_setting:
            setting = PlatformSettings(
                setting_key=key,
                setting_value=value,
                description=get_setting_description(key)
            )
            db.session.add(setting)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao inicializar configurações: {e}")

def get_setting_description(key):
    """Retorna descrição para cada configuração"""
    descriptions = {
        'platform_commission_percentage': 'Percentual de comissão da plataforma sobre vendas',
        'default_delivery_fee_per_km': 'Taxa de entrega padrão por quilômetro',
        'minimum_delivery_fee': 'Taxa mínima de entrega',
        'maximum_delivery_distance': 'Distância máxima para entrega em quilômetros',
        'default_minimum_order_value': 'Valor mínimo padrão para pedidos',
        'allow_store_set_minimum': 'Permitir que lojas definam valor mínimo próprio',
        'allow_store_set_delivery_fee': 'Permitir que lojas definam taxa de entrega própria',
        'platform_name': 'Nome da plataforma',
        'support_email': 'Email de suporte da plataforma',
        'support_phone': 'Telefone de suporte da plataforma'
    }
    return descriptions.get(key, '')

# Função para obter configuração
def get_platform_setting(key, default_value=None):
    """Obtém uma configuração da plataforma"""
    setting = PlatformSettings.query.filter_by(setting_key=key).first()
    if setting:
        return setting.setting_value
    return default_value

# Função para atualizar configuração
def update_platform_setting(key, value, description=None):
    """Atualiza uma configuração da plataforma"""
    setting = PlatformSettings.query.filter_by(setting_key=key).first()
    if setting:
        setting.setting_value = str(value)
        setting.updated_at = datetime.utcnow()
        if description:
            setting.description = description
    else:
        setting = PlatformSettings(
            setting_key=key,
            setting_value=str(value),
            description=description or get_setting_description(key)
        )
        db.session.add(setting)
    
    db.session.commit()
    return setting


# APIs específicas para controle de taxas e pedido mínimo

@admin_bp.route('/platform/fees', methods=['GET'])
@jwt_required()
def get_platform_fees():
    """Obter configurações de taxas da plataforma"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        fees = {
            'platform_commission_percentage': float(get_platform_setting('platform_commission_percentage', '5.0')),
            'default_delivery_fee_per_km': float(get_platform_setting('default_delivery_fee_per_km', '2.0')),
            'minimum_delivery_fee': float(get_platform_setting('minimum_delivery_fee', '5.0')),
            'maximum_delivery_distance': float(get_platform_setting('maximum_delivery_distance', '10.0')),
            'default_minimum_order_value': float(get_platform_setting('default_minimum_order_value', '30.0')),
            'allow_store_set_minimum': get_platform_setting('allow_store_set_minimum', 'false') == 'true',
            'allow_store_set_delivery_fee': get_platform_setting('allow_store_set_delivery_fee', 'false') == 'true'
        }
        
        return jsonify({'fees': fees}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/platform/fees', methods=['PUT'])
@jwt_required()
def update_platform_fees():
    """Atualizar configurações de taxas da plataforma"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Validar e atualizar cada configuração
        if 'platform_commission_percentage' in data:
            commission = float(data['platform_commission_percentage'])
            if commission < 0 or commission > 50:
                return jsonify({'error': 'Comissão deve estar entre 0% e 50%'}), 400
            update_platform_setting('platform_commission_percentage', commission)
        
        if 'default_delivery_fee_per_km' in data:
            fee_per_km = float(data['default_delivery_fee_per_km'])
            if fee_per_km < 0:
                return jsonify({'error': 'Taxa por km não pode ser negativa'}), 400
            update_platform_setting('default_delivery_fee_per_km', fee_per_km)
        
        if 'minimum_delivery_fee' in data:
            min_fee = float(data['minimum_delivery_fee'])
            if min_fee < 0:
                return jsonify({'error': 'Taxa mínima não pode ser negativa'}), 400
            update_platform_setting('minimum_delivery_fee', min_fee)
        
        if 'maximum_delivery_distance' in data:
            max_distance = float(data['maximum_delivery_distance'])
            if max_distance <= 0:
                return jsonify({'error': 'Distância máxima deve ser maior que zero'}), 400
            update_platform_setting('maximum_delivery_distance', max_distance)
        
        if 'default_minimum_order_value' in data:
            min_order = float(data['default_minimum_order_value'])
            if min_order < 0:
                return jsonify({'error': 'Valor mínimo não pode ser negativo'}), 400
            update_platform_setting('default_minimum_order_value', min_order)
        
        if 'allow_store_set_minimum' in data:
            allow_min = 'true' if data['allow_store_set_minimum'] else 'false'
            update_platform_setting('allow_store_set_minimum', allow_min)
        
        if 'allow_store_set_delivery_fee' in data:
            allow_fee = 'true' if data['allow_store_set_delivery_fee'] else 'false'
            update_platform_setting('allow_store_set_delivery_fee', allow_fee)
        
        return jsonify({'message': 'Configurações de taxas atualizadas com sucesso'}), 200
        
    except ValueError:
        return jsonify({'error': 'Valores inválidos fornecidos'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/platform/calculate-delivery-fee', methods=['POST'])
def calculate_delivery_fee():
    """Calcular taxa de entrega baseada na distância"""
    try:
        data = request.get_json()
        
        if 'distance_km' not in data:
            return jsonify({'error': 'Distância em km é obrigatória'}), 400
        
        distance = float(data['distance_km'])
        city_id = data.get('city_id')
        
        # Verificar se a cidade tem configurações específicas
        if city_id:
            city = AllowedCity.query.get(city_id)
            if city and city.is_active:
                fee_per_km = city.delivery_fee_per_km
            else:
                fee_per_km = float(get_platform_setting('default_delivery_fee_per_km', '2.0'))
        else:
            fee_per_km = float(get_platform_setting('default_delivery_fee_per_km', '2.0'))
        
        # Calcular taxa
        calculated_fee = distance * fee_per_km
        minimum_fee = float(get_platform_setting('minimum_delivery_fee', '5.0'))
        maximum_distance = float(get_platform_setting('maximum_delivery_distance', '10.0'))
        
        # Verificar distância máxima
        if distance > maximum_distance:
            return jsonify({
                'error': f'Distância excede o máximo permitido de {maximum_distance}km'
            }), 400
        
        # Aplicar taxa mínima
        final_fee = max(calculated_fee, minimum_fee)
        
        return jsonify({
            'distance_km': distance,
            'fee_per_km': fee_per_km,
            'calculated_fee': calculated_fee,
            'minimum_fee': minimum_fee,
            'final_delivery_fee': final_fee,
            'within_delivery_area': distance <= maximum_distance
        }), 200
        
    except ValueError:
        return jsonify({'error': 'Distância inválida'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/platform/order-limits', methods=['GET'])
def get_order_limits():
    """Obter limites de pedido para uma cidade específica"""
    try:
        city_id = request.args.get('city_id')
        
        if city_id:
            city = AllowedCity.query.get(city_id)
            if city and city.is_active:
                minimum_order_value = city.minimum_order_value
            else:
                minimum_order_value = float(get_platform_setting('default_minimum_order_value', '30.0'))
        else:
            minimum_order_value = float(get_platform_setting('default_minimum_order_value', '30.0'))
        
        return jsonify({
            'minimum_order_value': minimum_order_value,
            'maximum_delivery_distance': float(get_platform_setting('maximum_delivery_distance', '10.0')),
            'allow_store_set_minimum': get_platform_setting('allow_store_set_minimum', 'false') == 'true'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# APIs avançadas de gestão para administrador

@admin_bp.route('/orders/reassign', methods=['POST'])
@jwt_required()
def reassign_order():
    """Reatribuir pedido para outro entregador"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Validar dados obrigatórios
        required_fields = ['order_id', 'new_deliverer_id', 'reason']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        order = Order.query.get(data['order_id'])
        if not order:
            return jsonify({'error': 'Pedido não encontrado'}), 404
        
        # Verificar se o pedido pode ser reatribuído
        if order.status not in ['accepted', 'preparing', 'ready']:
            return jsonify({'error': 'Pedido não pode ser reatribuído neste status'}), 400
        
        # Verificar se o novo entregador existe e está ativo
        new_deliverer = User.query.filter_by(
            id=data['new_deliverer_id'],
            user_type='deliverer',
            is_active=True
        ).first()
        
        if not new_deliverer:
            return jsonify({'error': 'Entregador não encontrado ou inativo'}), 404
        
        # Verificar se o entregador está aprovado
        deliverer_profile = Deliverer.query.filter_by(user_id=new_deliverer.id).first()
        if not deliverer_profile or not deliverer_profile.is_approved:
            return jsonify({'error': 'Entregador não está aprovado'}), 400
        
        # Salvar entregador anterior para histórico
        old_deliverer_id = order.deliverer_id
        
        # Reatribuir pedido
        order.deliverer_id = data['new_deliverer_id']
        order.updated_at = datetime.utcnow()
        
        # Criar log da reatribuição
        admin_user = get_jwt_identity()
        log_entry = f"Pedido reatribuído pelo admin {admin_user}. Entregador anterior: {old_deliverer_id}, Novo entregador: {data['new_deliverer_id']}. Motivo: {data['reason']}"
        
        # Adicionar ao campo notes do pedido
        if order.notes:
            order.notes += f"\n\n[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] {log_entry}"
        else:
            order.notes = f"[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] {log_entry}"
        
        db.session.commit()
        
        return jsonify({
            'message': 'Pedido reatribuído com sucesso',
            'order': order.to_dict(),
            'old_deliverer_id': old_deliverer_id,
            'new_deliverer_id': data['new_deliverer_id']
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@jwt_required()
def cancel_order_admin():
    """Cancelar pedido (apenas admin)"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        reason = data.get('reason', 'Cancelado pelo administrador')
        
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'error': 'Pedido não encontrado'}), 404
        
        # Verificar se o pedido pode ser cancelado
        if order.status in ['delivered', 'cancelled']:
            return jsonify({'error': 'Pedido não pode ser cancelado neste status'}), 400
        
        # Cancelar pedido
        order.status = 'cancelled'
        order.updated_at = datetime.utcnow()
        
        # Adicionar motivo do cancelamento
        admin_user = get_jwt_identity()
        cancel_log = f"[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] Pedido cancelado pelo admin {admin_user}. Motivo: {reason}"
        
        if order.notes:
            order.notes += f"\n\n{cancel_log}"
        else:
            order.notes = cancel_log
        
        db.session.commit()
        
        return jsonify({
            'message': 'Pedido cancelado com sucesso',
            'order': order.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/orders/<int:order_id>/status', methods=['PUT'])
@jwt_required()
def update_order_status_admin():
    """Atualizar status do pedido (apenas admin)"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        if 'status' not in data:
            return jsonify({'error': 'Status é obrigatório'}), 400
        
        valid_statuses = ['pending', 'accepted', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']
        if data['status'] not in valid_statuses:
            return jsonify({'error': 'Status inválido'}), 400
        
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'error': 'Pedido não encontrado'}), 404
        
        old_status = order.status
        order.status = data['status']
        order.updated_at = datetime.utcnow()
        
        # Log da alteração
        admin_user = get_jwt_identity()
        reason = data.get('reason', 'Ajuste administrativo')
        status_log = f"[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] Status alterado pelo admin {admin_user} de '{old_status}' para '{data['status']}'. Motivo: {reason}"
        
        if order.notes:
            order.notes += f"\n\n{status_log}"
        else:
            order.notes = status_log
        
        db.session.commit()
        
        return jsonify({
            'message': 'Status do pedido atualizado com sucesso',
            'order': order.to_dict(),
            'old_status': old_status,
            'new_status': data['status']
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/reports/detailed', methods=['GET'])
@jwt_required()
def get_detailed_reports():
    """Obter relatórios detalhados para admin"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Parâmetros de filtro
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Query base para pedidos
        orders_query = Order.query
        
        # Aplicar filtros de data se fornecidos
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                orders_query = orders_query.filter(Order.created_at >= start_dt)
            except ValueError:
                return jsonify({'error': 'Formato de data inválido para start_date (use YYYY-MM-DD)'}), 400
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                # Adicionar 1 dia para incluir todo o dia final
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                orders_query = orders_query.filter(Order.created_at <= end_dt)
            except ValueError:
                return jsonify({'error': 'Formato de data inválido para end_date (use YYYY-MM-DD)'}), 400
        
        orders = orders_query.all()
        
        # Calcular métricas
        total_orders = len(orders)
        total_revenue = sum(order.total_amount for order in orders)
        total_delivery_fees = sum(order.delivery_fee for order in orders)
        
        # Pedidos por status
        orders_by_status = {}
        for order in orders:
            status = order.status
            if status not in orders_by_status:
                orders_by_status[status] = 0
            orders_by_status[status] += 1
        
        # Top lojas por receita
        store_revenue = {}
        for order in orders:
            store_id = order.store_id
            if store_id not in store_revenue:
                store_revenue[store_id] = {
                    'store_name': order.store_rel.name if order.store_rel else 'Loja não encontrada',
                    'total_revenue': 0,
                    'order_count': 0
                }
            store_revenue[store_id]['total_revenue'] += order.total_amount
            store_revenue[store_id]['order_count'] += 1
        
        # Ordenar lojas por receita
        top_stores = sorted(store_revenue.items(), key=lambda x: x[1]['total_revenue'], reverse=True)[:10]
        
        # Top entregadores por entregas
        deliverer_stats = {}
        for order in orders:
            if order.deliverer_id and order.status == 'delivered':
                deliverer_id = order.deliverer_id
                if deliverer_id not in deliverer_stats:
                    deliverer_user = User.query.get(deliverer_id)
                    deliverer_stats[deliverer_id] = {
                        'deliverer_name': deliverer_user.name if deliverer_user else 'Entregador não encontrado',
                        'delivery_count': 0,
                        'total_delivery_fees': 0
                    }
                deliverer_stats[deliverer_id]['delivery_count'] += 1
                deliverer_stats[deliverer_id]['total_delivery_fees'] += order.delivery_fee
        
        # Ordenar entregadores por número de entregas
        top_deliverers = sorted(deliverer_stats.items(), key=lambda x: x[1]['delivery_count'], reverse=True)[:10]
        
        # Pedidos por dia (últimos 30 dias)
        from datetime import timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_orders = Order.query.filter(Order.created_at >= thirty_days_ago).all()
        
        orders_by_day = {}
        for order in recent_orders:
            day = order.created_at.strftime('%Y-%m-%d')
            if day not in orders_by_day:
                orders_by_day[day] = 0
            orders_by_day[day] += 1
        
        return jsonify({
            'summary': {
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'total_delivery_fees': total_delivery_fees,
                'average_order_value': total_revenue / total_orders if total_orders > 0 else 0
            },
            'orders_by_status': orders_by_status,
            'top_stores': [{'store_id': k, **v} for k, v in top_stores],
            'top_deliverers': [{'deliverer_id': k, **v} for k, v in top_deliverers],
            'orders_by_day': orders_by_day,
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'total_days': (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days + 1 if start_date and end_date else None
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/orders/problematic', methods=['GET'])
@jwt_required()
def get_problematic_orders():
    """Obter pedidos com problemas que precisam de atenção admin"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Pedidos que estão há muito tempo no mesmo status
        from datetime import timedelta
        two_hours_ago = datetime.utcnow() - timedelta(hours=2)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        problematic_orders = []
        
        # Pedidos aceitos há mais de 2 horas
        stuck_accepted = Order.query.filter(
            Order.status == 'accepted',
            Order.updated_at <= two_hours_ago
        ).all()
        
        for order in stuck_accepted:
            problematic_orders.append({
                **order.to_dict(),
                'problem_type': 'stuck_accepted',
                'problem_description': 'Pedido aceito há mais de 2 horas sem progresso'
            })
        
        # Pedidos em preparo há mais de 1 hora
        stuck_preparing = Order.query.filter(
            Order.status == 'preparing',
            Order.updated_at <= one_hour_ago
        ).all()
        
        for order in stuck_preparing:
            problematic_orders.append({
                **order.to_dict(),
                'problem_type': 'stuck_preparing',
                'problem_description': 'Pedido em preparo há mais de 1 hora'
            })
        
        # Pedidos prontos há mais de 30 minutos
        thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
        stuck_ready = Order.query.filter(
            Order.status == 'ready',
            Order.updated_at <= thirty_minutes_ago
        ).all()
        
        for order in stuck_ready:
            problematic_orders.append({
                **order.to_dict(),
                'problem_type': 'stuck_ready',
                'problem_description': 'Pedido pronto há mais de 30 minutos sem coleta'
            })
        
        # Pedidos em entrega há mais de 1 hora
        stuck_delivering = Order.query.filter(
            Order.status == 'delivering',
            Order.updated_at <= one_hour_ago
        ).all()
        
        for order in stuck_delivering:
            problematic_orders.append({
                **order.to_dict(),
                'problem_type': 'stuck_delivering',
                'problem_description': 'Pedido em entrega há mais de 1 hora'
            })
        
        return jsonify({
            'problematic_orders': problematic_orders,
            'total_problems': len(problematic_orders),
            'summary': {
                'stuck_accepted': len(stuck_accepted),
                'stuck_preparing': len(stuck_preparing),
                'stuck_ready': len(stuck_ready),
                'stuck_delivering': len(stuck_delivering)
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# APIs para exclusão segura de cadastros

@admin_bp.route('/users/<int:user_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_user_account():
    """Excluir conta de usuário (clientes, lojistas ou entregadores)"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Motivo é obrigatório para exclusão
        if 'reason' not in data or not data['reason']:
            return jsonify({'error': 'Motivo da exclusão é obrigatório'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        # Verificar se é um admin tentando excluir outro admin
        if user.user_type == 'admin':
            return jsonify({'error': 'Não é possível excluir contas de administrador'}), 403
        
        # Coletar informações antes da exclusão para log
        user_info = {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'user_type': user.user_type,
            'created_at': user.created_at.isoformat() if user.created_at else None
        }
        
        # Verificar dependências e coletar estatísticas
        dependencies = {}
        
        if user.user_type == 'store_owner':
            # Verificar loja associada
            store = Store.query.filter_by(user_id=user.id).first()
            if store:
                # Contar produtos da loja
                products_count = Product.query.filter_by(store_id=store.id).count()
                # Contar pedidos da loja
                orders_count = Order.query.filter_by(store_id=store.id).count()
                
                dependencies['store'] = {
                    'id': store.id,
                    'name': store.name,
                    'products_count': products_count,
                    'orders_count': orders_count
                }
        
        elif user.user_type == 'deliverer':
            # Verificar perfil de entregador
            deliverer = Deliverer.query.filter_by(user_id=user.id).first()
            if deliverer:
                # Contar entregas realizadas
                deliveries_count = Order.query.filter_by(deliverer_id=user.id).count()
                
                dependencies['deliverer'] = {
                    'id': deliverer.id,
                    'deliveries_count': deliveries_count,
                    'rating': deliverer.rating
                }
        
        elif user.user_type == 'client':
            # Contar pedidos do cliente
            orders_count = Order.query.filter_by(client_id=user.id).count()
            dependencies['client'] = {
                'orders_count': orders_count
            }
        
        # Verificar se há pedidos ativos que impedem a exclusão
        active_orders = Order.query.filter(
            db.or_(
                Order.client_id == user.id,
                Order.deliverer_id == user.id,
                db.and_(
                    Order.store_id.in_(
                        db.session.query(Store.id).filter_by(user_id=user.id)
                    ) if user.user_type == 'store_owner' else False
                )
            ),
            Order.status.in_(['pending', 'accepted', 'preparing', 'ready', 'delivering'])
        ).all()
        
        if active_orders:
            return jsonify({
                'error': f'Não é possível excluir usuário. Há {len(active_orders)} pedidos ativos.',
                'active_orders': [order.to_dict() for order in active_orders]
            }), 400
        
        # Confirmar exclusão com flag de confirmação
        if not data.get('confirm_deletion', False):
            return jsonify({
                'error': 'Confirmação de exclusão necessária',
                'user_info': user_info,
                'dependencies': dependencies,
                'message': 'Para confirmar a exclusão, envie confirm_deletion: true'
            }), 400
        
        # Realizar exclusão em cascata
        admin_user = get_jwt_identity()
        deletion_log = {
            'deleted_by': admin_user,
            'deleted_at': datetime.utcnow().isoformat(),
            'reason': data['reason'],
            'user_info': user_info,
            'dependencies': dependencies
        }
        
        try:
            # Excluir dados relacionados primeiro
            if user.user_type == 'store_owner':
                store = Store.query.filter_by(user_id=user.id).first()
                if store:
                    # Excluir produtos da loja
                    Product.query.filter_by(store_id=store.id).delete()
                    # Excluir loja
                    db.session.delete(store)
            
            elif user.user_type == 'deliverer':
                deliverer = Deliverer.query.filter_by(user_id=user.id).first()
                if deliverer:
                    db.session.delete(deliverer)
            
            # Atualizar pedidos históricos para remover referências
            Order.query.filter_by(client_id=user.id).update({
                'client_id': None
            })
            Order.query.filter_by(deliverer_id=user.id).update({
                'deliverer_id': None
            })
            
            # Excluir usuário
            db.session.delete(user)
            db.session.commit()
            
            # Log da exclusão (em produção, salvar em arquivo de log)
            print(f"DELETION LOG: {deletion_log}")
            
            return jsonify({
                'message': f'Usuário {user_info["name"]} ({user_info["user_type"]}) excluído com sucesso',
                'deleted_user': user_info,
                'dependencies_removed': dependencies,
                'reason': data['reason']
            }), 200
            
        except Exception as e:
            db.session.rollback()
            raise e
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/suspend', methods=['POST'])
@jwt_required()
def suspend_user_account():
    """Suspender conta de usuário (alternativa à exclusão)"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Motivo é obrigatório para suspensão
        if 'reason' not in data or not data['reason']:
            return jsonify({'error': 'Motivo da suspensão é obrigatório'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        # Verificar se é um admin tentando suspender outro admin
        if user.user_type == 'admin':
            return jsonify({'error': 'Não é possível suspender contas de administrador'}), 403
        
        # Suspender usuário
        user.is_active = False
        user.updated_at = datetime.utcnow()
        
        # Adicionar log de suspensão
        admin_user = get_jwt_identity()
        suspension_log = f"[{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] Conta suspensa pelo admin {admin_user}. Motivo: {data['reason']}"
        
        # Se for lojista, suspender loja também
        if user.user_type == 'store_owner':
            store = Store.query.filter_by(user_id=user.id).first()
            if store:
                store.is_active = False
        
        # Se for entregador, marcar como inativo
        elif user.user_type == 'deliverer':
            deliverer = Deliverer.query.filter_by(user_id=user.id).first()
            if deliverer:
                deliverer.is_online = False
        
        db.session.commit()
        
        return jsonify({
            'message': f'Usuário {user.name} suspenso com sucesso',
            'user': user.to_dict(),
            'reason': data['reason'],
            'suspended_by': admin_user
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/reactivate', methods=['POST'])
@jwt_required()
def reactivate_user_account():
    """Reativar conta de usuário suspensa"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        reason = data.get('reason', 'Reativação administrativa')
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        if user.is_active:
            return jsonify({'error': 'Usuário já está ativo'}), 400
        
        # Reativar usuário
        user.is_active = True
        user.updated_at = datetime.utcnow()
        
        # Se for lojista, reativar loja também (se aprovada)
        if user.user_type == 'store_owner':
            store = Store.query.filter_by(user_id=user.id).first()
            if store and store.is_approved:
                store.is_active = True
        
        admin_user = get_jwt_identity()
        db.session.commit()
        
        return jsonify({
            'message': f'Usuário {user.name} reativado com sucesso',
            'user': user.to_dict(),
            'reason': reason,
            'reactivated_by': admin_user
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/bulk-action', methods=['POST'])
@jwt_required()
def bulk_user_action():
    """Ação em lote para múltiplos usuários"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        required_fields = ['user_ids', 'action', 'reason']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        valid_actions = ['suspend', 'reactivate', 'delete']
        if data['action'] not in valid_actions:
            return jsonify({'error': 'Ação inválida'}), 400
        
        user_ids = data['user_ids']
        if not isinstance(user_ids, list) or len(user_ids) == 0:
            return jsonify({'error': 'Lista de IDs de usuários inválida'}), 400
        
        # Verificar se todos os usuários existem
        users = User.query.filter(User.id.in_(user_ids)).all()
        if len(users) != len(user_ids):
            return jsonify({'error': 'Alguns usuários não foram encontrados'}), 404
        
        # Verificar se há admins na lista
        admin_users = [u for u in users if u.user_type == 'admin']
        if admin_users:
            return jsonify({'error': 'Não é possível executar ações em lote em contas de administrador'}), 403
        
        results = []
        errors = []
        
        for user in users:
            try:
                if data['action'] == 'suspend':
                    if user.is_active:
                        user.is_active = False
                        results.append(f'Usuário {user.name} suspenso')
                    else:
                        results.append(f'Usuário {user.name} já estava suspenso')
                
                elif data['action'] == 'reactivate':
                    if not user.is_active:
                        user.is_active = True
                        results.append(f'Usuário {user.name} reativado')
                    else:
                        results.append(f'Usuário {user.name} já estava ativo')
                
                elif data['action'] == 'delete':
                    # Para exclusão em lote, verificar pedidos ativos
                    active_orders = Order.query.filter(
                        db.or_(
                            Order.client_id == user.id,
                            Order.deliverer_id == user.id
                        ),
                        Order.status.in_(['pending', 'accepted', 'preparing', 'ready', 'delivering'])
                    ).count()
                    
                    if active_orders > 0:
                        errors.append(f'Usuário {user.name}: {active_orders} pedidos ativos impedem exclusão')
                        continue
                    
                    # Excluir dados relacionados
                    if user.user_type == 'store_owner':
                        store = Store.query.filter_by(user_id=user.id).first()
                        if store:
                            Product.query.filter_by(store_id=store.id).delete()
                            db.session.delete(store)
                    
                    elif user.user_type == 'deliverer':
                        deliverer = Deliverer.query.filter_by(user_id=user.id).first()
                        if deliverer:
                            db.session.delete(deliverer)
                    
                    db.session.delete(user)
                    results.append(f'Usuário {user.name} excluído')
                
            except Exception as e:
                errors.append(f'Erro ao processar usuário {user.name}: {str(e)}')
        
        db.session.commit()
        
        admin_user = get_jwt_identity()
        
        return jsonify({
            'message': f'Ação em lote "{data["action"]}" executada',
            'results': results,
            'errors': errors,
            'total_processed': len(results),
            'total_errors': len(errors),
            'action': data['action'],
            'reason': data['reason'],
            'executed_by': admin_user
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# Endpoints para gerenciar privilégio das lojas

@admin_bp.route('/stores/<int:store_id>/privilege', methods=['POST'])
@jwt_required()
def toggle_store_privilege(store_id):
    """Conceder ou remover privilégio de uma loja"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado - apenas administradores'}), 403
        
        store = Store.query.get(store_id)
        if not store:
            return jsonify({'error': 'Loja não encontrada'}), 404
        
        data = request.get_json()
        is_privileged = data.get('is_privileged', False)
        reason = data.get('reason', '')
        
        # Atualizar status de privilégio
        store.is_privileged = is_privileged
        db.session.commit()
        
        action = 'concedido' if is_privileged else 'removido'
        
        return jsonify({
            'message': f'Privilégio {action} com sucesso para a loja {store.name}',
            'store': {
                'id': store.id,
                'name': store.name,
                'is_privileged': store.is_privileged
            },
            'action': action,
            'reason': reason,
            'updated_at': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/privileged', methods=['GET'])
@jwt_required()
def get_privileged_stores():
    """Listar todas as lojas privilegiadas"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado - apenas administradores'}), 403
        
        privileged_stores = Store.query.filter_by(
            is_privileged=True,
            is_approved=True,
            is_active=True
        ).all()
        
        stores_data = []
        for store in privileged_stores:
            store_info = store.to_dict()
            store_info['user_name'] = store.user.name if store.user else None
            store_info['user_email'] = store.user.email if store.user else None
            store_info['products_count'] = Product.query.filter_by(
                store_id=store.id,
                is_active=True
            ).count()
            stores_data.append(store_info)
        
        return jsonify({
            'privileged_stores': stores_data,
            'total': len(stores_data),
            'last_update': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/privilege-candidates', methods=['GET'])
@jwt_required()
def get_privilege_candidates():
    """Listar lojas que podem receber privilégio (aprovadas e ativas)"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado - apenas administradores'}), 403
        
        candidate_stores = Store.query.filter_by(
            is_approved=True,
            is_active=True
        ).all()
        
        stores_data = []
        for store in candidate_stores:
            store_info = store.to_dict()
            store_info['user_name'] = store.user.name if store.user else None
            store_info['user_email'] = store.user.email if store.user else None
            store_info['products_count'] = Product.query.filter_by(
                store_id=store.id,
                is_active=True
            ).count()
            
            # Estatísticas da loja
            total_orders = Order.query.filter_by(store_id=store.id).count()
            delivered_orders = Order.query.filter_by(
                store_id=store.id,
                status='delivered'
            ).count()
            
            store_info['total_orders'] = total_orders
            store_info['delivered_orders'] = delivered_orders
            store_info['success_rate'] = (delivered_orders / total_orders * 100) if total_orders > 0 else 0
            
            stores_data.append(store_info)
        
        # Ordenar por número de produtos e taxa de sucesso
        stores_data.sort(key=lambda x: (x['products_count'], x['success_rate']), reverse=True)
        
        return jsonify({
            'candidate_stores': stores_data,
            'total': len(stores_data),
            'privileged_count': len([s for s in stores_data if s['is_privileged']]),
            'non_privileged_count': len([s for s in stores_data if not s['is_privileged']]),
            'last_update': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/stores/privilege/batch', methods=['POST'])
@jwt_required()
def batch_manage_privilege():
    """Gerenciar privilégio de múltiplas lojas em lote"""
    try:
        if not admin_required():
            return jsonify({'error': 'Acesso negado - apenas administradores'}), 403
        
        data = request.get_json()
        store_ids = data.get('store_ids', [])
        action = data.get('action')  # 'grant' ou 'revoke'
        reason = data.get('reason', '')
        
        if not store_ids or action not in ['grant', 'revoke']:
            return jsonify({'error': 'IDs das lojas e ação válida são obrigatórios'}), 400
        
        is_privileged = action == 'grant'
        results = []
        errors = []
        
        for store_id in store_ids:
            try:
                store = Store.query.get(store_id)
                if not store:
                    errors.append(f'Loja ID {store_id} não encontrada')
                    continue
                
                if not store.is_approved or not store.is_active:
                    errors.append(f'Loja {store.name} não está aprovada ou ativa')
                    continue
                
                store.is_privileged = is_privileged
                action_text = 'concedido' if is_privileged else 'removido'
                results.append(f'Privilégio {action_text} para {store.name}')
                
            except Exception as e:
                errors.append(f'Erro ao processar loja ID {store_id}: {str(e)}')
        
        db.session.commit()
        
        return jsonify({
            'message': f'Ação em lote "{action}" executada',
            'results': results,
            'errors': errors,
            'total_processed': len(results),
            'total_errors': len(errors),
            'action': action,
            'reason': reason
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

