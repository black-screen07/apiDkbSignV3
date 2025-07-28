from flask import Blueprint, jsonify, request, url_for, current_app, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import Document, Company, User, Signer, db, Contact
from pathlib import Path
from math import ceil
from sqlalchemy.exc import SQLAlchemyError

document_bp = Blueprint('document_bp', __name__)

DRAFTS_FOLDER = Path("documents/drafts")
DRAFTS_FOLDER.mkdir(parents=True, exist_ok=True)

SIGNED_PDF_FOLDER = Path("documents/doc_signed")
SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)


@document_bp.route('/documents/drafts/<path:subfolder>/<filename>', methods=['GET'])
def download_file(subfolder, filename):
    file_path = DRAFTS_FOLDER / subfolder / filename
    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404
    return send_from_directory((DRAFTS_FOLDER / subfolder).resolve(), filename)


@document_bp.route('/documents/doc_signed/<path:subfolder>/<filename>', methods=['GET'])
def download_signed_file(subfolder, filename):
    """
    Endpoint pour télécharger un fichier signé en fonction du sous-dossier.
    """
    file_path = SIGNED_PDF_FOLDER / subfolder / filename
    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404
    return send_from_directory((SIGNED_PDF_FOLDER / subfolder).resolve(), filename)


@document_bp.route('/companies/<int:company_id>/documents', methods=['GET'])
@jwt_required()
def get_all_documents_by_company(company_id):
    """
    Récupère tous les documents signés d'une entreprise spécifique avec pagination.
    """
    try:
        # Vérifier si l'entreprise existe
        company = Company.query.get(company_id)
        if not company:
            return jsonify({"error": "Entreprise introuvable."}), 404

        # Supprimer les espaces du nom de l'entreprise pour le sous-dossier
        subfolder = f"companies/{company.name.replace(' ', '_')}"

        # Récupération des paramètres de pagination
        page = int(request.args.get('page', 1))  # Page actuelle (par défaut : 1)
        per_page = int(request.args.get('per_page', 10))  # Nombre d'éléments par page (par défaut : 10)

        # Récupérer les documents signés par les employés de cette entreprise avec pagination
        query = (
            Document.query.join(User, Document.user_id == User.id)
            .filter(User.company_id == company_id)
            .order_by(Document.created_at.desc())
        )
        total_documents = query.count()
        documents = query.paginate(page=page, per_page=per_page, error_out=False).items

        # Construire les données pour chaque document
        result = [
            {
                "id": doc.id,
                "name": doc.name,
                "status": doc.status,
                "user_id": doc.user_id,
                "created_at": doc.created_at.strftime('%Y-%m-%d %H:%M:%S') if doc.created_at else None,
                "download_link": url_for(
                    'signature_bp.download_file',
                    subfolder=subfolder,
                    filename=Path(doc.file_path).name,
                    _external=True
                )
            }
            for doc in documents
        ]

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_documents / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_documents,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        return jsonify({
            "message": f"Documents de l'entreprise {company.name} récupérés avec succès.",
            "documents": result,
            "metadata": metadata
        }), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des documents : {str(e)}"}), 500


@document_bp.route('/companies/<int:company_id>/documents/<int:document_id>', methods=['GET'])
@jwt_required()
def get_document_by_company_and_id(company_id, document_id):
    """
    Récupère un document signé spécifique pour une entreprise donnée avec son lien de téléchargement.
    """
    try:
        # Vérifier si l'entreprise existe
        company = Company.query.get(company_id)
        if not company:
            return jsonify({"error": "Entreprise introuvable."}), 404

        # Supprimer les espaces du nom de l'entreprise pour le sous-dossier
        subfolder = f"companies/{company.name.replace(' ', '_')}"

        # Vérifier si le document existe pour cette entreprise
        document = (
            Document.query.join(User, Document.user_id == User.id)
            .filter(User.company_id == company_id, Document.id == document_id)
            .order_by(Document.created_at.desc())
            .first()
        )
        if not document:
            return jsonify({"error": "Document introuvable pour cette entreprise."}), 404

        # Extraire le nom du fichier à partir de son chemin
        filename = Path(document.file_path).name

        document_data = {
            "id": document.id,
            "name": document.name,
            "status": document.status,
            "user_id": document.user_id,
            "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S') if document.created_at else None,
            "download_link": url_for(
                'signature_bp.download_file',
                subfolder=subfolder,
                filename=filename,
                _external=True
            )
        }
        return jsonify({
            "message": f"Document {document.name} récupéré avec succès.",
            "document": document_data
        }), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération du document : {str(e)}"}), 500


@document_bp.route('/signed-documents', methods=['GET'])
@jwt_required()
def get_signed_documents():
    """
    Récupère tous les documents signés par l'utilisateur connecté avec pagination.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupération des paramètres de pagination
        page = int(request.args.get('page', 1))  # Page actuelle (par défaut : 1)
        per_page = int(request.args.get('per_page', 10))  # Nombre d'éléments par page (par défaut : 10)

        # Requête pour obtenir tous les documents signés
        query = (
            db.session.query(Document)
            .distinct()
            .outerjoin(Signer, Signer.document_id == Document.id)
            .filter(
                db.or_(
                    # Cas 1: Document signé via la table Signer
                    db.and_(
                        Signer.signer_id == user.id,
                        Signer.status == "signed"
                    ),
                    # Cas 2: Document signé directement dans la table Document
                    db.and_(
                        Document.user_id == user.id,
                        Document.status == "signed"
                    ),
                    # Cas 3: Document avec un signataire "prepared"
                    db.and_(
                        Signer.signer_id == user.id,
                        Signer.status == "prepared"
                    )
                )
            )
            .order_by(Document.created_at.desc())
        )

        # Appliquer la pagination
        total_documents = query.count()
        documents = query.paginate(page=page, per_page=per_page, error_out=False).items

        # Préparer la réponse
        result = []
        for document in documents:
            # Déterminer le sous-dossier pour les documents
            if document.user.account_type == "individual":
                subfolder = f"users/{document.user.email}"
            elif document.user.account_type == "employee" and document.user.company_id:
                company = Company.query.get(document.user.company_id)
                if not company:
                    continue
                subfolder = f"companies/{company.name.replace(' ', '_')}"
            else:
                continue

            # Extraire uniquement le nom du fichier depuis le chemin pour l'URL
            filename = Path(document.file_path).name

            # Récupérer les informations des signataires pour ce document
            signers = Signer.query.filter_by(document_id=document.id).all()
            signers_info = []

            for signer in signers:
                signer_data = {
                    "signer_id": signer.signer_id,
                    "account_type": signer.account_type,
                    "status": signer.status,
                    "email_status": signer.email_status,
                    "role": signer.role,
                    "signed_at": signer.signed_at.isoformat() if signer.signed_at else None,
                    "uuid": signer.uuid,
                    "positions": signer.positions,
                    "priority": signer.priority,
                    "email_sent": signer.email_sent,
                    "reminder_sent": signer.reminder_sent,
                    "notes": signer.notes,
                    "is_verified": signer.is_verified,
                    "verified_at": signer.verified_at.isoformat() if signer.verified_at else None,
                    "created_at": signer.created_at.isoformat(),
                    "updated_at": signer.updated_at.isoformat()
                }

                # Récupérer les informations du signataire selon son type
                if signer.account_type in ["individual", "employee"]:
                    # Récupérer depuis la table User
                    user_info = User.query.get(signer.signer_id)
                    if user_info:
                        signer_data["user_info"] = {
                            "name": user_info.name,
                            "sub_name": user_info.sub_name,
                            "email": user_info.email,
                            "phone": user_info.phone,
                            "address": user_info.address,
                            "city": user_info.city,
                            "country": user_info.country,
                            "company_id": user_info.company_id,
                            "account_type": user_info.account_type
                        }
                else:
                    # Récupérer depuis la table Contact
                    contact_info = Contact.query.get(signer.signer_id)
                    if contact_info:
                        signer_data["user_info"] = {
                            "name": contact_info.name,
                            "email": contact_info.email,
                            "phone": contact_info.phone,
                            "address": contact_info.address,
                            "company_name": contact_info.company_name,
                            "notes": contact_info.notes
                        }

                signers_info.append(signer_data)

            # Vérifier si au moins un signataire a signé le document
            has_signed = Signer.query.filter_by(
                document_id=document.id,
                status="signed"
            ).first() is not None

            # Générer l'URL du document en fonction de l'état des signatures
            document_url = None
            if document.status == "signed":  # Cas où le document est signé directement
                document_url = url_for(
                    'document_bp.download_signed_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )
            elif has_signed:  # Cas où au moins un signataire a signé
                document_url = url_for(
                    'document_bp.download_signed_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )
            else:  # Cas où le document n'est pas encore signé
                document_url = url_for(
                    'document_bp.download_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )

            doc_data = {
                "document_id": document.id,
                "name": document.name,
                "description": document.description,
                "file_path": document.file_path,
                "document_url": document_url,
                "status": document.status,
                "pdf_metadata": document.pdf_metadata,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
                "signers": signers_info
            }
            result.append(doc_data)

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_documents / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_documents,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        return jsonify({
            "message": "Documents signés récupérés avec succès.",
            "documents": result,
            "metadata": metadata
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des documents : {str(e)}"}), 500


@document_bp.route('/signed-documents/<int:document_id>', methods=['GET'])
@jwt_required()
def get_user_document_by_id(document_id):
    """
    Récupère un document spécifique signé par l'utilisateur connecté avec son lien de téléchargement.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupérer le document signé
        document = (
            db.session.query(Document)
            .outerjoin(Signer, Signer.document_id == Document.id)
            .filter(
                Document.id == document_id,
                db.or_(
                    # Cas 1: Document signé via la table Signer
                    db.and_(
                        Signer.signer_id == user.id,
                        Signer.status == "signed"
                    ),
                    # Cas 2: Document signé directement dans la table Document
                    db.and_(
                        Document.user_id == user.id,
                        Document.status == "signed"
                    )
                )
            )
            .order_by(Document.created_at.desc())
            .first()
        )

        if not document:
            return jsonify({"error": "Document non trouvé ou non autorisé"}), 404

        # Déterminer le sous-dossier pour les documents
        if document.user.account_type == "individual":
            subfolder = f"users/{document.user.email}"
        elif document.user.account_type == "employee" and document.user.company_id:
            company = Company.query.get(document.user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            return jsonify({"error": "Type d'utilisateur invalide."}), 400

        # Extraire uniquement le nom du fichier depuis le chemin pour l'URL
        filename = Path(document.file_path).name

        # Récupérer les informations des signataires pour ce document
        signers = Signer.query.filter_by(document_id=document.id).all()
        signers_info = []

        for signer in signers:
            signer_data = {
                "signer_id": signer.signer_id,
                "account_type": signer.account_type,
                "status": signer.status,
                "email_status": signer.email_status,
                "role": signer.role,
                "signed_at": signer.signed_at.isoformat() if signer.signed_at else None,
                "uuid": signer.uuid,
                "positions": signer.positions,
                "priority": signer.priority,
                "email_sent": signer.email_sent,
                "reminder_sent": signer.reminder_sent,
                "notes": signer.notes,
                "is_verified": signer.is_verified,
                "verified_at": signer.verified_at.isoformat() if signer.verified_at else None,
                "created_at": signer.created_at.isoformat(),
                "updated_at": signer.updated_at.isoformat()
            }

            # Récupérer les informations du signataire selon son type
            if signer.account_type in ["individual", "employee"]:
                # Récupérer depuis la table User
                user_info = User.query.get(signer.signer_id)
                if user_info:
                    signer_data["user_info"] = {
                        "name": user_info.name,
                        "sub_name": user_info.sub_name,
                        "email": user_info.email,
                        "phone": user_info.phone,
                        "address": user_info.address,
                        "city": user_info.city,
                        "country": user_info.country,
                        "company_id": user_info.company_id,
                        "account_type": user_info.account_type
                    }
            else:
                # Récupérer depuis la table Contact
                contact_info = Contact.query.get(signer.signer_id)
                if contact_info:
                    signer_data["user_info"] = {
                        "name": contact_info.name,
                        "email": contact_info.email,
                        "phone": contact_info.phone,
                        "address": contact_info.address,
                        "company_name": contact_info.company_name,
                        "notes": contact_info.notes
                    }

            signers_info.append(signer_data)

        # Vérifier si au moins un signataire a signé le document
        has_signed = Signer.query.filter_by(
            document_id=document.id,
            status="signed"
        ).first() is not None

        # Générer l'URL du document en fonction de l'état des signatures
        document_url = None
        if document.status == "signed":  # Cas où le document est signé directement
            document_url = url_for(
                'document_bp.download_signed_file',
                subfolder=document.file_path.rsplit('/', 1)[0],
                filename=document.file_path.rsplit('/', 1)[-1],
                _external=True
            )
        elif has_signed:  # Cas où au moins un signataire a signé
            document_url = url_for(
                'document_bp.download_signed_file',
                subfolder=document.file_path.rsplit('/', 1)[0],
                filename=document.file_path.rsplit('/', 1)[-1],
                _external=True
            )
        else:  # Cas où le document n'est pas encore signé
            document_url = url_for(
                'document_bp.download_file',
                subfolder=document.file_path.rsplit('/', 1)[0],
                filename=document.file_path.rsplit('/', 1)[-1],
                _external=True
            )

        # Format des données du document
        document_data = {
            "document_id": document.id,
            "name": document.name,
            "description": document.description,
            "file_path": document.file_path,
            "document_url": document_url,
            "status": document.status,
            "pdf_metadata": document.pdf_metadata,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat(),
            "signers": signers_info
        }

        return jsonify({"document": document_data}), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération du document : {str(e)}"}), 500


@document_bp.route('/pending-documents', methods=['GET'])
@jwt_required()
def list_user_pending_documents():
    try:
        # Récupérer l'ID de l'utilisateur connecté depuis le JWT
        user_email = get_jwt_identity()
        user = User.query.filter_by(email=user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupération des paramètres de pagination
        page = int(request.args.get('page', 1))  # Page actuelle (par défaut : 1)
        per_page = int(request.args.get('per_page', 10))  # Nombre d'éléments par page (par défaut : 10)

        # Récupérer tous les documents où l'utilisateur est signataire avec un statut "pending"
        query = (
            db.session.query(Document)
            .join(Signer, Signer.document_id == Document.id)
            .filter(Signer.signer_id == user.id, Signer.status == "pending")
            .order_by(Document.created_at.desc())  # Tri par date
        )

        # Appliquer la pagination
        total_documents = query.count()
        documents = query.paginate(page=page, per_page=per_page, error_out=False).items

        if not documents:
            # Calcul des métadonnées de pagination même si pas de documents
            total_pages = ceil(total_documents / per_page)
            metadata = {
                "current_page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "total_items": total_documents,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }
            return jsonify({
                "message": "Aucun document en attente de signature pour cet utilisateur.",
                "documents": [],
                "metadata": metadata
            }), 200

        # Format des données de réponse
        result = []
        for document in documents:
            # Récupérer les informations des signataires pour ce document
            signers = Signer.query.filter_by(document_id=document.id).all()
            signers_info = []

            for signer in signers:
                signer_data = {
                    "signer_id": signer.signer_id,
                    "account_type": signer.account_type,
                    "status": signer.status,
                    "email_status": signer.email_status,
                    "role": signer.role,
                    "signed_at": signer.signed_at.isoformat() if signer.signed_at else None,
                    "uuid": signer.uuid,
                    "positions": signer.positions,
                    "priority": signer.priority,
                    "email_sent": signer.email_sent,
                    "reminder_sent": signer.reminder_sent,
                    "notes": signer.notes,
                    "is_verified": signer.is_verified,
                    "verified_at": signer.verified_at.isoformat() if signer.verified_at else None,
                    "created_at": signer.created_at.isoformat(),
                    "updated_at": signer.updated_at.isoformat()
                }

                # Récupérer les informations du signataire selon son type
                if signer.account_type in ["individual", "employee"]:
                    # Récupérer depuis la table User
                    user_info = User.query.get(signer.signer_id)
                    if user_info:
                        signer_data["user_info"] = {
                            "name": user_info.name,
                            "sub_name": user_info.sub_name,
                            "email": user_info.email,
                            "phone": user_info.phone,
                            "address": user_info.address,
                            "city": user_info.city,
                            "country": user_info.country,
                            "company_id": user_info.company_id,
                            "account_type": user_info.account_type
                        }
                else:
                    # Récupérer depuis la table Contact
                    contact_info = Contact.query.get(signer.signer_id)
                    if contact_info:
                        signer_data["user_info"] = {
                            "name": contact_info.name,
                            "email": contact_info.email,
                            "phone": contact_info.phone,
                            "address": contact_info.address,
                            "company_name": contact_info.company_name,
                            "notes": contact_info.notes
                        }

                signers_info.append(signer_data)

            # Vérifier si au moins un signataire a signé le document
            has_signed = Signer.query.filter_by(
                document_id=document.id,
                status="signed"
            ).first() is not None

            # Générer l'URL du document en fonction de l'état des signatures
            document_url = None
            if document.status == "signed":  # Cas où le document est signé directement
                document_url = url_for(
                    'document_bp.download_signed_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )
            elif has_signed:  # Cas où au moins un signataire a signé
                document_url = url_for(
                    'document_bp.download_signed_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )
            else:  # Cas où le document n'est pas encore signé
                document_url = url_for(
                    'document_bp.download_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )

            result.append({
                "document_id": document.id,
                "name": document.name,
                "description": document.description,
                "file_path": document.file_path,
                "document_url": document_url,
                "status": document.status,
                "pdf_metadata": document.pdf_metadata,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
                "signers": signers_info
            })

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_documents / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_documents,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        return jsonify({
            "message": "Documents en attente récupérés avec succès.",
            "documents": result,
            "metadata": metadata
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des documents en attente : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@document_bp.route('/pending-documents/<int:document_id>', methods=['GET'])
@jwt_required()
def get_user_pending_document(document_id):
    try:
        # Récupérer l'utilisateur connecté depuis le JWT
        user_email = get_jwt_identity()
        user = User.query.filter_by(email=user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier si le document est associé à l'utilisateur et en attente de signature
        document = (
            db.session.query(Document)
            .join(Signer, Signer.document_id == Document.id)
            .filter(Signer.signer_id == user.id, Signer.status == "pending", Document.id == document_id)
            .order_by(Document.created_at.desc())
            .first()
        )

        if not document:
            return jsonify({"message": "Aucun document en attente de signature trouvé pour cet utilisateur."}), 404

        # Déterminer le sous-dossier pour les documents
        if document.user.account_type == "individual":
            subfolder = f"users/{document.user.email}"
        elif document.user.account_type == "employee" and document.user.company_id:
            company = Company.query.get(document.user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            return jsonify({"error": "Type d'utilisateur invalide."}), 400

        # Extraire uniquement le nom du fichier depuis le chemin pour l'URL
        filename = Path(document.file_path).name

        # Vérifier si au moins un signataire a signé le document
        has_signed = Signer.query.filter_by(
            document_id=document.id,
            status="signed"
        ).first() is not None

        # Générer l'URL du document en fonction de l'état des signatures
        document_url = None
        if document.status == "signed":  # Cas où le document est signé directement
            document_url = url_for(
                'document_bp.download_signed_file',
                subfolder=document.file_path.rsplit('/', 1)[0],
                filename=document.file_path.rsplit('/', 1)[-1],
                _external=True
            )
        elif has_signed:  # Cas où au moins un signataire a signé
            document_url = url_for(
                'document_bp.download_signed_file',
                subfolder=document.file_path.rsplit('/', 1)[0],
                filename=document.file_path.rsplit('/', 1)[-1],
                _external=True
            )
        else:  # Cas où le document n'est pas encore signé
            document_url = url_for(
                'document_bp.download_file',
                subfolder=document.file_path.rsplit('/', 1)[0],
                filename=document.file_path.rsplit('/', 1)[-1],
                _external=True
            )

        # Récupérer les informations des signataires pour ce document
        signers = Signer.query.filter_by(document_id=document.id).all()
        signers_info = []

        for signer in signers:
            signer_data = {
                "signer_id": signer.signer_id,
                "account_type": signer.account_type,
                "status": signer.status,
                "email_status": signer.email_status,
                "role": signer.role,
                "signed_at": signer.signed_at.isoformat() if signer.signed_at else None,
                "uuid": signer.uuid,
                "positions": signer.positions,
                "priority": signer.priority,
                "email_sent": signer.email_sent,
                "reminder_sent": signer.reminder_sent,
                "notes": signer.notes,
                "is_verified": signer.is_verified,
                "verified_at": signer.verified_at.isoformat() if signer.verified_at else None,
                "created_at": signer.created_at.isoformat(),
                "updated_at": signer.updated_at.isoformat()
            }

            # Récupérer les informations du signataire selon son type
            if signer.account_type in ["individual", "employee"]:
                # Récupérer depuis la table User
                user_info = User.query.get(signer.signer_id)
                if user_info:
                    signer_data["user_info"] = {
                        "name": user_info.name,
                        "sub_name": user_info.sub_name,
                        "email": user_info.email,
                        "phone": user_info.phone,
                        "address": user_info.address,
                        "city": user_info.city,
                        "country": user_info.country,
                        "company_id": user_info.company_id,
                        "account_type": user_info.account_type
                    }
            else:
                # Récupérer depuis la table Contact
                contact_info = Contact.query.get(signer.signer_id)
                if contact_info:
                    signer_data["user_info"] = {
                        "name": contact_info.name,
                        "email": contact_info.email,
                        "phone": contact_info.phone,
                        "address": contact_info.address,
                        "company_name": contact_info.company_name,
                        "notes": contact_info.notes
                    }

            signers_info.append(signer_data)

        # Format des données du document
        document_data = {
            "document_id": document.id,
            "name": document.name,
            "description": document.description,
            "file_path": document.file_path,
            "document_url": document_url,
            "status": document.status,
            "pdf_metadata": document.pdf_metadata,
            "created_at": document.created_at.isoformat(),
            "updated_at": document.updated_at.isoformat(),
            "signers": signers_info
        }

        return jsonify({"document": document_data}), 200

    except SQLAlchemyError as db_error:
        return jsonify({"error": "Erreur de base de données."}), 500

    except Exception as e:
        return jsonify({"error": f"Erreur: {str(e)}"}), 500


@document_bp.route('/documents/sign/<path:file_path>', methods=['GET'])
@jwt_required()
def get_document_to_sign(file_path):
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Construire le chemin complet du fichier
        full_path = Path(file_path)
        if not full_path.exists():
            return jsonify({"error": "Document non trouvé"}), 404

        # Vérifier que l'utilisateur a accès au document
        document = Document.query.filter_by(file_path=file_path).first()
        if not document:
            return jsonify({"error": "Document non trouvé dans la base de données"}), 404

        if document.user_id != user.id and not Signer.query.filter_by(document_id=document.id, signer_id=user.id).first():
            return jsonify({"error": "Accès non autorisé"}), 403

        # Retourner le fichier
        return send_from_directory(
            str(full_path.parent),
            full_path.name,
            as_attachment=False
        )

    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'accès au document : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@document_bp.route('/doc-to-sign/', methods=['GET'])
def get_document_url():
    try:
        # Récupérer l'UUID depuis les paramètres de requête
        uuid = request.args.get('uuid')
        if not uuid:
            return jsonify({"error": "UUID manquant"}), 400

        current_app.logger.info(f"UUID reçu : {uuid}")  # Log pour le débogage

        # Trouver le signataire avec cet UUID
        current_signer = (
            Signer.query
            .join(Document, Document.id == Signer.document_id)
            .filter(Signer.uuid == uuid)
            .order_by(Document.created_at.desc())
            .first()
        )

        if not current_signer:
            return jsonify({"error": "Signataire non trouvé"}), 404

        # Vérifier si le signataire est en attente
        if current_signer.status != 'pending':
            return jsonify({"error": "Le signataire n'est pas en attente"}), 403

        # Récupérer le document associé
        document = Document.query.get(current_signer.document_id)
        if not document:
            return jsonify({"error": "Document non trouvé"}), 404

        # Récupérer tous les signataires pour ce document
        all_signers = Signer.query.filter_by(document_id=document.id).all()
        
        # Déterminer quelle fonction de téléchargement utiliser
        use_signed_download = False
        has_prepared = False
        for signer in all_signers:
            if signer.status == 'signed':
                use_signed_download = True
                break
            elif signer.status == 'prepared':
                has_prepared = True

        # Construire l'URL de téléchargement
        if document.user_id:
            user = User.query.get(document.user_id)
            if user.account_type == "employee" and user.company_id:
                company = Company.query.get(user.company_id)
                subfolder = f"companies/{company.name.replace(' ', '_')}"
            else:
                subfolder = f"users/{user.email}"
        else:
            return jsonify({"error": "Propriétaire du document non trouvé"}), 404

        filename = Path(document.file_path).name
        
        # Choisir la bonne fonction de téléchargement
        if use_signed_download:
            download_endpoint = 'document_bp.download_signed_file'
        else:
            download_endpoint = 'document_bp.download_file'

        download_link = url_for(
            download_endpoint,
            subfolder=subfolder,
            filename=filename,
            _external=True
        )

        # Préparer les informations des signataires
        signers_info = []
        for signer in all_signers:
            # Récupérer le nom, l'email et le sub_name du signataire selon son type
            signer_name = None
            signer_email = None
            signer_sub_name = None
            if signer.account_type in ["individual", "employee"]:
                user_info = User.query.get(signer.signer_id)
                if user_info:
                    signer_name = user_info.name
                    signer_email = user_info.email
                    signer_sub_name = user_info.sub_name
            elif signer.account_type == "contact":
                contact_info = Contact.query.get(signer.signer_id)
                if contact_info:
                    signer_name = contact_info.name
                    signer_email = contact_info.email
                    signer_sub_name = ""

            signer_info = {
                "id": signer.id,
                "signer_id": signer.signer_id,
                "account_type": signer.account_type,
                "status": signer.status,
                "priority": signer.priority,
                "uuid": signer.uuid,
                "name": signer_name,
                "email": signer_email,
                "sub_name": signer_sub_name,
                "signed_at": signer.signed_at.strftime('%Y-%m-%d %H:%M:%S') if signer.signed_at else None,
                "created_at": signer.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "positions": signer.positions
            }

            # Ajouter les informations additionnelles du signataire selon son type
            if signer.account_type in ["individual", "employee"]:
                user_info = User.query.get(signer.signer_id)
                if user_info:
                    signer_info.update({
                        "phone": user_info.phone
                    })
            elif signer.account_type == "contact":
                contact_info = Contact.query.get(signer.signer_id)
                if contact_info:
                    signer_info.update({
                        "phone": contact_info.phone
                    })

            signers_info.append(signer_info)

        # Préparer la réponse dans le même format que les autres routes
        document_data = {
            "id": document.id,
            "name": document.name,
            "description": document.description,
            "status": document.status,
            "pdf_metadata": document.pdf_metadata,
            "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "updated_at": document.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            "download_link": download_link,
            "signers": signers_info
        }

        return jsonify({
            "message": "Document trouvé avec succès",
            "document": document_data
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération du document : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500
