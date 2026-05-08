from flask import Blueprint, request, jsonify, render_template, url_for, send_from_directory, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from pathlib import Path
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from pyhanko.sign.signers import PdfSignatureMetadata
from pyhanko.pdf_utils import images
from pyhanko import stamp
from io import BytesIO
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
from PIL import Image
import uuid
import json
from app.models import User, Company, Document, Contact, DocumentConsent, Signer, CertTypeEnum, db, UrgencyEnum
from app.services.email_service import send_email
from app.services.signature_proof_service import create_signature_proof, build_proof_urls
from datetime import datetime
import tempfile
import os
from sqlalchemy.exc import SQLAlchemyError
import urllib.parse
import http.client
from app.utils.signature_utils import (
    load_pdf,
    retrieve_certificates,
    load_signature_image,
    prepare_pdf_paths,
    sign_pdf_pages,
    apply_qr_codes,
    add_text_to_pdf,
    apply_stamp_to_pdf,
    update_signature_volumes,
    notify_next_signer,
    create_pdf_signer,
    apply_optional_texts,
    apply_stamp
)


sign_and_assign_bp = Blueprint('sign_and_assign_bp', __name__)

SIGNED_PDF_FOLDER = Path("documents/doc_signed")
SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)

CERTIFICATE_FOLDER = Path("certificates/users")
SIGNATURE_FOLDER = Path("signatures/users")
COMPANY_SIGNATURE_FOLDER = Path("signatures/companies")
DRAFT_PDF_FOLDER = Path("documents/doc_draft")

DRAFT_PDF_FOLDER = Path("documents/drafts")
DRAFT_PDF_FOLDER.mkdir(parents=True, exist_ok=True)


@sign_and_assign_bp.route('/documents/doc_signed/<path:subfolder>/<filename>', methods=['GET'])
def download_file(subfolder, filename):
    file_path = SIGNED_PDF_FOLDER / subfolder / filename
    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404
    return send_from_directory((SIGNED_PDF_FOLDER / subfolder).resolve(), filename)


@sign_and_assign_bp.route('/sign-and-assign', methods=['POST'])
@jwt_required()
def sign_pdf():
    """
    Point d’entrée principal pour la signature et l’envoi aux autres signataires.
    """
    try:
        # 1) Récupération de l’utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # 2) Vérification du volume de signatures
        if user.account_type == "individual" and user.signature_volume_used >= user.signature_volume:
            return jsonify({"error": "Votre volume de signatures est épuisé. Veuillez recharger votre compte."}), 400

        company = None
        if user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404
            if company.signature_volume_used >= company.signature_volume:
                return jsonify({"error": "Le volume de signatures de l'entreprise est épuisé. Veuillez contacter l'administrateur."}), 400

        # 3) Vérification du volume de signatures
        if user.account_type == "individual" and user.signature_volume_used >= user.signature_volume:
            return jsonify({"error": "Votre volume de signatures est épuisé. Veuillez recharger votre compte."}), 400

        # 4) Analyse des paramètres (JSON) + chargement du PDF
        params, file_url, file = parse_request_content(request)
        if not params or "pages" not in params or not isinstance(params["pages"], list):
            return jsonify({"error": "Les paramètres JSON sont mal structurés ou manquants (clé 'pages')."}), 400

        # Vérifier et formater file_url
        if not file_url:
            return jsonify({"error": "URL du fichier requise"}), 400
        file_url = file_url.replace('\\', '/')  # Remplacer les barres obliques inversées
        parsed_url = urllib.parse.urlparse(file_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return jsonify({"error": "URL du fichier invalide"}), 400

        # Récupérer document_id des paramètres
        document_id = params.get("document_id")

        # Récupérer la date limite et l'urgence
        deadline = params.get("deadline")
        urgency = params.get("urgency", UrgencyEnum.NORMAL)

        # Valider la date limite si elle est fournie
        if deadline:
            try:
                deadline_date = datetime.strptime(deadline, '%Y-%m-%dT%H:%M:%SZ')
                if deadline_date < datetime.utcnow():
                    return jsonify({"error": "La date limite ne peut pas être dans le passé."}), 400
            except ValueError:
                return jsonify({"error": "Format de date invalide. Utilisez le format ISO 8601 (YYYY-MM-DDThh:mm:ssZ)."}), 400

        # Valider l'urgence
        valid_urgencies = [UrgencyEnum.NORMAL, UrgencyEnum.URGENT, UrgencyEnum.TRES_URGENT]
        if urgency not in valid_urgencies:
            return jsonify({"error": f"Niveau d'urgence invalide. Valeurs possibles : normal, urgent, tres_urgent"}), 400

        # Vérifier si l'initiateur a déjà signé le document
        if document_id:
            existing_signer = Signer.query.filter_by(signer_id=user.id, document_id=document_id).first()
            if existing_signer and existing_signer.status == "signed":
                return jsonify({"error": "L'initiateur a déjà signé ce document."}), 400

        # 2) Récupération des certificats et du cachet du signataire
        cert_path, key_path, cert_chain = retrieve_certificates(user, company)
        if not cert_path or not key_path:
            return jsonify({"error": "Certificat ou clé privée introuvable."}), 400
            
        signer_stamp = load_signature_image(user)
        if not signer_stamp:
            return jsonify({"error": "Image de signature introuvable."}), 400

        # 4) Analyse des paramètres (JSON) + chargement du PDF
        params, file_url, file = parse_request_content(request)
        if not params or "pages" not in params or not isinstance(params["pages"], list):
            return jsonify({"error": "Les paramètres JSON sont mal structurés ou manquants (clé 'pages')."}), 400

        document_id = params.get("document_id")
        document = None

        # 5) Gestion du consentement éventuel
        requires_consent = False
        if user.account_type == "individual":
            requires_consent = user.with_consent
        elif user.account_type == "employee" and company:
            requires_consent = company.with_consent

        if requires_consent and not document_id:
            return jsonify({"error": "Le consentement est requis pour signer ce document, mais aucun document_id n'a été fourni."}), 400

        if document_id:
            document = retrieve_document(user, document_id)
            if requires_consent:
                consent = DocumentConsent.query.filter_by(
                    document_id=document_id,
                    user_id=user.id,
                    is_verified=True
                ).first()
                if not consent:
                    return jsonify({"error": "Aucun consentement vérifié trouvé pour ce document. Veuillez confirmer votre consentement avant de signer."}), 403

        # 6) Configuration du signataire PyHanko
        signer = create_pdf_signer(key_path, cert_path, cert_chain)

        # 7) Charger le PDF dans un buffer
        input_pdf_buffer = load_pdf(file, file_url)
        if not input_pdf_buffer:
            return jsonify({"error": "Échec du chargement du fichier PDF."}), 400
        input_pdf_buffer.seek(0)

        # 8) AJOUTS AU PDF (AVANT de signer)
        # Paraphe, date, texte personnalisé
        input_pdf_buffer = apply_optional_texts(input_pdf_buffer, params)
        
        # Cachet (Stamp)
        input_pdf_buffer = apply_stamp(input_pdf_buffer, user, params)

        # Générer un seul UUID pour tout le processus
        file_uuid = uuid.uuid4().hex
        unique_filename = f"signed_pdf_{file_uuid}.pdf"
        
        # Préparer le chemin de sauvegarde avec l'email de l'initiateur
        company_part = f"companies/{company.name.replace(' ', '_')}/" if user.account_type == "employee" and company else ""
        user_part = f"users/{current_user_email}/"
        subfolder = f"{company_part}{user_part}".rstrip('/')
        
        signed_pdf_folder = os.path.join(SIGNED_PDF_FOLDER, subfolder)
        os.makedirs(signed_pdf_folder, exist_ok=True)
        
        signed_pdf_path = os.path.join(signed_pdf_folder, unique_filename)
        relative_file_path = os.path.relpath(signed_pdf_path, SIGNED_PDF_FOLDER).replace("\\", "/")

        # Générer l'URL finale avec le même UUID
        full_signed_pdf_url = url_for(
            'sign_and_assign_bp.download_file',
            subfolder=subfolder,
            filename=unique_filename,
            _external=True
        )

        # QR Codes (AVANT signature)
        qr_code_positions = params.get("qrcodes", [])
        if qr_code_positions:
            input_pdf_buffer = apply_qr_codes(input_pdf_buffer, params, user, full_signed_pdf_url)

        # 9) Préparation du signataire PDF
        signer = create_pdf_signer(key_path, cert_path, cert_chain)

        # 10) Application des signatures
        pages_dict = {}
        for page_params in params["pages"]:
            page_index = page_params.get("page", 0)
            signatures = page_params.get("signatures", [])
            if not signatures or not isinstance(signatures, list):
                return jsonify({"error": f"Signatures invalides pour la page {page_index}."}), 400

            for signature in signatures:
                if page_index not in pages_dict:
                    pages_dict[page_index] = []
                pages_dict[page_index].append(signature)

        pages = [{"page": p, "signatures": pages_dict[p]} for p in pages_dict]
        # Préparer les infos du signataire pour affichage sous la signature
        signer_info = {
            'name': user.name,
            'sub_name': user.sub_name if hasattr(user, 'sub_name') else None,
            'function': user.function if hasattr(user, 'function') else None,
            'email': user.email
        }
        # is_workflow=True pour ne pas invalider les signatures précédentes
        input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, pages, signer, signer_stamp, signer_info, is_workflow=True)

        # 11) Sauvegarder le PDF final
        try:
            # Préparer le chemin final du PDF avec l'email de l'initiateur
            company_part = f"companies/{company.name.replace(' ', '_')}/" if user.account_type == "employee" and company else ""
            user_part = f"users/{current_user_email}/"
            subfolder = f"{company_part}{user_part}".rstrip('/')
            
            signed_pdf_folder = os.path.join(SIGNED_PDF_FOLDER, subfolder)
            os.makedirs(signed_pdf_folder, exist_ok=True)

            signed_pdf_path = os.path.join(signed_pdf_folder, unique_filename)
            relative_file_path = os.path.relpath(signed_pdf_path, SIGNED_PDF_FOLDER).replace("\\", "/")

            full_signed_pdf_url = url_for(
                'sign_and_assign_bp.download_file',
                subfolder=subfolder,
                filename=unique_filename,
                _external=True
            )

            with open(signed_pdf_path, 'wb') as output_file:
                output_file.write(input_pdf_buffer.getvalue())
        except Exception as file_error:
            current_app.logger.error(f"Erreur lors de l'enregistrement du PDF signé : {str(file_error)}", exc_info=True)
            return jsonify({"error": "Erreur lors de l'enregistrement du PDF signé."}), 500

        # 12) Créer ou mettre à jour le Document
        if document_id and document:
            update_existing_document(document, params, relative_file_path)
        else:
            document = create_new_document(user, params, relative_file_path)

        # 13) Mettre à jour le volume de signature
        update_signature_volumes(user, company, 1)

        # 14) GESTION DES SIGNATAIRES (y compris l’initiateur)
        signers_data = params.get("signers", [])
        if not signers_data:
            return jsonify({"error": "Aucune information de signataire fournie (clé 'signers')."}), 400

        # Positions de signature de l’initiateur (si besoin d’en garder une trace)
        initiator_positions = []
        for page_param in params.get("pages", []):
            for sig in page_param.get("signatures", []):
                initiator_positions.append({
                    "page": page_param.get("page", 0),
                    "x": sig.get("x", 50),
                    "y": sig.get("y", 100)
                })

        initiator_signer = {
            "signer_id": user.id,
            "account_type": user.account_type,
            "positions": initiator_positions,
            "priority": 0,
            "notes": "Initiateur du document",
            "deadline": deadline,
            "urgency": urgency
        }
        all_signers = [initiator_signer] + signers_data

        # Déterminer les priorités
        priorities = [s.get("priority") for s in signers_data if "priority" in s]
        if not priorities:
            top_priority_signers = signers_data
        else:
            sorted_signers = sorted(signers_data, key=lambda x: x.get("priority", 1))
            top_priority = sorted_signers[0].get("priority", 1)
            top_priority_signers = [s for s in sorted_signers if s.get("priority", 1) == top_priority]

        # Ajouter l'initiateur dans la table Signer (statut "signed")
        try:
            current_app.logger.info(f"Début de l'ajout de l'initiateur - Document ID: {document.id}, User ID: {user.id}")
            
            # Vérifier si l'initiateur existe déjà
            existing_initiator = Signer.query.filter_by(
                document_id=document.id,
                signer_id=user.id
            ).first()
            
            if existing_initiator:
                current_app.logger.info(f"Mise à jour de l'initiateur existant - Signer ID: {existing_initiator.id}")
                # Mettre à jour l'initiateur existant
                existing_initiator.status = "signed"
                existing_initiator.positions = initiator_positions if initiator_positions else []
                existing_initiator.priority = 0
                existing_initiator.notes = "Initiateur du document"
                existing_initiator.deadline = deadline
                existing_initiator.urgency = urgency
                db.session.add(existing_initiator)
            else:
                current_app.logger.info("Création d'un nouvel initiateur")
                # Créer un nouvel initiateur avec un UUID
                initiator_signer_db = Signer(
                    document_id=document.id,
                    signer_id=user.id,
                    account_type=user.account_type,
                    status="signed",
                    email_status="not_sent",
                    positions=initiator_positions if initiator_positions else [],
                    priority=0,
                    email_sent=False,
                    reminder_sent=False,
                    notes="Initiateur du document",
                    deadline=deadline,
                    urgency=urgency,
                    uuid=str(uuid.uuid4())  # Utilisation directe de uuid qui est importé au début du fichier
                )
                # Générer l'OTP pour l'initiateur
                initiator_signer_db.generate_otp()
                current_app.logger.info(f"Données de l'initiateur: {initiator_signer_db.__dict__}")
                db.session.add(initiator_signer_db)

            try:
                current_app.logger.info("Tentative de flush de la session")
                db.session.flush()
                current_app.logger.info("Flush réussi")
            except SQLAlchemyError as flush_error:
                db.session.rollback()
                current_app.logger.error(f"Erreur détaillée lors du flush de l'initiateur : {str(flush_error)}\nType d'erreur: {type(flush_error)}", exc_info=True)
                return jsonify({"error": f"Erreur de base de données lors de l'ajout de l'initiateur: {str(flush_error)}"}), 500

        except SQLAlchemyError as db_error:
            db.session.rollback()
            current_app.logger.error(f"Erreur détaillée lors de l'ajout de l'initiateur : {str(db_error)}\nType d'erreur: {type(db_error)}", exc_info=True)
            return jsonify({"error": f"Erreur de base de données lors de l'ajout de l'initiateur: {str(db_error)}"}), 500
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Erreur inattendue lors de l'ajout de l'initiateur : {str(e)}", exc_info=True)
            return jsonify({"error": f"Erreur inattendue lors de l'ajout de l'initiateur: {str(e)}"}), 500

        # Enregistrer tous les signataires
        for signer_info in all_signers:
            if signer_info["signer_id"] == user.id:
                # Ne pas redemander d'email à l'initiateur
                continue

            signer_id = signer_info.get("signer_id")
            account_type = signer_info.get("account_type")
            positions = signer_info.get("positions", [])
            priority = signer_info.get("priority", 1)
            notes = signer_info.get("notes", "")

            try:
                with db.session.begin_nested():
                    # Récupérer l'utilisateur ou le contact
                    email = None
                    name = None
                    signer_user = None
                    if account_type in ["employee", "individual"]:
                        signer_user = User.query.get(signer_info["signer_id"])
                        if not signer_user:
                            return jsonify({"error": f"Signataire ID {signer_id} introuvable."}), 404
                        email = signer_user.email
                        name = signer_user.name
                    elif account_type == "external":
                        signer_user = Contact.query.get(signer_info["signer_id"])
                        if not signer_user:
                            return jsonify({"error": f"Contact externe ID {signer_id} introuvable."}), 404
                        email = signer_user.email
                        name = signer_user.name
                    else:
                        return jsonify({"error": f"Type de compte inconnu pour le signataire ID {signer_id}."}), 400

                    # Créer l'entrée en BD
                    new_signer = Signer(
                        document_id=document.id,
                        signer_id=signer_id,
                        account_type=account_type,
                        status="pending",
                        email_status="sent",
                        positions=positions,
                        priority=priority,
                        email_sent=True,
                        reminder_sent=False,
                        notes=notes,
                        deadline=signer_info.get("deadline"),
                        urgency=signer_info.get("urgency", UrgencyEnum.NORMAL),
                        uuid=str(uuid.uuid4())
                    )
                    new_signer.generate_otp()
                    db.session.add(new_signer)

            except SQLAlchemyError as db_error:
                db.session.rollback()
                current_app.logger.error(f"Erreur de base de données pour le signataire {signer_id}: {str(db_error)}", exc_info=True)
                return jsonify({"error": "Erreur de base de données lors de l'ajout d'un signataire."}), 500

            # Envoi d'email
            # CORRECTION: Les contacts externes doivent TOUJOURS recevoir le lien direct avec OTP
            # car ils n'ont pas de compte pour se connecter
            if account_type == "external" or not priorities or signer_info in top_priority_signers:
                # Email avec lien direct + OTP (pour contacts externes et signataires prioritaires)
                sign_url = f"https://dkb-sign-ui.vercel.app/signed-docs/verify?uuid={new_signer.uuid}"
                subject = "Please Sign the Document"
                
                # Construction du message avec la date limite si définie
                deadline_msg = ""
                if new_signer.deadline:
                    deadline_date = datetime.strptime(new_signer.deadline, '%Y-%m-%dT%H:%M:%SZ')
                    deadline_msg = f"\nDate limite de signature : {deadline_date.strftime('%d/%m/%Y %H:%M')}"

                body = (
                    f"Bonjour {name},\n\n"
                    f"Veuillez cliquer sur le lien suivant pour signer le document : {sign_url}\n\n"
                    f"Votre code OTP : {new_signer.otp_code}"
                    f"{deadline_msg}\n\n"
                    f"Cordialement,\nL'équipe DKB-Sign"
                )
                html = render_template(
                    'sign_document_email.html',
                    name=name,
                    sign_url=sign_url,
                    otp_code=new_signer.otp_code,
                    deadline=deadline_date.strftime('%d/%m/%Y %H:%M') if new_signer.deadline else None,
                    urgency=new_signer.urgency,
                    document_name=document.name,
                    current_year=datetime.now().year
                )

            else:
                # Notification simple (UNIQUEMENT pour les utilisateurs internes avec compte)
                subject = "Signature Request Notification"
                body = (
                    f"Bonjour {name},\n\n"
                    f"Vous avez été ajouté en tant que signataire pour le document \"{document.name}\".\n"
                    f"Veuillez vous connecter à votre compte pour visualiser et signer.\n\n"
                    f"Cordialement,\nL'équipe DKB-Sign"
                )
                html = render_template(
                    'simple_notification_email.html',
                    name=name,
                    document_name=document.name,
                    current_year=datetime.now().year
                )

            try:
                current_app.logger.info(f"Tentative d'envoi d'email à {email}")
                send_email(subject, email, body, html)
                current_app.logger.info(f"Email envoyé avec succès à {email}")
                
                # Mettre à jour le statut d'envoi de l'email
                new_signer.email_sent = True
                db.session.commit()
            except Exception as email_error:
                current_app.logger.error(f"Erreur lors de l'envoi de l'email à {email}: {str(email_error)}", exc_info=True)
                # On continue quand même le process

            # Envoyer une notification WhatsApp si le numéro est disponible
            if hasattr(signer_user, 'phone') and signer_user.phone:
                # Nettoyer le numéro de téléphone (enlever +, espaces, etc.)
                clean_phone = ''.join(filter(str.isdigit, signer_user.phone))
                if clean_phone:
                    whatsapp_message = f"Bonjour {name},\n\nVous avez un document à signer : {document.name}\n\nVotre code OTP : {new_signer.otp_code}\n\nLien de signature : {sign_url}"
                    send_whatsapp_notification(clean_phone, whatsapp_message)

        # 15) Commit final
        db.session.commit()

        # Vérifier si c'est le dernier signataire
        remaining_signers = Signer.query.filter(
            Signer.document_id == document.id,
            Signer.status != "signed"
        ).count()

        if remaining_signers == 0:
            # Tous les signataires ont signé, envoyer une copie à chacun
            all_signers = Signer.query.filter_by(document_id=document.id).all()
            
            for signer in all_signers:
                # Récupérer les informations du signataire
                if signer.account_type == "external":
                    recipient = Contact.query.get(signer.signer_id)
                else:
                    recipient = User.query.get(signer.signer_id)
                if recipient:
                    download_link = url_for(
                        'sign_and_assign_bp.download_file',
                        subfolder=document.file_path.rsplit('/', 1)[0],
                        filename=document.file_path.rsplit('/', 1)[-1],
                        _external=True
                    )
                    subject = f"Document {document.name} - Copie finale signée"
                    recipient_name = getattr(recipient, 'name', recipient.email)
                    body = (
                        f"Bonjour {recipient_name},\n\nLe document {document.name} a été signé par tous les signataires actifs.\n\n"
                        f"Vous pouvez télécharger la version finale ici : {download_link}"
                    )
                    html = render_template(
                        'final_document_email.html',
                        name=recipient_name,
                        document_name=document.name,
                        document_url=download_link,
                        current_year=datetime.now().year
                    )

                    # Envoyer l'email
                    try:
                        send_email(
                            subject=subject,
                            recipient=recipient.email,
                            body=html,
                            sender_name="DKB-Sign"
                        )
                    except Exception as e:
                        current_app.logger.error(f"Erreur lors de l'envoi de l'email à {recipient.email}: {str(e)}")

        # Génération de la preuve de signature
        proof = create_signature_proof(
            document_id=document.id,
            signer=user,
            signer_type='user',
            document_name=params.get("name", "document"),
            file_path_after=signed_pdf_path,
            cert_path=cert_path,
            cert_type=company.cert_type if company else None,
            signature_method='jwt',
            signature_positions=params.get("pages"),
            consent_accepted=True,
            company=company,
            batch_id=params.get("batch_id"),
        )

        return jsonify({
            "message": "Document signé par l'initiateur et notifications envoyées.",
            "doc_signed": full_signed_pdf_url,
            "document_id": document.id,
            "status": document.status,
            "proof": build_proof_urls(proof) if proof else None
        }), 200

    except SQLAlchemyError as db_error:
        db.session.rollback()
        current_app.logger.error(f"Erreur de base de données : {str(db_error)}", exc_info=True)
        return jsonify({"error": "Erreur de base de données lors de la signature."}), 500

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la signature : {str(e)}", exc_info=True)
        return jsonify({"error": f"Erreur lors de la signature : {str(e)}"}), 500


@sign_and_assign_bp.route('/verify-ext-doc-access', methods=['POST'])
def verify_otp():
    try:
        data = request.get_json()
        if not data or 'otp_code' not in data or 'signer_uuid' not in data:
            return jsonify({"error": "Les champs 'otp_code' et 'signer_uuid' sont requis."}), 400

        otp_code = data['otp_code']
        signer_uuid = data['signer_uuid']

        signer_rec = Signer.query.filter_by(uuid=signer_uuid).first()
        if not signer_rec:
            return jsonify({"error": "Signataire introuvable."}), 404

        # Vérifier le code OTP
        if not signer_rec.verify_otp(otp_code):
            return jsonify({"error": "Code OTP invalide."}), 400

        signer_rec.is_verified = True
        db.session.commit()

        document = signer_rec.document
        if not document:
            return jsonify({"error": "Document associé introuvable."}), 404

        full_signed_pdf_url = url_for(
            'sign_and_assign_bp.download_file',
            subfolder=document.file_path.rsplit('/', 1)[0],
            filename=document.file_path.rsplit('/', 1)[-1],
            _external=True
        )

        return jsonify({
            "message": "Code OTP validé avec succès.",
            "document_link": full_signed_pdf_url,
            "document_status": document.status
        }), 200

    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Erreur de base de données."}), 500
    except Exception as e:
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@sign_and_assign_bp.route('/verify-ext-doc-access-multiple', methods=['POST'])
def verify_otp_multiple():
    """
    Endpoint pour vérifier les codes OTP de plusieurs signataires associés à un batch_uuid.
    """
    try:
        data = request.get_json()
        if not data or 'otp_code' not in data or 'batch_uuid' not in data:
            return jsonify({"error": "Les champs 'otp_code' et 'batch_uuid' sont requis."}), 400

        otp_code = data['otp_code']
        batch_uuid = data['batch_uuid']

        current_app.logger.info(f"Processing OTP verification for batch_uuid: {batch_uuid}")

        # Récupérer tous les signataires pour ce batch_uuid
        signer_records = Signer.query.filter_by(batch_uuid=batch_uuid).all()
        if not signer_records:
            return jsonify({"error": "Aucun signataire trouvé pour ce batch_uuid."}), 404

        results = []
        errors = []

        # Traiter chaque signataire
        for signer_rec in signer_records:
            try:
                current_app.logger.info(f"Processing signer_id: {signer_rec.signer_id}, document_id: {signer_rec.document_id}")

                # Vérifier si le signataire est déjà vérifié
                if signer_rec.is_verified:
                    document = signer_rec.document
                    if not document:
                        errors.append({
                            "signer_id": signer_rec.signer_id,
                            "document_id": signer_rec.document_id,
                            "error": "Document associé introuvable."
                        })
                        continue

                    full_signed_pdf_url = url_for(
                        'sign_and_assign_bp.download_file',
                        subfolder=document.file_path.rsplit('/', 1)[0],
                        filename=document.file_path.rsplit('/', 1)[-1],
                        _external=True
                    )
                    results.append({
                        "signer_id": signer_rec.signer_id,
                        "document_id": signer_rec.document_id,
                        "message": "Signataire déjà vérifié.",
                        "document_link": full_signed_pdf_url,
                        "document_status": document.status
                    })
                    continue

                # Vérifier le code OTP
                if not signer_rec.verify_otp(otp_code):
                    errors.append({
                        "signer_id": signer_rec.signer_id,
                        "document_id": signer_rec.document_id,
                        "error": "Code OTP invalide."
                    })
                    continue

                # Mettre à jour le statut de vérification
                signer_rec.is_verified = True

                # Récupérer le document associé
                document = signer_rec.document
                if not document:
                    errors.append({
                        "signer_id": signer_rec.signer_id,
                        "document_id": signer_rec.document_id,
                        "error": "Document associé introuvable."
                    })
                    continue

                # Générer l'URL du document
                full_signed_pdf_url = url_for(
                    'sign_and_assign_bp.download_file',
                    subfolder=document.file_path.rsplit('/', 1)[0],
                    filename=document.file_path.rsplit('/', 1)[-1],
                    _external=True
                )

                # Ajouter le résultat pour ce signataire
                results.append({
                    "signer_id": signer_rec.signer_id,
                    "document_id": signer_rec.document_id,
                    "message": "Code OTP validé avec succès.",
                    "document_link": full_signed_pdf_url,
                    "document_status": document.status
                })

            except Exception as e:
                current_app.logger.error(
                    f"Error processing signer_id {signer_rec.signer_id}, document_id {signer_rec.document_id}: {str(e)}",
                    exc_info=True
                )
                errors.append({
                    "signer_id": signer_rec.signer_id,
                    "document_id": signer_rec.document_id,
                    "error": f"Erreur lors de la vérification : {str(e)}"
                })
                continue

        # Valider les modifications en base de données
        try:
            db.session.commit()
            current_app.logger.info("Database commit successful")
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database commit failed: {str(e)}", exc_info=True)
            return jsonify({
                "error": f"Erreur de base de données : {str(e)}",
                "results": results,
                "errors": errors
            }), 500

        # Retourner la réponse
        if not results and errors:
            return jsonify({"error": "Aucun OTP n'a pu être vérifié.", "errors": errors}), 400
        return jsonify({
            "message": f"{len(results)} OTP(s) vérifié(s) avec succès.",
            "results": results,
            "errors": errors
        }), 200 if not errors else 207

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@sign_and_assign_bp.route('/sign-recep-pdf', methods=['POST'])
def sign_document():
    """
    Endpoint pour un signataire (interne ou externe) qui signe un document déjà en circulation.
    """
    try:
        signer_id = request.form.get('signer_id')
        document_id = request.form.get('doc_id')
        if not signer_id or not document_id:
            return jsonify({"error": "Les champs signer_id et doc_id sont obligatoires."}), 400

        # Récupération du signataire courant
        current_signer = Signer.query.filter_by(signer_id=signer_id, document_id=document_id).first()
        if not current_signer:
            return jsonify({"error": "Signataire ou document introuvable."}), 404
        if current_signer.status == "signed":
            return jsonify({"message": "Document déjà signé."}), 200

        # Vérification de l'ordre de signature
        all_signers = Signer.query.filter_by(document_id=document_id).order_by(Signer.priority).all()
        active_signers = [s for s in all_signers if s.status != "prepared"]
        signed_signers = [s for s in active_signers if s.status == "signed"]
        max_signed_priority = max([s.priority for s in signed_signers], default=0)
        if current_signer.priority > max_signed_priority + 1:
            pending_before = [s for s in active_signers if s.priority < current_signer.priority and s.status == "pending"]
            if pending_before:
                return jsonify({
                    "error": "D'autres signataires doivent signer avant vous.",
                    "pending_count": len(pending_before)
                }), 403

        # Récupération de l'initiateur (priority=0) pour définir le sous-dossier et obtenir les positions QR
        initiator = Signer.query.filter_by(document_id=document_id, priority=0).first()
        if not initiator:
            return jsonify({"error": "Initiateur du document introuvable."}), 404
        initiator_user = User.query.get(initiator.signer_id)
        if not initiator_user:
            return jsonify({"error": "Utilisateur initiateur introuvable."}), 404

        # Construction du sous-dossier selon le type d'utilisateur initiateur
        company_part = f"companies/{initiator_user.company.name.replace(' ', '_')}/" if initiator_user.account_type == "employee" and initiator_user.company_id else ""
        user_part = f"users/{initiator_user.email}/"
        subfolder = f"{company_part}{user_part}".rstrip('/')

        # Récupération du document
        document = Document.query.get(document_id)
        if not document:
            return jsonify({"error": "Document introuvable."}), 404

        # Identification de l'utilisateur ou du contact du signataire courant
        if current_signer.account_type in ["employee", "individual"]:
            user_acc = User.query.get(current_signer.signer_id)
        elif current_signer.account_type == "external":
            user_acc = Contact.query.get(current_signer.signer_id)
        else:
            return jsonify({"error": "Type de compte du signataire inconnu."}), 400
        if not user_acc:
            return jsonify({"error": "Utilisateur ou contact introuvable."}), 404

        # CORRECTION: Vérifier si le contact externe a un compte associé
        is_external_with_account = False
        if current_signer.account_type == "external" and hasattr(user_acc, 'user_account_id') and user_acc.user_account_id:
            # Ce contact a un compte utilisateur associé, utiliser ce compte pour la signature
            associated_user = User.query.get(user_acc.user_account_id)
            if associated_user:
                current_app.logger.info(f"Contact externe {user_acc.email} a un compte associé (User ID: {associated_user.id})")
                user_acc = associated_user
                is_external_with_account = True

        company = None
        if hasattr(user_acc, 'company_id') and user_acc.company_id:
            company = Company.query.get(user_acc.company_id)

        # Chargement de l'image de signature directement en objet PIL
        # pour éviter la perte de qualité liée au cycle save/reload via fichier temporaire
        signer_stamp_img = None
        if current_signer.account_type == "external" and not is_external_with_account:
            # Contact externe sans compte associé: demander l'upload de l'image
            if 'signature_image' not in request.files:
                return jsonify({"error": "Le fichier 'signature_image' est obligatoire pour un signataire externe."}), 400
            file_img = request.files['signature_image']
            if file_img.filename == '':
                return jsonify({"error": "Aucun fichier de signature n'a été fourni."}), 400
            file_img.stream.seek(0)
            signer_stamp_img = Image.open(file_img.stream)
        else:
            # Utilisateur avec compte (ou contact avec compte associé): utiliser l'image de signature du compte
            signer_stamp_img = load_signature_image(user_acc)
            if not signer_stamp_img:
                return jsonify({"error": "Image de signature introuvable."}), 400

        # Récupération des certificats via la fonction utilitaire
        cert_path, key_path, cert_chain = retrieve_certificates(user_acc, company, document_id)
        if not cert_path or not key_path:
            return jsonify({"error": "Certificat ou clé privée introuvable."}), 400
        signer_obj = signers.SimpleSigner.load(
            key_file=key_path,
            cert_file=cert_path,
            ca_chain_files=cert_chain
        )

        # Détermination du dossier source du PDF (dossier brouillons ou doc_signed)
        all_signers_db = Signer.query.filter_by(document_id=document_id).all()
        if all(s.status == "pending" for s in all_signers_db):
            source_folder = DRAFT_PDF_FOLDER
        else:
            source_folder = SIGNED_PDF_FOLDER
        source_pdf_path = os.path.join(source_folder, document.file_path)
        if not os.path.exists(source_pdf_path):
            alternate_folder = DRAFT_PDF_FOLDER if source_folder == SIGNED_PDF_FOLDER else SIGNED_PDF_FOLDER
            alternate_path = os.path.join(alternate_folder, document.file_path)
            if os.path.exists(alternate_path):
                source_pdf_path = alternate_path
            else:
                return jsonify({
                    "error": "Document source introuvable",
                    "details": {
                        "tried_paths": [source_pdf_path, alternate_path],
                        "document_path": document.file_path
                    }
                }), 404

        # Chargement du PDF source en mémoire
        with open(source_pdf_path, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
            input_pdf_buffer = BytesIO(pdf_content)

        # Calcul de l'URL finale et génération d'un nouveau nom de fichier pour le document signé
        new_filename = f"signed_pdf_{uuid.uuid4().hex}.pdf"
        # Pour le premier signataire, on génère une nouvelle URL
        # Pour les signataires suivants, on conserve l'URL existante du document
        if max_signed_priority == 0:
            final_signed_pdf_url = url_for(
                'sign_and_assign_bp.download_file',
                subfolder=subfolder,
                filename=new_filename,
                _external=True
            )
        else:
            # Conserver l'URL existante pour ne pas invalider les signatures précédentes
            new_filename = os.path.basename(document.file_path)
            final_signed_pdf_url = url_for(
                'sign_and_assign_bp.download_file',
                subfolder=subfolder,
                filename=new_filename,
                _external=True
            )

        # Insertion du QR code uniquement si c'est le premier signataire
        if max_signed_priority == 0 and hasattr(initiator, 'qr_positions') and initiator.qr_positions:
            try:
                qr_positions = (
                    json.loads(initiator.qr_positions)
                    if isinstance(initiator.qr_positions, str)
                    else initiator.qr_positions
                )
            except Exception:
                qr_positions = []
            # Mise à jour de la donnée de chaque QR code avec l'URL finale
            for qr in qr_positions:
                qr['data'] = final_signed_pdf_url
            temp_params = {"qrcodes": qr_positions}
            input_pdf_buffer = apply_qr_codes(input_pdf_buffer, temp_params, user_acc, final_signed_pdf_url)
        else:
            # Si aucun QR code n'est défini, on conserve le nom existant
            new_filename = os.path.basename(document.file_path)
            final_signed_pdf_url = url_for(
                'sign_and_assign_bp.download_file',
                subfolder=subfolder,
                filename=new_filename,
                _external=True
            )

        # Transformation des positions de signature pour l'utilitaire sign_pdf_pages
        pages_dict = {}
        for pos in current_signer.positions:
            page = pos.get("page", 0)
            if page not in pages_dict:
                pages_dict[page] = []
            pages_dict[page].append(pos)
        pages = [{"page": p, "signatures": pages_dict[p]} for p in pages_dict]

        # Application de la signature via l'utilitaire (toute la révision, QR code compris, sera signée)
        # Préparer les infos du signataire pour affichage sous la signature
        signer_info = {
            'name': user_acc.name if hasattr(user_acc, 'name') else None,
            'sub_name': user_acc.sub_name if hasattr(user_acc, 'sub_name') else None,
            'function': user_acc.function if hasattr(user_acc, 'function') else None,
            'email': user_acc.email if hasattr(user_acc, 'email') else None
        }
        # is_workflow=True pour ne pas invalider les signatures précédentes
        input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, pages, signer_obj, signer_stamp_img, signer_info, is_workflow=True)

        # Sauvegarde du PDF signé
        new_signed_pdf_folder = os.path.join(SIGNED_PDF_FOLDER, subfolder)
        os.makedirs(new_signed_pdf_folder, exist_ok=True)
        final_signed_pdf_path = os.path.join(new_signed_pdf_folder, new_filename)
        relative_file_path = os.path.relpath(final_signed_pdf_path, SIGNED_PDF_FOLDER).replace("\\", "/")
        with open(final_signed_pdf_path, 'wb') as f:
            f.write(input_pdf_buffer.getvalue())

        # Mise à jour de la base de données
        current_signer.status = "signed"
        current_signer.signed_at = datetime.utcnow()
        document.file_path = relative_file_path
        db.session.commit()

        # Notification du signataire suivant (fonction présumée définie ailleurs)
        notify_next_signer(document_id)

        # Si tous les signataires (hors "prepared") ont signé, marquer le document comme terminé et notifier
        all_signers = Signer.query.filter_by(document_id=document_id).all()
        if all(s.status in ["signed", "prepared"] for s in all_signers):
            document.status = "signed"
            document.signed_file_path = relative_file_path
            db.session.commit()
            for signer in all_signers:
                if signer.account_type == "external":
                    recipient = Contact.query.get(signer.signer_id)
                else:
                    recipient = User.query.get(signer.signer_id)
                if recipient:
                    download_link = url_for(
                        'sign_and_assign_bp.download_file',
                        subfolder=subfolder,
                        filename=new_filename,
                        _external=True
                    )
                    subject = f"Document {document.name} - Signatures terminées"
                    recipient_name = getattr(recipient, 'name', recipient.email)
                    body = (
                        f"Bonjour {recipient_name},\n\nLe document {document.name} a été signé par tous les signataires actifs.\n\n"
                        f"Vous pouvez télécharger la version finale ici : {download_link}"
                    )
                    html = render_template(
                        "final_document_email.html",
                        name=recipient_name,
                        document_name=document.name,
                        document_url=download_link,
                        current_year=datetime.now().year
                    )
                    send_email(subject, recipient.email, body, html)
                    if hasattr(recipient, 'phone') and recipient.phone:
                        clean_phone = ''.join(filter(str.isdigit, recipient.phone))
                        if clean_phone:
                            whatsapp_message = (
                                f"Bonjour {recipient_name},\n\nLe document {document.name} a été signé par tous les signataires actifs.\n\n"
                                f"Vous pouvez le télécharger ici : {download_link}"
                            )
                            send_whatsapp_notification(clean_phone, whatsapp_message)

        full_signed_pdf_url = url_for(
            'sign_and_assign_bp.download_file',
            subfolder=subfolder,
            filename=new_filename,
            _external=True
        )
        return jsonify({"message": "Document signé avec succès.", "doc_signed": full_signed_pdf_url}), 200

    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Erreur de base de données."}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Erreur: {str(e)}"}), 500


@sign_and_assign_bp.route('/sign-recep-pdf-multiple', methods=['POST'])
def sign_document_multiple():
    """
    Endpoint pour un signataire (interne ou externe) qui signe plusieurs documents en circulation associés à un batch_uuid.
    Marque les pièces jointes (documents avec une seule entrée dans signers et status='prepared') comme 'signed' après que
    tous les signataires des documents normaux du batch ont signé.
    """
    try:
        signer_id = request.form.get('signer_id')
        batch_uuid = request.form.get('batch_uuid')
        if not signer_id or not batch_uuid:
            return jsonify({"error": "Les champs signer_id et batch_uuid sont obligatoires."}), 400

        current_app.logger.info(f"Processing signature for signer_id: {signer_id}, batch_uuid: {batch_uuid}")

        # Récupérer tous les signataires pour ce batch_uuid
        signer_records = Signer.query.filter_by(signer_id=signer_id, batch_uuid=batch_uuid).all()
        if not signer_records:
            return jsonify({"error": "Aucun signataire trouvé pour ce batch_uuid."}), 404

        # Récupérer les documents associés
        document_ids = list(set(signer.document_id for signer in signer_records))
        documents = Document.query.filter(Document.id.in_(document_ids)).all()
        if not documents:
            return jsonify({"error": "Aucun document trouvé pour ce batch_uuid."}), 404

        results = []
        errors = []

        # Traiter chaque document
        for document in documents:
            try:
                current_app.logger.info(f"Processing document_id: {document.id}")

                # Récupérer le signataire courant pour ce document
                current_signer = next((s for s in signer_records if s.document_id == document.id), None)
                if not current_signer:
                    errors.append({"document_id": document.id, "error": "Signataire introuvable pour ce document."})
                    continue
                if current_signer.status == "signed":
                    results.append({
                        "document_id": document.id,
                        "message": "Document déjà signé.",
                        "doc_signed": document.file_path
                    })
                    continue

                # Vérification de l'ordre de signature
                all_signers = Signer.query.filter_by(document_id=document.id).order_by(Signer.priority).all()
                active_signers = [s for s in all_signers if s.status != "prepared"]
                signed_signers = [s for s in active_signers if s.status == "signed"]
                max_signed_priority = max([s.priority for s in signed_signers], default=0)
                if current_signer.priority > max_signed_priority + 1:
                    pending_before = [s for s in active_signers if s.priority < current_signer.priority and s.status == "pending"]
                    if pending_before:
                        errors.append({
                            "document_id": document.id,
                            "error": "D'autres signataires doivent signer avant vous.",
                            "pending_count": len(pending_before)
                        })
                        continue

                # Récupération de l'initiateur (priority=0)
                initiator = Signer.query.filter_by(document_id=document.id, priority=0).first()
                if not initiator:
                    errors.append({"document_id": document.id, "error": "Initiateur du document introuvable."})
                    continue
                initiator_user = User.query.get(initiator.signer_id)
                if not initiator_user:
                    errors.append({"document_id": document.id, "error": "Utilisateur initiateur introuvable."})
                    continue

                # Construction du sous-dossier
                company_part = f"companies/{initiator_user.company.name.replace(' ', '_')}/" if initiator_user.account_type == "employee" and initiator_user.company_id else ""
                user_part = f"users/{initiator_user.email}/"
                subfolder = f"{company_part}{user_part}".rstrip('/')

                # Identification du signataire courant
                if current_signer.account_type in ["employee", "individual"]:
                    user_acc = User.query.get(current_signer.signer_id)
                elif current_signer.account_type == "external":
                    user_acc = Contact.query.get(current_signer.signer_id)
                else:
                    errors.append({"document_id": document.id, "error": "Type de compte du signataire inconnu."})
                    continue
                if not user_acc:
                    errors.append({"document_id": document.id, "error": "Utilisateur ou contact introuvable."})
                    continue

                # CORRECTION: Vérifier si le contact externe a un compte associé
                is_external_with_account = False
                if current_signer.account_type == "external" and hasattr(user_acc, 'user_account_id') and user_acc.user_account_id:
                    # Ce contact a un compte utilisateur associé, utiliser ce compte pour la signature
                    associated_user = User.query.get(user_acc.user_account_id)
                    if associated_user:
                        current_app.logger.info(f"Contact externe {user_acc.email} a un compte associé (User ID: {associated_user.id})")
                        user_acc = associated_user
                        is_external_with_account = True

                company = None
                if hasattr(user_acc, 'company_id') and user_acc.company_id:
                    company = Company.query.get(user_acc.company_id)

                # Chargement de l'image de signature directement en objet PIL
                # pour éviter la perte de qualité liée au cycle save/reload via fichier temporaire
                signer_stamp_img = None
                if current_signer.account_type == "external" and not is_external_with_account:
                    # Contact externe sans compte associé: demander l'upload de l'image
                    if 'signature_image' not in request.files:
                        errors.append({
                            "document_id": document.id,
                            "error": "Le fichier 'signature_image' est obligatoire pour un signataire externe."
                        })
                        continue
                    file_img = request.files['signature_image']
                    if file_img.filename == '':
                        errors.append({"document_id": document.id, "error": "Aucun fichier de signature n'a été fourni."})
                        continue
                    file_img.stream.seek(0)
                    signer_stamp_img = Image.open(file_img.stream)
                else:
                    # Utilisateur avec compte (ou contact avec compte associé): utiliser l'image de signature du compte
                    signer_stamp_img = load_signature_image(user_acc)
                    if not signer_stamp_img:
                        errors.append({"document_id": document.id, "error": "Image de signature introuvable."})
                        continue

                # Récupération des certificats
                current_app.logger.info(f"Retrieving certificates for user_acc: {user_acc.id}, document_id: {document.id}")
                cert_path, key_path, cert_chain = retrieve_certificates(user_acc, company, document.id)
                if not cert_path or not key_path:
                    errors.append({"document_id": document.id, "error": "Certificat ou clé privée introuvable."})
                    continue
                current_app.logger.info(f"Certificates retrieved: cert_path={cert_path}, key_path={key_path}, cert_chain={cert_chain}")

                # Charger le signataire PDF
                signer_obj = signers.SimpleSigner.load(
                    key_file=key_path,
                    cert_file=cert_path,
                    ca_chain_files=cert_chain
                )

                # Détermination du dossier source du PDF
                all_signers_db = Signer.query.filter_by(document_id=document.id).all()
                if all(s.status == "pending" for s in all_signers_db):
                    source_folder = DRAFT_PDF_FOLDER
                else:
                    source_folder = SIGNED_PDF_FOLDER
                source_pdf_path = os.path.join(source_folder, document.file_path)
                current_app.logger.info(f"Checking source PDF path: {source_pdf_path}")
                if not os.path.exists(source_pdf_path):
                    alternate_folder = DRAFT_PDF_FOLDER if source_folder == SIGNED_PDF_FOLDER else SIGNED_PDF_FOLDER
                    alternate_path = os.path.join(alternate_folder, document.file_path)
                    if os.path.exists(alternate_path):
                        source_pdf_path = alternate_path
                        current_app.logger.info(f"Using alternate path: {alternate_path}")
                    else:
                        errors.append({
                            "document_id": document.id,
                            "error": "Document source introuvable",
                            "details": {
                                "tried_paths": [source_pdf_path, alternate_path],
                                "document_path": document.file_path
                            }
                        })
                        continue

                # Chargement du PDF source en mémoire
                current_app.logger.info(f"Loading PDF from: {source_pdf_path}")
                with open(source_pdf_path, 'rb') as pdf_file:
                    pdf_content = pdf_file.read()
                    input_pdf_buffer = BytesIO(pdf_content)

                # Calcul de l'URL finale et génération d'un nouveau nom de fichier pour le document signé
                new_filename = f"signed_pdf_{uuid.uuid4().hex}.pdf"
                if max_signed_priority == 0:
                    final_signed_pdf_url = url_for(
                        'sign_and_assign_bp.download_file',
                        subfolder=subfolder,
                        filename=new_filename,
                        _external=True
                    )
                else:
                    new_filename = os.path.basename(document.file_path)
                    final_signed_pdf_url = url_for(
                        'sign_and_assign_bp.download_file',
                        subfolder=subfolder,
                        filename=new_filename,
                        _external=True
                    )

                # Insertion du QR code uniquement pour le premier signataire
                if max_signed_priority == 0 and hasattr(initiator, 'qr_positions') and initiator.qr_positions:
                    try:
                        qr_positions = (
                            json.loads(initiator.qr_positions)
                            if isinstance(initiator.qr_positions, str)
                            else initiator.qr_positions
                        )
                    except Exception as e:
                        current_app.logger.warning(f"Failed to parse QR positions: {str(e)}")
                        qr_positions = []
                    for qr in qr_positions:
                        qr['data'] = final_signed_pdf_url
                    temp_params = {"qrcodes": qr_positions}
                    input_pdf_buffer = apply_qr_codes(input_pdf_buffer, temp_params, user_acc, final_signed_pdf_url)
                else:
                    new_filename = os.path.basename(document.file_path)
                    final_signed_pdf_url = url_for(
                        'sign_and_assign_bp.download_file',
                        subfolder=subfolder,
                        filename=new_filename,
                        _external=True
                    )

                # Transformation des positions de signature
                pages_dict = {}
                for pos in current_signer.positions:
                    page = pos.get("page", 0)
                    if page not in pages_dict:
                        pages_dict[page] = []
                    pages_dict[page].append(pos)
                pages = [{"page": p, "signatures": pages_dict[p]} for p in pages_dict]

                # Application de la signature
                current_app.logger.info(f"Applying signature to document_id: {document.id}")
                # Préparer les infos du signataire pour affichage sous la signature
                signer_info = {
                    'name': user_acc.name if hasattr(user_acc, 'name') else None,
                    'sub_name': user_acc.sub_name if hasattr(user_acc, 'sub_name') else None,
                    'function': user_acc.function if hasattr(user_acc, 'function') else None,
                    'email': user_acc.email if hasattr(user_acc, 'email') else None
                }
                # is_workflow=True pour ne pas invalider les signatures précédentes
                input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, pages, signer_obj, signer_stamp_img, signer_info, is_workflow=True)

                # Sauvegarde du PDF signé
                new_signed_pdf_folder = os.path.join(SIGNED_PDF_FOLDER, subfolder)
                os.makedirs(new_signed_pdf_folder, exist_ok=True)
                final_signed_pdf_path = os.path.join(new_signed_pdf_folder, new_filename)
                relative_file_path = os.path.relpath(final_signed_pdf_path, SIGNED_PDF_FOLDER).replace("\\", "/")
                current_app.logger.info(f"Saving signed PDF to: {final_signed_pdf_path}")
                with open(final_signed_pdf_path, 'wb') as f:
                    f.write(input_pdf_buffer.getvalue())

                # Mise à jour de la base de données
                current_signer.status = "signed"
                current_signer.signed_at = datetime.utcnow()
                document.file_path = relative_file_path

                # Vérifier si le document est entièrement signé
                all_signers = Signer.query.filter_by(document_id=document.id).all()
                if all(s.status in ["signed", "prepared"] for s in all_signers):
                    document.status = "signed"
                    document.signed_file_path = relative_file_path
                    current_app.logger.info(f"Document {document.id} fully signed, notifying all signers")
                    for signer in all_signers:
                        if signer.account_type == "external":
                            recipient = Contact.query.get(signer.signer_id)
                        else:
                            recipient = User.query.get(signer.signer_id)
                        if recipient:
                            download_link = url_for(
                                'sign_and_assign_bp.download_file',
                                subfolder=subfolder,
                                filename=new_filename,
                                _external=True
                            )
                            subject = f"Document {document.name} - Signatures terminées"
                            recipient_name = getattr(recipient, 'name', recipient.email)
                            body = (
                                f"Bonjour {recipient_name},\n\nLe document {document.name} a été signé par tous les signataires actifs.\n\n"
                                f"Vous pouvez télécharger la version finale ici : {download_link}"
                            )
                            html = render_template(
                                "final_document_email.html",
                                name=recipient_name,
                                document_name=document.name,
                                document_url=download_link,
                                current_year=datetime.now().year
                            )
                            send_email(subject, recipient.email, body, html)
                            if hasattr(recipient, 'phone') and recipient.phone:
                                clean_phone = ''.join(filter(str.isdigit, recipient.phone))
                                if clean_phone:
                                    whatsapp_message = (
                                        f"Bonjour {recipient_name},\n\nLe document {document.name} a été signé par tous les signataires actifs.\n\n"
                                        f"Vous pouvez le télécharger ici : {download_link}"
                                    )
                                    send_whatsapp_notification(clean_phone, whatsapp_message)

                # Notification du signataire suivant
                current_app.logger.info(f"Notifying next signer for document_id: {document.id}")
                notify_next_signer(document.id)

                # Ajouter le résultat pour ce document
                results.append({
                    "document_id": document.id,
                    "message": "Document signé avec succès.",
                    "doc_signed": final_signed_pdf_url
                })

            except Exception as e:
                current_app.logger.error(f"Error processing document_id {document.id}: {str(e)}", exc_info=True)
                errors.append({"document_id": document.id, "error": f"Erreur lors de la signature : {str(e)}"})
                continue

        # Vérifier et mettre à jour les pièces jointes
        # Étape 1 : Identifier les documents normaux et les pièces jointes
        from sqlalchemy import func
        all_batch_documents = Document.query.filter_by(batch_id=batch_uuid).all()
        document_signer_counts = {}
        signer_counts_query = db.session.query(
            Signer.document_id,
            func.count(Signer.id).label('signer_count'),
            func.min(Signer.status).label('status')
        ).filter(Signer.batch_uuid == batch_uuid).group_by(Signer.document_id).all()
        for row in signer_counts_query:
            document_signer_counts[row.document_id] = {
                "signer_count": row.signer_count,
                "is_attachment": row.signer_count == 1 and row.status == "prepared"
            }

        # Étape 2 : Vérifier si tous les signataires des documents normaux ont signé
        all_normal_docs_signed = True
        for document in all_batch_documents:
            if document.id not in document_signer_counts:
                continue  # Document sans signataire, ignorer
            info = document_signer_counts[document.id]
            if not info["is_attachment"]:  # Document normal
                all_signers = Signer.query.filter_by(document_id=document.id).all()
                if not all(s.status == "signed" for s in all_signers if s.priority != 0):  # Ignorer l'initiateur
                    all_normal_docs_signed = False
                    break

        # Étape 3 : Si tous les signataires des documents normaux ont signé, marquer les pièces jointes comme signées
        if all_normal_docs_signed:
            for document in all_batch_documents:
                if document.id in document_signer_counts and document_signer_counts[document.id]["is_attachment"]:
                    document.status = "signed"
                    document.signed_file_path = document.file_path
                    current_app.logger.info(f"Pièce jointe {document.id} (nom: {document.name}) marquée comme signée pour batch {batch_uuid}")

        # Étape 4 : Cas spécial - Batch avec uniquement des pièces jointes
        if all(info["is_attachment"] for info in document_signer_counts.values()):
            current_app.logger.info(f"Le batch {batch_uuid} ne contient que des pièces jointes")
            for document in all_batch_documents:
                if document.id in document_signer_counts and document_signer_counts[document.id]["is_attachment"]:
                    document.status = "signed"
                    document.signed_file_path = document.file_path
                    current_app.logger.info(f"Pièce jointe {document.id} (nom: {document.name}) marquée comme signée (batch uniquement pièces jointes)")

        # Valider les modifications en base de données
        try:
            db.session.commit()
            current_app.logger.info("Database commit successful")
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database commit failed: {str(e)}", exc_info=True)
            return jsonify({
                "error": f"Erreur de base de données : {str(e)}",
                "results": results,
                "errors": errors
            }), 500

        # Retourner la réponse
        if not results and errors:
            return jsonify({"error": "Aucun document n'a pu être signé.", "errors": errors}), 400
        return jsonify({
            "message": f"{len(results)} document(s) signé(s) avec succès.",
            "results": results,
            "errors": errors
        }), 200 if not errors else 207

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


def retrieve_document(user, document_id):
    document = Document.query.get(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    if document.user_id != user.id:
        raise ValueError("Vous n'avez pas la permission d'accéder à ce document.")
    return document


def parse_request_content(request):
    params = {}
    file_url = None
    file = None

    if request.content_type == "application/json":
        try:
            params = request.json.get("params", {})
            file_url = request.json.get("file_url")
            # Récupérer la date limite et l'urgence
            params["deadline"] = request.json.get("deadline")
            params["urgency"] = request.json.get("urgency", UrgencyEnum.NORMAL)
        except Exception as e:
            raise ValueError(f"Le JSON fourni est invalide ou manquant : {str(e)}")
    elif request.content_type.startswith("multipart/form-data"):
        raw_params = request.form.get("params", "{}")
        try:
            params = json.loads(raw_params)
            file_url = request.form.get("file_url")
            file = request.files.get("file")
            # Récupérer la date limite et l'urgence
            params["deadline"] = request.form.get("deadline")
            params["urgency"] = request.form.get("urgency", UrgencyEnum.NORMAL)
        except json.JSONDecodeError as e:
            raise ValueError(f"Les paramètres JSON dans form-data sont invalides : {str(e)}")
    else:
        raise ValueError("Type de contenu non pris en charge.")

    if not isinstance(params, dict):
        raise ValueError("Les paramètres JSON sont mal structurés ou manquants.")

    return params, file_url, file


def update_existing_document(document, params, relative_file_path):
    """
    Met à jour un Document existant (file_path, name, status...).
    """
    document.file_path = relative_file_path
    document.name = params.get("name", document.name)
    document.description = params.get("description", document.description)
    document.status = params.get("status", document.status)
    document.deadline = params.get("deadline")
    document.urgency = params.get("urgency", UrgencyEnum.NORMAL)
    db.session.commit()

def create_new_document(user, params, relative_file_path):
    """
    Crée un nouveau Document (status="pending").
    """
    document = Document(
        name=params.get("name", "Document sans nom"),
        file_path=relative_file_path,
        status="pending",
        user_id=user.id,
        description=params.get("description", ""),
        deadline=params.get("deadline"),
        urgency=params.get("urgency", UrgencyEnum.NORMAL)
    )
    db.session.add(document)
    db.session.commit()
    return document

def send_whatsapp_notification(phone_number, message):
    """
    Envoie une notification WhatsApp à un numéro donné.
    Le numéro doit être au format international sans le +
    """
    try:
        conn = http.client.HTTPSConnection("waapi.app")
        payload = json.dumps({
            "chatId": f"{phone_number}@c.us",
            "message": message
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer vse7etIiNMrUoXuignxqPFU3RLUPozeNCkyW1CTX14ce82f1'
        }
        conn.request("POST", "/api/v1/instances/36424/client/action/send-message", payload, headers)
        response = conn.getresponse()
        data = response.read()
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi WhatsApp: {str(e)}")
        return None