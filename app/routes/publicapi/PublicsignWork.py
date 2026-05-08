import json
import traceback

from flask import Blueprint, request, jsonify, send_from_directory, current_app
from pathlib import Path
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.utils.debug_logger import (
    signature_logger, 
    log_signature_process, 
    log_image_info, 
    log_api_request,
    log_error,
    create_session_log,
    close_session_log
)
from app.utils.public_signature_utils import (
    retrieve_certificates,
    retrieve_certificates_by_email,
    parse_request_content,
    load_signature_image,
    load_pdf,
    update_signature_volumes,
    get_user_company,
    validate_signature_volumes,
    validate_signature_params,
    process_document_consent,
    create_pdf_signer,
    apply_optional_texts,
    apply_stamp,
    prepare_pdf_paths,
    apply_qr_codes,
    sign_pdf_pages,
    save_final_pdf,
    update_document_record,
    prepare_signature_image,
    add_vertical_text_to_pdf,
    add_qr_code_to_pdf,
    generate_qr_code_image,
    mm_to_points,
    extract_certificate_and_key
)
from app.models import db, Document, Contact, Signer, User, CertTypeEnum
from datetime import datetime
import uuid
import os
import tempfile
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

publicapi_signature_bp = Blueprint('publicapi_signature_bp', __name__)

SIGNED_PDF_FOLDER = Path("documents/doc_signed")
SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)
COMPANY_SIGNATURE_FOLDER = Path("signatures/companies")

@publicapi_signature_bp.route('/documents/doc_signed/<path:subfolder>/<filename>', methods=['GET'])
def download_file(subfolder, filename):
    """
    Endpoint pour télécharger un fichier signé en fonction du sous-dossier.
    """
    file_path = SIGNED_PDF_FOLDER / subfolder / filename

    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404

    return send_from_directory((SIGNED_PDF_FOLDER / subfolder).resolve(), filename)

@publicapi_signature_bp.route('/sign-pdf', methods=['POST'])
@require_api_key
def sign_pdf():
    """
    Point d'entrée pour la signature d'un PDF.
    Authentification par API key requise.
    """
    try:
        # 1. Récupération et validation de l'utilisateur et de son entreprise
        user = get_authenticated_user_by_api_key()
        company = get_user_company(user)
        validate_signature_volumes(user, company)

        # 2. Récupération des certificats et du cachet du signataire
        cert_path, key_path, cert_chain = retrieve_certificates(user, company)
        if not cert_path or not key_path:
            return jsonify({"error": "Certificat ou clé privée introuvable."}), 400
        signer_stamp = load_signature_image(user)

        # 3. Analyse et validation de la requête
        params, file_url, file = parse_request_content(request)
        validate_signature_params(params)

        # 4. Gestion du consentement et récupération du document le cas échéant
        document = process_document_consent(user, company, params)

        # 5. Préparation du signataire PDF
        signer = create_pdf_signer(key_path, cert_path, cert_chain)

        # 6. Chargement du PDF et application des modifications avant signature
        input_pdf_buffer = load_pdf(file, file_url)
        input_pdf_buffer = apply_optional_texts(input_pdf_buffer, params)
        input_pdf_buffer = apply_stamp(input_pdf_buffer, user, params)

        # 7. Préparation de l'emplacement de sauvegarde et de l'URL finale
        full_signed_pdf_url, relative_file_path, signed_pdf_path = prepare_pdf_paths(user, company)

        # 8. Application des QR codes (mise à jour des données si nécessaire)
        input_pdf_buffer = apply_qr_codes(input_pdf_buffer, params, user, full_signed_pdf_url)

        # 9. Application des signatures sur chaque page concernée avec informations de l'utilisateur
        user_info = {
            'name': user.name if hasattr(user, 'name') and user.name else user.email,
            'sub_name': user.sub_name if hasattr(user, 'sub_name') else '',
            'function': 'Utilisateur authentifié',
            'grade': params.get('grade', ''),
            'show_legal_mention': params.get('show_legal_mention', False),
            'document_type': params.get('document_type', ''),
            'legal_mention_x': params.get('legal_mention_x'),
            'legal_mention_y': params.get('legal_mention_y'),
            'show_signer_details': params.get('show_signer_details', False),
            'signer_details_x': params.get('signer_details_x'),
            'signer_details_y': params.get('signer_details_y')
        }
        input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, params["pages"], signer, signer_stamp, user_info, signature_size=params.get('signature_size'))

        # 10. Enregistrement du PDF final sur le disque
        save_final_pdf(input_pdf_buffer, signed_pdf_path)

        # 11. Mise à jour de la base de données
        update_document_record(user, params, document, relative_file_path)
        update_signature_volumes(user, company, 1)
        db.session.commit()

        return jsonify({
            "message": "Document signé avec succès.",
            "doc_signed": full_signed_pdf_url
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la signature : {str(e)}")
        return jsonify({"error": f"Erreur lors de la signature : {str(e)}"}), 500

@publicapi_signature_bp.route('/sign-pdfs', methods=['POST'])
@require_api_key
def sign_multiple_pdfs():
    """
    Point d'entrée pour la signature de plusieurs PDFs via JSON.
    """
    try:
        # 1. Récupération et validation de l'utilisateur et de son entreprise
        user = get_authenticated_user_by_api_key()
        company = get_user_company(user)
        validate_signature_volumes(user, company)

        # 2. Récupération des certificats et du cachet du signataire
        cert_path, key_path, cert_chain = retrieve_certificates(user, company)
        if not cert_path or not key_path:
            return jsonify({"error": "Certificat ou clé privée introuvable."}), 400
        signer_stamp = load_signature_image(user)

        # 3. Vérification du corps JSON
        data = request.get_json()
        if not data or 'documents' not in data or not data['documents']:
            return jsonify({"error": "Aucun document fourni."}), 400

        signed_results = []
        total_signatures = 0

        # 4. Traiter chaque document
        for doc in data['documents']:
            file_url = doc.get('file_url')
            params = doc.get('params')
            if not file_url or not params:
                return jsonify({"error": "file_url ou params manquants pour un document."}), 400

            # 5. Validation des paramètres
            validate_signature_params(params)

            # 6. Gestion du consentement et récupération du document
            document = process_document_consent(user, company, params)

            # 7. Préparation du signataire PDF
            signer = create_pdf_signer(key_path, cert_path, cert_chain)

            # 8. Chargement du PDF
            input_pdf_buffer = load_pdf(None, file_url)  # Aucun fichier uploadé, seulement file_url

            # 9. Application des modifications avant signature
            input_pdf_buffer = apply_optional_texts(input_pdf_buffer, params)
            input_pdf_buffer = apply_stamp(input_pdf_buffer, user, params)

            # 10. Préparation des chemins de sauvegarde
            full_signed_pdf_url, relative_file_path, signed_pdf_path = prepare_pdf_paths(user, company)

            # 11. Application des QR codes
            input_pdf_buffer = apply_qr_codes(input_pdf_buffer, params, user, full_signed_pdf_url)

            # 12. Application des signatures avec informations de l'utilisateur
            user_info = {
                'name': user.name if hasattr(user, 'name') and user.name else user.email,
                'sub_name': user.sub_name if hasattr(user, 'sub_name') else '',
                'function': 'Utilisateur authentifié',
                'grade': params.get('grade', ''),
                'show_legal_mention': params.get('show_legal_mention', False),
                'document_type': params.get('document_type', ''),
                'legal_mention_x': params.get('legal_mention_x'),
                'legal_mention_y': params.get('legal_mention_y'),
                'show_signer_details': params.get('show_signer_details', False),
                'signer_details_x': params.get('signer_details_x'),
                'signer_details_y': params.get('signer_details_y')
            }
            input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, params.get("pages", []), signer, signer_stamp, user_info, signature_size=params.get('signature_size'))

            # 13. Enregistrement du PDF final
            save_final_pdf(input_pdf_buffer, signed_pdf_path)

            # 14. Mise à jour de la base de données
            update_document_record(user, params, document, relative_file_path)
            total_signatures += 1

            signed_results.append({
                "filename": params.get("name", "Unnamed"),
                "message": "Document signé avec succès.",
                "doc_signed": full_signed_pdf_url
            })

        # 15. Mise à jour du volume de signatures
        update_signature_volumes(user, company, total_signatures)
        db.session.commit()

        return jsonify({
            "message": f"{len(signed_results)} document(s) signé(s) avec succès.",
            "signed_documents": signed_results
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la signature : {str(e)}")
        return jsonify({"error": f"Erreur lors de la signature : {str(e)}"}), 500


@publicapi_signature_bp.route('/sign-upload-multiple', methods=['POST'])
@require_api_key
def sign_upload_multiple_documents():
    """
    Point d'entrée pour la signature de plusieurs PDFs uploadés avec signataires externes.
    
    Paramètres attendus :
    - documents[] : fichiers PDF à signer
    - signers_data : JSON avec les informations des signataires externes
    - signature_params : JSON avec les paramètres de signature pour chaque document
    
    Format signers_data :
    [
        {
            "name": "Nom du signataire",
            "firstname": "Prénom", 
            "function": "Fonction",
            "email": "signataire@example.com",
            "signature_image": "nom_fichier_signature.png",
            "use_stored_signature": true  # Si true, cherche l'image dans le dossier par email
        }
    ]
    
    Format signature_params :
    [
        {
            "document_index": 0,
            "signer_index": 0,
            "pages": [{"page": 0, "signatures": [{"x": 100, "y": 200}]}],
            "stamp_pages": [0],
            "qrcodes": [{"page": 0, "x": 50, "y": 50, "data": "custom_data"}],
            "signature_size": {"width": 150, "height": 50},
            "signature_date": {
                "day": 15,
                "month": 3,
                "year": 2025,
                "hour": 14,
                "minute": 30,
                "second": 45
            }
        }
    ]
    
    Note: Le paramètre "signature_date" est optionnel. Si non fourni, la date/heure actuelle sera utilisée.
    Les champs hour, minute et second sont optionnels (par défaut: 0).
    Vous pouvez aussi passer une string formatée directement: "signature_date": "15/03/2025 à 14:30:45"
    """
    session_id = None
    try:
        # Créer une session de log pour tracer toute la requête
        session_id = create_session_log()
        
        # 1. Récupération et validation de l'utilisateur et de son entreprise
        user = get_authenticated_user_by_api_key()
        log_api_request("/v3/sign-upload-multiple", "POST", user.email)
        signature_logger.info(f"Utilisateur authentifié: {user.email} (Type: {user.account_type})")
        
        company = get_user_company(user)
        if company:
            signature_logger.info(f"Entreprise: {company.name} (Cert type: {company.cert_type})")
        
        validate_signature_volumes(user, company)
        signature_logger.info(f"Volumes validés - User: {user.signature_volume_used}/{user.signature_volume}")

        # 2. Récupération des certificats de l'utilisateur initiateur
        cert_path, key_path, cert_chain = retrieve_certificates(user, company)
        if not cert_path or not key_path:
            return jsonify({"error": "Certificat ou clé privée introuvable."}), 400

        # 3. Vérification des fichiers uploadés
        uploaded_files = request.files.getlist('documents')
        signature_logger.info(f"Fichiers uploadés: {len(uploaded_files)} document(s)")
        
        if not uploaded_files:
            log_error("Aucun document fourni", "Validation")
            return jsonify({"error": "Aucun document fourni."}), 400
        
        # Limite de sécurité pour éviter les problèmes de performance
        MAX_DOCUMENTS_PER_REQUEST = 100
        if len(uploaded_files) > MAX_DOCUMENTS_PER_REQUEST:
            log_error(f"Trop de documents: {len(uploaded_files)}", "Validation")
            return jsonify({
                "error": f"Nombre maximum de documents dépassé. Limite: {MAX_DOCUMENTS_PER_REQUEST} documents par requête."
            }), 400

        # 4. Récupération des données des signataires externes
        signers_data_json = request.form.get('signers_data')
        if not signers_data_json:
            log_error("Données signataires manquantes", "Validation")
            return jsonify({"error": "Données des signataires manquantes."}), 400
        
        try:
            signers_data = json.loads(signers_data_json)
            signature_logger.info(f"Signataires: {len(signers_data)} signataire(s) externes")
        except json.JSONDecodeError as e:
            log_error(e, "Parse JSON signers_data")
            return jsonify({"error": "Format JSON invalide pour signers_data."}), 400

        # 5. Récupération des paramètres de signature
        signature_params_json = request.form.get('signature_params')
        if not signature_params_json:
            return jsonify({"error": "Paramètres de signature manquants."}), 400
        
        try:
            signature_params = json.loads(signature_params_json)
        except json.JSONDecodeError:
            return jsonify({"error": "Format JSON invalide pour signature_params."}), 400

        # 6. Récupération et chargement immédiat des images de signature pour chaque signataire
        signature_images = {}  # Stockera des objets PIL Image, pas des FileStorage
        
        # Fonction helper pour charger une signature stockée
        def load_stored_signature(email):
            """Charge une signature stockée depuis le dossier externe par email."""
            try:
                from app.routes.publicapi.external_signatures_routes import (
                    get_signature_folder_for_email, 
                    ALLOWED_EXTENSIONS
                )
                signature_folder = get_signature_folder_for_email(email)
                
                # Chercher le fichier de signature
                for ext in ALLOWED_EXTENSIONS:
                    signature_file = signature_folder / f"signature.{ext}"
                    if signature_file.exists():
                        sig_image = Image.open(signature_file)
                        if sig_image.mode != 'RGBA':
                            sig_image = sig_image.convert('RGBA')
                        current_app.logger.info(f"✅ Signature chargée depuis le dossier pour {email}: {signature_file}")
                        return sig_image
                
                current_app.logger.warning(f"⚠️ Aucune signature stockée trouvée pour {email}")
                return None
            except Exception as e:
                current_app.logger.error(f"❌ Erreur lors du chargement de la signature stockée pour {email}: {str(e)}")
                return None
        
        # Première méthode : vérifier si use_stored_signature est activé
        for i, signer in enumerate(signers_data):
            # Vérifier explicitement que use_stored_signature est présent et True
            use_stored = signer.get('use_stored_signature')
            signer_email = signer.get('email')
            
            # Ne charger que si explicitement demandé (True) et email fourni
            if use_stored is True and signer_email:
                # Charger depuis le dossier de signatures stockées
                stored_sig = load_stored_signature(signer_email)
                if stored_sig:
                    signature_images[i] = stored_sig
                    log_image_info(i, stored_sig, f"Chargée depuis dossier stocké pour {signer_email}")
                    continue  # Passer au signataire suivant
        
        # Deuxième méthode : récupération par index (signature_image_0, signature_image_1, etc.)
        for i, signer in enumerate(signers_data):
            # Sauter si déjà chargée depuis le dossier stocké
            if i in signature_images:
                continue
                
            image_key = f'signature_image_{i}'
            if image_key in request.files:
                sig_file = request.files[image_key]
                if sig_file and sig_file.filename:
                    try:
                        # Charger immédiatement l'image en objet PIL pour éviter les problèmes de stream
                        sig_file.stream.seek(0)  # Réinitialiser le stream au début
                        sig_image_pil = Image.open(sig_file.stream)
                        
                        # Convertir en RGBA pour garder la transparence (PyHanko supporte RGBA)
                        # Ne PAS convertir en RGB car ça cache le texte du PDF en dessous
                        if sig_image_pil.mode == 'P':
                            # Convertir les images avec palette en RGBA
                            sig_image_pil = sig_image_pil.convert('RGBA')
                        elif sig_image_pil.mode in ('L', 'LA'):
                            # Convertir niveaux de gris en RGBA
                            sig_image_pil = sig_image_pil.convert('RGBA')
                        elif sig_image_pil.mode == 'RGB':
                            # Ajouter un canal alpha aux images RGB (opaque)
                            sig_image_pil = sig_image_pil.convert('RGBA')
                        # Si déjà RGBA, ne rien faire
                        
                        # Stocker l'objet PIL Image (pas le FileStorage)
                        signature_images[i] = sig_image_pil
                        log_image_info(i, sig_image_pil, f"Chargée via clé '{image_key}' - {sig_file.filename}")
                    except Exception as e:
                        log_error(e, f"Chargement image signataire {i} (clé '{image_key}')", traceback.format_exc())
        
        # Troisième méthode : recherche par nom de fichier (fallback)
        for i, signer in enumerate(signers_data):
            # Sauter si déjà chargée
            if i in signature_images:
                continue
            
            if 'signature_image' in signer:
                # Rechercher par nom de fichier
                for key, file in request.files.items():
                    if key.startswith('signature_image_') and file.filename == signer['signature_image']:
                        try:
                            file.stream.seek(0)  # Réinitialiser le stream
                            sig_image_pil = Image.open(file.stream)
                            
                            # Convertir en RGBA pour garder la transparence (PyHanko supporte RGBA)
                            # Ne PAS convertir en RGB car ça cache le texte du PDF en dessous
                            if sig_image_pil.mode == 'P':
                                # Convertir les images avec palette en RGBA
                                sig_image_pil = sig_image_pil.convert('RGBA')
                            elif sig_image_pil.mode in ('L', 'LA'):
                                # Convertir niveaux de gris en RGBA
                                sig_image_pil = sig_image_pil.convert('RGBA')
                            elif sig_image_pil.mode == 'RGB':
                                # Ajouter un canal alpha aux images RGB (opaque)
                                sig_image_pil = sig_image_pil.convert('RGBA')
                            # Si déjà RGBA, ne rien faire
                            
                            signature_images[i] = sig_image_pil
                            current_app.logger.info(f"🖼️ Image chargée pour signataire {i} via nom de fichier '{file.filename}' ({sig_image_pil.size}, {sig_image_pil.mode})")
                            break
                        except Exception as e:
                            current_app.logger.error(f"❌ Erreur lors du chargement de l'image pour signataire {i} (nom '{file.filename}'): {str(e)}")
        
        # NOTE: Ne PAS appeler prepare_signature_image ici - sign_pdf_pages le fait déjà.
        # Un double traitement (double sharpening, double trim) dégrade la qualité.
        
        # Log du résumé des images trouvées
        signature_logger.info(f"📊 RÉSUMÉ: {len(signature_images)} images chargées sur {len(signers_data)} signataires")
        for idx, img in signature_images.items():
            log_image_info(idx, img, "Résumé final")

        # 7. Validation des signataires
        for i, signer in enumerate(signers_data):
            required_fields = ['name', 'firstname', 'function']
            for field in required_fields:
                if not signer.get(field):
                    return jsonify({"error": f"Champ '{field}' manquant pour le signataire {i}."}), 400

        # 8. Traitement de chaque document
        signed_results = []
        total_signatures = 0

        for doc_index, uploaded_file in enumerate(uploaded_files):
            if not uploaded_file or uploaded_file.filename == '':
                continue

            # 9. Filtrer les paramètres de signature pour ce document
            doc_signature_params = [p for p in signature_params if p.get('document_index') == doc_index]
            if not doc_signature_params:
                return jsonify({"error": f"Aucun paramètre de signature trouvé pour le document {doc_index}."}), 400

            # 10. Chargement du PDF uploadé
            input_pdf_buffer = load_pdf(uploaded_file, None)
            if not input_pdf_buffer:
                return jsonify({"error": f"Impossible de charger le document {doc_index}."}), 400

            # 10.1. Détecter le nombre de pages du PDF
            from PyPDF2 import PdfReader
            pdf_reader = PdfReader(input_pdf_buffer)
            total_pages = len(pdf_reader.pages)
            last_page_index = total_pages - 1
            signature_logger.info(f"Document {doc_index}: {total_pages} page(s), dernière page: {last_page_index}")
            
            # Réinitialiser le buffer après lecture
            input_pdf_buffer.seek(0)

            # 11. Préparation des chemins de sauvegarde
            full_signed_pdf_url, relative_file_path, signed_pdf_path = prepare_pdf_paths(user, company)

            # 12. Traiter l'option "sign_on_last_page" pour chaque signataire individuellement
            signataires_avec_last_page = []
            signataires_sans_last_page = []
            
            for param in doc_signature_params:
                if param.get('sign_on_last_page', False):
                    signataires_avec_last_page.append(param)
                else:
                    signataires_sans_last_page.append(param)
            
            # Traiter les signataires avec sign_on_last_page
            if signataires_avec_last_page:
                signature_logger.info(f"📄 {len(signataires_avec_last_page)} signataire(s) avec 'sign_on_last_page' activé")
                
                # Calculer les positions automatiques uniquement pour ceux sans positions personnalisées
                base_y = 250  # Position de départ (haut de la page)
                spacing = 100  # Espacement entre signatures
                base_x = 100  # Position X par défaut
                auto_position_index = 0
                
                for param in signataires_avec_last_page:
                    # Vérifier si des positions personnalisées sont fournies dans pages
                    custom_positions = param.get('pages', [])
                    
                    if custom_positions and len(custom_positions) > 0 and len(custom_positions[0].get('signatures', [])) > 0:
                        # Utiliser les positions personnalisées mais sur la dernière page
                        custom_sig = custom_positions[0]['signatures'][0]
                        x_position = custom_sig.get('x', base_x)
                        y_position = custom_sig.get('y', base_y - (auto_position_index * spacing))
                        signature_logger.info(f"  - Signataire {param.get('signer_index')}: position PERSONNALISÉE (x={x_position}, y={y_position})")
                    else:
                        # Calculer automatiquement la position
                        x_position = param.get('custom_x', base_x)
                        y_position = base_y - (auto_position_index * spacing)
                        signature_logger.info(f"  - Signataire {param.get('signer_index')}: position AUTO (x={x_position}, y={y_position})")
                    
                    # Remplacer les pages par la dernière page avec la position
                    param['pages'] = [
                        {
                            "page": last_page_index,
                            "signatures": [
                                {
                                    "x": x_position,
                                    "y": y_position
                                }
                            ]
                        }
                    ]
                    auto_position_index += 1

            # ================================================================
            # PREMIÈRE PASSE CRITIQUE: Appliquer TOUT le contenu visuel
            # (textes, QR codes, cachets) AVANT toute signature numérique.
            # Toute modification du PDF après une signature invalide le certificat.
            # ================================================================
            current_pdf_buffer = input_pdf_buffer
            
            # 13a. Ajouter tous les textes d'informations signataires
            for param in doc_signature_params:
                show_signer_info = param.get('show_signer_info', False)
                if show_signer_info:
                    signer_index = param.get('signer_index')
                    if signer_index is not None and signer_index < len(signers_data):
                        signer_data = signers_data[signer_index]
                        signer_info = {
                            'name': signer_data.get('name', ''),
                            'sub_name': signer_data.get('firstname', ''),
                            'function': signer_data.get('function', ''),
                            'email': signer_data.get('email', ''),
                            'phone': signer_data.get('phone', '')
                        }
                        
                        pages = param.get('pages', [])
                        for page_params in pages:
                            page_index = page_params.get("page", 0)
                            signatures = page_params.get("signatures", [])
                            
                            for signature in signatures:
                                try:
                                    from app.utils.public_signature_utils import mm_to_points, add_signer_info_text
                                    x = mm_to_points(signature.get("x", 50))
                                    y = mm_to_points(signature.get("y", 100))
                                    
                                    current_pdf_buffer = add_signer_info_text(
                                        current_pdf_buffer,
                                        page_index,
                                        x,
                                        y,
                                        signer_info
                                    )
                                    signature_logger.info(f"✅ Texte ajouté pour signataire {signer_index} sur page {page_index}")
                                except Exception as e:
                                    signature_logger.error(f"⚠️ Erreur ajout texte signataire {signer_index}: {str(e)}")
            
            # 13b. Appliquer TOUS les QR codes de TOUS les signataires AVANT les signatures
            for param in doc_signature_params:
                qrcodes = param.get('qrcodes', [])
                if qrcodes:
                    try:
                        current_pdf_buffer = apply_qr_codes(current_pdf_buffer, {'qrcodes': qrcodes}, user, full_signed_pdf_url)
                        signature_logger.info(f"✅ QR codes appliqués pour signataire {param.get('signer_index')} ({len(qrcodes)} QR code(s))")
                    except Exception as e:
                        signature_logger.error(f"⚠️ Erreur ajout QR codes pour signataire {param.get('signer_index')}: {str(e)}")
            
            # 13c. Appliquer TOUS les cachets de TOUS les signataires AVANT les signatures
            for param in doc_signature_params:
                stamp_pages = param.get('stamp_pages', [])
                if stamp_pages:
                    try:
                        current_pdf_buffer = apply_stamp(current_pdf_buffer, user, {'stamp_pages': stamp_pages})
                        signature_logger.info(f"✅ Cachet appliqué pour signataire {param.get('signer_index')} sur pages {stamp_pages}")
                    except Exception as e:
                        signature_logger.error(f"⚠️ Erreur ajout cachet pour signataire {param.get('signer_index')}: {str(e)}")
            
            signature_logger.info(f"✅ Première passe terminée: textes, QR codes et cachets appliqués. Passage aux signatures numériques.")
            
            # ================================================================
            # DEUXIÈME PASSE: Appliquer les signatures numériques.
            # RIEN ne doit être ajouté au PDF après cette étape.
            # ================================================================
            for param in doc_signature_params:
                signer_index = param.get('signer_index')
                if signer_index is None or signer_index >= len(signers_data):
                    return jsonify({"error": f"Index de signataire invalide : {signer_index}."}), 400

                signer_info = signers_data[signer_index]
                pages = param.get('pages', [])
                
                if not pages:
                    continue

                # 13. Récupération de l'image de signature du signataire externe
                signer_stamp = None
                
                log_signature_process(signer_index, "Début traitement", {"images_disponibles": list(signature_images.keys())})
                
                # Vérifier si une image personnalisée est fournie pour ce signataire
                if signer_index in signature_images:
                    try:
                        # L'image est déjà chargée en objet PIL, il suffit de la récupérer
                        sig_image_pil = signature_images[signer_index]
                        log_image_info(signer_index, sig_image_pil, "Image trouvée dans dictionnaire")
                        
                        # Créer une copie pour éviter de modifier l'original (important si réutilisé)
                        sig_image_pil = sig_image_pil.copy()
                        
                        signer_stamp = sig_image_pil
                        log_image_info(signer_index, signer_stamp, "Image ASSIGNÉE à signer_stamp")
                        log_signature_process(signer_index, "Image personnalisée assignée avec succès")
                        
                    except Exception as e:
                        log_error(e, f"Utilisation image signataire {signer_index}", traceback.format_exc())
                        signer_stamp = None
                else:
                    log_signature_process(signer_index, "Aucune image personnalisée trouvée", level="WARNING")
                
                # Si aucune image spécifique n'est fournie, utiliser l'image par défaut de l'utilisateur
                if signer_stamp is None:
                    try:
                        default_image = load_signature_image(user)
                        
                        if default_image:
                            # Créer une copie pour éviter de modifier l'original
                            signer_stamp = default_image.copy()
                            current_app.logger.info(f"⚠️ Utilisation de l'image de signature par défaut de l'utilisateur pour signataire {signer_index}")
                        else:
                            current_app.logger.warning(f"⚠️ Aucune image par défaut disponible pour l'utilisateur")
                    except Exception as e:
                        current_app.logger.error(f"❌ Impossible de charger l'image de signature par défaut: {str(e)}")
                        current_app.logger.warning(f"⚠️ Signature sans image pour le signataire {signer_index}")

                # 14. Configuration du signataire PyHanko
                # Pour personnePhysique: utiliser le certificat P12 propre au signataire (via son email)
                # Pour cachetServeur ou individual: utiliser le certificat global de l'initiateur
                signer_email_for_cert = signers_data[signer_index].get('email', '')
                if company and company.cert_type == CertTypeEnum.PERSONNE_PHYSIQUE and signer_email_for_cert:
                    try:
                        s_cert_path, s_key_path, s_cert_chain = retrieve_certificates_by_email(signer_email_for_cert, company)
                        signer = create_pdf_signer(s_key_path, s_cert_path, s_cert_chain)
                        signature_logger.info(f"🔐 Certificat personnel chargé pour {signer_email_for_cert} (personnePhysique)")
                    except (ValueError, FileNotFoundError) as cert_err:
                        signature_logger.warning(f"⚠️ Certificat personnel introuvable pour {signer_email_for_cert}: {str(cert_err)}. Utilisation du certificat de l'initiateur.")
                        signer = create_pdf_signer(key_path, cert_path, cert_chain)
                else:
                    signer = create_pdf_signer(key_path, cert_path, cert_chain)

                # 15. Application des signatures sur les pages avec informations du signataire
                signer_info = None
                if signer_index is not None and signer_index < len(signers_data):
                    signer_data = signers_data[signer_index]
                    signer_info = {
                        'name': signer_data.get('name', ''),
                        'sub_name': signer_data.get('firstname', ''),  # Utiliser firstname du JSON
                        'function': signer_data.get('function', ''),
                        'email': signer_data.get('email', ''),
                        'phone': signer_data.get('phone', ''),
                        'grade': signer_data.get('grade', ''),
                        'show_legal_mention': signer_data.get('show_legal_mention', False),
                        'document_type': signer_data.get('document_type', ''),
                        'legal_mention_x': signer_data.get('legal_mention_x'),
                        'legal_mention_y': signer_data.get('legal_mention_y'),
                        'show_signer_details': signer_data.get('show_signer_details', False),
                        'signer_details_x': signer_data.get('signer_details_x'),
                        'signer_details_y': signer_data.get('signer_details_y')
                    }
                
                log_image_info(signer_index, signer_stamp, "AVANT sign_pdf_pages")
                
                # Vérifier que signer_stamp n'est pas None avant d'appeler sign_pdf_pages
                if signer_stamp is None:
                    # Créer une image par défaut simple si aucune image n'est disponible
                    try:
                        # Créer une image par défaut avec le nom du signataire
                        default_width, default_height = 150, 50
                        default_image = Image.new('RGB', (default_width, default_height), color='white')
                        draw = ImageDraw.Draw(default_image)
                        
                        # Texte par défaut
                        signer_name = f"{signer_info.get('name', '')} {signer_info.get('sub_name', '')}".strip()
                        if not signer_name:
                            signer_name = "Signature"
                        
                        # Dessiner un rectangle et le texte
                        draw.rectangle([1, 1, default_width-2, default_height-2], outline='black', width=1)
                        
                        # Essayer d'utiliser une police par défaut
                        try:
                            font = ImageFont.load_default()
                        except:
                            font = None
                        
                        # Calculer la position du texte pour le centrer
                        if font:
                            bbox = draw.textbbox((0, 0), signer_name, font=font)
                            text_width = bbox[2] - bbox[0]
                            text_height = bbox[3] - bbox[1]
                        else:
                            text_width = len(signer_name) * 6  # Estimation
                            text_height = 10
                        
                        text_x = (default_width - text_width) // 2
                        text_y = (default_height - text_height) // 2
                        
                        draw.text((text_x, text_y), signer_name, fill='black', font=font)
                        
                        signer_stamp = default_image
                        current_app.logger.info(f"🖼️ Image par défaut créée pour le signataire {signer_index}: {signer_name}")
                        
                    except Exception as e:
                        current_app.logger.error(f"❌ Impossible de créer une image par défaut pour le signataire {signer_index}: {str(e)}")
                        continue  # Passer ce signataire seulement si on ne peut pas créer d'image par défaut
                
                log_image_info(signer_index, signer_stamp, "Appel sign_pdf_pages")
                
                # Extraire et formater la date de signature personnalisée si fournie
                custom_timestamp = None
                signature_date = param.get('signature_date')
                
                if signature_date:
                    try:
                        # Vérifier si c'est un dict avec les composants de date/heure
                        if isinstance(signature_date, dict):
                            day = signature_date.get('day')
                            month = signature_date.get('month')
                            year = signature_date.get('year')
                            hour = signature_date.get('hour', 0)
                            minute = signature_date.get('minute', 0)
                            second = signature_date.get('second', 0)
                            
                            if day and month and year:
                                # Formater au format "DD/MM/YYYY à HH:MM:SS"
                                custom_timestamp = f"{int(day):02d}/{int(month):02d}/{int(year):04d} à {int(hour):02d}:{int(minute):02d}:{int(second):02d}"
                                signature_logger.info(f"📅 Date de signature personnalisée pour signataire {signer_index}: {custom_timestamp}")
                        # Sinon, si c'est déjà une string formatée, l'utiliser directement
                        elif isinstance(signature_date, str):
                            custom_timestamp = signature_date
                            signature_logger.info(f"📅 Date de signature personnalisée (string) pour signataire {signer_index}: {custom_timestamp}")
                    except Exception as e:
                        signature_logger.warning(f"⚠️ Erreur lors du formatage de la date personnalisée pour signataire {signer_index}: {str(e)}. Utilisation de la date actuelle.")
                        custom_timestamp = None
                
                # NOTE: show_signer_info est forcé à False car les textes ont déjà été ajoutés
                # dans la première passe pour éviter d'invalider les certificats
                current_pdf_buffer = sign_pdf_pages(
                    current_pdf_buffer, 
                    pages, 
                    signer, 
                    signer_stamp, 
                    signer_info,
                    show_signer_info=False,  # Textes déjà ajoutés avant
                    custom_timestamp=custom_timestamp,  # Date personnalisée ou None
                    signature_size=param.get('signature_size')  # Taille personnalisée
                )
                log_signature_process(signer_index, "sign_pdf_pages terminé avec succès")

                # NOTE: QR codes et cachets ont déjà été appliqués dans la première passe
                # Ne RIEN ajouter au PDF après la signature numérique pour ne pas invalider le certificat

            # 18. Sauvegarde du PDF final
            save_final_pdf(current_pdf_buffer, signed_pdf_path)

            # 19. Création d'un enregistrement de document en base
            try:
                document_name = uploaded_file.filename or f"document_{doc_index}.pdf"
                new_document = Document(
                    name=document_name,
                    file_path=relative_file_path,
                    user_id=user.id,
                    status="signed",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.session.add(new_document)
                db.session.commit()

                # 20. Création des enregistrements de signataires externes
                for param in doc_signature_params:
                    signer_index = param.get('signer_index')
                    if signer_index is not None and signer_index < len(signers_data):
                        signer_info = signers_data[signer_index]
                        
                        # Construire le nom complet du contact
                        full_contact_name = signer_info['name']
                        if signer_info.get('firstname'):
                            full_contact_name += f" {signer_info['firstname']}"
                        
                        # Gérer l'email du signataire
                        signer_email = signer_info.get('email')
                        external_contact = None
                        
                        if signer_email:
                            # Vérifier si un contact avec cet email existe déjà pour cet utilisateur
                            external_contact = Contact.query.filter_by(
                                user_id=user.id,
                                email=signer_email
                            ).first()
                        
                        if not external_contact:
                            # Créer un nouveau contact si aucun n'existe ou si pas d'email fourni
                            contact_email = signer_email or f"external_{uuid.uuid4().hex}@temp.com"
                            external_contact = Contact(
                                name=full_contact_name,
                                email=contact_email,
                                phone=signer_info.get('phone', ''),
                                user_id=user.id,
                                created_at=datetime.utcnow()
                            )
                            db.session.add(external_contact)
                            db.session.flush()  # Pour obtenir l'ID
                        else:
                            # Mettre à jour les informations du contact existant si nécessaire
                            if signer_info.get('phone') and not external_contact.phone:
                                external_contact.phone = signer_info.get('phone')
                            external_contact.updated_at = datetime.utcnow()

                        # Créer l'enregistrement de signataire
                        signer_record = Signer(
                            document_id=new_document.id,
                            signer_id=external_contact.id,
                            account_type="external",
                            status="signed",
                            priority=signer_index + 1,
                            uuid=str(uuid.uuid4()),
                            created_at=datetime.utcnow(),
                            signed_at=datetime.utcnow()
                        )
                        db.session.add(signer_record)

                db.session.commit()

            except Exception as e:
                current_app.logger.error(f"Erreur lors de la création du document en base : {str(e)}")
                # Continue même si l'enregistrement en base échoue

            signed_results.append({
                "document_name": uploaded_file.filename,
                "signed_pdf_url": full_signed_pdf_url,
                "signers": [{
                    "name": signer['name'],
                    "firstname": signer['firstname'], 
                    "function": signer['function']
                } for signer in signers_data]
            })
            
            # Compter 1 signature par document traité
            total_signatures += 1

        # 21. Mise à jour des volumes de signature
        signature_logger.info(f"Décompte de {total_signatures} document(s) signé(s) pour l'utilisateur {user.email}")
        update_signature_volumes(user, company, total_signatures)
        db.session.commit()
        
        close_session_log(session_id, success=True, message=f"{len(signed_results)} documents signés avec succès")

        return jsonify({
            "message": f"{len(signed_results)} document(s) signé(s) avec succès avec signataires externes.",
            "signed_documents": signed_results,
            "total_signatures": total_signatures
        }), 200

    except Exception as e:
        db.session.rollback()
        error_traceback = traceback.format_exc()
        log_error(e, "Erreur globale sign-upload-multiple", error_traceback)
        if session_id:
            close_session_log(session_id, success=False, message=str(e))
        
        # Retourner l'erreur détaillée avec le traceback pour debug en production
        return jsonify({
            "error": f"Erreur lors de la signature : {str(e)}",
            "error_type": type(e).__name__,
            "traceback": error_traceback.split('\n')[-10:]  # Dernières 10 lignes du traceback
        }), 500


# ================================================================
# ROUTE SPÉCIFIQUE ARCOP
# Signature automatique avec positions prédéfinies
# ================================================================

ARCOP_SIGNATURE_FOLDER = Path("signatures/companies/ARCOP")
ARCOP_CERTIFICATE_FOLDER = Path("certificates/companies/ARCOP")

@publicapi_signature_bp.route('/sign-arcop', methods=['POST'])
@require_api_key
def sign_arcop():
    """
    Route spécifique pour l'ARCOP — signature automatique complète.
    L'ARCOP envoie uniquement le PDF et le nom du signataire.
    Tout le reste est automatique : cachet, QR code, textes d'info, 
    mention verticale, points colorés, référence QNRR, bandeau bas.
    
    Paramètres (form-data):
        - document: Fichier PDF à signer (obligatoire, ou file_url)
        - file_url: URL du PDF si pas de fichier uploadé (alternatif)
        - signer_name: Nom du signataire (ex: "OUATTARA Oumar") - obligatoire
    """
    try:
        # 1. Authentification et validation
        user = get_authenticated_user_by_api_key()
        company = get_user_company(user)
        validate_signature_volumes(user, company)

        # 2. Paramètre obligatoire : nom du signataire
        signer_name = request.form.get('signer_name', '').strip()
        if not signer_name:
            return jsonify({"error": "Le paramètre 'signer_name' est obligatoire."}), 400

        # 3. Récupération des certificats de l'entreprise
        cert_path, key_path, cert_chain = retrieve_certificates(user, company)
        if not cert_path or not key_path:
            return jsonify({"error": "Certificat ou clé privée introuvable."}), 400
        signer = create_pdf_signer(key_path, cert_path, cert_chain)

        # 4. Chargement de l'image de signature (cachet) depuis le dossier de l'entreprise
        company_sig_folder = Path("signatures/companies") / company.name
        arcop_sig_path = None
        for ext in ['png', 'jpg', 'jpeg']:
            candidate = company_sig_folder / f"signature.{ext}"
            if candidate.exists():
                arcop_sig_path = candidate
                break
        if not arcop_sig_path and company_sig_folder.exists():
            for f in company_sig_folder.iterdir():
                if f.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                    arcop_sig_path = f
                    break
        if not arcop_sig_path:
            return jsonify({"error": f"Image de signature introuvable dans {company_sig_folder}"}), 400

        signer_stamp = Image.open(arcop_sig_path)
        if signer_stamp.mode != 'RGBA':
            signer_stamp = signer_stamp.convert('RGBA')
        current_app.logger.info(f"✅ Cachet ARCOP chargé: {arcop_sig_path} ({signer_stamp.size})")

        # 5. Chargement du PDF
        uploaded_file = request.files.get('document')
        file_url = request.form.get('file_url')
        if uploaded_file and uploaded_file.filename:
            input_pdf_buffer = load_pdf(uploaded_file, None)
        elif file_url:
            input_pdf_buffer = load_pdf(None, file_url)
        else:
            return jsonify({"error": "Aucun document fourni. Utilisez 'document' (fichier) ou 'file_url' (URL)."}), 400
        if not input_pdf_buffer:
            return jsonify({"error": "Impossible de charger le document."}), 400

        # 6. Analyse du PDF (nombre de pages, dimensions dernière page)
        from PyPDF2 import PdfReader
        input_pdf_buffer.seek(0)
        pdf_reader = PdfReader(input_pdf_buffer)
        total_pages = len(pdf_reader.pages)
        last_page = total_pages - 1
        lp = pdf_reader.pages[last_page]
        page_w = float(lp.mediabox.width)
        page_h = float(lp.mediabox.height)
        input_pdf_buffer.seek(0)
        current_app.logger.info(f"📄 ARCOP: {total_pages} pages, dernière={page_w:.0f}x{page_h:.0f} pts")

        # 7. Préparation des chemins de sauvegarde
        full_signed_pdf_url, relative_file_path, signed_pdf_path = prepare_pdf_paths(user, company)

        # ================================================================
        # CONSTANTES ARCOP (positions basées sur le modèle de document)
        # Le document contient DÉJÀ : points orange/vert, QNRR, bandeau,
        # www.arcop.ci, 800 00 100, "Digitally signed by", "Signé électroniquement"
        # L'API ajoute UNIQUEMENT : QR code, cachet/signature, nom signataire, mention verticale
        # ================================================================
        QR_DATA = full_signed_pdf_url

        # Positions en mm (origine = bas-gauche du PDF) — calées sur la capture de référence
        QR_X, QR_Y, QR_SIZE = 10, 43, 15        # QR code: petit, tout en bas à gauche
        SIG_X, SIG_Y = 115, 55                   # Cachet: centre-droit, sous "Fait à Abidjan"
        VERTICAL_TEXT = "Ce document est signé électroniquement selon les normes de confidentialité et de sécurité de l'ARTCI"

        # ================================================================
        # PASSE 1 : Contenu visuel AVANT signature numérique
        # ================================================================
        current_pdf = input_pdf_buffer

        # 8a. Mention verticale sur le bord droit (toutes les pages)
        for page_idx in range(total_pages):
            try:
                current_pdf = add_vertical_text_to_pdf(
                    current_pdf, page_idx, VERTICAL_TEXT,
                    font_size=6, margin_right=8, color=(0.3, 0.3, 0.3),
                    y_start_ratio=0.105
                )
            except Exception as e:
                current_app.logger.error(f"⚠️ Mention verticale page {page_idx}: {e}")

        # 8b. QR code en bas à gauche (dernière page)
        try:
            qr_image = generate_qr_code_image(
                QR_DATA, size=QR_SIZE,
                fill_color="black", back_color="white",
                box_size=10, border=2
            )
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_qr:
                qr_image.save(tmp_qr.name)
                tmp_qr_path = tmp_qr.name
            try:
                current_pdf = add_qr_code_to_pdf(
                    current_pdf, tmp_qr_path, last_page,
                    mm_to_points(QR_X), mm_to_points(QR_Y), mm_to_points(QR_SIZE)
                )
                current_app.logger.info(f"✅ QR code ajouté page {last_page}")
            finally:
                os.remove(tmp_qr_path)
        except Exception as e:
            current_app.logger.error(f"⚠️ Erreur QR code: {e}")

        # ================================================================
        # PASSE 2 : Signature numérique PyHanko (avec image du cachet)
        # ================================================================
        sig_pages = [{
            "page": last_page,
            "signatures": [{"x": SIG_X, "y": SIG_Y}]
        }]
        signer_info = {
            'name': signer_name,
            'sub_name': '',
            'function': 'Le Secrétaire Général',
            'email': user.email,
            'phone': '',
            'grade': '',
            'show_legal_mention': False,
            'document_type': '',
            'show_signer_details': False
        }
        current_pdf = sign_pdf_pages(
            current_pdf, sig_pages, signer, signer_stamp, signer_info,
            signature_size={'width': 180, 'height': 100}
        )

        # 9. Sauvegarde
        save_final_pdf(current_pdf, signed_pdf_path)

        # 10. Mise à jour base de données
        update_signature_volumes(user, company, 1)
        db.session.commit()

        current_app.logger.info(f"✅ Document ARCOP signé: {full_signed_pdf_url}")
        return jsonify({
            "message": "Document ARCOP signé avec succès.",
            "doc_signed": full_signed_pdf_url,
            "signer_name": signer_name,
            "pages": total_pages
        }), 200

    except Exception as e:
        db.session.rollback()
        error_tb = traceback.format_exc()
        current_app.logger.error(f"❌ Erreur signature ARCOP: {str(e)}\n{error_tb}")
        return jsonify({
            "error": f"Erreur lors de la signature ARCOP : {str(e)}",
            "error_type": type(e).__name__,
            "traceback": error_tb.split('\n')[-10:]
        }), 500