from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.notification_models import db, DeviceToken
from src.models.wendy_models import User
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)

notifications_bp = Blueprint("notifications", __name__)

@notifications_bp.route("/register-device", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["token", "device_type"],
    optional_fields=[]
)
@secure_headers()
def register_device():
    """Registra um token de dispositivo para notificações push"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Sanitizar dados de entrada
        token = SecurityValidator.sanitize_string(data.get("token"), max_length=500)
        device_type = SecurityValidator.sanitize_string(data.get("device_type"), max_length=50)

        if not token or len(token) < 10:
            SecurityLogger.log_security_event("invalid_device_token", 
                                            {"user_id": user_id, "token_length": len(token) if token else 0})
            return jsonify({"error": "Token de dispositivo inválido"}), 400
            
        if device_type not in ["android", "ios", "web"]:
            SecurityLogger.log_security_event("invalid_device_type", 
                                            {"user_id": user_id, "device_type": data.get("device_type")})
            return jsonify({"error": "Tipo de dispositivo deve ser 'android', 'ios' ou 'web'"}), 400

        user = User.query.get(user_id)
        if not user:
            SecurityLogger.log_security_event("user_not_found_for_device_registration", 
                                            {"user_id": user_id})
            return jsonify({"error": "Usuário não encontrado"}), 404

        # Verifica se o token já existe para este usuário
        existing_token = DeviceToken.query.filter_by(user_id=user_id, token=token).first()
        if existing_token:
            SecurityLogger.log_security_event("device_token_already_registered", 
                                            {"user_id": user_id, "token_hash": SecurityValidator.hash_sensitive_data(token)})
            return jsonify({"message": "Token de dispositivo já registrado"}), 200

        # Limitar número de tokens por usuário (máximo 5 dispositivos)
        user_token_count = DeviceToken.query.filter_by(user_id=user_id).count()
        if user_token_count >= 5:
            # Remove o token mais antigo
            oldest_token = DeviceToken.query.filter_by(user_id=user_id).order_by(DeviceToken.created_at.asc()).first()
            if oldest_token:
                db.session.delete(oldest_token)
                SecurityLogger.log_security_event("old_device_token_removed", 
                                                {"user_id": user_id, "removed_token_id": oldest_token.id})

        new_device_token = DeviceToken(user_id=user_id, token=token, device_type=device_type)
        db.session.add(new_device_token)
        db.session.commit()

        SecurityLogger.log_security_event("device_token_registered", 
                                        {"user_id": user_id, "device_type": device_type, "token_id": new_device_token.id})

        return jsonify({"message": "Token de dispositivo registrado com sucesso"}), 201

    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("device_registration_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@notifications_bp.route("/unregister-device", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["token"],
    optional_fields=[]
)
@secure_headers()
def unregister_device():
    """Remove um token de dispositivo"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        token = SecurityValidator.sanitize_string(data.get("token"), max_length=500)

        if not token:
            SecurityLogger.log_security_event("missing_token_for_unregister", 
                                            {"user_id": user_id})
            return jsonify({"error": "Token é obrigatório"}), 400

        # Verificar se o token pertence ao usuário logado
        device_token = DeviceToken.query.filter_by(token=token, user_id=user_id).first()
        if not device_token:
            SecurityLogger.log_security_event("unauthorized_token_unregister_attempt", 
                                            {"user_id": user_id, "token_hash": SecurityValidator.hash_sensitive_data(token)})
            return jsonify({"error": "Token não encontrado ou não autorizado"}), 404

        db.session.delete(device_token)
        db.session.commit()

        SecurityLogger.log_security_event("device_token_unregistered", 
                                        {"user_id": user_id, "token_id": device_token.id})

        return jsonify({"message": "Token de dispositivo removido com sucesso"}), 200

    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("device_unregistration_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@notifications_bp.route("/send-notification", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=20, window_minutes=5, per="user")
@validate_json_input(
    required_fields=["target_user_id", "title", "body"],
    optional_fields=["data"]
)
@secure_headers()
def send_notification():
    """Envia uma notificação para um usuário específico (simulado)"""
    try:
        sender_id = get_jwt_identity()
        data = request.get_json()
        
        # Sanitizar dados de entrada
        target_user_id = SecurityValidator.sanitize_int(data.get("target_user_id"))
        title = SecurityValidator.sanitize_string(data.get("title"), max_length=100)
        body = SecurityValidator.sanitize_string(data.get("body"), max_length=500)
        notification_data = data.get("data", {})

        if not target_user_id or target_user_id <= 0:
            SecurityLogger.log_security_event("invalid_target_user_id", 
                                            {"sender_id": sender_id, "target_user_id": data.get("target_user_id")})
            return jsonify({"error": "ID do usuário de destino inválido"}), 400
            
        if not title or not body:
            SecurityLogger.log_security_event("missing_notification_content", 
                                            {"sender_id": sender_id, "target_user_id": target_user_id})
            return jsonify({"error": "Título e corpo da notificação são obrigatórios"}), 400

        # Verificar se o usuário de destino existe
        target_user = User.query.get(target_user_id)
        if not target_user:
            SecurityLogger.log_security_event("target_user_not_found", 
                                            {"sender_id": sender_id, "target_user_id": target_user_id})
            return jsonify({"error": "Usuário de destino não encontrado"}), 404

        # Verificar se o remetente tem permissão para enviar notificação
        sender = User.query.get(sender_id)
        if not sender:
            SecurityLogger.log_security_event("sender_not_found", 
                                            {"sender_id": sender_id})
            return jsonify({"error": "Remetente não encontrado"}), 404

        # Apenas admins ou usuários relacionados podem enviar notificações
        if sender.user_type != "admin":
            # Verificar se há alguma relação entre os usuários (pedidos, conversas, etc.)
            # Por simplicidade, vamos permitir apenas para admins por enquanto
            SecurityLogger.log_security_event("unauthorized_notification_send", 
                                            {"sender_id": sender_id, "target_user_id": target_user_id})
            return jsonify({"error": "Você não tem permissão para enviar notificações para este usuário"}), 403

        user_tokens = DeviceToken.query.filter_by(user_id=target_user_id).all()
        if not user_tokens:
            SecurityLogger.log_security_event("no_device_tokens_found", 
                                            {"sender_id": sender_id, "target_user_id": target_user_id})
            return jsonify({"message": "Nenhum token de dispositivo encontrado para este usuário"}), 200

        # Simula o envio da notificação para cada token
        sent_count = 0
        for device_token in user_tokens:
            # Aqui seria integrado com um serviço real de push notifications (Firebase, etc.)
            print(f"Simulando envio de notificação para {device_token.token[:20]}... (Tipo: {device_token.device_type}): {title} - {body}")
            sent_count += 1

        SecurityLogger.log_security_event("notifications_sent", 
                                        {"sender_id": sender_id, "target_user_id": target_user_id, "count": sent_count})

        return jsonify({"message": f"Simulado envio de {sent_count} notificações"}), 200

    except Exception as e:
        SecurityLogger.log_security_event("notification_send_error", 
                                        {"sender_id": sender_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@notifications_bp.route("/my-devices", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=1, per="user")
@secure_headers()
def get_my_devices():
    """Obter lista de dispositivos registrados do usuário"""
    try:
        user_id = get_jwt_identity()
        
        devices = DeviceToken.query.filter_by(user_id=user_id).order_by(DeviceToken.created_at.desc()).all()
        
        device_list = []
        for device in devices:
            device_list.append({
                "id": device.id,
                "device_type": device.device_type,
                "token_preview": device.token[:20] + "..." if len(device.token) > 20 else device.token,
                "created_at": device.created_at.isoformat(),
                "last_used": device.last_used.isoformat() if device.last_used else None
            })
        
        return jsonify({
            "devices": device_list,
            "total": len(device_list)
        }), 200

    except Exception as e:
        SecurityLogger.log_security_event("get_devices_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

