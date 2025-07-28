
from flask import Blueprint, request, jsonify
from app.models import Company, User, CertTypeEnum
from pathlib import Path
from app import db
from flask_jwt_extended import jwt_required
from math import ceil
from sqlalchemy import or_, and_
import shutil

company_bp = Blueprint('company_bp', __name__)

CERTIFICATE_FOLDER = Path("certificates")


@company_bp.route('/companies', methods=['GET'])
@jwt_required()
def list_companies():
    """
    Endpoint pour lister toutes les entreprises non archivées avec pagination, recherche et nombre d'employés.
    """
    try:
        # Récupération des paramètres de pagination depuis les query parameters
        page = int(request.args.get('page', 1))  # Page actuelle (par défaut : 1)
        per_page = int(request.args.get('per_page', 10))  # Nombre d'éléments par page (par défaut : 10)

        # Récupération du terme de recherche
        search_term = request.args.get('search', '').strip()

        # Base de la requête (filtrer les entreprises non archivées)
        query = db.session.query(
            Company,
            db.func.count(User.id).label('employee_count')
        ).outerjoin(
            User, and_(User.company_id == Company.id, User.archived == False)
        ).filter(Company.archived == False).group_by(Company.id)

        # Appliquer le filtre de recherche si un terme est fourni
        if search_term:
            query = query.filter(
                or_(
                    Company.name.ilike(f'%{search_term}%'),  # Recherche par nom
                    Company.email.ilike(f'%{search_term}%'),  # Recherche par email
                    Company.phone.ilike(f'%{search_term}%'),  # Recherche par téléphone
                    Company.city.ilike(f'%{search_term}%')  # Recherche par ville
                )
            )

        # Trier les entreprises par date de création (plus récentes en premier)
        query = query.order_by(Company.created_at.desc())

        # Pagination
        total_companies = query.count()
        companies = query.paginate(page=page, per_page=per_page, error_out=False).items

        # Structurer les données pour l'API
        companies_data = []
        for company, employee_count in companies:
            companies_data.append({
                "id": company.id,
                "name": company.name,
                "phone": company.phone,
                "email": company.email,
                "address": company.address,
                "city": company.city,
                "country": company.country,
                "cert_type": company.cert_type,
                "cert_path": company.cert_path,
                "key_path": company.key_path,
                "signature_volume": company.signature_volume,
                "signature_volume_used": company.signature_volume_used,
                "employee_count": employee_count,  # Ajout du nombre d'employés
                "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
            })

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_companies / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_companies,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        return jsonify({
            "message": "Liste des entreprises non archivées récupérée avec succès.",
            "companies": companies_data,
            "metadata": metadata
        }), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des entreprises : {str(e)}"}), 500


@company_bp.route('/companies/<int:company_id>', methods=['GET'])
@jwt_required()
def get_company(company_id):
    """
    Endpoint pour récupérer les détails d'une entreprise spécifique, incluant le nombre d'employés,
    uniquement si l'entreprise n'est pas archivée.
    """
    try:
        # Récupérer l'entreprise par son ID, en vérifiant qu'elle n'est pas archivée
        company = Company.query.filter(Company.id == company_id, Company.archived == False).first()

        if not company:
            return jsonify({"error": "Entreprise introuvable ou archivée."}), 404

        # Compter le nombre d'employés associés à l'entreprise
        employee_count = db.session.query(db.func.count(User.id)).filter(User.company_id == company.id).scalar()

        # Structurer les données de l'entreprise
        company_data = {
            "id": company.id,
            "name": company.name,
            "phone": company.phone,
            "email": company.email,
            "address": company.address,
            "city": company.city,
            "country": company.country,
            "cert_type": company.cert_type,
            "cert_path": company.cert_path,
            "key_path": company.key_path,
            "signature_volume": company.signature_volume,
            "signature_volume_used": company.signature_volume_used,
            "employee_count": employee_count,  # Ajout du nombre d'employés
            "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
        }

        return jsonify({
            "message": "Détails de l'entreprise récupérés avec succès.",
            "company": company_data
        }), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération de l'entreprise : {str(e)}"}), 500


@company_bp.route('/companies/<int:company_id>', methods=['PUT'])
@jwt_required()
def update_company(company_id):
    """
    Endpoint pour mettre à jour les informations d'une entreprise spécifique.
    """
    try:
        # Récupérer l'entreprise par son ID
        company = Company.query.get(company_id)

        if not company:
            return jsonify({"error": "Entreprise introuvable."}), 404

        # Récupérer les données envoyées via le formulaire
        data = request.form
        name = data.get('name')
        phone = data.get('phone')
        email = data.get('email')
        address = data.get('address')
        city = data.get('city')
        country = data.get('country')
        cert_type = data.get('cert_type')  # "cachetServeur" ou "PersonnePhysique"
        signature_volume = data.get('signature_volume')

        # Gestion des fichiers pour certificat et clé
        cert_file = request.files.get('cert')
        key_file = request.files.get('key')

        # Mise à jour des champs autorisés (mise à jour immédiate du nom si présent)
        if name:
            company.name = name
        if phone:
            company.phone = phone
        if email:
            company.email = email
        if address:
            company.address = address
        if city:
            company.city = city
        if country:
            company.country = country
        if signature_volume:
            company.signature_volume = signature_volume
        if cert_type:
            if cert_type not in [CertTypeEnum.CACHET_SERVEUR, CertTypeEnum.PERSONNE_PHYSIQUE]:
                return jsonify({"error": "Type de certificat invalide."}), 400
            company.cert_type = cert_type

        # Utiliser le nom mis à jour pour constituer le dossier des certificats
        safe_company_name = company.name.replace(" ", "_")
        company_cert_path = CERTIFICATE_FOLDER / "companies" / safe_company_name
        company_cert_path.mkdir(parents=True, exist_ok=True)

        # Gestion des fichiers
        if cert_file:
            cert_path = company_cert_path / "cert.crt"
            cert_file.save(cert_path)
            company.cert_path = str(cert_path)

        if key_file:
            key_path = company_cert_path / "key.key"
            key_file.save(key_path)
            company.key_path = str(key_path)

        # Sauvegarder les modifications
        db.session.commit()

        # Structurer les données mises à jour
        updated_company = {
            "id": company.id,
            "name": company.name,
            "phone": company.phone,
            "email": company.email,
            "address": company.address,
            "city": company.city,
            "country": company.country,
            "cert_type": company.cert_type,
            "cert_path": company.cert_path,
            "signature_volume": company.signature_volume,
            "key_path": company.key_path,
            "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
        }

        return jsonify({
            "message": "Informations de l'entreprise mises à jour avec succès.",
            "company": updated_company
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la mise à jour de l'entreprise : {str(e)}"}), 500


@company_bp.route('/companies/<int:company_id>/archive', methods=['PUT'])
@jwt_required()
def archive_company(company_id):

    """
    Endpoint pour archiver une entreprise.
    """
    try:
        # Récupérer l'entreprise par son ID
        company = Company.query.get(company_id)

        if not company:
            return jsonify({"error": "Entreprise introuvable."}), 404

        # Vérifier si l'entreprise est déjà archivée
        if company.archived:
            return jsonify({"message": "L'entreprise est déjà archivée."}), 200

        # Archiver l'entreprise
        company.archived = True
        db.session.commit()

        return jsonify({"message": "Entreprise archivée avec succès."}), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'archivage de l'entreprise : {str(e)}"}), 500


@company_bp.route('/companies/<int:company_id>', methods=['DELETE'])
@jwt_required()
def delete_company(company_id):
    """
    Endpoint pour supprimer une entreprise et ses fichiers associés.
    """
    try:
        # Récupérer l'entreprise par son ID
        company = Company.query.get(company_id)

        if not company:
            return jsonify({"error": "Entreprise introuvable."}), 404

        # Construire le chemin du dossier des certificats
        safe_company_name = company.name.replace(" ", "_")
        company_cert_path = CERTIFICATE_FOLDER / "companies" / safe_company_name

        # Supprimer le dossier de certificats s'il existe
        if company_cert_path.exists() and company_cert_path.is_dir():
            shutil.rmtree(company_cert_path)

        # Supprimer l'entreprise de la base de données
        db.session.delete(company)
        db.session.commit()

        return jsonify({"message": "Entreprise supprimée avec succès."}), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la suppression de l'entreprise : {str(e)}"}), 500



