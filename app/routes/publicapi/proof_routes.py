from flask import Blueprint, request, jsonify, send_file, send_from_directory
from app.models import db, User, Document, SignatureProof
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.services.signature_proof_service import (
    get_proof_by_id,
    get_proofs_by_document,
    get_proofs_by_signer,
    verify_proof_integrity,
)
import os
from datetime import datetime
from pathlib import Path

PROOF_PDF_FOLDER = Path("documents/proofs")

publicapi_proof_bp = Blueprint('publicapi_proof_bp', __name__)


@publicapi_proof_bp.route('/documents/proofs/<doc_folder>/<filename>', methods=['GET'])
def download_proof_file(doc_folder, filename):
    """
    Endpoint public pour télécharger un PDF de preuve de signature.
    Accessible sans authentification via URL directe.
    """
    file_path = PROOF_PDF_FOLDER / doc_folder / filename

    if not file_path.exists():
        return jsonify({"error": "Fichier de preuve introuvable."}), 404

    return send_from_directory(
        (PROOF_PDF_FOLDER / doc_folder).resolve(),
        filename,
        mimetype='application/pdf'
    )


@publicapi_proof_bp.route('/proofs/document/<int:document_id>', methods=['GET'])
@require_api_key
def get_document_proofs(document_id):
    """
    [Public API] Récupère toutes les preuves de signature pour un document donné.
    """
    user = get_authenticated_user_by_api_key()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    document = Document.query.get(document_id)
    if not document:
        return jsonify({"error": "Document introuvable."}), 404

    if document.user_id != user.id:
        return jsonify({"error": "Accès non autorisé à ce document."}), 403

    proofs = get_proofs_by_document(document_id)
    return jsonify({
        "document_id": document_id,
        "document_name": document.name,
        "total_proofs": len(proofs),
        "proofs": [proof.to_dict() for proof in proofs],
    }), 200


@publicapi_proof_bp.route('/proofs/<proof_id>', methods=['GET'])
@require_api_key
def get_proof_detail(proof_id):
    """
    [Public API] Récupère le détail d'une preuve de signature spécifique.
    """
    user = get_authenticated_user_by_api_key()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    proof = get_proof_by_id(proof_id)
    if not proof:
        return jsonify({"error": "Preuve introuvable."}), 404

    document = Document.query.get(proof.document_id)
    if document and document.user_id != user.id and proof.signer_id != user.id:
        return jsonify({"error": "Accès non autorisé à cette preuve."}), 403

    return jsonify(proof.to_dict()), 200


@publicapi_proof_bp.route('/proofs/<proof_id>/pdf', methods=['GET'])
@require_api_key
def download_proof_pdf(proof_id):
    """
    [Public API] Télécharge le PDF de preuve de signature.
    """
    user = get_authenticated_user_by_api_key()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    proof = get_proof_by_id(proof_id)
    if not proof:
        return jsonify({"error": "Preuve introuvable."}), 404

    document = Document.query.get(proof.document_id)
    if document and document.user_id != user.id and proof.signer_id != user.id:
        return jsonify({"error": "Accès non autorisé à cette preuve."}), 403

    if not proof.proof_pdf_path or not os.path.exists(proof.proof_pdf_path):
        return jsonify({"error": "Le PDF de preuve n'est pas disponible."}), 404

    return send_file(
        proof.proof_pdf_path,
        as_attachment=True,
        download_name=f"preuve_signature_{proof.proof_id[:16]}.pdf",
        mimetype='application/pdf'
    )


@publicapi_proof_bp.route('/proofs/<proof_id>/verify', methods=['GET'])
@require_api_key
def verify_proof(proof_id):
    """
    [Public API] Vérifie l'intégrité d'une preuve de signature.
    Retourne si la preuve n'a pas été altérée.
    """
    is_valid, message = verify_proof_integrity(proof_id)

    if is_valid is None:
        return jsonify({"error": message}), 404

    return jsonify({
        "proof_id": proof_id,
        "is_valid": is_valid,
        "message": message,
        "verification_timestamp": datetime.utcnow().isoformat(),
    }), 200


@publicapi_proof_bp.route('/proofs/pdf-public/<proof_id>', methods=['GET'])
def download_proof_pdf_public(proof_id):
    """
    [Public - Sans authentification] Télécharge le PDF de preuve de signature.
    Endpoint public pour permettre à quiconque de consulter une preuve via le lien.
    """
    from flask import current_app
    from app.services.signature_proof_service import generate_proof_pdf
    
    proof = get_proof_by_id(proof_id)
    if not proof:
        return jsonify({"error": "Preuve introuvable."}), 404

    # Si le PDF n'existe pas, essayer de le régénérer
    if not proof.proof_pdf_path or not os.path.exists(proof.proof_pdf_path):
        current_app.logger.warning(f"PDF de preuve manquant pour {proof_id}, tentative de régénération...")
        try:
            pdf_path = generate_proof_pdf(proof)
            proof.proof_pdf_path = pdf_path
            db.session.commit()
            current_app.logger.info(f"PDF de preuve régénéré avec succès: {pdf_path}")
        except Exception as e:
            current_app.logger.error(f"Erreur lors de la régénération du PDF de preuve: {e}")
            return jsonify({"error": "Le PDF de preuve n'a pas pu être généré."}), 500

    # Vérifier à nouveau après régénération
    if not proof.proof_pdf_path or not os.path.exists(proof.proof_pdf_path):
        return jsonify({"error": "Le PDF de preuve n'est pas disponible."}), 404

    return send_file(
        proof.proof_pdf_path,
        as_attachment=False,
        download_name=f"preuve_signature_{proof.proof_id[:16]}.pdf",
        mimetype='application/pdf'
    )


@publicapi_proof_bp.route('/proofs/verify-public/<proof_id>', methods=['GET'])
def verify_proof_public(proof_id):
    """
    [Public - Sans authentification] Vérifie l'intégrité d'une preuve de signature.
    Endpoint public pour permettre à quiconque de vérifier une preuve.
    Retourne uniquement le statut de validité, sans détails sensibles.
    """
    is_valid, message = verify_proof_integrity(proof_id)

    if is_valid is None:
        return jsonify({"error": "Preuve introuvable."}), 404

    proof = get_proof_by_id(proof_id)
    return jsonify({
        "proof_id": proof_id,
        "transaction_id": proof.transaction_id if proof else None,
        "is_valid": is_valid,
        "message": message,
        "platform": proof.platform_name if proof else None,
        "document_name": proof.document_name if proof else None,
        "document_hash": proof.document_hash_signed if proof else None,
        "signer_name": f"{proof.signer_name} {proof.signer_first_name or ''}" if proof else None,
        "signer_email": proof.signer_email if proof else None,
        "signed_at": proof.signed_at.isoformat() if proof and proof.signed_at else None,
        "signature_method": proof.signature_method if proof else None,
        "environment": proof.environment if proof else None,
        "verification_timestamp": datetime.utcnow().isoformat(),
    }), 200


@publicapi_proof_bp.route('/proofs/my-signatures', methods=['GET'])
@require_api_key
def get_my_signature_proofs():
    """
    [Public API] Récupère toutes les preuves de signature de l'utilisateur connecté.
    """
    user = get_authenticated_user_by_api_key()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    proofs = get_proofs_by_signer(user.id, 'user')

    return jsonify({
        "signer_id": user.id,
        "signer_email": user.email,
        "total_proofs": len(proofs),
        "proofs": [proof.to_dict() for proof in proofs],
    }), 200
