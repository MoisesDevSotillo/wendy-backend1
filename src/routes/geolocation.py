from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, User, Order, Deliverer
from src.models.geolocation_models import DelivererLocation, OrderTracking, GeofenceArea
from datetime import datetime, timedelta
import math

geolocation_bp = Blueprint('geolocation', __name__)

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calcular distância entre duas coordenadas usando fórmula de Haversine"""
    R = 6371  # Raio da Terra em km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat/2) * math.sin(dlat/2) + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon/2) * math.sin(dlon/2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance

def estimate_arrival_time(distance_km, avg_speed_kmh=25):
    """Estimar tempo de chegada baseado na distância e velocidade média"""
    if distance_km <= 0:
        return datetime.utcnow()
    
    time_hours = distance_km / avg_speed_kmh
    time_minutes = time_hours * 60
    
    return datetime.utcnow() + timedelta(minutes=time_minutes)

@geolocation_bp.route('/update-location', methods=['POST'])
@jwt_required()
def update_deliverer_location():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != 'deliverer':
            return jsonify({'error': 'Acesso negado'}), 403
        
        deliverer = Deliverer.query.filter_by(user_id=user_id).first()
        
        if not deliverer or not deliverer.is_online:
            return jsonify({'error': 'Entregador deve estar online'}), 403
        
        data = request.get_json()
        
        # Validar dados obrigatórios
        required_fields = ['latitude', 'longitude']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        # Desativar localização anterior
        DelivererLocation.query.filter_by(
            deliverer_id=user_id,
            is_active=True
        ).update({'is_active': False})
        
        # Criar nova localização
        location = DelivererLocation(
            deliverer_id=user_id,
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            accuracy=data.get('accuracy'),
            speed=data.get('speed'),
            heading=data.get('heading')
        )
        
        db.session.add(location)
        
        # Atualizar tracking de pedidos ativos
        active_orders = Order.query.filter_by(
            deliverer_id=user_id,
            status='delivering'
        ).all()
        
        for order in active_orders:
            # Calcular distância até o destino (simulado)
            # Em produção, usar API de mapas para rota real
            dest_lat = -23.5505  # Coordenadas de exemplo (São Paulo)
            dest_lon = -46.6333
            
            distance = calculate_distance(
                float(data['latitude']), float(data['longitude']),
                dest_lat, dest_lon
            )
            
            estimated_arrival = estimate_arrival_time(distance)
            
            tracking = OrderTracking(
                order_id=order.id,
                deliverer_id=user_id,
                latitude=float(data['latitude']),
                longitude=float(data['longitude']),
                status='in_transit',
                estimated_arrival=estimated_arrival,
                distance_remaining=distance
            )
            
            db.session.add(tracking)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Localização atualizada com sucesso',
            'location': location.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@geolocation_bp.route('/track-order/<int:order_id>', methods=['GET'])
@jwt_required()
def track_order(order_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        order = Order.query.get(order_id)
        
        if not order:
            return jsonify({'error': 'Pedido não encontrado'}), 404
        
        # Verificar permissão de acesso
        has_access = False
        if user.user_type == 'client' and order.client_id == user_id:
            has_access = True
        elif user.user_type == 'store':
            from src.models.wendy_models import Store
            store = Store.query.filter_by(user_id=user_id).first()
            if store and order.store_id == store.id:
                has_access = True
        elif user.user_type == 'deliverer' and order.deliverer_id == user_id:
            has_access = True
        elif user.user_type == 'admin':
            has_access = True
        
        if not has_access:
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Buscar tracking mais recente
        latest_tracking = OrderTracking.query.filter_by(
            order_id=order_id
        ).order_by(OrderTracking.created_at.desc()).first()
        
        # Buscar localização atual do entregador
        current_location = None
        if order.deliverer_id:
            current_location = DelivererLocation.query.filter_by(
                deliverer_id=order.deliverer_id,
                is_active=True
            ).first()
        
        # Histórico de tracking
        tracking_history = OrderTracking.query.filter_by(
            order_id=order_id
        ).order_by(OrderTracking.created_at.desc()).limit(10).all()
        
        return jsonify({
            'order_id': order_id,
            'status': order.status,
            'latest_tracking': latest_tracking.to_dict() if latest_tracking else None,
            'current_location': current_location.to_dict() if current_location else None,
            'tracking_history': [t.to_dict() for t in tracking_history],
            'deliverer_name': order.deliverer.name if order.deliverer else None
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@geolocation_bp.route('/nearby-deliverers', methods=['GET'])
@jwt_required()
def get_nearby_deliverers():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type not in ['store', 'admin']:
            return jsonify({'error': 'Acesso negado'}), 403
        
        # Parâmetros de busca
        latitude = float(request.args.get('latitude', -23.5505))
        longitude = float(request.args.get('longitude', -46.6333))
        radius_km = float(request.args.get('radius', 5))  # Raio padrão de 5km
        
        # Buscar entregadores online com localização recente
        recent_time = datetime.utcnow() - timedelta(minutes=10)
        
        locations = db.session.query(DelivererLocation).join(
            Deliverer, DelivererLocation.deliverer_id == Deliverer.user_id
        ).filter(
            DelivererLocation.is_active == True,
            DelivererLocation.created_at >= recent_time,
            Deliverer.is_online == True,
            Deliverer.is_approved == True
        ).all()
        
        nearby_deliverers = []
        
        for location in locations:
            distance = calculate_distance(
                latitude, longitude,
                location.latitude, location.longitude
            )
            
            if distance <= radius_km:
                deliverer_data = location.to_dict()
                deliverer_data['distance_km'] = round(distance, 2)
                deliverer_data['estimated_arrival'] = estimate_arrival_time(distance).isoformat()
                nearby_deliverers.append(deliverer_data)
        
        # Ordenar por distância
        nearby_deliverers.sort(key=lambda x: x['distance_km'])
        
        return jsonify({
            'deliverers': nearby_deliverers,
            'total': len(nearby_deliverers),
            'search_radius_km': radius_km,
            'search_center': {
                'latitude': latitude,
                'longitude': longitude
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@geolocation_bp.route('/delivery-zones', methods=['GET'])
def get_delivery_zones():
    try:
        zones = GeofenceArea.query.filter_by(
            area_type='delivery_zone',
            is_active=True
        ).all()
        
        return jsonify({
            'zones': [zone.to_dict() for zone in zones]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@geolocation_bp.route('/delivery-zones', methods=['POST'])
@jwt_required()
def create_delivery_zone():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != 'admin':
            return jsonify({'error': 'Acesso negado'}), 403
        
        data = request.get_json()
        
        # Validar dados obrigatórios
        required_fields = ['name', 'center_latitude', 'center_longitude', 'radius']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        zone = GeofenceArea(
            name=data['name'],
            center_latitude=float(data['center_latitude']),
            center_longitude=float(data['center_longitude']),
            radius=float(data['radius']),
            area_type=data.get('area_type', 'delivery_zone')
        )
        
        db.session.add(zone)
        db.session.commit()
        
        return jsonify({
            'message': 'Zona de entrega criada com sucesso',
            'zone': zone.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@geolocation_bp.route('/admin/all-deliverers', methods=['GET'])
@jwt_required()
def get_all_deliverers_location():
    """Endpoint para Site Administrador visualizar localização de todos os entregadores em tempo real"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != 'admin':
            return jsonify({'error': 'Acesso negado - apenas administradores'}), 403
        
        # Buscar entregadores online com localização recente (últimos 5 minutos)
        recent_time = datetime.utcnow() - timedelta(minutes=5)
        
        # Query para buscar localizações ativas dos entregadores
        deliverers_locations = db.session.query(
            DelivererLocation,
            Deliverer,
            User
        ).join(
            Deliverer, DelivererLocation.deliverer_id == Deliverer.user_id
        ).join(
            User, Deliverer.user_id == User.id
        ).filter(
            DelivererLocation.is_active == True,
            DelivererLocation.created_at >= recent_time,
            Deliverer.is_approved == True
        ).all()
        
        deliverers_data = []
        
        for location, deliverer, user in deliverers_locations:
            # Buscar pedido ativo do entregador
            active_order = Order.query.filter_by(
                deliverer_id=user.id,
                status='delivering'
            ).first()
            
            deliverer_info = {
                'deliverer_id': user.id,
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'is_online': deliverer.is_online,
                'vehicle_type': deliverer.vehicle_type,
                'location': {
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                    'accuracy': location.accuracy,
                    'speed': location.speed,
                    'heading': location.heading,
                    'last_update': location.created_at.isoformat()
                },
                'current_order': None,
                'status': 'available' if not active_order else 'busy'
            }
            
            # Se tem pedido ativo, incluir informações do pedido
            if active_order:
                deliverer_info['current_order'] = {
                    'order_id': active_order.id,
                    'store_name': active_order.store.name if active_order.store else None,
                    'client_name': active_order.client.name if active_order.client else None,
                    'delivery_address': active_order.delivery_address,
                    'order_status': active_order.status,
                    'created_at': active_order.created_at.isoformat()
                }
            
            deliverers_data.append(deliverer_info)
        
        # Estatísticas gerais
        total_deliverers = Deliverer.query.filter_by(is_approved=True).count()
        online_deliverers = Deliverer.query.filter_by(is_approved=True, is_online=True).count()
        busy_deliverers = len([d for d in deliverers_data if d['status'] == 'busy'])
        available_deliverers = len([d for d in deliverers_data if d['status'] == 'available'])
        
        return jsonify({
            'deliverers': deliverers_data,
            'statistics': {
                'total_approved': total_deliverers,
                'online': online_deliverers,
                'with_recent_location': len(deliverers_data),
                'busy': busy_deliverers,
                'available': available_deliverers
            },
            'last_update': datetime.utcnow().isoformat(),
            'location_timeout_minutes': 5
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@geolocation_bp.route('/estimate-delivery', methods=['POST'])
def estimate_delivery_time():
    try:
        data = request.get_json()
        
        # Validar dados obrigatórios
        required_fields = ['pickup_lat', 'pickup_lon', 'delivery_lat', 'delivery_lon']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Campo {field} é obrigatório'}), 400
        
        # Calcular distância
        distance = calculate_distance(
            float(data['pickup_lat']), float(data['pickup_lon']),
            float(data['delivery_lat']), float(data['delivery_lon'])
        )
        
        # Estimar tempo e preço
        estimated_time = estimate_arrival_time(distance)
        base_price = 5.0  # Taxa base
        price_per_km = 2.5
        estimated_price = base_price + (distance * price_per_km)
        
        return jsonify({
            'distance_km': round(distance, 2),
            'estimated_time_minutes': round((estimated_time - datetime.utcnow()).total_seconds() / 60),
            'estimated_price': round(estimated_price, 2),
            'pickup_coordinates': {
                'latitude': float(data['pickup_lat']),
                'longitude': float(data['pickup_lon'])
            },
            'delivery_coordinates': {
                'latitude': float(data['delivery_lat']),
                'longitude': float(data['delivery_lon'])
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500



