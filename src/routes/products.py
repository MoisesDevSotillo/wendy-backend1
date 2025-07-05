from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from src.models.wendy_models import db, Product, Store, User, Category, Subcategory
from sqlalchemy import or_
from src.security_improvements import (
    SecurityValidator, rate_limit, validate_json_input, secure_headers, SecurityLogger
)
from datetime import datetime

products_bp = Blueprint("products", __name__)

@products_bp.route("/", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_products():
    try:
        # Parâmetros de filtro
        store_id = request.args.get("store_id")
        category_id = request.args.get("category_id")
        search = request.args.get("search")
        min_price = request.args.get("min_price")
        max_price = request.args.get("max_price")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        
        query = Product.query.filter(Product.is_active == True)
        
        # Filtrar apenas produtos de lojas aprovadas
        query = query.join(Store).filter(Store.is_approved == True, Store.is_active == True)
        
        if store_id:
            store_id = SecurityValidator.sanitize_string(store_id)
            if not store_id.isdigit():
                return jsonify({"error": "ID da loja inválido"}), 400
            query = query.filter(Product.store_id == int(store_id))
        
        if category_id:
            category_id = SecurityValidator.sanitize_string(category_id)
            if not category_id.isdigit():
                return jsonify({"error": "ID da categoria inválido"}), 400
            query = query.filter(Product.category_id == int(category_id))
        
        if search:
            search_term = f"%{SecurityValidator.sanitize_string(search)}%"
            query = query.filter(
                or_(
                    Product.name.ilike(search_term),
                    Product.description.ilike(search_term)
                )
            )
        
        if min_price:
            try:
                min_price = float(SecurityValidator.sanitize_string(min_price))
                query = query.filter(Product.price >= min_price)
            except ValueError:
                return jsonify({"error": "Preço mínimo inválido"}), 400
        
        if max_price:
            try:
                max_price = float(SecurityValidator.sanitize_string(max_price))
                query = query.filter(Product.price <= max_price)
            except ValueError:
                return jsonify({"error": "Preço máximo inválido"}), 400
        
        # Paginação com ordenação por privilégio da loja
        # Primeiro, lojas privilegiadas, depois as demais
        query = query.order_by(Store.is_privileged.desc(), Product.created_at.desc())
        
        products = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            "products": [product.to_dict() for product in products.items],
            "total": products.total,
            "pages": products.pages,
            "current_page": page,
            "per_page": per_page
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_products_error", {"error": str(e), "query_params": request.args.to_dict()})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/<int:product_id>", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_product(product_id):
    try:
        # Sanitizar product_id
        product_id = int(SecurityValidator.sanitize_string(str(product_id)))
        
        product = Product.query.get(product_id)
        
        if not product or not product.is_active:
            return jsonify({"error": "Produto não encontrado"}), 404
        
        # Verificar se a loja está aprovada
        if not product.store.is_approved or not product.store.is_active:
            return jsonify({"error": "Produto não disponível"}), 404
        
        return jsonify(product.to_dict()), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_product_error", {"error": str(e), "product_id": product_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/my-products", methods=["GET"])
@jwt_required()
@rate_limit(max_requests=30, window_minutes=1, per="user")
@secure_headers()
def get_my_products():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/products/my-products", "method": "GET"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        products = Product.query.filter_by(store_id=store.id).all()
        
        return jsonify({
            "products": [product.to_dict() for product in products],
            "total": len(products)
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_my_products_error", {"error": str(e), "user_id": user_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/", methods=["POST"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=5, per="user")
@validate_json_input(
    required_fields=["name", "price", "category_id"],
    optional_fields=["description", "stock_quantity", "image_url", "subcategory_id"]
)
@secure_headers()
def create_product():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/products", "method": "POST"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        data = request.get_json()
        
        # Sanitizar e validar dados
        name = SecurityValidator.sanitize_string(data["name"], 100)
        description = SecurityValidator.sanitize_string(data.get("description", ""), 500)
        
        try:
            price = float(SecurityValidator.sanitize_string(str(data["price"])))
            if price <= 0:
                return jsonify({"error": "Preço deve ser um valor positivo"}), 400
        except ValueError:
            return jsonify({"error": "Preço inválido"}), 400
        
        try:
            stock_quantity = int(SecurityValidator.sanitize_string(str(data.get("stock_quantity", 0))))
            if stock_quantity < 0:
                return jsonify({"error": "Quantidade em estoque não pode ser negativa"}), 400
        except ValueError:
            return jsonify({"error": "Quantidade em estoque inválida"}), 400
        
        image_url = SecurityValidator.sanitize_string(data.get("image_url", ""), 500)
        
        # Validar categoria
        category_id = SecurityValidator.sanitize_string(str(data["category_id"])) # Sanitiza para int
        if not category_id.isdigit():
            return jsonify({"error": "ID da categoria inválido"}), 400
        category = Category.query.get(int(category_id))
        if not category:
            return jsonify({"error": "Categoria não encontrada"}), 404
        
        # Validar subcategoria (se fornecida)
        subcategory_id = None
        if "subcategory_id" in data and data["subcategory_id"] is not None:
            subcategory_id = SecurityValidator.sanitize_string(str(data["subcategory_id"])) # Sanitiza para int
            if not subcategory_id.isdigit():
                return jsonify({"error": "ID da subcategoria inválido"}), 400
            subcategory = Subcategory.query.get(int(subcategory_id))
            if not subcategory or subcategory.category_id != category.id:
                return jsonify({"error": "Subcategoria não encontrada ou não pertence à categoria selecionada"}), 404
            subcategory_id = int(subcategory_id)

        product = Product(
            store_id=store.id,
            name=name,
            description=description,
            price=price,
            category_id=int(category_id),
            subcategory_id=subcategory_id,
            stock_quantity=stock_quantity,
            image_url=image_url
        )
        
        db.session.add(product)
        db.session.commit()
        
        SecurityLogger.log_security_event("product_create_success", {"user_id": user_id, "product_id": product.id})
        
        return jsonify({
            "message": "Produto criado com sucesso",
            "product": product.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("product_create_error", {"error": str(e), "user_id": user_id, "data": data})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/<int:product_id>", methods=["PUT"])
@jwt_required()
@rate_limit(max_requests=10, window_minutes=5, per="user")
@validate_json_input(
    optional_fields=["name", "description", "price", "category_id", "stock_quantity", "image_url", "is_active", "subcategory_id"]
)
@secure_headers()
def update_product(product_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/products/<id>", "method": "PUT"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        
        if not product:
            return jsonify({"error": "Produto não encontrado"}), 404
        
        data = request.get_json()
        
        # Atualizar campos permitidos com sanitização e validação
        if "name" in data:
            product.name = SecurityValidator.sanitize_string(data["name"], 100)
        if "description" in data:
            product.description = SecurityValidator.sanitize_string(data["description"], 500)
        if "price" in data:
            try:
                price = float(SecurityValidator.sanitize_string(str(data["price"])))
                if price <= 0:
                    return jsonify({"error": "Preço deve ser um valor positivo"}), 400
                product.price = price
            except ValueError:
                return jsonify({"error": "Preço inválido"}), 400
        if "category_id" in data:
            category_id = SecurityValidator.sanitize_string(str(data["category_id"])) # Sanitiza para int
            if not category_id.isdigit():
                return jsonify({"error": "ID da categoria inválido"}), 400
            category = Category.query.get(int(category_id))
            if not category:
                return jsonify({"error": "Categoria não encontrada"}), 404
            product.category_id = int(category_id)
        if "subcategory_id" in data and data["subcategory_id"] is not None:
            subcategory_id = SecurityValidator.sanitize_string(str(data["subcategory_id"])) # Sanitiza para int
            if not subcategory_id.isdigit():
                return jsonify({"error": "ID da subcategoria inválido"}), 400
            subcategory = Subcategory.query.get(int(subcategory_id))
            if not subcategory or subcategory.category_id != product.category_id:
                return jsonify({"error": "Subcategoria não encontrada ou não pertence à categoria selecionada"}), 404
            product.subcategory_id = int(subcategory_id)
        elif "subcategory_id" in data and data["subcategory_id"] is None:
            product.subcategory_id = None # Permite remover a subcategoria
        if "stock_quantity" in data:
            try:
                stock_quantity = int(SecurityValidator.sanitize_string(str(data["stock_quantity"])))
                if stock_quantity < 0:
                    return jsonify({"error": "Quantidade em estoque não pode ser negativa"}), 400
                product.stock_quantity = stock_quantity
            except ValueError:
                return jsonify({"error": "Quantidade em estoque inválida"}), 400
        if "image_url" in data:
            product.image_url = SecurityValidator.sanitize_string(data["image_url"], 500)
        if "is_active" in data:
            product.is_active = bool(data["is_active"])
        
        db.session.commit()
        
        SecurityLogger.log_security_event("product_update_success", {"user_id": user_id, "product_id": product.id})
        
        return jsonify({
            "message": "Produto atualizado com sucesso",
            "product": product.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("product_update_error", {"error": str(e), "user_id": user_id, "product_id": product_id, "data": data})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/<int:product_id>", methods=["DELETE"])
@jwt_required()
@rate_limit(max_requests=5, window_minutes=5, per="user")
@secure_headers()
def delete_product(product_id):
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or user.user_type != "store":
            SecurityLogger.log_security_event("unauthorized_access", 
                                            {"user_id": user_id, "route": "/products/<id>", "method": "DELETE"})
            return jsonify({"error": "Acesso negado"}), 403
        
        store = Store.query.filter_by(user_id=user_id).first()
        
        if not store:
            return jsonify({"error": "Loja não encontrada"}), 404
        
        product = Product.query.filter_by(id=product_id, store_id=store.id).first()
        
        if not product:
            return jsonify({"error": "Produto não encontrado"}), 404
        
        # Soft delete - apenas desativar o produto
        product.is_active = False
        db.session.commit()
        
        SecurityLogger.log_security_event("product_delete_success", {"user_id": user_id, "product_id": product.id})
        
        return jsonify({"message": "Produto removido com sucesso"}), 200
        
    except Exception as e:
        db.session.rollback()
        SecurityLogger.log_security_event("product_delete_error", {"error": str(e), "user_id": user_id, "product_id": product_id})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/categories", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_product_categories():
    try:
        # Buscar categorias únicas dos produtos ativos
        categories = Category.query.filter_by(is_active=True).all()
        
        return jsonify({
            "categories": [cat.to_dict() for cat in categories]
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_product_categories_error", {"error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500

@products_bp.route("/featured", methods=["GET"])
@rate_limit(max_requests=100, window_minutes=1)
@secure_headers()
def get_featured_products():
    try:
        # Produtos em destaque (mais vendidos ou com maior estoque)
        # Priorizar lojas privilegiadas
        products = Product.query.join(Store).filter(
            Product.is_active == True,
            Store.is_approved == True,
            Store.is_active == True,
            Product.stock_quantity > 0
        ).order_by(
            Store.is_privileged.desc(),
            Product.stock_quantity.desc()
        ).limit(12).all()
        
        return jsonify({
            "products": [product.to_dict() for product in products]
        }), 200
        
    except Exception as e:
        SecurityLogger.log_security_event("get_featured_products_error", {"error": str(e)})
        return jsonify({"error": "Erro interno do servidor"}), 500


