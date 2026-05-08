from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import db, User, Document, SignatureProof
from app.services.signature_proof_service import (
    get_proof_by_id,
    get_proofs_by_document,
    get_proofs_by_signer,
    verify_proof_integrity,
)
import os

proof_bp = Blueprint('proof_bp', __name__)


@proof_bp.route('/proofs/document/<int:document_id>', methods=['GET'])
@jwt_required()
def get_document_proofs(document_id):
    """
    Récupère toutes les preuves de signature pour un document donné.
    """
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    document = Document.query.get(document_id)
    if not document:
        return jsonify({"error": "Document introuvable."}), 404

    # Vérifier que l'utilisateur a accès au document
    if document.user_id != user.id:
        return jsonify({"error": "Accès non autorisé à ce document."}), 403

    proofs = get_proofs_by_document(document_id)
    return jsonify({
        "document_id": document_id,
        "document_name": document.name,
        "total_proofs": len(proofs),
        "proofs": [proof.to_dict() for proof in proofs],
    }), 200


@proof_bp.route('/proofs/<proof_id>', methods=['GET'])
@jwt_required()
def get_proof_detail(proof_id):
    """
    Récupère le détail d'une preuve de signature spécifique.
    """
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    proof = get_proof_by_id(proof_id)
    if not proof:
        return jsonify({"error": "Preuve introuvable."}), 404

    # Vérifier l'accès
    document = Document.query.get(proof.document_id)
    if document and document.user_id != user.id and proof.signer_id != user.id:
        return jsonify({"error": "Accès non autorisé à cette preuve."}), 403

    return jsonify(proof.to_dict()), 200


@proof_bp.route('/proofs/<proof_id>/pdf', methods=['GET'])
@jwt_required()
def download_proof_pdf(proof_id):
    """
    Télécharge le PDF de preuve de signature.
    """
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    proof = get_proof_by_id(proof_id)
    if not proof:
        return jsonify({"error": "Preuve introuvable."}), 404

    # Vérifier l'accès
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


@proof_bp.route('/proofs/<proof_id>/verify', methods=['GET'])
@jwt_required()
def verify_proof(proof_id):
    """
    Vérifie l'intégrité d'une preuve de signature.
    """
    is_valid, message = verify_proof_integrity(proof_id)

    if is_valid is None:
        return jsonify({"error": message}), 404

    return jsonify({
        "proof_id": proof_id,
        "is_valid": is_valid,
        "message": message,
        "verification_timestamp": __import__('datetime').datetime.utcnow().isoformat(),
    }), 200


@proof_bp.route('/proofs/my-signatures', methods=['GET'])
@jwt_required()
def get_my_signature_proofs():
    """
    Récupère toutes les preuves de signature de l'utilisateur connecté.
    """
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"error": "Utilisateur introuvable."}), 404

    proofs = get_proofs_by_signer(user.id, 'user')

    return jsonify({
        "signer_id": user.id,
        "signer_email": user.email,
        "total_proofs": len(proofs),
        "proofs": [proof.to_dict() for proof in proofs],
    }), 200
