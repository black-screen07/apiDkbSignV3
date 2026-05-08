from dotenv import load_dotenv
import os
from datetime import timedelta

load_dotenv()

class Config:
    # Sécurité
    SECRET_KEY = os.getenv('SECRET_KEY', 'fallback_secret')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    
    # Limite de taille des fichiers uploadés (50 MB par défaut)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    # Base de données
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Options du moteur SQLAlchemy
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 50
    }

    # Durée de vie du token d'accès
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=10)   # Ex. 10 heure
    # Durée de vie du token de rafraîchissement
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)  # Ex. 30 jours

    # Configuration pour Flask-Mail
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 465))  # Convertir en entier
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', 'no-reply@dkbsign.com')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', 'fallback_password')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'no-reply@example.com')
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'False').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'True').lower() == 'true'
    MAIL_DEBUG = os.getenv('MAIL_DEBUG', 'True').lower() == 'true'
