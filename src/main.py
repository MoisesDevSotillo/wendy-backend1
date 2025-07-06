import os
import sys
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from src.models.wendy_models import db
from src.models.geolocation_models import DelivererLocation, OrderTracking, GeofenceArea
from src.models.chat_models import Conversation, Message
from src.models.rating_models import Rating, UserRatingStats
from src.models.notification_models import DeviceToken
from src.routes.auth import auth_bp
from src.routes.stores import stores_bp
from src.routes.products import products_bp
from src.routes.orders import orders_bp
from src.routes.deliverers import deliverers_bp
from src.routes.admin import admin_bp
from src.routes.geolocation import geolocation_bp
from src.routes.chat import chat_bp
from src.routes.ratings import ratings_bp
from src.routes.notifications import notifications_bp
from src.routes.reports import reports_bp

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Configurações
app.config['SECRET_KEY'] = 'wendy-marketplace-secret-key-2025'
app.config['JWT_SECRET_KEY'] = 'wendy-jwt-secret-key-2025'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False

# CORS - permitir os 3 frontends
CORS(app, origins=[
    "https://wendy-site-admin.vercel.app",
    "https://wendy-site-lojista.vercel.app",
    "https://wendy-site-app.vercel.app"
])

# JWT
jwt = JWTManager(app)

# Registrar blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(stores_bp, url_prefix='/api/stores')
app.register_blueprint(products_bp, url_prefix='/api/products')
app.register_blueprint(orders_bp, url_prefix='/api/orders')
app.register_blueprint(deliverers_bp, url_prefix='/api/deliverers')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(geolocation_bp, url_prefix='/api/geolocation')
app.register_blueprint(chat_bp, url_prefix='/api/chat')
app.register_blueprint(ratings_bp, url_prefix='/api/ratings')
app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
app.register_blueprint(reports_bp, url_prefix='/api/reports')


# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Criar tabelas
with app.app_context():
    db.create_all()

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'Wendy Backend API is running',
        'version': '2.4.0',
        'features': ['geolocation', 'real-time-tracking', 'chat', 'ratings', 'notifications', 'reports']
    })

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return jsonify({'error': 'Static folder not configured'}), 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return jsonify({
                'message': 'Wendy Backend API v2.4.0',
                'endpoints': {
                    'health': '/api/health',
                    'auth': '/api/auth/*',
                    'stores': '/api/stores/*',
                    'products': '/api/products/*',
                    'orders': '/api/orders/*',
                    'deliverers': '/api/deliverers/*',
                    'admin': '/api/admin/*',
                    'geolocation': '/api/geolocation/*',
                    'chat': '/api/chat/*',
                    'ratings': '/api/ratings/*',
                    'notifications': '/api/notifications/*',
                    'reports': '/api/reports/*',
                    'store': '/api/store/*'
                },
                'new_features': [
                    'Real-time location tracking',
                    'Order tracking with maps',
                    'Delivery time estimation',
                    'Nearby deliverers search',
                    'Geofence zones',
                    'Chat between users',
                    'Ratings system',
                    'Push notifications',
                    'Advanced reports'
                ]
            })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

