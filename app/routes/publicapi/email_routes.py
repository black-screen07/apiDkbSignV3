from flask import Blueprint, request, jsonify
from app.services.email_service import send_email

email_bp = Blueprint('email_bp', __name__)


@email_bp.route('/send-email', methods=['POST'])
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
