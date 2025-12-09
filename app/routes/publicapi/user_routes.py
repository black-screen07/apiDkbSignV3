
from flask import Blueprint, request, jsonify
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.models import User, Company, CertTypeEnum
from pathlib import Path
from app import db
from math import ceil
from sqlalchemy import or_
import base64
import os
import logging
from werkzeug.utils import secure_filename
import json
import shutil

publicapi_user_bp = Blueprint('publicapi_users', __name__)

CERTIFICATE_FOLDER = Path("certificates")
SIGNATURE_FOLDER = Path("signatures")

def get_base64_encoded_image(image_path):
    """
    Convertit une image en base64.
    """
    try:
        if image_path and os.path.exists(image_path):  # Vérifier si le fichier existe
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                return f"data:image/png;base64,{encoded_string}"  # Ajout du préfixe MIME
        else:
            return None  # Retourner None si le fichier n'existe pas
    except Exception as e:
        print(f"Erreur lors de l'encodage de l'image : {str(e)}")
        return None

@publicapi_user_bp.route('/users', methods=['GET'])
@require_api_key
def get_all_individual_users():
    """
    Endpoint pour récupérer tous les utilisateurs individuels non archivés, avec pagination, recherche et informations complètes.
    """
    try:
        # Récupération des paramètres de pagination avec des valeurs par défaut
        page = request.args.get('page', 1, type=int)  # Page actuelle (par défaut : 1)
        per_page = request.args.get('per_page', 10, type=int)  # Nombre d'éléments par page (par défaut : 10)

        # Validation des paramètres de pagination
        if page < 1 or per_page < 1:
            return jsonify({"error": "Les paramètres 'page' et 'per_page' doivent être des entiers positifs."}), 400

        # Récupération du terme de recherche
        search_term = request.args.get('search', '').strip()

        # Base de la requête pour filtrer les utilisateurs non archivés
        query = User.query.filter_by(account_type='individual', archived=False)

        # Filtrer par terme de recherche si fourni
        if search_term:
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search_term}%'),   # Recherche par nom
                    User.email.ilike(f'%{search_term}%'),  # Recherche par email
                    User.phone.ilike(f'%{search_term}%'),  # Recherche par téléphone
                    User.city.ilike(f'%{search_term}%')    # Recherche par ville
                )
            )

        # Trier par 'created_at' du plus récent au plus ancien
        query = query.order_by(User.created_at.desc())

        # Pagination
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # Construire la liste des utilisateurs avec les informations pertinentes
        users_data = [
            {
                "id": user.id,
                "email": user.email,
                "user_type": user.account_type,
                "name": user.name,
                "sub_name": user.sub_name,
                "phone": user.phone,
                "address": user.address,
                "city": user.city,
                "country": user.country,
                "cni_number": user.cni_number,
                "cert_path": user.cert_path,
                "img_sign_files": {
                    "current_img_sign":user.current_img_sign,
                    "img_sign_base64": get_base64_encoded_image(user.img_sign_path),
                    "name_sign_base64": get_base64_encoded_image(user.name_sign_path),
                    "pad_sign_base64": get_base64_encoded_image(user.pad_sign_path),
                    "name_sign": user.name_sign
                },
                "signature_volume": user.signature_volume,
                "signature_volume_used": user.signature_volume_used,
                "with_consent": user.with_consent,
                "created_at": user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
            }
            for user in pagination.items
        ]

        # Métadonnées de pagination
        metadata = {
            "current_page": pagination.page,
            "per_page": pagination.per_page,
            "total_pages": pagination.pages,
            "total_items": pagination.total,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        }

        return jsonify({
            "message": "Liste des utilisateurs non archivés récupérée avec succès.",
            "users": users_data,
            "metadata": metadata
        }), 200

    except ValueError as ve:
        logging.error(f"Erreur de validation des paramètres : {str(ve)}")
        return jsonify({"error": "Paramètres invalides."}), 400

    except Exception as e:
        logging.error(f"Erreur lors de la récupération des utilisateurs : {str(e)}")
        return jsonify({"error": f"Erreur inattendue : {str(e)}"}), 500

@publicapi_user_bp.route('/users/<int:user_id>', methods=['GET'])
@require_api_key
def get_non_admin_user_with_company(user_id):
    """
    Endpoint pour récupérer un utilisateur individuel spécifique par son ID,
    """
    try:
        # Rechercher l'utilisateur par ID, exclure ceux ayant un account_type 'admin' ou étant archivés
        user = User.query.filter(User.id == user_id, User.account_type != 'admin', User.archived == False).first()

        if not user:
            return jsonify({"error": "Utilisateur non trouvé, archivé ou type de compte non autorisé."}), 404

        # Construire les données de l'utilisateur
        user_data = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "sub_name": user.sub_name,
            "phone": user.phone,
            "address": user.address,
            "city": user.city,
            "country": user.country,
            "cni_number": user.cni_number,
            "account_type": user.account_type,
            "sign_roles": user.sign_roles,
            "with_consent": user.with_consent,
            "signature_volume": user.signature_volume,
            "signature_volume_used": user.signature_volume_used,
            "cert_path": user.cert_path,
            "img_sign_files": {
                "current_img_sign":user.current_img_sign,
                "img_sign_base64": get_base64_encoded_image(user.img_sign_path),
                "name_sign_base64": get_base64_encoded_image(user.name_sign_path),
                "pad_sign_base64": get_base64_encoded_image(user.pad_sign_path),
                "stamp_base64": get_base64_encoded_image(user.stamp_path),
                "name_sign": user.name_sign
            },
            "created_at": user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
        }

        # Si l'utilisateur est un employé, inclure les informations de la société
        if user.account_type == "employee" and user.company_id:
            company = Company.query.filter(Company.id == user.company_id, Company.archived == False).first()
            if company:
                user_data["company"] = {
                    "id": company.id,
                    "name": company.name,
                    "phone": company.phone,
                    "email": company.email,
                    "address": company.address,
                    "city": company.city,
                    "country": company.country,
                    "cert_type": company.cert_type,
                    "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
                }

        return jsonify({
            "message": "Utilisateur récupéré avec succès.",
            "user": user_data
        }), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération de l'utilisateur : {str(e)}"}), 500

@publicapi_user_bp.route('/companies/<int:company_id>/users', methods=['GET'])
@require_api_key
def get_users_by_company(company_id):
    """
    Endpoint pour récupérer les utilisateurs rattachés à une compagnie donnée.
    """
    try:
        # Récupération des paramètres de pagination
        page = int(request.args.get('page', 1))  # Page actuelle (par défaut : 1)
        per_page = int(request.args.get('per_page', 10))  # Nombre d'éléments par page (par défaut : 10)

        # Récupération du terme de recherche
        search_term = request.args.get('search', '').strip()

        # Vérifier si la compagnie existe et n'est pas archivée
        company = Company.query.filter(Company.id == company_id, Company.archived == False).first()
        if not company:
            return jsonify({"error": "Compagnie introuvable ou archivée."}), 404

        # Base de la requête pour les utilisateurs rattachés à cette compagnie
        query = User.query.filter(
            User.account_type == 'employee',
            User.company_id == company_id,
            User.archived == False  # Exclure les utilisateurs archivés
        )

        # Appliquer le filtre de recherche si un terme est fourni
        if search_term:
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search_term}%'),  # Recherche par nom
                    User.email.ilike(f'%{search_term}%'),  # Recherche par email
                    User.phone.ilike(f'%{search_term}%')  # Recherche par téléphone
                )
            )

        # Trier les utilisateurs par date de création (plus récents en premier)
        query = query.order_by(User.created_at.desc())

        # Pagination
        total_users = query.count()
        users = query.paginate(page=page, per_page=per_page, error_out=False).items

        # Construire les données pour chaque utilisateur
        users_data = []
        for user in users:
            users_data.append({
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "sub_name": user.sub_name,
                "phone": user.phone,
                "address": user.address,
                "city": user.city,
                "country": user.country,
                "cni_number": user.cni_number,
                "account_type": user.account_type,
                "sign_roles": user.sign_roles,
                "with_consent": user.with_consent,
                "cert_path": user.cert_path,
                "img_sign_files": {
                    "current_img_sign": user.current_img_sign,
                    "img_sign_base64": get_base64_encoded_image(user.img_sign_path),
                    "name_sign_base64": get_base64_encoded_image(user.name_sign_path),
                    "pad_sign_base64": get_base64_encoded_image(user.pad_sign_path),
                    "stamp_base64": get_base64_encoded_image(user.stamp_path),
                    "name_sign": user.name_sign
                },
                "created_at": user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
            })

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_users / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_users,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

        return jsonify({
            "message": f"Liste des utilisateurs rattachés à la compagnie {company.name} récupérée avec succès.",
            "company": {
                "id": company.id,
                "name": company.name,
                "phone": company.phone,
                "email": company.email,
                "address": company.address,
                "city": company.city,
                "country": company.country,
                "cert_type": company.cert_type,
                "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
            },
            "users": users_data,
            "metadata": metadata
        }), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des utilisateurs : {str(e)}"}), 500

@publicapi_user_bp.route('/companies/<int:company_id>/users/<int:user_id>', methods=['GET'])
@require_api_key
def get_user_by_company_and_id(company_id, user_id):
    """
    Endpoint pour récupérer les détails d'un utilisateur spécifique rattaché à une compagnie donnée,
    uniquement si la compagnie et l'utilisateur ne sont pas archivés.
    Inclut l'image de signature encodée en Base64.
    """
    try:
        # Vérifier si la compagnie existe et n'est pas archivée
        company = Company.query.filter(Company.id == company_id, Company.archived == False).first()
        if not company:
            return jsonify({"error": "Compagnie introuvable ou archivée."}), 404

        # Vérifier si l'utilisateur existe, n'est pas archivé et est rattaché à la compagnie
        user = User.query.filter_by(id=user_id, company_id=company_id, account_type='employee', archived=False).first()
        if not user:
            return jsonify({"error": "Utilisateur introuvable, archivé ou non rattaché à cette compagnie."}), 404

        # Construire les données de réponse
        user_data = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "sub_name": user.sub_name,
            "phone": user.phone,
            "address": user.address,
            "city": user.city,
            "country": user.country,
            "cni_number": user.cni_number,
            "account_type": user.account_type,
            "sign_roles": user.sign_roles,
            "with_consent": user.with_consent,
            "cert_path": user.cert_path,
            "img_sign_files": {
                "current_img_sign": user.current_img_sign,
                "img_sign_base64": get_base64_encoded_image(user.img_sign_path),
                "name_sign_base64": get_base64_encoded_image(user.name_sign_path),
                "pad_sign_base64": get_base64_encoded_image(user.pad_sign_path),
                "stamp_base64": get_base64_encoded_image(user.pad_sign_path),
                "name_sign": user.name_sign
            },
            "created_at": user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
        }

        company_data = {
            "id": company.id,
            "name": company.name,
            "phone": company.phone,
            "email": company.email,
            "address": company.address,
            "city": company.city,
            "country": company.country,
            "cert_type": company.cert_type,
            "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
        }

        return jsonify({
            "message": "Utilisateur récupéré avec succès.",
            "user": user_data,
            "company": company_data
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération de l'utilisateur : {str(e)}"}), 500

@publicapi_user_bp.route('/users/<int:user_id>', methods=['PUT'])
@require_api_key
def update_user(user_id):
    """
    Met à jour les informations d'un utilisateur spécifique.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        current_user = User.query.filter_by(email=current_user_email).first()

        if not current_user:
            return jsonify({"error": "Utilisateur connecté introuvable."}), 404

        # Vérifier si l'utilisateur à mettre à jour existe
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier que seul l'utilisateur lui-même ou un admin peut modifier les informations
        if current_user.id != user.id and current_user.account_type != "admin":
            return jsonify({"error": "Vous n'avez pas les droits pour modifier cet utilisateur."}), 403

        # Récupérer les données envoyées
        data = request.form
        cert_file = request.files.get('cert')
        img_sign_file = request.files.get('img_sign_file')
        name_sign_file = request.files.get('name_sign_file')
        pad_sign_file = request.files.get('pad_sign_file')

        # Champs obligatoires
        email = data.get('email')
        name = data.get('name')

        if not email or not name:
            return jsonify({"error": "Les champs 'email' et 'name' sont obligatoires."}), 400

        # Récupération et validation des rôles de signature
        sign_roles_raw = data.get('sign_roles')

        if not sign_roles_raw:
            return jsonify({"error": "Le champ 'sign_roles' est requis et doit être un tableau JSON valide."}), 400

        # S'assurer que sign_roles est bien un tableau JSON
        try:
            sign_roles = json.loads(sign_roles_raw) if isinstance(sign_roles_raw, str) else sign_roles_raw
        except json.JSONDecodeError:
            return jsonify({"error": "Le champ 'sign_roles' doit être un tableau JSON valide."}), 400

        # Validation des rôles acceptés
        valid_roles = {"sign", "doSign", "signDoSign"}
        if not isinstance(sign_roles, list) or not all(isinstance(role, str) for role in sign_roles):
            return jsonify({"error": "Le champ 'sign_roles' doit être une liste de chaînes de caractères."}), 400

        invalid_roles = [role for role in sign_roles if role not in valid_roles]
        if invalid_roles:
            return jsonify({
                "error": f"Rôles invalides : {invalid_roles}. Rôles acceptés : {list(valid_roles)}"
            }), 400

        # Mise à jour des champs utilisateur
        user.email = email
        user.name = name
        user.sub_name = data.get('sub_name')
        user.phone = data.get('phone')
        user.address = data.get('address')
        user.city = data.get('city')
        user.country = data.get('country')
        user.cni_number = data.get('cni_number')
        user.name_sign = data.get('name_sign')
        user.with_consent = data.get('with_consent', 'true').lower() == 'true'
        user.current_img_sign = data.get('current_img_sign')
        user.sign_roles = sign_roles

        # Initialisation des dossiers nécessaires
        CERTIFICATE_FOLDER.mkdir(parents=True, exist_ok=True)
        SIGNATURE_FOLDER.mkdir(parents=True, exist_ok=True)

        # Gestion des fichiers pour certificat et signatures
        try:
            if user.account_type == "individual":
                # Gestion des fichiers pour utilisateurs individuels
                user_cert_path = CERTIFICATE_FOLDER / "users"
                user_cert_path.mkdir(parents=True, exist_ok=True)

                user_sign_path = SIGNATURE_FOLDER / "users" / secure_filename(email)
                user_sign_path.mkdir(parents=True, exist_ok=True)

                if cert_file:
                    cert_path = user_cert_path / f"{secure_filename(email)}_cert.p12"
                    cert_file.save(cert_path)
                    user.cert_path = str(cert_path)

                if img_sign_file:
                    img_sign_path = user_sign_path / "img_sign.png"
                    img_sign_file.save(img_sign_path)
                    user.img_sign_path = str(img_sign_path)

                if name_sign_file:
                    name_sign_path = user_sign_path / "name_sign.png"
                    name_sign_file.save(name_sign_path)
                    user.name_sign_path = str(name_sign_path)

                if pad_sign_file:
                    pad_sign_path = user_sign_path / "pad_sign.png"
                    pad_sign_file.save(pad_sign_path)
                    user.pad_sign_path = str(pad_sign_path)

            elif user.account_type == "employee" and user.company_id:
                # Gestion des fichiers pour les employés associés à une entreprise
                company = Company.query.get(user.company_id)
                if not company:
                    return jsonify({"error": "Entreprise associée introuvable."}), 404

                safe_company_name = secure_filename(company.name)
                employee_cert_path = CERTIFICATE_FOLDER / "companies" / safe_company_name / "employees"
                employee_sign_path = SIGNATURE_FOLDER / "companies" / safe_company_name / "employees"

                employee_cert_path.mkdir(parents=True, exist_ok=True)
                employee_sign_path.mkdir(parents=True, exist_ok=True)

                if cert_file:
                    cert_path = employee_cert_path / f"{secure_filename(email)}_cert.p12"
                    cert_file.save(cert_path)
                    user.cert_path = str(cert_path)

                if img_sign_file:
                    signature_path = employee_sign_path / f"{secure_filename(email)}_signature.png"
                    img_sign_file.save(signature_path)
                    user.signature_path = str(signature_path)

        except Exception as e:
            return jsonify({"error": f"Erreur lors de la gestion des fichiers : {str(e)}"}), 500

        # Sauvegarde des modifications
        db.session.commit()

        # Construire la réponse
        response = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "sub_name": user.sub_name,
            "phone": user.phone,
            "address": user.address,
            "city": user.city,
            "country": user.country,
            "cni_number": user.cni_number,
            "cert_path": user.cert_path,
            "with_consent": user.with_consent,
            "sign_roles": user.sign_roles,  # Ajout du champ mis à jour
            "img_sign_files": {
                "current_img_sign": user.current_img_sign,
                "img_sign_base64": get_base64_encoded_image(user.img_sign_path),
                "name_sign_base64": get_base64_encoded_image(user.name_sign_path),
                "pad_sign_base64": get_base64_encoded_image(user.pad_sign_path),
                "name_sign": user.name_sign
            },
        }

        if user.account_type == "employee" and user.company_id:
            response["company"] = {
                "id": company.id,
                "name": company.name,
                "cert_type": company.cert_type
            }

        return jsonify({
            "message": "Informations utilisateur mises à jour avec succès.",
            "user": response
        }), 200

    except Exception as e:
        logging.error(f"Erreur lors de la mise à jour de l'utilisateur : {str(e)}")
        return jsonify({"error": f"Erreur lors de la mise à jour : {str(e)}"}), 500

@publicapi_user_bp.route('/users/<int:user_id>/update-signatures', methods=['PUT'])
@require_api_key
def update_user_signatures(user_id):
    """
    Met à jour les images de signature d'un utilisateur (img_sign, name_sign, pad_sign, stamp)
    et retourne les données en base64 avec les champs additionnels 'name_sign' et 'current_img_sign'.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        current_user = User.query.filter_by(email=current_user_email).first()

        if not current_user:
            return jsonify({"error": "Utilisateur connecté introuvable."}), 404

        # Vérifier si l'utilisateur à mettre à jour existe
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier les permissions (l'utilisateur doit être lui-même ou un admin)
        if current_user.id != user.id and current_user.account_type != "admin":
            return jsonify(
                {"error": "Vous n'avez pas les droits pour modifier les signatures de cet utilisateur."}
            ), 403

        # Récupérer les données additionnelles
        data = request.form
        user.name_sign = data.get('name_sign', user.name_sign)  # Conserve l'ancienne valeur si non fournie
        user.current_img_sign = data.get('current_img_sign', user.current_img_sign)

        # Récupérer les fichiers de signature
        img_sign_file = request.files.get('img_sign_file')
        name_sign_file = request.files.get('name_sign_file')
        pad_sign_file = request.files.get('pad_sign_file')
        stamp_file = request.files.get('stamp_file')

        # Vérifier qu'au moins un champ est fourni
        if not any([img_sign_file, name_sign_file, pad_sign_file, stamp_file, user.name_sign, user.current_img_sign]):
            return jsonify({
                "error": "Au moins un fichier de signature (img_sign, name_sign, pad_sign, stamp) ou les champs 'name_sign', 'current_img_sign' doivent être fournis."
            }), 400

        # Définir le dossier pour stocker les signatures
        if user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable."}), 404

            safe_company_name = secure_filename(company.name)
            user_sign_path = SIGNATURE_FOLDER / "companies" / safe_company_name / "employees" / secure_filename(user.email)
        else:
            user_sign_path = SIGNATURE_FOLDER / "users" / secure_filename(user.email)

        # Créer le répertoire si nécessaire
        user_sign_path.mkdir(parents=True, exist_ok=True)

        # Définir les chemins des fichiers
        if img_sign_file:
            img_sign_path = user_sign_path / "img_sign.png"
            img_sign_file.save(img_sign_path)
            user.img_sign_path = str(img_sign_path)

        if name_sign_file:
            name_sign_path = user_sign_path / "name_sign.png"
            name_sign_file.save(name_sign_path)
            user.name_sign_path = str(name_sign_path)

        if pad_sign_file:
            pad_sign_path = user_sign_path / "pad_sign.png"
            pad_sign_file.save(pad_sign_path)
            user.pad_sign_path = str(pad_sign_path)

        if stamp_file:
            stamp_path = user_sign_path / "stamp.png"
            stamp_file.save(stamp_path)
            user.stamp_path = str(stamp_path)

        # Sauvegarder les modifications dans la base de données
        db.session.commit()

        # Encoder les fichiers mis à jour en base64 (ou retourner None si non définis)
        img_sign_base64 = get_base64_encoded_image(user.img_sign_path) if user.img_sign_path else None
        name_sign_base64 = get_base64_encoded_image(user.name_sign_path) if user.name_sign_path else None
        pad_sign_base64 = get_base64_encoded_image(user.pad_sign_path) if user.pad_sign_path else None
        stamp_base64 = get_base64_encoded_image(user.stamp_path) if user.stamp_path else None

        # Construire la réponse
        response = {
            "id": user.id,
            "email": user.email,
            "img_sign_base64": img_sign_base64,
            "name_sign_base64": name_sign_base64,
            "pad_sign_base64": pad_sign_base64,
            "name_sign": user.name_sign,
            "current_img_sign": user.current_img_sign,
            "stamp_base64": stamp_base64,
        }

        return jsonify({
            "message": "Signatures mises à jour avec succès.",
            "user": response
        }), 200

    except Exception as e:
        logging.error(f"Erreur lors de la mise à jour des signatures : {str(e)}")
        return jsonify({"error": f"Erreur lors de la mise à jour des signatures : {str(e)}"}), 500

@publicapi_user_bp.route('/users/<int:user_id>/archive', methods=['PUT'])
@require_api_key
def archive_user(user_id):
    """
    Endpoint pour archiver un utilisateur.
    """
    try:
        # Récupérer l'utilisateur par son ID
        user = User.query.get(user_id)

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier si l'utilisateur est déjà archivé
        if user.archived:
            return jsonify({"message": "L'utilisateur est déjà archivé."}), 200

        # Archiver l'utilisateur
        user.archived = True
        db.session.commit()

        return jsonify({"message": "Utilisateur archivé avec succès."}), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de l'archivage de l'utilisateur : {str(e)}"}), 500

@publicapi_user_bp.route('/users/<int:user_id>', methods=['DELETE'])
@require_api_key
def delete_user(user_id):
    """
    Supprime un utilisateur et ses fichiers associés.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        current_user = User.query.filter_by(email=current_user_email).first()

        if not current_user:
            return jsonify({"error": "Utilisateur connecté introuvable."}), 404

        # Vérifier si l'utilisateur à supprimer existe
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier que seul l'utilisateur lui-même ou un admin peut supprimer un compte
        if current_user.id != user.id and current_user.account_type != "admin":
            return jsonify({"error": "Vous n'avez pas les droits pour supprimer cet utilisateur."}), 403

        # Construire les chemins des fichiers de certificats et de signatures
        user_cert_path = CERTIFICATE_FOLDER / "users" / f"{secure_filename(user.email)}_cert.p12"
        user_sign_path = SIGNATURE_FOLDER / "users" / secure_filename(user.email)

        # Supprimer les fichiers de certificat et de signature s'ils existent
        if user_cert_path.exists():
            user_cert_path.unlink()  # Supprime le fichier

        if user_sign_path.exists() and user_sign_path.is_dir():
            shutil.rmtree(user_sign_path)  # Supprime tout le dossier des signatures

        # Supprimer l'utilisateur de la base de données
        db.session.delete(user)
        db.session.commit()

        return jsonify({"message": "Utilisateur supprimé avec succès."}), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la suppression de l'utilisateur : {str(e)}"}), 500