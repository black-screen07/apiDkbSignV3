from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template, current_app
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.services.email_service import send_email
from app.models import db, DocumentConsent

publicapi_email_bp = Blueprint('publicapi_email_bp', __name__)

OTP_TTL_MINUTES = 5


@publicapi_email_bp.route('/send-email', methods=['POST'])
def send_email_route():
    """
    Envoie un email simple.
    """
    try:
        # Récupérer les données du corps de la requête
        data = request.json
        subject = data.get('subject')
        recipient = data.get('recipient')
        body = data.get('body')
        html = data.get('html', None)  # HTML est facultatif

        # Vérification des champs obligatoires
        if not subject or not recipient or not body:
            return jsonify({"error": "Les champs 'subject', 'recipient' et 'body' sont obligatoires."}), 400

        # Envoi de l'email
        send_email(subject, recipient, body, html)

        return jsonify({"message": f"Email envoyé avec succès à {recipient}."}), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'envoi de l'email : {str(e)}"}), 500


@publicapi_email_bp.route('/send-otp', methods=['POST'])
@require_api_key
def send_otp_email():
    """
    Envoie un code OTP à 6 chiffres à l'adresse email fournie.
    JSON attendu: { "email": "destinataire@exemple.com" }
    L'OTP est persisté dans document_consents et valide 5 minutes.
    """
    try:
        data = request.json or {}
        recipient = (data.get('email') or '').strip().lower()

        if not recipient:
            return jsonify({"error": "Le champ 'email' est obligatoire."}), 400

        consent = DocumentConsent(email=recipient)
        db.session.add(consent)
        db.session.commit()

        try:
            send_email(
                subject="Votre code de vérification",
                recipient=recipient,
                body=f"Votre code de vérification est : {consent.otp_code}\nCe code est valide pendant {OTP_TTL_MINUTES} minutes.",
                html=render_template(
                    "otp_notification.html",
                    otp=consent.otp_code,
                    document_name="vérification"
                )
            )
        except Exception as email_error:
            db.session.delete(consent)
            db.session.commit()
            current_app.logger.error(f"Erreur lors de l'envoi de l'email OTP : {str(email_error)}")
            return jsonify({"error": f"Erreur lors de l'envoi de l'email : {str(email_error)}"}), 500

        return jsonify({"message": f"Code OTP envoyé avec succès à {recipient}."}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de l'envoi de l'OTP : {str(e)}")
        return jsonify({"error": f"Erreur lors de l'envoi de l'OTP : {str(e)}"}), 500


@publicapi_email_bp.route('/verify-otp', methods=['POST'])
@require_api_key
def verify_otp_email():
    """
    Vérifie un code OTP précédemment envoyé à une adresse email.
    JSON attendu: { "email": "destinataire@exemple.com", "otp": "123456" }
    """
    try:
        data = request.json or {}
        recipient = (data.get('email') or '').strip().lower()
        otp_code = (data.get('otp') or '').strip()

        if not recipient or not otp_code:
            return jsonify({"error": "Les champs 'email' et 'otp' sont obligatoires."}), 400

        consent = (
            DocumentConsent.query
            .filter_by(email=recipient, is_verified=False)
            .order_by(DocumentConsent.otp_sent_at.desc())
            .first()
        )

        if not consent or not consent.otp_sent_at:
            return jsonify({"valid": False, "error": "Aucun OTP en attente pour cet email."}), 404

        if consent.otp_sent_at < datetime.utcnow() - timedelta(minutes=OTP_TTL_MINUTES):
            return jsonify({"valid": False, "error": "Code OTP expiré."}), 410

        valid, message = consent.verify_otp(otp_code)
        if not valid:
            return jsonify({"valid": False, "error": message}), 400

        db.session.commit()
        return jsonify({"valid": True, "message": message}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la vérification de l'OTP : {str(e)}")
        return jsonify({"error": f"Erreur lors de la vérification de l'OTP : {str(e)}"}), 500
