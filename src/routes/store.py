from flask import Blueprint, request, jsonify

store_bp = Blueprint('store_bp', __name__)

@store_bp.route('/login', methods=['POST'])
def store_login():
    return jsonify({"message": "Login de lojista funcionando!"})

@store_bp.route('/register', methods=['POST'])
def store_register():
    return jsonify({"message": "Cadastro de lojista funcionando!"})
