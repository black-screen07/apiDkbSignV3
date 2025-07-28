from flask import current_app
from flask_mail import Message
from app import mail

def send_email(subject, recipient, body, html=None):
    """
    Envoie un email via Flask-Mail avec des logs détaillés.
    """
    try:
        current_app.logger.info(f"Préparation de l'email pour {recipient}.")
        current_app.logger.debug(f"Sujet : {subject}, Corps : {body[:100]}...")  # Limiter à 100 caractères pour éviter un log trop long

        # Créer le message
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body,
            html=html,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )

        # Log avant l'envoi
        current_app.logger.debug(f"Message créé : {msg.__dict__}")

        # Envoyer l'email
        mail.send(msg)
        current_app.logger.info(f"Email envoyé avec succès à {recipient}.")

    except ConnectionError as conn_err:
        current_app.logger.error(f"Erreur de connexion SMTP : {conn_err}")
        raise conn_err
    except TimeoutError as timeout_err:
        current_app.logger.error(f"Délai d'attente expiré pour l'envoi d'email à {recipient} : {timeout_err}")
        raise timeout_err
    except Exception as e:
        current_app.logger.error(f"Erreur inattendue lors de l'envoi de l'email à {recipient} : {e}")
        current_app.logger.debug("Stack trace complète : ", exc_info=True)
        raise e

def send_email_with_attachment(subject, recipient, body, attachment_filename, attachment_content, content_type, html=None):
    """
    Envoie un email avec une pièce jointe via Flask-Mail.
    
    Args:
        subject (str): Sujet de l'email
        recipient (str): Adresse email du destinataire
        body (str): Corps du message en texte brut
        attachment_filename (str): Nom du fichier à joindre
        attachment_content (bytes): Contenu du fichier à joindre
        content_type (str): Type MIME du fichier (ex: 'application/pdf')
        html (str, optional): Corps du message en HTML. Defaults to None.
    """
    try:
        current_app.logger.info(f"Préparation de l'email avec pièce jointe pour {recipient}.")
        
        # Créer le message
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body,
            html=html,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        
        # Ajouter la pièce jointe
        msg.attach(
            filename=attachment_filename,
            content_type=content_type,
            data=attachment_content
        )

        # Log avant l'envoi
        current_app.logger.debug(f"Message avec pièce jointe créé pour {recipient}")

        # Envoyer l'email
        mail.send(msg)
        current_app.logger.info(f"Email avec pièce jointe envoyé avec succès à {recipient}.")

    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email avec pièce jointe à {recipient} : {e}")
        current_app.logger.debug("Stack trace complète : ", exc_info=True)
        raise e