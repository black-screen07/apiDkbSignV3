from flask import Blueprint, request, jsonify, render_template, url_for, send_from_directory, current_app
from flask_jwt_extended import jwt_required
from pathlib import Path
import uuid
from datetime import datetime
import random
import string
from app.models import Document, Signer, Contact, User, db, UrgencyEnum
from app.services.email_service import send_email

# On importe ici les fonctions utilitaires partagées
from app.utils.signature_utils import (
    get_authenticated_user,
    get_user_company,
    load_pdf,
    apply_optional_texts,
    apply_qr_codes,
)

assign_only_bp = Blueprint('assign_only_bp', __name__)

# Dossiers pour les documents
DRAFTS_FOLDER = Path("documents/drafts")
DRAFTS_FOLDER.mkdir(parents=True, exist_ok=True)
SIGNED_PDF_FOLDER = Path("documents/doc_signed")
SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)


def update_assign_document(document, params, relative_file_path):
    """Version spécifique de update_existing_document pour assign_only qui ne change pas le statut"""
    document.name = params.get("name", document.name)
    document.file_path = relative_file_path
    document.status = "pending"  # Toujours pending pour assign_only
    updated_at = params.get("updated_at")
    if updated_at:
        document.updated_at = updated_at


def create_assign_document(user, params, relative_file_path):
    """Version spécifique de create_new_document pour assign_only qui met le statut à pending"""
    new_doc = Document(
        name=params.get("name", f"Document_{uuid.uuid4().hex}"),
        file_path=relative_file_path,
        status="pending",  # Toujours pending pour assign_only
        user_id=user.id
    )
    description = params.get("description")
    if description:
        new_doc.description = description
    db.session.add(new_doc)
    return new_doc


@assign_only_bp.route('/assign-only', methods=['POST'])
@jwt_required()
def assign_only():
    try:
        # 1) Récupérer l'utilisateur connecté et son entreprise via les fonctions utilitaires
        user = get_authenticated_user()
        company = get_user_company(user)

        # 2) Récupérer les données du formulaire
        data = request.get_json()
        file_url = data.get('file_url')
        params = data.get('params', {})
        document_id = params.get('document_id')

        if not file_url:
            return jsonify({"error": "URL du fichier requise"}), 400

        # Récupérer les données des signataires
        signers_data = params.get('signers', [])
        if not signers_data:
            return jsonify({"error": "Au moins un signataire est requis"}), 400

        # 3) Charger ou créer le document existant
        if document_id:
            document = Document.query.get(document_id)
            if not document:
                return jsonify({"error": "Document non trouvé"}), 404
            if document.user_id != user.id:
                return jsonify({"error": "Vous n'avez pas les droits pour modifier ce document"}), 403

        # 4) Charger le PDF en utilisant la fonction utilitaire
        try:
            input_pdf = load_pdf(None, file_url)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # 5) Créer la structure de dossiers et sauvegarder le fichier original
        base_path = Path(current_app.config.get('UPLOAD_FOLDER', "documents"))
        drafts_path = base_path / "drafts"
        if user.account_type == "employee" and company:
            company_folder = "companies/" + company.name.replace(' ', '_') + "/users/" + user.email
            user_path = drafts_path / "companies" / company.name.replace(' ', '_') / "users" / user.email
        else:
            company_folder = "users/" + user.email
            user_path = drafts_path / "users" / user.email

        user_path.mkdir(parents=True, exist_ok=True)
        original_filename = f"{uuid.uuid4().hex}.pdf"
        file_path = user_path / original_filename
        with open(file_path, 'wb') as f:
            f.write(input_pdf.getvalue())
        relative_file_path = str(file_path.relative_to(base_path)).replace('\\', '/')

        # 6) Mettre à jour ou créer le document en base de données
        if document_id:
            update_assign_document(document, params, relative_file_path)  # Utiliser notre version spécifique
        else:
            document = create_assign_document(user, params, relative_file_path)  # Utiliser notre version spécifique
            db.session.flush()
            document_id = document.id

        # 7) Ajouter l'initiateur comme premier signataire avec priorité 0
        initiator_signer = Signer(
            document_id=document_id,
            signer_id=user.id,
            account_type="individual" if user.account_type == "individual" else "employee",
            status="prepared",
            positions=params.get('initiator_positions', []),
            qr_positions=params.get('qrcodes', []),
            priority=0,
            notes="Initiateur du document",
            uuid=str(uuid.uuid4()),
            is_verified=True
        )
        db.session.add(initiator_signer)
        db.session.flush()

        # 8) Ajouter les autres signataires et envoyer les emails
        priorities = [s.get('priority', 1) for s in params.get('signers', [])]
        min_priority = min(priorities) if priorities else 1
        top_priority_signers = [s for s in params.get('signers', []) if s.get('priority', 1) == min_priority]

        for signer_data in params.get('signers', []):
            otp = ''.join(random.choices(string.digits, k=6))
            if signer_data.get('account_type') == "external":
                signer_info = Contact.query.get(signer_data.get('signer_id'))
                if not signer_info:
                    current_app.logger.error(f"Contact externe {signer_data.get('signer_id')} introuvable")
                    continue
                name = signer_info.name
                email = signer_info.email
            else:
                signer_info = User.query.get(signer_data.get('signer_id'))
                if not signer_info:
                    current_app.logger.error(f"Utilisateur {signer_data.get('signer_id')} introuvable")
                    continue
                name = getattr(signer_info, 'name', signer_info.email)
                email = signer_info.email

            deadline = None
            deadline_str = ""
            if signer_data.get('deadline'):
                try:
                    deadline = datetime.fromisoformat(signer_data.get('deadline').replace('Z', '+00:00'))
                    deadline_str = deadline.strftime("%d/%m/%Y à %H:%M")
                except (ValueError, TypeError):
                    current_app.logger.warning(f"Format de date d'échéance invalide pour le signataire {name}")

            urgency = signer_data.get('urgency', 'normal')
            if urgency not in [UrgencyEnum.NORMAL, UrgencyEnum.URGENT, UrgencyEnum.TRES_URGENT]:
                urgency = UrgencyEnum.NORMAL

            new_signer = Signer(
                document_id=document_id,
                signer_id=signer_data.get('signer_id'),
                account_type=signer_data.get('account_type'),
                status="pending",
                positions=signer_data.get('positions', []),
                priority=signer_data.get('priority', 1),
                notes=signer_data.get('notes'),
                otp_code=otp,
                otp_sent_at=datetime.utcnow(),
                is_verified=False,
                uuid=str(uuid.uuid4()),
                deadline=deadline,
                urgency=urgency
            )
            db.session.add(new_signer)

            try:
                document_in_db = Document.query.get(document_id)
                if not document_in_db:
                    current_app.logger.error(f"Document {document_id} introuvable")
                    continue

                urgency_message = ""
                if urgency == UrgencyEnum.URGENT:
                    urgency_message = "\n⚠️ Ce document est marqué comme URGENT."
                elif urgency == UrgencyEnum.TRES_URGENT:
                    urgency_message = "\n⚠️ Ce document est marqué comme TRÈS URGENT !"
                deadline_message = f"\nDate limite de signature : {deadline_str}" if deadline else ""

                # CORRECTION: Les contacts externes doivent TOUJOURS recevoir le lien direct avec OTP
                # car ils n'ont pas de compte pour se connecter
                if signer_data.get('account_type') == "external" or not priorities or signer_data in top_priority_signers:
                    sign_url = f"https://dkb-sign-ui.vercel.app/signed-docs/verify?uuid={new_signer.uuid}"
                    subject = "Veuillez signer le document"
                    if urgency != UrgencyEnum.NORMAL:
                        subject = f"[{urgency.upper()}] {subject}"
                    body = (
                        f"Bonjour {name},\n\n"
                        f"Veuillez cliquer sur le lien suivant pour signer le document : {sign_url}\n\n"
                        f"Votre code OTP : {otp}{urgency_message}{deadline_message}\n\n"
                        f"Cordialement,\nL'équipe DKB-Sign"
                    )
                    html = render_template(
                        'sign_document_email.html',
                        name=name,
                        sign_url=sign_url,
                        document_name=document_in_db.name,
                        otp_code=otp,
                        urgency=urgency,
                        deadline=deadline_str if deadline else None,
                        current_year=datetime.now().year
                    )
                else:
                    # Notification simple (UNIQUEMENT pour les utilisateurs internes avec compte)
                    subject = "Notification de demande de signature"
                    if urgency != UrgencyEnum.NORMAL:
                        subject = f"[{urgency.upper()}] {subject}"
                    body = (
                        f"Bonjour {name},\n\n"
                        f"Vous avez été ajouté en tant que signataire pour le document \"{document_in_db.name}\".\n"
                        f"Veuillez vous connecter à votre compte pour visualiser et signer.\n\n"
                        f"Cordialement,\nL'équipe DKB-Sign"
                    )
                    html = render_template(
                        'simple_notification_email.html',
                        name=name,
                        document_name=document_in_db.name,
                        current_year=datetime.now().year
                    )

                send_email(subject, email, body, html)
                current_app.logger.info(f"Email envoyé à {email}")
            except Exception as email_error:
                current_app.logger.error(f"Erreur lors de l'envoi de l'email à {email}: {str(email_error)}", exc_info=True)
                continue

        # 9) Appliquer les modifications visuelles au PDF via les fonctions utilitaires
        # Ici, on prépare l'URL de brouillon qui sera intégrée dans les QR codes (si besoin)
        draft_filename = f"{uuid.uuid4().hex}.pdf"
        draft_url = url_for('assign_only_bp.get_draft_document',
                            subfolder=company_folder,
                            filename=draft_filename,
                            _external=True)
        # Application des textes optionnels puis des QR codes
        output_pdf = apply_optional_texts(input_pdf, params)
        output_pdf = apply_qr_codes(output_pdf, params, user, draft_url)

        # 10) Sauvegarder le document modifié dans le dossier des brouillons
        save_path = DRAFTS_FOLDER / company_folder
        save_path.mkdir(parents=True, exist_ok=True)
        final_file_path = save_path / draft_filename
        with open(final_file_path, 'wb') as f:
            f.write(output_pdf.getvalue())

        document.file_path = f"{company_folder}/{draft_filename}"
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Erreur lors de la sauvegarde : {str(e)}"}), 500

        document_url = f"/documents/drafts/{company_folder}/{draft_filename}"
        return jsonify({
            "message": "Document préparé avec succès",
            "document_id": document_id,
            "file_path": document.file_path,
            "document": {
                "id": document.id,
                "name": document.name,
                "status": document.status,
                "created_at": document.created_at.isoformat() if document.created_at else None,
                "updated_at": document.updated_at.isoformat() if document.updated_at else None
            },
            "url": document_url
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@assign_only_bp.route('/check-signer-account-type', methods=['GET'])
def check_signer_type():
    try:
        uuid_val = request.args.get('uuid')
        signer = Signer.query.filter_by(uuid=uuid_val).first()
        if not signer:
            return jsonify({"error": "Signataire introuvable avec cet UUID."}), 404
        return jsonify({
            "uuid": signer.uuid,
            "account_type": signer.account_type,
            "signer_id": signer.signer_id,
            "status": signer.status
        }), 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la vérification du type de signataire : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue lors de la vérification : {str(e)}"}), 500


@assign_only_bp.route('/documents/drafts/<path:subfolder>/<filename>', methods=['GET'])
def get_draft_document(subfolder, filename):
    try:
        file_path = DRAFTS_FOLDER / subfolder / filename
        if not file_path.exists():
            return jsonify({"error": "Fichier introuvable"}), 404
        return send_from_directory((DRAFTS_FOLDER / subfolder).resolve(), filename)
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'accès au document : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@assign_only_bp.route('/documents/<int:document_id>/download')
@jwt_required()
def download_document(document_id):
    try:
        user = get_authenticated_user()
        document = Document.query.get(document_id)
        if not document:
            return jsonify({"error": "Document non trouvé"}), 404
        if document.user_id != user.id and not Signer.query.filter_by(document_id=document_id, signer_id=user.id).first():
            return jsonify({"error": "Accès non autorisé"}), 403
        file_path = Path(document.file_path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            return jsonify({"error": "Fichier non trouvé"}), 404
        return send_from_directory(
            file_path.parent,
            file_path.name,
            as_attachment=True,
            download_name=document.name
        )
    except Exception as e:
        current_app.logger.error(f"Erreur lors du téléchargement : {str(e)}", exc_info=True)
        return jsonify({"error": "Erreur lors du téléchargement"}), 500


@assign_only_bp.route('/documents/<int:document_id>/view')
@jwt_required()
def view_document(document_id):
    try:
        user = get_authenticated_user()
        document = Document.query.get(document_id)
        if not document:
            return jsonify({"error": "Document non trouvé"}), 404
        if document.user_id != user.id and not Signer.query.filter_by(document_id=document_id, signer_id=user.id).first():
            return jsonify({"error": "Accès non autorisé"}), 403
        file_path = Path(document.file_path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            return jsonify({"error": "Fichier non trouvé"}), 404
        return send_from_directory(
            file_path.parent,
            file_path.name,
            as_attachment=False
        )
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'affichage : {str(e)}", exc_info=True)
        return jsonify({"error": "Erreur lors de l'affichage"}), 500


@assign_only_bp.route('/documents/doc_signed/<path:subfolder>/<filename>', methods=['GET'])
def download_signed_file(subfolder, filename):
    file_path = SIGNED_PDF_FOLDER / subfolder / filename
    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404
    return send_from_directory((SIGNED_PDF_FOLDER / subfolder).resolve(), filename)


@assign_only_bp.route('/assign-only-multiple', methods=['POST'])
@jwt_required()
def assign_only_multiple():
    """
    Assigne des signataires à plusieurs documents, applique des modifications visuelles,
    envoie un seul email par signataire pour le batch avec signer_id dans le lien,
    et met à jour le statut des documents à 'signed' si tous les signataires ont signé
    ou si le document est une pièce jointe (sans signataire).
    """
    try:
        # 1) Récupérer l'utilisateur connecté et son entreprise
        user = get_authenticated_user()
        company = get_user_company(user)

        # 2) Récupérer les données du formulaire
        data = request.get_json()
        documents_data = data.get('documents', [])
        batch_name = data.get('batch_name', f"Dossier_{uuid.uuid4().hex[:8]}")

        if not documents_data:
            return jsonify({"error": "Aucun document fourni"}), 400

        # Générer un batch_id unique (utilisé pour Document.batch_id et Signer.batch_uuid)
        batch_id = str(uuid.uuid4())
        results = []
        errors = []
        signers_by_id = {}  # Dictionnaire pour regrouper les signataires par (signer_id, account_type)
        document_signers = {}  # Dictionnaire pour suivre les signataires par document

        # 3) Traiter chaque document
        for doc_data in documents_data:
            try:
                file_url = doc_data.get('file_url')
                params = doc_data.get('params', {})
                document_id = params.get('document_id')

                if not file_url:
                    errors.append({"document": params.get('name', 'Inconnu'), "error": "URL du fichier requise"})
                    continue

                # Récupérer les données des signataires
                signers_data = params.get('signers', [])

                # 4) Charger ou créer le document existant
                if document_id:
                    document = Document.query.get(document_id)
                    if not document:
                        errors.append({"document": params.get('name', 'Inconnu'), "error": "Document non trouvé"})
                        continue
                    if document.user_id != user.id:
                        errors.append({"document": params.get('name', 'Inconnu'), "error": "Vous n'avez pas les droits pour modifier ce document"})
                        continue
                else:
                    document = None

                # 5) Charger le PDF
                try:
                    input_pdf = load_pdf(None, file_url)
                except ValueError as e:
                    errors.append({"document": params.get('name', 'Inconnu'), "error": str(e)})
                    continue

                # 6) Créer la structure de dossiers et sauvegarder le fichier original
                base_path = Path(current_app.config.get('UPLOAD_FOLDER', "documents"))
                drafts_path = base_path / "drafts"
                if user.account_type == "employee" and company:
                    company_folder = f"companies/{company.name.replace(' ', '_')}/users/{user.email}"
                    user_path = drafts_path / "companies" / company.name.replace(' ', '_') / "users" / user.email
                else:
                    company_folder = f"users/{user.email}"
                    user_path = drafts_path / "users" / user.email

                user_path.mkdir(parents=True, exist_ok=True)
                original_filename = f"{uuid.uuid4().hex}.pdf"
                file_path = user_path / original_filename
                with open(file_path, 'wb') as f:
                    f.write(input_pdf.getvalue())
                relative_file_path = str(file_path.relative_to(base_path)).replace('\\', '/')

                # 7) Mettre à jour ou créer le document en base de données
                if document:
                    update_assign_document(document, params, relative_file_path)
                    document.batch_id = batch_id
                    document.batch_name = batch_name
                else:
                    document = create_assign_document(user, params, relative_file_path)
                    document.batch_id = batch_id
                    document.batch_name = batch_name
                    db.session.add(document)
                db.session.flush()
                document_id = document.id

                # Initialiser la liste des signataires pour ce document
                document_signers[document_id] = []

                # 8) Ajouter l'initiateur comme premier signataire
                initiator_signer = Signer(
                    document_id=document_id,
                    signer_id=user.id,
                    account_type="individual" if user.account_type == "individual" else "employee",
                    status="prepared",
                    positions=params.get('initiator_positions', []),
                    qr_positions=params.get('qrcodes', []),
                    priority=0,
                    notes="Initiateur du document",
                    uuid=str(uuid.uuid4()),
                    is_verified=True,
                    batch_uuid=batch_id
                )
                current_app.logger.info(f"Initiator Signer batch_uuid: {batch_id}")
                db.session.add(initiator_signer)
                db.session.flush()
                document_signers[document_id].append(initiator_signer)

                # 9) Regrouper les signataires pour l'envoi d'email unique
                for signer_data in signers_data:
                    signer_key = (signer_data.get('signer_id'), signer_data.get('account_type'))
                    if signer_key not in signers_by_id:
                        otp = ''.join(random.choices(string.digits, k=6))
                        signers_by_id[signer_key] = {
                            "signer_id": signer_data.get('signer_id'),
                            "account_type": signer_data.get('account_type'),
                            "otp": otp,
                            "batch_uuid": batch_id,
                            "documents": [],
                            "deadlines": [],
                            "urgencies": [],
                            "name": None,
                            "email": None
                        }

                    # Ajouter le document au signataire
                    signers_by_id[signer_key]["documents"].append({
                        "document_id": document_id,
                        "name": params.get('name', 'Inconnu'),
                        "positions": signer_data.get('positions', []),
                        "priority": signer_data.get('priority', 1),
                        "notes": signer_data.get('notes')
                    })

                    # Collecter les deadlines et urgences
                    if signer_data.get('deadline'):
                        try:
                            deadline = datetime.fromisoformat(signer_data.get('deadline').replace('Z', '+00:00'))
                            signers_by_id[signer_key]["deadlines"].append(deadline)
                        except (ValueError, TypeError):
                            current_app.logger.warning(f"Format de date d'échéance invalide pour le signataire {signer_data.get('signer_id')}")
                    urgency = signer_data.get('urgency', 'normal')
                    if urgency in ['normal', 'urgent', 'tres_urgent']:
                        signers_by_id[signer_key]["urgencies"].append(urgency)
                    else:
                        current_app.logger.warning(f"Urgence invalide pour le signataire {signer_data.get('signer_id')}: {urgency}")

                    # Ajouter le signataire en base de données
                    new_signer = Signer(
                        document_id=document_id,
                        signer_id=signer_data.get('signer_id'),
                        account_type=signer_data.get('account_type'),
                        status="pending",
                        positions=signer_data.get('positions', []),
                        priority=signer_data.get('priority', 1),
                        notes=signer_data.get('notes'),
                        otp_code=signers_by_id[signer_key]["otp"],
                        otp_sent_at=datetime.utcnow(),
                        is_verified=False,
                        uuid=str(uuid.uuid4()),
                        deadline=signer_data.get('deadline'),
                        urgency=urgency,
                        batch_uuid=batch_id
                    )
                    current_app.logger.info(f"New Signer batch_uuid for signer_id {signer_data.get('signer_id')}: {batch_id}")
                    db.session.add(new_signer)
                    document_signers[document_id].append(new_signer)

                # 10) Appliquer les modifications visuelles au PDF
                draft_filename = f"{uuid.uuid4().hex}.pdf"
                draft_url = url_for(
                    'assign_only_bp.get_draft_document',
                    subfolder=company_folder,
                    filename=draft_filename,
                    _external=True
                )
                output_pdf = apply_optional_texts(input_pdf, params)
                output_pdf = apply_qr_codes(output_pdf, params, user, draft_url)

                # 11) Sauvegarder le document modifié
                save_path = DRAFTS_FOLDER / company_folder
                save_path.mkdir(parents=True, exist_ok=True)
                final_file_path = save_path / draft_filename
                with open(final_file_path, 'wb') as f:
                    f.write(output_pdf.getvalue())

                document.file_path = f"{company_folder}/{draft_filename}"
                db.session.flush()

                # Ajouter le résultat pour ce document
                document_url = f"/documents/drafts/{company_folder}/{draft_filename}"
                results.append({
                    "message": "Document préparé avec succès",
                    "document_id": document_id,
                    "file_path": document.file_path,
                    "document": {
                        "id": document.id,
                        "name": document.name,
                        "status": document.status,
                        "batch_id": document.batch_id,
                        "batch_name": document.batch_name,
                        "created_at": document.created_at.isoformat() if document.created_at else None,
                        "updated_at": document.updated_at.isoformat() if document.updated_at else None
                    },
                    "url": document_url
                })

            except Exception as e:
                errors.append({"document": params.get('name', 'Inconnu'), "error": f"Erreur lors du traitement : {str(e)}"})
                continue

        # 12) Vérifier et mettre à jour le statut des documents
        for document_id, signers in document_signers.items():
            document = Document.query.get(document_id)
            if not document:
                continue

            # Si le document n'a pas de signataires (pièce jointe), le considérer comme signé
            if not signers:
                document.status = "signed"
                current_app.logger.info(f"Document {document_id} (pièce jointe) marqué comme signé")
                continue

            # Vérifier si tous les signataires ont signé
            all_signed = all(signer.status == "signed" for signer in Signer.query.filter_by(document_id=document_id).all())
            if all_signed:
                document.status = "signed"
                current_app.logger.info(f"Document {document_id} marqué comme signé (tous les signataires ont signé)")

        # 13) Envoyer un seul email par signataire
        for signer_key, signer_info in signers_by_id.items():
            try:
                # Récupérer les informations du signataire
                if signer_info["account_type"] == "external":
                    contact = Contact.query.get(signer_info["signer_id"])
                    if not contact:
                        errors.append({"signer_id": signer_info["signer_id"], "error": "Contact externe introuvable"})
                        continue
                    signer_info["name"] = contact.name
                    signer_info["email"] = contact.email
                else:
                    user_info = User.query.get(signer_info["signer_id"])
                    if not user_info:
                        errors.append({"signer_id": signer_info["signer_id"], "error": "Utilisateur introuvable"})
                        continue
                    signer_info["name"] = getattr(user_info, 'name', user_info.email)
                    signer_info["email"] = user_info.email

                # Déterminer l'urgence la plus élevée
                urgency_order = {UrgencyEnum.TRES_URGENT: 3, UrgencyEnum.URGENT: 2, UrgencyEnum.NORMAL: 1}
                urgency = max(signer_info["urgencies"], key=lambda u: urgency_order.get(u, 1), default=UrgencyEnum.NORMAL)

                # Déterminer la date limite la plus proche
                deadline = min(signer_info["deadlines"]) if signer_info["deadlines"] else None
                deadline_str = deadline.strftime("%d/%m/%Y à %H:%M") if deadline else ""

                # Déterminer les priorités
                priorities = [doc["priority"] for doc in signer_info["documents"]]
                min_priority = min(priorities) if priorities else 1
                is_top_priority = any(doc["priority"] == min_priority for doc in signer_info["documents"])

                # Préparer l'email
                document_names = ", ".join([doc["name"] for doc in signer_info["documents"]])
                urgency_message = ""
                if urgency == UrgencyEnum.URGENT:
                    urgency_message = "\n⚠️ Ce lot de documents est marqué comme URGENT."
                elif urgency == UrgencyEnum.TRES_URGENT:
                    urgency_message = "\n⚠️ Ce lot de documents est marqué comme TRÈS URGENT !"
                deadline_message = f"\nDate limite de signature : {deadline_str}" if deadline else ""

                # CORRECTION: Les contacts externes doivent TOUJOURS recevoir le lien direct avec OTP
                # car ils n'ont pas de compte pour se connecter
                if signer_info["account_type"] == "external" or is_top_priority:
                    sign_url = f"https://dkb-sign-ui.vercel.app/signed-docs/verify?batch_uuid={signer_info['batch_uuid']}&signer_id={signer_info['signer_id']}"
                    subject = f"Veuillez signer {len(signer_info['documents'])} document(s)"
                    if urgency != UrgencyEnum.NORMAL:
                        subject = f"[{urgency.upper()}] {subject}"
                    body = (
                        f"Bonjour {signer_info['name']},\n\n"
                        f"Vous êtes invité à signer les documents suivants : {document_names}\n\n"
                        f"Veuillez cliquer sur le lien suivant pour signer : {sign_url}\n\n"
                        f"Votre code OTP : {signer_info['otp']}{urgency_message}{deadline_message}\n\n"
                        f"Cordialement,\nL'équipe DKB-Sign"
                    )
                    html = render_template(
                        'sign_document_email.html',
                        name=signer_info["name"],
                        sign_url=sign_url,
                        document_name=document_names,
                        otp_code=signer_info["otp"],
                        urgency=urgency,
                        deadline=deadline_str if deadline else None,
                        current_year=datetime.now().year
                    )
                else:
                    # Notification simple (UNIQUEMENT pour les utilisateurs internes avec compte)
                    subject = f"Notification de demande de signature pour {len(signer_info['documents'])} document(s)"
                    if urgency != UrgencyEnum.NORMAL:
                        subject = f"[{urgency.upper()}] {subject}"
                    body = (
                        f"Bonjour {signer_info['name']},\n\n"
                        f"Vous avez été ajouté en tant que signataire pour les documents suivants : {document_names}\n"
                        f"Veuillez vous connecter à votre compte pour visualiser et signer.\n\n"
                        f"Cordialement,\nL'équipe DKB-Sign"
                    )
                    html = render_template(
                        'simple_notification_email.html',
                        name=signer_info["name"],
                        document_name=document_names,
                        current_year=datetime.now().year
                    )

                send_email(subject, signer_info["email"], body, html)
                current_app.logger.info(f"Email envoyé à {signer_info['email']}")
            except Exception as email_error:
                errors.append({"signer_id": signer_info["signer_id"], "error": f"Erreur lors de l'envoi de l'email : {str(email_error)}"})
                continue

        # 14) Préparer la liste des batch_uuid pour les signataires
        signers_batch_uuids = [
            {
                "signer_id": signer_info["signer_id"],
                "account_type": signer_info["account_type"],
                "batch_uuid": signer_info["batch_uuid"]
            }
            for signer_key, signer_info in signers_by_id.items()
        ]

        # 15) Valider les modifications en base de données
        try:
            db.session.commit()
            current_app.logger.info("Database commit successful")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database commit failed: {str(e)}")
            return jsonify({"error": f"Erreur lors de la sauvegarde : {str(e)}", "partial_results": results, "errors": errors}), 500

        # 16) Retourner la réponse
        return jsonify({
            "message": f"{len(results)} document(s) préparé(s) avec succès",
            "batch_id": batch_id,
            "batch_name": batch_name,
            "results": results,
            "errors": errors,
            "signers_batch_uuids": signers_batch_uuids
        }), 200 if not errors else 207

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500