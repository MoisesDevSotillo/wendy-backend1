from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, User, Order
from src.models.chat_models import Conversation, Message
from sqlalchemy import or_
from datetime import datetime
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/conversations", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_conversations():
    user_id = get_jwt_identity()
    
    conversations = Conversation.query.filter(or_(
        Conversation.participant1_id == user_id,
        Conversation.participant2_id == user_id
    )).order_by(Conversation.updated_at.desc()).all()
    
    result = []
    for conv in conversations:
        other_participant_id = conv.participant1_id if conv.participant2_id == user_id else conv.participant2_id
        other_participant = User.query.get(other_participant_id)
        
        last_message = Message.query.filter_by(conversation_id=conv.id)
        last_message = last_message.order_by(Message.timestamp.desc()).first()
        
        unread_count = Message.query.filter_by(
            conversation_id=conv.id,
            is_read=False,
            sender_id=other_participant_id
        ).count()
        
        conv_dict = conv.to_dict()
        conv_dict["other_participant_name"] = other_participant.name if other_participant else "Usuário Desconhecido"
        conv_dict["last_message_content"] = last_message.content if last_message else None
        conv_dict["last_message_timestamp"] = last_message.timestamp.isoformat() if last_message else None
        conv_dict["unread_count"] = unread_count
        result.append(conv_dict)
        
    return jsonify(result), 200

@chat_bp.route("/conversations", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["participant2_id"],
    optional_fields=["order_id"]
)
@secure_headers()
def create_conversation():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    participant2_id = SecurityValidator.sanitize_int(data.get("participant2_id"))
    order_id = SecurityValidator.sanitize_int(data.get("order_id"))
    
    if not participant2_id:
        SecurityLogger.log_security_event("missing_participant2_id", 
                                        {"user_id": user_id, "route": "/chat/conversations", "method": "POST"})
        return jsonify({"error": "ID do segundo participante é obrigatório"}), 400
        
    if user_id == participant2_id:
        SecurityLogger.log_security_event("self_conversation_attempt", 
                                        {"user_id": user_id, "route": "/chat/conversations", "method": "POST"})
        return jsonify({"error": "Não é possível criar conversa consigo mesmo"}), 400

    # Verificar se já existe uma conversa entre os dois participantes para o mesmo pedido
    existing_conversation = Conversation.query.filter(
        or_(
            (Conversation.participant1_id == user_id and Conversation.participant2_id == participant2_id),
            (Conversation.participant1_id == participant2_id and Conversation.participant2_id == user_id)
        ),
        Conversation.order_id == order_id
    ).first()

    if existing_conversation:
        SecurityLogger.log_security_event("existing_conversation_found", 
                                        {"user_id": user_id, "conversation_id": existing_conversation.id})
        return jsonify({"message": "Conversa já existe", "conversation": existing_conversation.to_dict()}), 200

    new_conversation = Conversation(
        participant1_id=user_id,
        participant2_id=participant2_id,
        order_id=order_id
    )
    db.session.add(new_conversation)
    db.session.commit()
    
    SecurityLogger.log_security_event("conversation_created", 
                                    {"user_id": user_id, "conversation_id": new_conversation.id})
    
    return jsonify({"message": "Conversa criada com sucesso", "conversation": new_conversation.to_dict()}), 201

@chat_bp.route("/conversations/<int:conversation_id>/messages", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=60, window_minutes=1, per="user")
@secure_headers()
def get_messages(conversation_id):
    user_id = get_jwt_identity()
    
    sanitized_conversation_id = SecurityValidator.sanitize_int(conversation_id)
    if sanitized_conversation_id is None or sanitized_conversation_id <= 0:
        return jsonify({"error": "ID da conversa inválido"}), 400

    conversation = Conversation.query.get(sanitized_conversation_id)
    if not conversation:
        SecurityLogger.log_security_event("conversation_not_found", 
                                        {"user_id": user_id, "conversation_id": sanitized_conversation_id, "route": f"/chat/conversations/{conversation_id}/messages", "method": "GET"})
        return jsonify({"error": "Conversa não encontrada"}), 404
        
    if user_id not in [conversation.participant1_id, conversation.participant2_id]:
        SecurityLogger.log_security_event("unauthorized_conversation_access", 
                                        {"user_id": user_id, "conversation_id": sanitized_conversation_id, "route": f"/chat/conversations/{conversation_id}/messages", "method": "GET"})
        return jsonify({"error": "Acesso negado a esta conversa"}), 403
        
    messages = Message.query.filter_by(conversation_id=sanitized_conversation_id)
    messages = messages.order_by(Message.timestamp.asc()).all()
    
    # Marcar mensagens como lidas
    Message.query.filter_by(
        conversation_id=sanitized_conversation_id,
        is_read=False
    ).filter(Message.sender_id != user_id).update({"is_read": True})
    db.session.commit()
    
    return jsonify([msg.to_dict() for msg in messages]), 200

@chat_bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=1, per="user")
@validate_json_input(
    required_fields=["content"]
)
@secure_headers()
def send_message(conversation_id):
    try:
        user_id = get_jwt_identity()
        
        sanitized_conversation_id = SecurityValidator.sanitize_int(conversation_id)
        if sanitized_conversation_id is None or sanitized_conversation_id <= 0:
            return jsonify({"error": "ID da conversa inválido"}), 400

        conversation = Conversation.query.get(sanitized_conversation_id)
        if not conversation:
            SecurityLogger.log_security_event("conversation_not_found", 
                                            {"user_id": user_id, "conversation_id": sanitized_conversation_id, "route": f"/chat/conversations/{conversation_id}/messages", "method": "POST"})
            return jsonify({"error": "Conversa não encontrada"}), 404
            
        if user_id not in [conversation.participant1_id, conversation.participant2_id]:
            SecurityLogger.log_security_event("unauthorized_conversation_access", 
                                            {"user_id": user_id, "conversation_id": sanitized_conversation_id, "route": f"/chat/conversations/{conversation_id}/messages", "method": "POST"})
            return jsonify({"error": "Acesso negado a esta conversa"}), 403
            
        data = request.get_json()
        content = SecurityValidator.sanitize_string(data.get("content"), 1000) # Limite de 1000 caracteres para mensagens
        if not content:
            return jsonify({"error": "Conteúdo da mensagem é obrigatório"}), 400
            
        new_message = Message(
            conversation_id=sanitized_conversation_id,
            sender_id=user_id,
            content=content
        )
        db.session.add(new_message)
        
        # Atualizar timestamp da conversa
        conversation.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        SecurityLogger.log_security_event("message_sent", 
                                        {"user_id": user_id, "conversation_id": sanitized_conversation_id, "message_id": new_message.id})
        
        return jsonify({"message": "Mensagem enviada com sucesso", "message_data": new_message.to_dict()}), 201
        
    except Exception as e:
        SecurityLogger.log_security_event("send_message_error", 
                                        {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@chat_bp.route("/conversations/<int:conversation_id>/mark-read", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=1, per="user")
@secure_headers()
def mark_messages_read(conversation_id):
    try:
        user_id = get_jwt_identity()
        
        sanitized_conversation_id = SecurityValidator.sanitize_int(conversation_id)
        if sanitized_conversation_id is None or sanitized_conversation_id <= 0:
            return jsonify({"error": "ID da conversa inválido"}), 400

        conversation = Conversation.query.get(sanitized_conversation_id)
        if not conversation:
            SecurityLogger.log_security_event("conversation_not_found", 
                                            {"user_id": user_id, "conversation_id": sanitized_conversation_id, "route": f"/chat/conversations/{conversation_id}/mark-read", "method": "POST"})
            return jsonify({"error": "Conversa não encontrada"}), 404
            
        if user_id not in [conversation.participant1_id, conversation.participant2_id]:
            SecurityLogger.log_security_event("unauthorized_conversation_access", 
                                            {"user_id": user_id, "conversation_id": sanitized_conversation_id, "route": f"/chat/conversations/{conversation_id}/mark-read", "method": "POST"})
            return jsonify({"error": "Acesso negado a esta conversa"}), 403
            
        Message.query.filter_by(
            conversation_id=sanitized_conversation_id,
            is_read=False
        ).filter(Message.sender_id != user_id).update({"is_read": True})
        db.session.commit()
        
        SecurityLogger.log_security_event("messages_marked_read", 
                                        {"user_id": user_id, "conversation_id": sanitized_conversation_id})
        
        return jsonify({"message": "Mensagens marcadas como lidas"}), 200
    except Exception as e:
        SecurityLogger.log_error("mark_messages_read_error", {"user_id": user_id, "error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

