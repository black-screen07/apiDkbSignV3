"""
Utilitaires pour l'authentification par API key dans les routes publiques.
"""

from functools import wraps
from flask import request, jsonify, current_app
from app.models import User, db


def get_user_by_api_key(api_key):
    """
    Récupère un utilisateur par sa clé API.
    
    Args:
        api_key (str): La clé API à vérifier
        
    Returns:
        User: L'utilisateur correspondant à la clé API ou None si non trouvé
    """
    if not api_key:
        return None
        
    user = User.query.filter_by(api_key=api_key, api_key_active=True).first()
    return user


def require_api_key(f):
    """
    Décorateur pour exiger une authentification par API key.
    
    Usage:
        @require_api_key
        def my_route():
            # La variable g.current_user contiendra l'utilisateur authentifié
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Récupérer la clé API depuis les headers
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            # Essayer aussi avec Authorization header
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ')[1]
        
        if not api_key:
            return jsonify({
                'error': 'Clé API manquante. Utilisez le header X-API-Key ou Authorization: Bearer <api_key>'
            }), 401
        
        # Vérifier la clé API
        user = get_user_by_api_key(api_key)
        if not user:
            return jsonify({
                'error': 'Clé API invalide ou inactive'
            }), 401
        
        # Stocker l'utilisateur dans le contexte de la requête
        from flask import g
        g.current_user = user
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_authenticated_user_by_api_key():
    """
    Récupère l'utilisateur authentifié par API key depuis le contexte de la requête.
    
    Returns:
        User: L'utilisateur authentifié ou None si non authentifié
    """
    from flask import g
    return getattr(g, 'current_user', None)


def validate_api_key_header():
    """
    Valide la présence et la validité d'une clé API dans les headers de la requête.
    
    Returns:
        tuple: (user, error_response) où user est l'utilisateur authentifié 
               et error_response est None si succès ou une réponse d'erreur si échec
    """
    # Récupérer la clé API depuis les headers
    api_key = request.headers.get('X-API-Key')
    
    if not api_key:
        # Essayer aussi avec Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            api_key = auth_header.split(' ')[1]
    
    if not api_key:
        return None, jsonify({
            'error': 'Clé API manquante. Utilisez le header X-API-Key ou Authorization: Bearer <api_key>'
        }), 401
    
    # Vérifier la clé API
    user = get_user_by_api_key(api_key)
    if not user:
        return None, jsonify({
            'error': 'Clé API invalide ou inactive'
        }), 401
    
    return user, None


def log_api_usage(user, endpoint, method):
    """
    Log l'utilisation de l'API par un utilisateur.
    
    Args:
        user (User): L'utilisateur qui utilise l'API
        endpoint (str): L'endpoint appelé
        method (str): La méthode HTTP utilisée
    """
    try:
        current_app.logger.info(
            f"API Usage - User: {user.email} ({user.id}), "
            f"Endpoint: {method} {endpoint}, "
            f"API Key: {user.api_key[:8]}..."
        )
    except Exception as e:
        current_app.logger.error(f"Erreur lors du logging de l'utilisation de l'API : {str(e)}")
