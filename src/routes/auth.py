from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from src.models.wendy_models import db, User, Store, Deliverer, AllowedCity
from src.security_improvements import (
    SecurityValidator, rate_limit, login_attempt_limiter, 
    validate_json_input, secure_headers, SecurityLogger
)
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
@rate_limit(max_requests=10, window_minutes=5)  # Limita criação de contas
@validate_json_input(
    required_fields=['email', 'password', 'name', 'user_type'],
    optional_fields=['store_name', 'category', 'cnpj', 'address', 'city', 'state', 
                    'zip_code', 'phone', 'cpf', 'vehicle_type', 'vehicle_plate']
)
@secure_headers()
def register():
    try:
        data = request.get_json()
        
        # Validar e sanitizar dados básicos
        email = SecurityValidator.sanitize_string(data['email'], 100).lower()
        password = data['password']
        name = SecurityValidator.sanitize_string(data['name'], 100)
        user_type = data['user_type']
        
        # Validar email
        if not SecurityValidator.validate_email(email):
            SecurityLogger.log_security_event('invalid_email_registration', 
                                            {'email': email, 'user_type': user_type})
            return jsonify({'error': 'Email inválido'}), 400
        
        # Validar senha
        password_valid, password_message = SecurityValidator.validate_password(password)
        if not password_valid:
            SecurityLogger.log_security_event('weak_password_registration', 
                                            {'email': email, 'message': password_message})
            return jsonify({'error': password_message}), 400
        
        # Validar tipo de usuário
        valid_user_types = ['client', 'store', 'deliverer']
        if user_type not in valid_user_types:
            SecurityLogger.log_security_event('invalid_user_type_registration', 
                                            {'email': email, 'user_type': user_type})
            return jsonify({'error': 'Tipo de usuário inválido'}), 400
        
        # Verificar se email já existe
        if User.query.filter_by(email=email).first():
            SecurityLogger.log_security_event('duplicate_email_registration', 
                                            {'email': email})
            return jsonify({'error': 'Email já cadastrado'}), 400
        
        # Validar campos específicos por tipo de usuário
        if user_type == 'store':
            store_required_fields = [
                'store_name', 'category', 'cnpj', 'address', 
                'city', 'state', 'zip_code', 'phone'
            ]
            for field in store_required_fields:
                if field not in data or not data[field]:
                    field_names = {
                        'store_name': 'Nome da loja',
                        'category': 'Categoria',
                        'cnpj': 'CNPJ',
                        'address': 'Endereço',
                        'city': 'Cidade',
                        'state': 'Estado',
                        'zip_code': 'CEP',
                        'phone': 'Telefone'
                    }
                    return jsonify({'error': f'Campo {field_names.get(field, field)} é obrigatório para lojistas'}), 400
            
            # Validar CNPJ com algoritmo completo
            cnpj = SecurityValidator.sanitize_string(data['cnpj'], 20)
            if not SecurityValidator.validate_cnpj(cnpj):
                SecurityLogger.log_security_event('invalid_cnpj_registration', 
                                                {'email': email, 'cnpj': cnpj[:4] + '****'})
                return jsonify({'error': 'CNPJ inválido'}), 400
            
            # Validar telefone
            phone = SecurityValidator.sanitize_string(data['phone'], 20)
            if not SecurityValidator.validate_phone(phone):
                return jsonify({'error': 'Telefone inválido. Use formato brasileiro (10-11 dígitos)'}), 400
            
            # Validar CEP
            zip_code = SecurityValidator.sanitize_string(data['zip_code'], 10)
            zip_code_clean = zip_code.replace('-', '').replace(' ', '')
            if len(zip_code_clean) != 8 or not zip_code_clean.isdigit():
                return jsonify({'error': 'CEP deve ter 8 dígitos'}), 400
            
            # Sanitizar outros campos
            store_name = SecurityValidator.sanitize_string(data['store_name'], 100)
            category = SecurityValidator.sanitize_string(data['category'], 50)
            address = SecurityValidator.sanitize_string(data['address'], 200)
            city = SecurityValidator.sanitize_string(data['city'], 50)
            state = SecurityValidator.sanitize_string(data['state'], 2)
            
            # Verificar se a cidade está permitida
            allowed_city = AllowedCity.query.filter_by(
                name=city.lower(), 
                state=state.upper(), 
                is_active=True
            ).first()
            
            if not allowed_city:
                SecurityLogger.log_security_event('unauthorized_city_registration', 
                                                {'email': email, 'city': city, 'state': state})
                return jsonify({'error': f'Cidade {city}/{state} não está disponível para cadastro'}), 400
        
        elif user_type == 'deliverer':
            deliverer_required_fields = ['cpf', 'vehicle_type', 'vehicle_plate', 'phone']
            for field in deliverer_required_fields:
                if field not in data or not data[field]:
                    field_names = {
                        'cpf': 'CPF',
                        'vehicle_type': 'Tipo de veículo',
                        'vehicle_plate': 'Placa do veículo',
                        'phone': 'Telefone'
                    }
                    return jsonify({'error': f'Campo {field_names.get(field, field)} é obrigatório para entregadores'}), 400
            
            # Validar CPF com algoritmo completo
            cpf = SecurityValidator.sanitize_string(data['cpf'], 15)
            if not SecurityValidator.validate_cpf(cpf):
                SecurityLogger.log_security_event('invalid_cpf_registration', 
                                                {'email': email, 'cpf': cpf[:3] + '****'})
                return jsonify({'error': 'CPF inválido'}), 400
            
            # Validar telefone
            phone = SecurityValidator.sanitize_string(data['phone'], 20)
            if not SecurityValidator.validate_phone(phone):
                return jsonify({'error': 'Telefone inválido. Use formato brasileiro (10-11 dígitos)'}), 400
            
            # Validar tipo de veículo
            valid_vehicle_types = ['motorcycle', 'bicycle', 'car']
            vehicle_type = SecurityValidator.sanitize_string(data['vehicle_type'], 20)
            if vehicle_type not in valid_vehicle_types:
                return jsonify({'error': 'Tipo de veículo inválido. Use: motorcycle, bicycle ou car'}), 400
            
            # Sanitizar placa
            vehicle_plate = SecurityValidator.sanitize_string(data['vehicle_plate'], 10).upper()
            
        elif user_type == 'client':
            # Para clientes, apenas telefone é obrigatório
            if 'phone' in data and data['phone']:
                phone = SecurityValidator.sanitize_string(data['phone'], 20)
                if not SecurityValidator.validate_phone(phone):
                    return jsonify({'error': 'Telefone inválido. Use formato brasileiro (10-11 dígitos)'}), 400
        
        # Criar usuário
        approval_status = 'pending' if user_type in ['store', 'deliverer'] else 'approved'
        
        user = User(
            email=email,
            name=name,
            user_type=user_type,
            is_approved=(user_type == 'client'),
            approval_status=approval_status,
            is_active=True
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.flush()  # Para obter o ID do usuário
        
        # Criar registros específicos por tipo
        if user_type == 'store':
            store = Store(
                user_id=user.id,
                name=store_name,
                category=category,
                cnpj=cnpj,
                address=address,
                city=city,
                state=state,
                zip_code=zip_code_clean,
                phone=phone,
                is_approved=False,
                approval_status='pending'
            )
            db.session.add(store)
            
        elif user_type == 'deliverer':
            deliverer = Deliverer(
                user_id=user.id,
                cpf=cpf,
                vehicle_type=vehicle_type,
                vehicle_plate=vehicle_plate,
                phone=phone,
                is_approved=False,
                approval_status='pending'
            )
            db.session.add(deliverer)
        
        db.session.commit()
        
        # Log de sucesso
        SecurityLogger.log_security_event('successful_registration', 
                                        {'email': email, 'user_type': user_type, 'user_id': user.id})
        
        # Criar token de acesso
        access_token = create_access_token(identity=user.id)
        
        response_data = {
            'message': 'Usuário criado com sucesso',
            'user': user.to_dict(),
            'access_token': access_token
        }
        
        # Adicionar mensagem específica para usuários que precisam de aprovação
        if user_type in ['store', 'deliverer']:
            response_data['approval_required'] = True
            response_data['approval_message'] = 'Seu cadastro foi enviado para análise. Você receberá uma confirmação em breve.'
        
        return jsonify(response_data), 201
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event('registration_error', 
                                        {'error': str(e), 'email': data.get('email', 'unknown')})
        return jsonify({'error': 'Erro interno do servidor'}), 500

@auth_bp.route('/login', methods=['POST'])
@login_attempt_limiter(max_attempts=5, lockout_minutes=15)
@rate_limit(max_requests=20, window_minutes=5)
@validate_json_input(
    required_fields=['email', 'password'],
    optional_fields=[]
)
@secure_headers()
def login():
    try:
        data = request.get_json()
        
        # Validar e sanitizar dados
        email = SecurityValidator.sanitize_string(data['email'], 100).lower()
        password = data['password']
        
        # Validar email
        if not SecurityValidator.validate_email(email):
            SecurityLogger.log_security_event('invalid_email_login', {'email': email})
            return jsonify({'error': 'Email inválido'}), 400
        
        # Buscar usuário
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            SecurityLogger.log_security_event('failed_login_attempt', 
                                            {'email': email, 'reason': 'invalid_credentials'})
            return jsonify({'error': 'Email ou senha inválidos'}), 401
        
        if not user.is_active:
            SecurityLogger.log_security_event('inactive_user_login', {'email': email, 'user_id': user.id})
            return jsonify({'error': 'Usuário inativo'}), 401
        
        # Verificar se o usuário está aprovado (para lojistas e entregadores)
        if user.user_type in ['store', 'deliverer'] and not user.is_approved:
            if user.approval_status == 'pending':
                return jsonify({
                    'error': 'Cadastro pendente de aprovação',
                    'message': 'Seu cadastro está sendo analisado. Aguarde a aprovação.',
                    'approval_status': 'pending'
                }), 403
            elif user.approval_status == 'rejected':
                return jsonify({
                    'error': 'Cadastro rejeitado',
                    'message': f'Seu cadastro foi rejeitado. Motivo: {user.rejection_reason or "Não especificado"}',
                    'approval_status': 'rejected'
                }), 403
        
        # Login bem-sucedido
        SecurityLogger.log_security_event('successful_login', 
                                        {'email': email, 'user_id': user.id, 'user_type': user.user_type})
        
        access_token = create_access_token(identity=user.id)
        
        return jsonify({
            'message': 'Login realizado com sucesso',
            'user': user.to_dict(),
            'access_token': access_token
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event('login_error', 
                                        {'error': str(e), 'email': data.get('email', 'unknown')})
        return jsonify({'error': 'Erro interno do servidor'}), 500

@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per='user')
@secure_headers()
def get_profile():
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event('profile_access_error', 
                                        {'user_id': current_user_id, 'error': str(e)})
        return jsonify({'error': 'Erro interno do servidor'}), 500

@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=10, per='user')
@validate_json_input(
    required_fields=['current_password', 'new_password'],
    optional_fields=[]
)
@secure_headers()
def change_password():
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': 'Usuário não encontrado'}), 404
        
        # Verificar senha atual
        if not user.check_password(data['current_password']):
            SecurityLogger.log_security_event('failed_password_change', 
                                            {'user_id': current_user_id, 'reason': 'wrong_current_password'})
            return jsonify({'error': 'Senha atual incorreta'}), 400
        
        # Validar nova senha
        password_valid, password_message = SecurityValidator.validate_password(data['new_password'])
        if not password_valid:
            return jsonify({'error': password_message}), 400
        
        # Alterar senha
        user.set_password(data['new_password'])
        db.session.commit()
        
        SecurityLogger.log_security_event('successful_password_change', 
                                        {'user_id': current_user_id})
        
        return jsonify({'message': 'Senha alterada com sucesso'}), 200
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event('password_change_error', 
                                        {'user_id': current_user_id, 'error': str(e)})
        return jsonify({'error': 'Erro interno do servidor'}), 500

