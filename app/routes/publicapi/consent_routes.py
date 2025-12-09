import secrets
import uuid
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import User, Document, DocumentConsent
from app.services.email_service import send_email
from flask_jwt_extended import jwt_required, get_jwt_identity

consent_bp = Blueprint('consent_bp', __name__)


@consent_bp.route('/consents', methods=['POST'])
@jwt_required()
def request_consent():
    data = request.json or {}
    document_id = data.get('document_id')
    terms_version = data.get('terms_version')

    if not document_id:
        return jsonify({"error": "document_id est obligatoire."}), 400

    # Récupérer l'utilisateur connecté via son email
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()

    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    document = Document.query.get(document_id)
    if not document:
        return jsonify({"error": "Document introuvable."}), 404

    # Créer le consentement
    consent = DocumentConsent(user_id=user.id, document_id=document.id, terms_version=terms_version)
    db.session.add(consent)
    db.session.commit()

    # Envoyer l'OTP par email
    subject = "Confirmation de consentement"
    body = f"Bonjour {user.name},\n\nVoici votre code de confirmation : {consent.otp_code}\nVeuillez le saisir pour confirmer votre consentement."
    html = f"""
    <p>Bonjour {user.name},</p>
    <p>Veuillez utiliser ce code pour confirmer votre consentement :</p>
    <h2>{consent.otp_code}</h2>
    <p>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
    """
    send_email(subject, user.email, body, html)

    return jsonify({
        "message": "Consentement créé, un OTP a été envoyé.",
        "consent_id": consent.id
    }), 201


@consent_bp.route('/consents/verify', methods=['POST'])
@jwt_required()
def verify_consent():
    """
    Vérifie le code OTP fourni par l'utilisateur pour confirmer son consentement.
    JSON attendu: { "consent_id": ..., "otp_code": "..." }
    """
    data = request.json or {}
    consent_id = data.get('consent_id')
    otp_code = data.get('otp_code')

    if not consent_id or not otp_code:
        return jsonify({"error": "consent_id et otp_code sont obligatoires."}), 400

    # Récupérer l'email de l'utilisateur depuis le token
    current_user_email = get_jwt_identity()
    if not current_user_email:
        return jsonify({"error": "Utilisateur non authentifié."}), 401

    # Récupérer l'utilisateur à partir de son email
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    consent = DocumentConsent.query.get(consent_id)
    if not consent:
        return jsonify({"error": "Consentement introuvable."}), 404

    # Vérifier que le consentement appartient au bon utilisateur
    if consent.user_id != user.id:
        return jsonify({"error": "Vous n'avez pas accès à ce consentement."}), 403

    # Vérifier l'OTP
    valid, message = consent.verify_otp(otp_code)
    if not valid:
        return jsonify({"error": message}), 400

    db.session.commit()  # Sauvegarder les changements (consentement vérifié)

    return jsonify({
        "message": "Consentement confirmé avec succès.",
        "verified_at": consent.verified_at.isoformat() if consent.verified_at else None
    }), 200


@consent_bp.route('/consents/multiple', methods=['POST'])
@jwt_required()
def request_consents():
    """
    Crée un batch de consentements pour plusieurs documents avec un OTP partagé.
    JSON attendu: { "document_ids": [...], "terms_version": "..." }
    """
    try:
        # Récupérer l'email de l'utilisateur depuis le token
        current_user_email = get_jwt_identity()
        if not current_user_email:
            return jsonify({"error": "Utilisateur non authentifié."}), 401

        # Récupérer l'utilisateur à partir de son email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier le corps de la requête
        data = request.json or {}
        document_ids = data.get('document_ids')
        terms_version = data.get('terms_version')

        if not document_ids or not isinstance(document_ids, list) or len(document_ids) == 0:
            return jsonify({"error": "document_ids manquants ou invalides."}), 400
        if not terms_version:
            return jsonify({"error": "terms_version manquant."}), 400

        # Vérifier si les documents existent
        documents = Document.query.filter(Document.id.in_(document_ids)).all()
        if len(documents) != len(document_ids):
            return jsonify({"error": "Certains document_ids sont invalides."}), 400

        # Générer un batch_id unique
        batch_id = str(uuid.uuid4())

        # Générer un OTP unique pour tous les consentements
        otp_code = ''.join(secrets.choice("0123456789") for _ in range(6))

        # Créer un consentement pour chaque document
        consents = []
        for doc_id in document_ids:
            consent = DocumentConsent(
                user_id=user.id,
                document_id=doc_id,
                terms_version=terms_version,
                batch_id=batch_id
            )
            consent.otp_code = otp_code  # Utiliser le même OTP pour tous
            consent.otp_sent_at = datetime.utcnow()
            db.session.add(consent)
            consents.append(consent)

        db.session.commit()

        # Envoyer l'OTP par email
        subject = "Confirmation de consentement"
        body = f"Bonjour {user.name},\n\nVoici votre code de confirmation : {otp_code}\nVeuillez le saisir pour confirmer votre consentement."
        html = f"""
        <p>Bonjour {user.name},</p>
        <p>Veuillez utiliser ce code pour confirmer votre consentement :</p>
        <h2>{otp_code}</h2>
        <p>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.</p>
        """
        send_email(subject, user.email, body, html)

        return jsonify({
            "message": "Consentements créés, un OTP a été envoyé.",
            "batch_id": batch_id,
            "consent_ids": [consent.id for consent in consents]
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création des consentements : {str(e)}")
        return jsonify({"error": f"Erreur lors de la création des consentements : {str(e)}"}), 500


@consent_bp.route('/consents/verify/multiple', methods=['POST'])
@jwt_required()
def verify_consents():
    """
    Vérifie le code OTP fourni par l'utilisateur pour confirmer un batch de consentements.
    JSON attendu: { "batch_id": "...", "otp_code": "..." }
    """
    data = request.json or {}
    batch_id = data.get('batch_id')
    otp_code = data.get('otp_code')

    if not batch_id or not otp_code:
        return jsonify({"error": "batch_id et otp_code sont obligatoires."}), 400

    # Récupérer l'email de l'utilisateur depuis le token
    current_user_email = get_jwt_identity()
    if not current_user_email:
        return jsonify({"error": "Utilisateur non authentifié."}), 401

    # Récupérer l'utilisateur à partir de son email
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    # Récupérer tous les consentements pour ce batch_id
    consents = DocumentConsent.query.filter_by(
        user_id=user.id,
        batch_id=batch_id
    ).all()

    if not consents:
        return jsonify({"error": "Consentements introuvables pour ce batch_id."}), 404

    # Vérifier que tous les consentements appartiennent à l'utilisateur
    for consent in consents:
        if consent.user_id != user.id:
            return jsonify({"error": "Vous n'avez pas accès à certains consentements."}), 403

    # Vérifier si un consentement est déjà vérifié
    if any(consent.is_verified for consent in consents):
        return jsonify({"error": "Certains consentements sont déjà vérifiés."}), 400

    # Vérifier l'OTP sur le premier consentement (tous partagent le même OTP)
    first_consent = consents[0]
    valid, message = first_consent.verify_otp(otp_code)
    if not valid:
        return jsonify({"error": message}), 400

    # Marquer tous les consentements comme vérifiés
    for consent in consents:
        consent.is_verified = True
        consent.verified_at = datetime.utcnow()

    db.session.commit()  # Sauvegarder les changements (consentements vérifiés)

    return jsonify({
        "message": "Consentements confirmés avec succès.",
        "batch_id": batch_id,
        "consent_ids": [consent.id for consent in consents],
        "verified_at": first_consent.verified_at.isoformat() if first_consent.verified_at else None
    }), 200