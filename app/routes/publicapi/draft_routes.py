from flask import Blueprint, jsonify, request, url_for, send_from_directory, current_app
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.models import Draft, Company, User, Document
from pathlib import Path
from app import db
import uuid
from PyPDF2 import PdfReader
from PyPDF2.generic import NameObject, TextStringObject, NumberObject
import os
from decimal import Decimal
import logging

publicapi_draft_bp = Blueprint('publicapi_draft_bp', __name__)

DRAFT_FOLDER = Path("documents/drafts")

def human_readable_size(size):
    """
    Convertit la taille en octets en une taille lisible (Ko, Mo, Go).
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def convert_to_json_compatible(data):
    """
    Convertit les objets incompatibles JSON en types compatibles (par exemple, Decimal en float, MetaData en dict).
    """
    if isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, dict):
        return {key: convert_to_json_compatible(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_to_json_compatible(item) for item in data]
    elif isinstance(data, set):
        return list(data)  # Convertir un set en liste
    elif isinstance(data, NameObject) or isinstance(data, TextStringObject) or isinstance(data, NumberObject):
        return str(data)  # Convertir les objets spécifiques PyPDF2 en chaîne
    elif hasattr(data, "keys") and hasattr(data, "items"):  # MetaData ou objets similaires
        return {str(key): convert_to_json_compatible(value) for key, value in data.items()}
    return data

def extract_pdf_metadata(file_path):
    """
    Extrait les métadonnées enrichies d'un fichier PDF.
    """
    try:
        reader = PdfReader(file_path)
        file_size = os.path.getsize(file_path)

        metadata = {
            "file_name": os.path.basename(file_path),
            "file_size_bytes": file_size,
            "file_size_human": human_readable_size(file_size),
            "pdf_version": reader.pdf_header,
            "page_count": len(reader.pages),
            "title": str(reader.metadata.get("/Title", "N/A")),
            "author": str(reader.metadata.get("/Author", "N/A")),
            "producer": str(reader.metadata.get("/Producer", "N/A")),
            "creation_date": str(reader.metadata.get("/CreationDate", "N/A")),
            "modification_date": str(reader.metadata.get("/ModDate", "N/A")),
            "font_info": set(),
            "outline": [],
            "dimensions": [],
            "orientations": [],
        }

        # Parcourir les pages pour extraire des informations
        for page in reader.pages:
            media_box = page.mediabox
            width = float(media_box[2] - media_box[0])
            height = float(media_box[3] - media_box[1])
            orientation = "Landscape" if width > height else "Portrait"

            metadata["dimensions"].append({"width": width, "height": height})
            metadata["orientations"].append(orientation)

            # Gestion sécurisée des polices
            try:
                resources = page.get("/Resources", {})
                if isinstance(resources, dict) and "/Font" in resources:
                    fonts = resources["/Font"]
                    if hasattr(fonts, "keys"):
                        metadata["font_info"].update(str(key) for key in fonts.keys())
            except Exception as font_error:
                logging.warning(f"Erreur lors de l'extraction des polices : {str(font_error)}")

        # Convertir font_info (set) en liste et autres conversions pour JSON
        metadata["font_info"] = list(metadata["font_info"])
        metadata = convert_to_json_compatible(metadata)

        return metadata
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des métadonnées : {str(e)}")
        return {"error": f"Impossible d'extraire les métadonnées : {str(e)}"}

@publicapi_draft_bp.route('/documents/drafts/<path:subfolder>/<filename>', methods=['GET'])
def download_file(subfolder, filename):
    """
    Endpoint pour télécharger un fichier signé en fonction du sous-dossier.
    """
    file_path = DRAFT_FOLDER / subfolder / filename

    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404

    return send_from_directory((DRAFT_FOLDER / subfolder).resolve(), filename)

@publicapi_draft_bp.route('/drafts', methods=['POST'])
@require_api_key
def save_draft():
    """
    Enregistre un brouillon avec des métadonnées enrichies, puis crée également une entrée
    dans la table des documents.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur connecté introuvable."}), 404

        # Charger le fichier PDF
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "Aucun fichier PDF fourni."}), 400

        # Générer un nom de fichier unique
        unique_filename = f"{uuid.uuid4().hex}.pdf"

        # Déterminer le répertoire où sauvegarder le fichier
        if user.account_type == "individual":
            subfolder = f"users/{user.email.replace(' ', '_')}"
        elif user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            return jsonify({"error": "Type d'utilisateur invalide."}), 400

        document_folder = DRAFT_FOLDER / subfolder
        document_folder.mkdir(parents=True, exist_ok=True)

        # Chemin complet du fichier
        file_path = document_folder / unique_filename
        file.save(file_path)

        # Extraire les métadonnées enrichies
        metadata = extract_pdf_metadata(file_path)

        # Vérifier et générer un nom pour le brouillon
        provided_name = request.form.get('name', None)
        draft_name = provided_name if provided_name else f"Draft_{uuid.uuid4().hex[:8]}"

        # Sauvegarder le brouillon en base de données
        draft = Document(
            name=draft_name,
            file_path=str(file_path),
            status="drafts",
            user_id=user.id,
            description=request.form.get('description', ""),
            pdf_metadata=metadata,
        )
        db.session.add(draft)
        db.session.commit()

        # Générer le lien de téléchargement
        download_link = url_for(
            'publicapi_draft_bp.download_file',
            subfolder=subfolder,
            filename=unique_filename,
            _external=True
        )

        return jsonify({
            "message": "Brouillon enregistré avec succès, document créé.",
            "draft": {
                "id": draft.id,
                "name": draft.name,
                "file_path": draft.file_path,
                "status": draft.status,
                "description": draft.description,
                "metadata": draft.pdf_metadata,
                "download_link": download_link,
                "created_at": draft.created_at.strftime('%Y-%m-%d %H:%M:%S') if draft.created_at else None
            }
        }), 201

    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'enregistrement du brouillon et du document : {str(e)}"}), 500

@publicapi_draft_bp.route('/drafts', methods=['GET'])
@require_api_key
def get_all_drafts():
    """
    Récupère la liste de tous les documents avec le statut 'drafts' appartenant à l'utilisateur connecté.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupérer les documents avec le statut 'drafts' pour l'utilisateur
        drafts = Document.query.filter_by(user_id=user.id, status='drafts').all()

        # Construire la liste des brouillons
        drafts_list = []
        for d in drafts:
            # Générer le lien de téléchargement
            if user.account_type == "individual":
                subfolder = f"users/{user.email.replace(' ', '_')}"
            elif user.account_type == "employee" and user.company_id:
                company = Company.query.get(user.company_id)
                subfolder = f"companies/{company.name.replace(' ', '_')}"
            else:
                subfolder = "unknown"

            download_link = url_for(
                'publicapi_draft_bp.download_file',
                subfolder=subfolder,
                filename=Path(d.file_path).name,
                _external=True
            )

            # Ajouter le brouillon à la liste
            drafts_list.append({
                "id": d.id,
                "name": d.name,
                "file_path": d.file_path,
                "status": d.status,
                "description": d.description,
                "metadata": d.pdf_metadata,
                "download_link": download_link,
                "created_at": d.created_at.strftime('%Y-%m-%d %H:%M:%S') if d.created_at else None
            })

        return jsonify(drafts_list), 200

    except Exception as e:
        logging.error(f"Erreur lors de la récupération des brouillons : {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération des brouillons : {str(e)}"}), 500

@publicapi_draft_bp.route('/drafts/<int:id>', methods=['GET'])
@require_api_key
def get_one_draft(id):
    """
    Récupère un brouillon spécifique ayant le statut 'drafts', appartenant à l'utilisateur connecté.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupérer le brouillon avec le statut 'drafts' pour l'utilisateur connecté
        draft = Document.query.filter_by(id=id, user_id=user.id, status='drafts').first()

        if not draft:
            return jsonify({"error": "Brouillon introuvable ou non autorisé."}), 404

        # Générer le lien de téléchargement
        if user.account_type == "individual":
            subfolder = f"users/{user.email.replace(' ', '_')}"
        elif user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            subfolder = "unknown"

        download_link = url_for(
            'publicapi_draft_bp.download_file',
            subfolder=subfolder,
            filename=Path(draft.file_path).name,
            _external=True
        )

        # Préparer les données du brouillon
        draft_data = {
            "id": draft.id,
            "name": draft.name,
            "file_path": draft.file_path,
            "status": draft.status,
            "description": draft.description,
            "metadata": draft.pdf_metadata,
            "download_link": download_link,
            "created_at": draft.created_at.strftime('%Y-%m-%d %H:%M:%S') if draft.created_at else None
        }

        return jsonify(draft_data), 200

    except Exception as e:
        logging.error(f"Erreur lors de la récupération du brouillon : {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération du brouillon : {str(e)}"}), 500

@publicapi_draft_bp.route('/drafts/<int:id>', methods=['DELETE'])
@require_api_key
def delete_draft(id):
    """
    Supprime un brouillon spécifique ayant le statut 'drafts', appartenant à l'utilisateur connecté.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupérer le brouillon avec le statut 'drafts' pour l'utilisateur connecté
        draft = Document.query.filter_by(id=id, user_id=user.id, status='drafts').first()

        if not draft:
            return jsonify({"error": "Brouillon introuvable ou non autorisé."}), 404

        # Supprimer physiquement le fichier si nécessaire
        file_path = Path(draft.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logging.error(f"Erreur lors de la suppression du fichier associé au brouillon : {str(e)}")
                return jsonify({"error": "Impossible de supprimer le fichier associé au brouillon."}), 500

        # Supprimer le brouillon de la base de données
        db.session.delete(draft)
        db.session.commit()

        return jsonify({"message": "Brouillon supprimé avec succès."}), 200

    except Exception as e:
        logging.error(f"Erreur lors de la suppression du brouillon : {str(e)}")
        return jsonify({"error": f"Erreur lors de la suppression du brouillon : {str(e)}"}), 500

@publicapi_draft_bp.route('/drafts/multiple', methods=['POST'])
@require_api_key
def save_multiple_drafts():
    """
    Enregistre plusieurs documents avec des métadonnées enrichies, un batch_id commun,
    et un batch_name pour nommer le dossier. Les documents sont créés dans la table
    documents avec le statut 'drafts'.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur connecté introuvable."}), 404

        # Vérifier la présence de fichiers PDF
        files = request.files.getlist('files')
        if not files:
            return jsonify({"error": "Aucun fichier PDF fourni."}), 400

        # Déterminer le répertoire de sauvegarde
        if user.account_type == "individual":
            subfolder = f"users/{user.email.replace(' ', '_')}"
        elif user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            return jsonify({"error": "Type d'utilisateur invalide."}), 400

        document_folder = DRAFT_FOLDER / subfolder
        document_folder.mkdir(parents=True, exist_ok=True)

        # Générer un batch_id unique pour ce lot de documents
        batch_id = str(uuid.uuid4())

        # Récupérer le batch_name (optionnel) ou générer un nom par défaut
        batch_name = request.form.get('batch_name')
        if not batch_name:
            batch_name = f"Dossier_{batch_id[:8]}"

        # Liste pour stocker les documents créés
        saved_documents = []

        # Traiter chaque fichier PDF
        for file in files:
            # Vérifier que le fichier est un PDF
            if not file.filename.lower().endswith('.pdf'):
                continue

            # Générer un nom de fichier unique
            unique_filename = f"{uuid.uuid4().hex}.pdf"

            # Sauvegarder le fichier
            file_path = document_folder / unique_filename
            file.save(file_path)

            # Extraire les métadonnées enrichies
            metadata = extract_pdf_metadata(file_path)

            # Vérifier et générer un nom pour le document
            provided_name = request.form.get(f'name_{file.filename}', None)
            document_name = provided_name if provided_name else f"Draft_{uuid.uuid4().hex[:8]}"

            # Créer le document dans la table documents
            document = Document(
                name=document_name,
                file_path=str(file_path),
                status="drafts",
                user_id=user.id,
                description=request.form.get(f'description_{file.filename}', ""),
                pdf_metadata=metadata,
                batch_id=batch_id,
                batch_name=batch_name,
                is_workflow=False
            )
            db.session.add(document)
            saved_documents.append((document, unique_filename))

        # Valider toutes les modifications en base de données
        db.session.commit()

        # Construire la réponse après le commit
        documents_response = []
        for document, unique_filename in saved_documents:
            download_link = url_for(
                'publicapi_draft_bp.download_file',
                subfolder=subfolder,
                filename=unique_filename,
                _external=True
            )
            documents_response.append({
                "id": document.id,
                "name": document.name,
                "file_path": document.file_path,
                "status": document.status,
                "description": document.description,
                "metadata": document.pdf_metadata,
                "batch_id": document.batch_id,
                "batch_name": document.batch_name,
                "download_link": download_link,
                "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S') if document.created_at else None
            })

        return jsonify({
            "message": f"{len(documents_response)} document(s) enregistré(s) avec succès.",
            "batch_id": batch_id,
            "batch_name": batch_name,
            "drafts": documents_response
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de l'enregistrement des documents : {str(e)}", exc_info=True)
        return jsonify({"error": f"Erreur lors de l'enregistrement des documents : {str(e)}"}), 500

@publicapi_draft_bp.route('/drafts/batches', methods=['GET'])
@require_api_key
def get_all_batches():
    """
    Récupère tous les dossiers (batches) de documents appartenant à l'utilisateur connecté,
    avec tous les documents associés à chaque dossier.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Déterminer le sous-dossier pour les liens de téléchargement
        if user.account_type == "individual":
            subfolder = f"users/{user.email.replace(' ', '_')}"
        elif user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            subfolder = "unknown"

        # Récupérer tous les documents de l'utilisateur avec statut 'drafts'
        documents = Document.query.filter_by(user_id=user.id, status="drafts").all()

        # Grouper les documents par batch_id
        batches = {}
        for document in documents:
            batch_id = document.batch_id or "no_batch"
            batch_name = document.batch_name or f"Dossier_{batch_id[:8]}" if batch_id != "no_batch" else "Sans dossier"

            if batch_id not in batches:
                batches[batch_id] = {
                    "batch_id": batch_id if batch_id != "no_batch" else None,
                    "batch_name": batch_name,
                    "drafts": []
                }

            download_link = url_for(
                'publicapi_draft_bp.download_file',
                subfolder=subfolder,
                filename=Path(document.file_path).name,
                _external=True
            )

            batches[batch_id]["drafts"].append({
                "id": document.id,
                "name": document.name,
                "file_path": document.file_path,
                "status": document.status,
                "description": document.description,
                "metadata": document.pdf_metadata,
                "download_link": download_link,
                "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S') if document.created_at else None
            })

        batches_list = list(batches.values())

        return jsonify(batches_list), 200

    except Exception as e:
        logging.error(f"Erreur lors de la récupération des dossiers : {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération des dossiers : {str(e)}"}), 500

@publicapi_draft_bp.route('/drafts/batches/<batch_id>', methods=['GET'])
@require_api_key
def get_one_batch(batch_id):
    """
    Récupère un dossier spécifique (par batch_id) appartenant à l'utilisateur connecté,
    avec tous les documents associés.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Déterminer le sous-dossier pour les liens de téléchargement
        if user.account_type == "individual":
            subfolder = f"users/{user.email.replace(' ', '_')}"
        elif user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            subfolder = "unknown"

        # Récupérer les documents du batch pour l'utilisateur connecté
        documents = Document.query.filter_by(user_id=user.id, batch_id=batch_id, status="drafts").all()

        if not documents:
            return jsonify({"error": "Dossier introuvable ou non autorisé."}), 404

        batch_name = documents[0].batch_name or f"Dossier_{batch_id[:8]}"
        batch_data = {
            "batch_id": batch_id,
            "batch_name": batch_name,
            "drafts": []
        }

        for document in documents:
            download_link = url_for(
                'publicapi_draft_bp.download_file',
                subfolder=subfolder,
                filename=Path(document.file_path).name,
                _external=True
            )

            batch_data["drafts"].append({
                "id": document.id,
                "name": document.name,
                "file_path": document.file_path,
                "status": document.status,
                "description": document.description,
                "metadata": document.pdf_metadata,
                "download_link": download_link,
                "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S') if document.created_at else None
            })

        return jsonify(batch_data), 200

    except Exception as e:
        logging.error(f"Erreur lors de la récupération du dossier : {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération du dossier : {str(e)}"}), 500