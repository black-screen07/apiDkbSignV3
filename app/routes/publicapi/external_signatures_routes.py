"""
Routes pour la gestion des signatures publiques externes.
Permet de stocker et récupérer des images de signature par email pour les signataires externes.
"""

import os
import uuid
from pathlib import Path
from flask import Blueprint, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from PIL import Image
from app.models import db

publicapi_external_signatures_bp = Blueprint('publicapi_external_signatures_bp', __name__)

# Dossier de stockage des signatures publiques externes
EXTERNAL_SIGNATURES_FOLDER = Path("signatures/external_public")
EXTERNAL_SIGNATURES_FOLDER.mkdir(parents=True, exist_ok=True)

# Extensions d'images autorisées
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def sanitize_email_for_folder(email):
    """Convertit un email en nom de dossier sécurisé."""
    # Remplacer les caractères spéciaux par des underscores
    return email.replace('@', '_at_').replace('.', '_').replace('+', '_plus_')

def get_signature_folder_for_email(email):
    """Retourne le chemin du dossier de signature pour un email donné."""
    sanitized_email = sanitize_email_for_folder(email)
    folder_path = EXTERNAL_SIGNATURES_FOLDER / sanitized_email
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path

@publicapi_external_signatures_bp.route('/external-signatures/upload', methods=['POST'])
def upload_external_signature():
    """
    Upload une image de signature pour un signataire externe.
    Route publique sans authentification.
    
    Paramètres:
    - email: Email du signataire externe (obligatoire)
    - signature_image: Fichier image de signature (obligatoire)
    - overwrite: Booléen pour écraser l'image existante (optionnel, défaut: False)
    
    Retourne:
    - success: True/False
    - message: Message de confirmation
    - signature_path: Chemin relatif de l'image stockée
    """
    try:
        current_app.logger.info(f"Upload de signature externe")
        
        # Validation de l'email
        email = request.form.get('email')
        if not email:
            return jsonify({"error": "L'email du signataire est obligatoire."}), 400
        
        # Validation du format email
        if '@' not in email or '.' not in email.split('@')[1]:
            return jsonify({"error": "Format d'email invalide."}), 400
        
        # Validation du fichier
        if 'signature_image' not in request.files:
            return jsonify({"error": "Aucune image de signature fournie."}), 400
        
        signature_file = request.files['signature_image']
        if signature_file.filename == '':
            return jsonify({"error": "Nom de fichier vide."}), 400
        
        if not allowed_file(signature_file.filename):
            return jsonify({
                "error": f"Extension de fichier non autorisée. Extensions autorisées: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Vérifier si on doit écraser l'image existante
        overwrite = request.form.get('overwrite', 'false').lower() == 'true'
        
        # Obtenir le dossier de destination
        signature_folder = get_signature_folder_for_email(email)
        
        # Nom de fichier sécurisé
        original_extension = signature_file.filename.rsplit('.', 1)[1].lower()
        filename = f"signature.{original_extension}"
        file_path = signature_folder / filename
        
        # Vérifier si le fichier existe déjà
        if file_path.exists() and not overwrite:
            return jsonify({
                "error": "Une signature existe déjà pour cet email. Utilisez 'overwrite=true' pour la remplacer."
            }), 409
        
        # Charger et valider l'image
        try:
            signature_file.stream.seek(0)
            img = Image.open(signature_file.stream)
            
            # Convertir en RGBA pour la compatibilité
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Sauvegarder l'image optimisée
            img.save(file_path, format='PNG', optimize=True)
            
            current_app.logger.info(f"✅ Signature sauvegardée pour {email}: {file_path}")
            
            # Chemin relatif pour la réponse (convertir en absolu d'abord)
            relative_path = str(file_path)
            
            return jsonify({
                "success": True,
                "message": f"Signature uploadée avec succès pour {email}.",
                "email": email,
                "signature_path": relative_path,
                "overwritten": file_path.exists() and overwrite
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"❌ Erreur lors du traitement de l'image: {str(e)}")
            return jsonify({"error": f"Erreur lors du traitement de l'image: {str(e)}"}), 400
        
    except Exception as e:
        current_app.logger.error(f"❌ Erreur lors de l'upload: {str(e)}")
        return jsonify({"error": f"Erreur lors de l'upload: {str(e)}"}), 500


@publicapi_external_signatures_bp.route('/external-signatures/get/<email>', methods=['GET'])
def get_external_signature(email):
    """
    Récupère l'image de signature pour un signataire externe.
    Route publique sans authentification.
    
    Paramètres:
    - email: Email du signataire externe (dans l'URL)
    
    Retourne:
    - Le fichier image de signature ou une erreur 404
    """
    try:
        
        # Validation de l'email
        if not email or '@' not in email:
            return jsonify({"error": "Email invalide."}), 400
        
        # Obtenir le dossier de signature
        signature_folder = get_signature_folder_for_email(email)
        
        # Chercher le fichier de signature (peut avoir différentes extensions)
        signature_file = None
        for ext in ALLOWED_EXTENSIONS:
            potential_file = signature_folder / f"signature.{ext}"
            if potential_file.exists():
                signature_file = potential_file
                break
        
        if not signature_file:
            return jsonify({
                "error": f"Aucune signature trouvée pour l'email {email}."
            }), 404
        
        current_app.logger.info(f"📥 Récupération de signature pour {email}: {signature_file}")
        
        # Retourner le fichier image
        return send_file(
            signature_file,
            mimetype=f'image/{signature_file.suffix[1:]}',
            as_attachment=False
        )
        
    except Exception as e:
        current_app.logger.error(f"❌ Erreur lors de la récupération: {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération: {str(e)}"}), 500


@publicapi_external_signatures_bp.route('/external-signatures/check/<email>', methods=['GET'])
def check_external_signature(email):
    """
    Vérifie si une signature existe pour un signataire externe.
    Route publique sans authentification.
    
    Paramètres:
    - email: Email du signataire externe (dans l'URL)
    
    Retourne:
    - exists: True/False
    - signature_path: Chemin relatif si existe
    """
    try:
        
        # Validation de l'email
        if not email or '@' not in email:
            return jsonify({"error": "Email invalide."}), 400
        
        # Obtenir le dossier de signature
        signature_folder = get_signature_folder_for_email(email)
        
        # Chercher le fichier de signature
        signature_file = None
        for ext in ALLOWED_EXTENSIONS:
            potential_file = signature_folder / f"signature.{ext}"
            if potential_file.exists():
                signature_file = potential_file
                break
        
        if signature_file:
            relative_path = str(signature_file)
            return jsonify({
                "exists": True,
                "email": email,
                "signature_path": relative_path
            }), 200
        else:
            return jsonify({
                "exists": False,
                "email": email
            }), 200
        
    except Exception as e:
        current_app.logger.error(f"❌ Erreur lors de la vérification: {str(e)}")
        return jsonify({"error": f"Erreur lors de la vérification: {str(e)}"}), 500


@publicapi_external_signatures_bp.route('/external-signatures/delete/<email>', methods=['DELETE'])
def delete_external_signature(email):
    """
    Supprime l'image de signature pour un signataire externe.
    Route publique sans authentification.
    
    Paramètres:
    - email: Email du signataire externe (dans l'URL)
    
    Retourne:
    - success: True/False
    - message: Message de confirmation
    """
    try:
        current_app.logger.info(f"Suppression de signature externe pour {email}")
        
        # Validation de l'email
        if not email or '@' not in email:
            return jsonify({"error": "Email invalide."}), 400
        
        # Obtenir le dossier de signature
        signature_folder = get_signature_folder_for_email(email)
        
        # Chercher et supprimer le fichier de signature
        deleted = False
        for ext in ALLOWED_EXTENSIONS:
            potential_file = signature_folder / f"signature.{ext}"
            if potential_file.exists():
                potential_file.unlink()
                deleted = True
                current_app.logger.info(f"✅ Signature supprimée: {potential_file}")
        
        if deleted:
            # Supprimer le dossier s'il est vide
            try:
                signature_folder.rmdir()
                current_app.logger.info(f"✅ Dossier supprimé: {signature_folder}")
            except OSError:
                # Le dossier n'est pas vide, on le garde
                pass
            
            return jsonify({
                "success": True,
                "message": f"Signature supprimée avec succès pour {email}."
            }), 200
        else:
            return jsonify({
                "error": f"Aucune signature trouvée pour l'email {email}."
            }), 404
        
    except Exception as e:
        current_app.logger.error(f"❌ Erreur lors de la suppression: {str(e)}")
        return jsonify({"error": f"Erreur lors de la suppression: {str(e)}"}), 500


@publicapi_external_signatures_bp.route('/external-signatures/list', methods=['GET'])
def list_external_signatures():
    """
    Liste toutes les signatures externes stockées.
    Route publique sans authentification.
    
    Retourne:
    - signatures: Liste des emails avec signatures
    - total: Nombre total de signatures
    """
    try:
        
        signatures_list = []
        
        # Parcourir tous les dossiers de signatures
        if EXTERNAL_SIGNATURES_FOLDER.exists():
            for folder in EXTERNAL_SIGNATURES_FOLDER.iterdir():
                if folder.is_dir():
                    # Chercher un fichier de signature dans ce dossier
                    for ext in ALLOWED_EXTENSIONS:
                        signature_file = folder / f"signature.{ext}"
                        if signature_file.exists():
                            # Reconvertir le nom de dossier en email
                            sanitized_email = folder.name
                            # Approximation inverse (pas parfaite mais fonctionnelle)
                            email = sanitized_email.replace('_at_', '@').replace('_plus_', '+')
                            
                            relative_path = str(signature_file)
                            file_size = signature_file.stat().st_size
                            
                            signatures_list.append({
                                "email": email,
                                "signature_path": relative_path,
                                "file_size": file_size,
                                "extension": ext
                            })
                            break
        
        return jsonify({
            "signatures": signatures_list,
            "total": len(signatures_list)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"❌ Erreur lors du listage: {str(e)}")
        return jsonify({"error": f"Erreur lors du listage: {str(e)}"}), 500
