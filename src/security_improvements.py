# Melhorias de Segurança para a API Wendy
# Este arquivo contém funções e decoradores para aprimorar a segurança da aplicação

import re
import time
import hashlib
import secrets
from functools import wraps
from collections import defaultdict, deque
from datetime import datetime, timedelta
from flask import request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
import bleach

# Armazenamento em memória para rate limiting (em produção, usar Redis)
request_counts = defaultdict(lambda: deque())
failed_login_attempts = defaultdict(lambda: deque())

class SecurityValidator:
    """Classe para validação de entrada e sanitização de dados"""
    
    @staticmethod
    def validate_email(email):
        """Valida formato de email"""
        if not email or not isinstance(email, str):
            return False
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email.strip()) is not None
    
    @staticmethod
    def validate_password(password):
        """Valida força da senha"""
        if not password or not isinstance(password, str):
            return False, "Senha é obrigatória"
        
        if len(password) < 8:
            return False, "Senha deve ter pelo menos 8 caracteres"
        
        if not re.search(r'[A-Z]', password):
            return False, "Senha deve conter pelo menos uma letra maiúscula"
        
        if not re.search(r'[a-z]', password):
            return False, "Senha deve conter pelo menos uma letra minúscula"
        
        if not re.search(r'\d', password):
            return False, "Senha deve conter pelo menos um número"
        
        return True, "Senha válida"
    
    @staticmethod
    def validate_phone(phone):
        """Valida número de telefone brasileiro"""
        if not phone or not isinstance(phone, str):
            return False
        
        # Remove caracteres não numéricos
        phone_clean = re.sub(r'\D', '', phone)
        
        # Verifica se tem 10 ou 11 dígitos (com DDD)
        return len(phone_clean) in [10, 11] and phone_clean.isdigit()
    
    @staticmethod
    def validate_cpf(cpf):
        """Valida CPF brasileiro"""
        if not cpf or not isinstance(cpf, str):
            return False
        
        # Remove caracteres não numéricos
        cpf_clean = re.sub(r'\D', '', cpf)
        
        # Verifica se tem 11 dígitos
        if len(cpf_clean) != 11:
            return False
        
        # Verifica se não são todos os dígitos iguais
        if cpf_clean == cpf_clean[0] * 11:
            return False
        
        # Validação dos dígitos verificadores
        def calculate_digit(cpf_partial):
            sum_val = sum(int(cpf_partial[i]) * (len(cpf_partial) + 1 - i) for i in range(len(cpf_partial)))
            remainder = sum_val % 11
            return 0 if remainder < 2 else 11 - remainder
        
        first_digit = calculate_digit(cpf_clean[:9])
        second_digit = calculate_digit(cpf_clean[:10])
        
        return cpf_clean[9] == str(first_digit) and cpf_clean[10] == str(second_digit)
    
    @staticmethod
    def validate_cnpj(cnpj):
        """Valida CNPJ brasileiro"""
        if not cnpj or not isinstance(cnpj, str):
            return False
        
        # Remove caracteres não numéricos
        cnpj_clean = re.sub(r'\D', '', cnpj)
        
        # Verifica se tem 14 dígitos
        if len(cnpj_clean) != 14:
            return False
        
        # Verifica se não são todos os dígitos iguais
        if cnpj_clean == cnpj_clean[0] * 14:
            return False
        
        # Validação dos dígitos verificadores
        def calculate_cnpj_digit(cnpj_partial, weights):
            sum_val = sum(int(cnpj_partial[i]) * weights[i] for i in range(len(cnpj_partial)))
            remainder = sum_val % 11
            return 0 if remainder < 2 else 11 - remainder
        
        weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        
        first_digit = calculate_cnpj_digit(cnpj_clean[:12], weights1)
        second_digit = calculate_cnpj_digit(cnpj_clean[:13], weights2)
        
        return cnpj_clean[12] == str(first_digit) and cnpj_clean[13] == str(second_digit)
    
    @staticmethod
    def sanitize_string(text, max_length=None):
        """Sanitiza string removendo caracteres perigosos"""
        if not text or not isinstance(text, str):
            return ""
        
        # Remove tags HTML e scripts
        sanitized = bleach.clean(text.strip(), tags=[], strip=True)
        
        # Limita o tamanho se especificado
        if max_length and len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized
    
    @staticmethod
    def validate_numeric_range(value, min_val=None, max_val=None):
        """Valida se um valor numérico está dentro de um range"""
        try:
            num_value = float(value)
            if min_val is not None and num_value < min_val:
                return False
            if max_val is not None and num_value > max_val:
                return False
            return True
        except (ValueError, TypeError):
            return False

def rate_limit(max_requests=60, window_minutes=1, per='ip'):
    """
    Decorator para limitação de taxa de requisições
    
    Args:
        max_requests: Número máximo de requisições permitidas
        window_minutes: Janela de tempo em minutos
        per: 'ip' para limitar por IP, 'user' para limitar por usuário autenticado
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            now = datetime.utcnow()
            window_start = now - timedelta(minutes=window_minutes)
            
            # Determina a chave para o rate limiting
            if per == 'user':
                try:
                    verify_jwt_in_request()
                    key = f"user_{get_jwt_identity()}"
                except:
                    key = f"ip_{request.remote_addr}"
            else:
                key = f"ip_{request.remote_addr}"
            
            # Remove requisições antigas da janela
            while request_counts[key] and request_counts[key][0] < window_start:
                request_counts[key].popleft()
            
            # Verifica se excedeu o limite
            if len(request_counts[key]) >= max_requests:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Muitas requisições. Limite: {max_requests} por {window_minutes} minuto(s)',
                    'retry_after': 60
                }), 429
            
            # Adiciona a requisição atual
            request_counts[key].append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def login_attempt_limiter(max_attempts=5, lockout_minutes=15):
    """
    Decorator para limitar tentativas de login falhadas
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip_address = request.remote_addr
            now = datetime.utcnow()
            lockout_start = now - timedelta(minutes=lockout_minutes)
            
            # Remove tentativas antigas
            while failed_login_attempts[ip_address] and failed_login_attempts[ip_address][0] < lockout_start:
                failed_login_attempts[ip_address].popleft()
            
            # Verifica se está bloqueado
            if len(failed_login_attempts[ip_address]) >= max_attempts:
                return jsonify({
                    'error': 'Account temporarily locked',
                    'message': f'Muitas tentativas de login falhadas. Tente novamente em {lockout_minutes} minutos.',
                    'lockout_until': (now + timedelta(minutes=lockout_minutes)).isoformat()
                }), 423
            
            # Executa a função original
            result = f(*args, **kwargs)
            
            # Se o login falhou (status 401 ou 400), registra a tentativa
            if hasattr(result, 'status_code') and result.status_code in [400, 401]:
                failed_login_attempts[ip_address].append(now)
            elif hasattr(result, 'status_code') and result.status_code == 200:
                # Login bem-sucedido, limpa as tentativas falhadas
                failed_login_attempts[ip_address].clear()
            
            return result
        return decorated_function
    return decorator

def validate_json_input(required_fields=None, optional_fields=None):
    """
    Decorator para validar entrada JSON
    
    Args:
        required_fields: Lista de campos obrigatórios
        optional_fields: Lista de campos opcionais permitidos
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify({'error': 'Content-Type deve ser application/json'}), 400
            
            try:
                data = request.get_json()
            except Exception:
                return jsonify({'error': 'JSON inválido'}), 400
            
            if data is None:
                return jsonify({'error': 'Corpo da requisição não pode estar vazio'}), 400
            
            # Verifica campos obrigatórios
            if required_fields:
                missing_fields = [field for field in required_fields if field not in data or data[field] is None]
                if missing_fields:
                    return jsonify({
                        'error': 'Campos obrigatórios ausentes',
                        'missing_fields': missing_fields
                    }), 400
            
            # Verifica campos não permitidos
            if optional_fields is not None:
                allowed_fields = set(required_fields or []) | set(optional_fields)
                extra_fields = set(data.keys()) - allowed_fields
                if extra_fields:
                    return jsonify({
                        'error': 'Campos não permitidos',
                        'extra_fields': list(extra_fields)
                    }), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required():
    """Verifica se o usuário é administrador"""
    try:
        verify_jwt_in_request()
        current_user_id = get_jwt_identity()
        
        # Importar aqui para evitar importação circular
        from src.models.wendy_models import User
        user = User.query.get(current_user_id)
        
        if not user or user.user_type != 'admin':
            return False
        
        return True
    except:
        return False

def secure_headers():
    """Adiciona headers de segurança às respostas"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            
            # Adiciona headers de segurança
            if hasattr(response, 'headers'):
                response.headers['X-Content-Type-Options'] = 'nosniff'
                response.headers['X-Frame-Options'] = 'DENY'
                response.headers['X-XSS-Protection'] = '1; mode=block'
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
                response.headers['Content-Security-Policy'] = "default-src 'self'"
                response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            return response
        return decorated_function
    return decorator

def generate_secure_token():
    """Gera um token seguro para uso em operações sensíveis"""
    return secrets.token_urlsafe(32)

def hash_sensitive_data(data):
    """Gera hash de dados sensíveis para logging seguro"""
    return hashlib.sha256(str(data).encode()).hexdigest()[:16]

class SecurityLogger:
    """Classe para logging de eventos de segurança"""
    
    @staticmethod
    def log_security_event(event_type, details, user_id=None, ip_address=None):
        """
        Registra eventos de segurança
        
        Args:
            event_type: Tipo do evento (login_failed, rate_limit_exceeded, etc.)
            details: Detalhes do evento
            user_id: ID do usuário (se aplicável)
            ip_address: Endereço IP
        """
        timestamp = datetime.utcnow().isoformat()
        ip_address = ip_address or request.remote_addr
        
        log_entry = {
            'timestamp': timestamp,
            'event_type': event_type,
            'details': details,
            'user_id': user_id,
            'ip_address': hash_sensitive_data(ip_address),  # Hash do IP para privacidade
            'user_agent': request.headers.get('User-Agent', '')[:200]  # Limita tamanho
        }
        
        # Em produção, enviar para um sistema de logging centralizado
        print(f"SECURITY_EVENT: {log_entry}")
        
        return log_entry

