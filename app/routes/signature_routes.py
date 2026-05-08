import json

from flask import Blueprint, request, jsonify, send_from_directory, current_app
from flask_jwt_extended import jwt_required
from pathlib import Path
from app.utils.signature_utils import (
    retrieve_certificates,
    parse_request_content,
    load_signature_image,
    load_pdf,
    update_signature_volumes,
    get_authenticated_user,
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
    update_document_record
)
from app.models import db
from app.services.signature_proof_service import create_signature_proof, build_proof_urls

signature_bp = Blueprint('signature_bp', __name__)

SIGNED_PDF_FOLDER = Path("documents/doc_signed")
SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)
COMPANY_SIGNATURE_FOLDER = Path("signatures/companies")


@signature_bp.route('/documents/doc_signed/<path:subfolder>/<filename>', methods=['GET'])
def download_file(subfolder, filename):
    """
    Endpoint pour télécharger un fichier signé en fonction du sous-dossier.
    """
    file_path = SIGNED_PDF_FOLDER / subfolder / filename

    if not file_path.exists():
        return jsonify({"error": "Fichier introuvable."}), 404

    return send_from_directory((SIGNED_PDF_FOLDER / subfolder).resolve(), filename)


@signature_bp.route('/sign-pdf', methods=['POST'])
@jwt_required()
def sign_pdf():
    """
    Point d'entrée pour la signature d'un PDF.
    """
    try:
        # 1. Récupération et validation de l'utilisateur et de son entreprise
        user = get_authenticated_user()
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

        # 9. Application des signatures sur chaque page concernée
        # Préparer les infos du signataire pour affichage sous la signature
        signer_info = {
            'name': user.name,
            'sub_name': user.sub_name if hasattr(user, 'sub_name') else None,
            'function': user.function if hasattr(user, 'function') else None,
            'email': user.email
        }
        input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, params["pages"], signer, signer_stamp, signer_info)

        # 10. Enregistrement du PDF final sur le disque
        save_final_pdf(input_pdf_buffer, signed_pdf_path)

        # 11. Mise à jour de la base de données
        update_document_record(user, params, document, relative_file_path)
        update_signature_volumes(user, company, 1)
        db.session.commit()

        # 12. Génération de la preuve de signature
        proof = create_signature_proof(
            document_id=document.id if document else None,
            signer=user,
            signer_type='user',
            document_name=params.get("name", "document"),
            file_path_after=signed_pdf_path,
            cert_path=cert_path,
            cert_type=company.cert_type if company else None,
            signature_method='jwt',
            signature_positions=params.get("pages"),
            consent_accepted=bool(document),
            company=company,
            batch_id=params.get("batch_id"),
        )

        return jsonify({
            "message": "Document signé avec succès.",
            "doc_signed": full_signed_pdf_url,
            "proof": build_proof_urls(proof) if proof else None
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la signature : {str(e)}")
        return jsonify({"error": f"Erreur lors de la signature : {str(e)}"}), 500


@signature_bp.route('/sign-pdfs', methods=['POST'])
#@jwt_required()
def sign_multiple_pdfs():
    """
    Point d'entrée pour la signature de plusieurs PDFs via JSON.
    """
    try:
        # 1. Récupération et validation de l'utilisateur et de son entreprise
        user = get_authenticated_user()
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

            # 12. Application des signatures
            # Préparer les infos du signataire pour affichage sous la signature
            signer_info = {
                'name': user.name,
                'sub_name': user.sub_name if hasattr(user, 'sub_name') else None,
                'function': user.function if hasattr(user, 'function') else None,
                'email': user.email
            }
            input_pdf_buffer = sign_pdf_pages(input_pdf_buffer, params.get("pages", []), signer, signer_stamp, signer_info)

            # 13. Enregistrement du PDF final
            save_final_pdf(input_pdf_buffer, signed_pdf_path)

            # 14. Mise à jour de la base de données
            update_document_record(user, params, document, relative_file_path)
            total_signatures += 1

            # 14b. Génération de la preuve de signature
            proof = create_signature_proof(
                document_id=document.id if document else None,
                signer=user,
                signer_type='user',
                document_name=params.get("name", "Unnamed"),
                file_path_after=signed_pdf_path,
                cert_path=cert_path,
                cert_type=company.cert_type if company else None,
                signature_method='jwt',
                signature_positions=params.get("pages"),
                consent_accepted=bool(document),
                company=company,
                batch_id=params.get("batch_id"),
            )

            signed_results.append({
                "filename": params.get("name", "Unnamed"),
                "message": "Document signé avec succès.",
                "doc_signed": full_signed_pdf_url,
                "proof": build_proof_urls(proof) if proof else None
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





