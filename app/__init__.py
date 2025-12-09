from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config
from flask_mail import Mail

# Initialiser les extensions globales
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialisation des extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    mail.init_app(app)

    # Configuration avancée de CORS
    CORS(app, resources={
        r"/*": {
            "origins": ["*"],  # À ajuster en production
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "supports_credentials": True,
        }
    })

    # Importer et enregistrer les Blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.user_routes import user_bp
    from app.routes.signature_routes import signature_bp
    from app.routes.sign_and_assign_routes import sign_and_assign_bp
    from app.routes.assign_only_routes import assign_only_bp
    from app.routes.company_routes import company_bp
    from app.routes.document_routes import document_bp
    from app.routes.draft_routes import draft_bp
    from app.routes.email_routes import email_bp
    from app.routes.metric_routes import metric_bp
    from app.routes.consent_routes import consent_bp
    from app.routes.contact_routes import contact_bp
    from app.routes.workflow_routes import workflow_bp
    from app.routes.flow_routes import flow_bp
    from app.routes.flow_signature_routes import flow_signature_bp
    from app.routes.certificate_routes import certificate_bp
    from app.routes.health_routes import health_bp

    app.register_blueprint(health_bp)  # No prefix for health endpoints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(signature_bp, url_prefix='/signatures')
    app.register_blueprint(sign_and_assign_bp, url_prefix='/signatures')
    app.register_blueprint(assign_only_bp, url_prefix='/signatures')
    app.register_blueprint(company_bp, url_prefix='/')
    app.register_blueprint(user_bp, url_prefix='/')
    app.register_blueprint(document_bp, url_prefix='/')
    app.register_blueprint(draft_bp, url_prefix='/')
    app.register_blueprint(email_bp, url_prefix='/')
    app.register_blueprint(metric_bp, url_prefix='/')
    app.register_blueprint(consent_bp, url_prefix='/')
    app.register_blueprint(contact_bp, url_prefix='/')
    app.register_blueprint(workflow_bp, url_prefix='/')
    app.register_blueprint(flow_bp, url_prefix='/')
    app.register_blueprint(flow_signature_bp, url_prefix='/')
    app.register_blueprint(certificate_bp, url_prefix='/')

    # Importer et enregistrer les Blueprints public API
    from app.routes.publicapi.signature_routes import publicapi_signature_bp
    from app.routes.publicapi.sign_and_assign_routes import publicapi_sign_and_assign_bp
    from app.routes.publicapi.assign_only_routes import publicapi_assign_only_bp
    from app.routes.publicapi.user_routes import publicapi_user_bp
    from app.routes.publicapi.document_routes import publicapi_document_bp
    from app.routes.publicapi.draft_routes import publicapi_draft_bp
    from app.routes.publicapi.email_routes import publicapi_email_bp
    from app.routes.publicapi.metric_routes import publicapi_metric_bp
    from app.routes.publicapi.consent_routes import publicapi_consent_bp
    from app.routes.publicapi.workflow_routes import publicapi_workflow_bp
    from app.routes.publicapi.flow_routes import publicapi_flow_bp
    from app.routes.publicapi.flow_signature_routes import publicapi_flow_signature_bp
    from app.routes.publicapi.certificate_routes import publicapi_certificate_bp
    from app.routes.publicapi.user_registration_routes import publicapi_user_registration_bp

    app.register_blueprint(publicapi_signature_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_sign_and_assign_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_assign_only_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_user_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_document_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_draft_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_email_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_metric_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_consent_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_workflow_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_flow_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_flow_signature_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_certificate_bp, url_prefix='/v3')
    app.register_blueprint(publicapi_user_registration_bp, url_prefix='/v3/auth')


    return app
