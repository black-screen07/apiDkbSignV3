import json
import os
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.models import User, Company, db
from app.services.email_service import send_email

publicapi_user_registration_bp = Blueprint('publicapi_user_registration_bp', __name__)

# Dossiers pour les fichiers
CERTIFICATES_FOLDER = Path("certificates")
CERTIFICATES_FOLDER.mkdir(parents=True, exist_ok=True)

SIGNATURES_FOLDER = Path("signatures")
SIGNATURES_FOLDER.mkdir(parents=True, exist_ok=True)

STAMPS_FOLDER = Path("stamps")
STAMPS_FOLDER.mkdir(parents=True, exist_ok=True)

def save_uploaded_file(file, folder, filename):
    """Sauvegarde un fichier uploadé dans le dossier spécifié."""
    if file and file.filename:
        file_path = folder / filename
        file.save(file_path)
        return str(file_path)
    return None

@publicapi_user_registration_bp.route('/register/individual', methods=['POST'])
#@require_api_key
def register_individual():
    """
    Crée un compte utilisateur individuel avec mot de passe défini directement.
    Authentification par API key requise.
    """
    try:
        data = request.form
        cert_file = request.files.get('cert')
        img_sign_file = request.files.get('img_sign_file')
        name_sign_file = request.files.get('name_sign_file')
        pad_sign_file = request.files.get('pad_sign_file')
        stamp_file = request.files.get('stamp_file')

        # Champs obligatoires
        email = data.get('email')
        name = data.get('name')
        password = data.get('password')  # Mot de passe défini directement

        # Champs optionnels
        sub_name = data.get('sub_name')
        phone = data.get('phone')
        address = data.get('address')
        city = data.get('city')
        country = data.get('country')
        cni_number = data.get('cni_number')
        name_sign = data.get('name_sign')
        current_img_sign = data.get('current_img_sign')
        account_type = "individual"
        signature_volume = int(data.get('signature_volume', 10))
        sign_roles_raw = data.get('sign_roles', '[]')
        with_consent = data.get('with_consent', 'true').lower() == 'true'

        # Validation du JSON sign_roles
        try:
            sign_roles = json.loads(sign_roles_raw)
        except json.JSONDecodeError:
            return jsonify({"error": "Le champ 'sign_roles' doit être un tableau JSON valide."}), 400

        # Validation des rôles
        valid_roles = {"sign", "doSign", "signDoSign"}
        if not sign_roles:
            return jsonify({"error": "Aucun rôle fourni. Fournissez au moins un rôle valide."}), 400

        invalid_roles = [role for role in sign_roles if role not in valid_roles]
        if invalid_roles:
            return jsonify({
                "error": f"Rôles invalides : {invalid_roles}. Rôles acceptés : {list(valid_roles)}"
            }), 400

        # Vérification des champs obligatoires
        if not email or not cert_file or not name or not password:
            return jsonify({"error": "Les champs obligatoires (email, cert, name, password) doivent être remplis."}), 400

        # Validation du mot de passe
        if len(password) < 8:
            return jsonify({"error": "Le mot de passe doit contenir au moins 8 caractères."}), 400

        # Vérifier si l'utilisateur existe déjà
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Un utilisateur avec cet email existe déjà."}), 409

        # Créer le dossier utilisateur
        user_folder = CERTIFICATES_FOLDER / email.replace('@', '_at_').replace('.', '_')
        user_folder.mkdir(parents=True, exist_ok=True)

        # Sauvegarder les fichiers
        cert_path = save_uploaded_file(cert_file, user_folder, f"{email}_cert.p12")
        img_sign_path = save_uploaded_file(img_sign_file, SIGNATURES_FOLDER, f"{email}_img_sign.png")
        name_sign_path = save_uploaded_file(name_sign_file, SIGNATURES_FOLDER, f"{email}_name_sign.png")
        pad_sign_path = save_uploaded_file(pad_sign_file, SIGNATURES_FOLDER, f"{email}_pad_sign.png")
        stamp_path = save_uploaded_file(stamp_file, STAMPS_FOLDER, f"{email}_stamp.png")

        # Créer l'utilisateur
        new_user = User(
            email=email,
            name=name,
            sub_name=sub_name,
            phone=phone,
            address=address,
            city=city,
            country=country,
            cni_number=cni_number,
            account_type=account_type,
            cert_path=cert_path,
            img_sign_path=img_sign_path,
            name_sign_path=name_sign_path,
            pad_sign_path=pad_sign_path,
            current_img_sign=current_img_sign,
            name_sign=name_sign,
            stamp_path=stamp_path,
            signature_volume=signature_volume,
            sign_roles=sign_roles,
            with_consent=with_consent,
            password_hash=generate_password_hash(password)  # Hacher le mot de passe
        )

        db.session.add(new_user)
        db.session.commit()

        # Envoyer un email de bienvenue (optionnel)
        try:
            send_email(
                to_email=email,
                subject="Bienvenue sur DKB-Sign",
                template_name="welcome_individual.html",
                user_name=name,
                email=email
            )
        except Exception as e:
            current_app.logger.warning(f"Erreur lors de l'envoi de l'email de bienvenue : {str(e)}")

        return jsonify({
            "message": "Compte individuel créé avec succès",
            "user_id": new_user.id,
            "email": email,
            "account_type": account_type
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création du compte individuel : {str(e)}")
        return jsonify({"error": f"Erreur lors de l'enregistrement : {str(e)}"}), 500

@publicapi_user_registration_bp.route('/register/employee', methods=['POST'])
#@require_api_key
def register_employee():
    """
    Crée un compte employé dans une entreprise avec mot de passe défini directement.
    Authentification par API key requise.
    """
    try:
        data = request.form
        cert_file = request.files.get('cert')
        img_sign_file = request.files.get('img_sign_file')
        name_sign_file = request.files.get('name_sign_file')
        pad_sign_file = request.files.get('pad_sign_file')

        # Champs obligatoires
        email = data.get('email')
        name = data.get('name')
        company_id = data.get('company_id')
        password = data.get('password')  # Mot de passe défini directement

        # Champs optionnels
        sub_name = data.get('sub_name')
        phone = data.get('phone')
        address = data.get('address')
        city = data.get('city')
        country = data.get('country')
        cni_number = data.get('cni_number')
        sign_roles_raw = data.get('sign_roles', '[]')
        name_sign = data.get('name_sign')
        current_img_sign = data.get('current_img_sign')
        with_consent = data.get('with_consent', 'true').lower() == 'true'

        # Vérification des champs obligatoires
        if not all([email, name, company_id, password]):
            return jsonify({"error": "Les champs 'email', 'name', 'company_id' et 'password' sont obligatoires."}), 400

        # Validation du mot de passe
        if len(password) < 8:
            return jsonify({"error": "Le mot de passe doit contenir au moins 8 caractères."}), 400

        # Vérifier l'existence de l'entreprise
        company = Company.query.get(company_id)
        if not company:
            return jsonify({"error": "Entreprise introuvable."}), 404

        # Validation des rôles
        try:
            sign_roles = json.loads(sign_roles_raw)
        except json.JSONDecodeError:
            return jsonify({"error": "Le champ 'sign_roles' doit être un tableau JSON valide."}), 400

        valid_roles = {"sign", "doSign", "signDoSign"}
        if not sign_roles:
            return jsonify({"error": "Aucun rôle fourni. Fournissez au moins un rôle valide."}), 400

        invalid_roles = [role for role in sign_roles if role not in valid_roles]
        if invalid_roles:
            return jsonify({
                "error": f"Rôles invalides : {invalid_roles}. Rôles acceptés : {list(valid_roles)}"
            }), 400

        # Vérifier si l'utilisateur existe déjà
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({"error": "Un utilisateur avec cet email existe déjà."}), 409

        # Créer le dossier de l'entreprise s'il n'existe pas
        company_folder = CERTIFICATES_FOLDER / company.name.replace(' ', '_')
        company_folder.mkdir(parents=True, exist_ok=True)

        # Sauvegarder les fichiers
        cert_path = save_uploaded_file(cert_file, company_folder, f"{email}_cert.p12")
        img_sign_path = save_uploaded_file(img_sign_file, SIGNATURES_FOLDER, f"{email}_img_sign.png")
        name_sign_path = save_uploaded_file(name_sign_file, SIGNATURES_FOLDER, f"{email}_name_sign.png")
        pad_sign_path = save_uploaded_file(pad_sign_file, SIGNATURES_FOLDER, f"{email}_pad_sign.png")

        # Créer l'employé
        new_employee = User(
            email=email,
            name=name,
            sub_name=sub_name,
            phone=phone,
            address=address,
            city=city,
            country=country,
            cni_number=cni_number,
            account_type="employee",
            company_id=company_id,
            cert_path=cert_path,
            img_sign_path=img_sign_path,
            name_sign_path=name_sign_path,
            pad_sign_path=pad_sign_path,
            current_img_sign=current_img_sign,
            name_sign=name_sign,
            signature_volume=0,  # Les employés héritent du volume de l'entreprise
            sign_roles=sign_roles,
            with_consent=with_consent,
            password_hash=generate_password_hash(password)  # Hacher le mot de passe
        )

        db.session.add(new_employee)
        db.session.commit()

        # Envoyer un email de bienvenue (optionnel)
        try:
            send_email(
                to_email=email,
                subject="Bienvenue dans l'équipe DKB-Sign",
                template_name="welcome_employee.html",
                user_name=name,
                company_name=company.name,
                email=email
            )
        except Exception as e:
            current_app.logger.warning(f"Erreur lors de l'envoi de l'email de bienvenue : {str(e)}")

        return jsonify({
            "message": "Compte employé créé avec succès",
            "user_id": new_employee.id,
            "email": email,
            "company_name": company.name,
            "account_type": "employee"
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création du compte employé : {str(e)}")
        return jsonify({"error": f"Erreur lors de l'enregistrement : {str(e)}"}), 500

@publicapi_user_registration_bp.route('/register/company', methods=['POST'])
#@require_api_key
def register_company():
    """
    Crée une entreprise et son administrateur avec mot de passe défini directement.
    Authentification par API key requise.
    """
    try:
        data = request.form
        cert_file = request.files.get('cert')
        img_sign_file = request.files.get('img_sign_file')
        name_sign_file = request.files.get('name_sign_file')
        pad_sign_file = request.files.get('pad_sign_file')

        # Champs obligatoires pour l'entreprise
        company_name = data.get('company_name')
        company_address = data.get('company_address')
        company_city = data.get('company_city')
        company_country = data.get('company_country')
        
        # Champs obligatoires pour l'administrateur
        admin_email = data.get('admin_email')
        admin_name = data.get('admin_name')
        admin_password = data.get('admin_password')  # Mot de passe défini directement

        # Champs optionnels pour l'administrateur
        admin_sub_name = data.get('admin_sub_name')
        admin_phone = data.get('admin_phone')
        admin_cni_number = data.get('admin_cni_number')
        signature_volume = int(data.get('signature_volume', 100))
        sign_roles_raw = data.get('sign_roles', '["sign", "doSign", "signDoSign"]')

        # Vérification des champs obligatoires
        required_fields = [company_name, company_address, company_city, company_country, 
                          admin_email, admin_name, admin_password]
        if not all(required_fields):
            return jsonify({
                "error": "Tous les champs obligatoires doivent être remplis (company_name, company_address, company_city, company_country, admin_email, admin_name, admin_password)."
            }), 400

        # Validation du mot de passe
        if len(admin_password) < 8:
            return jsonify({"error": "Le mot de passe doit contenir au moins 8 caractères."}), 400

        # Validation des rôles
        try:
            sign_roles = json.loads(sign_roles_raw)
        except json.JSONDecodeError:
            return jsonify({"error": "Le champ 'sign_roles' doit être un tableau JSON valide."}), 400

        # Vérifier si l'entreprise existe déjà
        existing_company = Company.query.filter_by(name=company_name).first()
        if existing_company:
            return jsonify({"error": "Une entreprise avec ce nom existe déjà."}), 409

        # Vérifier si l'utilisateur existe déjà
        existing_user = User.query.filter_by(email=admin_email).first()
        if existing_user:
            return jsonify({"error": "Un utilisateur avec cet email existe déjà."}), 409

        # Créer l'entreprise
        new_company = Company(
            name=company_name,
            address=company_address,
            city=company_city,
            country=company_country,
            signature_volume=signature_volume
        )
        db.session.add(new_company)
        db.session.flush()  # Pour obtenir l'ID de l'entreprise

        # Créer le dossier de l'entreprise
        company_folder = CERTIFICATES_FOLDER / company_name.replace(' ', '_')
        company_folder.mkdir(parents=True, exist_ok=True)

        # Sauvegarder les fichiers de l'administrateur
        cert_path = save_uploaded_file(cert_file, company_folder, f"{admin_email}_cert.p12")
        img_sign_path = save_uploaded_file(img_sign_file, SIGNATURES_FOLDER, f"{admin_email}_img_sign.png")
        name_sign_path = save_uploaded_file(name_sign_file, SIGNATURES_FOLDER, f"{admin_email}_name_sign.png")
        pad_sign_path = save_uploaded_file(pad_sign_file, SIGNATURES_FOLDER, f"{admin_email}_pad_sign.png")

        # Créer l'administrateur de l'entreprise
        admin_user = User(
            email=admin_email,
            name=admin_name,
            sub_name=admin_sub_name,
            phone=admin_phone,
            address=company_address,
            city=company_city,
            country=company_country,
            cni_number=admin_cni_number,
            account_type="employee",
            company_id=new_company.id,
            cert_path=cert_path,
            img_sign_path=img_sign_path,
            name_sign_path=name_sign_path,
            pad_sign_path=pad_sign_path,
            signature_volume=0,  # Utilise le volume de l'entreprise
            sign_roles=sign_roles,
            password_hash=generate_password_hash(admin_password)  # Hacher le mot de passe
        )

        db.session.add(admin_user)
        db.session.commit()

        # Envoyer un email de bienvenue (optionnel)
        try:
            send_email(
                to_email=admin_email,
                subject="Bienvenue sur DKB-Sign - Entreprise créée",
                template_name="welcome_company_admin.html",
                user_name=admin_name,
                company_name=company_name,
                email=admin_email
            )
        except Exception as e:
            current_app.logger.warning(f"Erreur lors de l'envoi de l'email de bienvenue : {str(e)}")

        return jsonify({
            "message": "Entreprise et administrateur créés avec succès",
            "company_id": new_company.id,
            "company_name": company_name,
            "admin_user_id": admin_user.id,
            "admin_email": admin_email
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création de l'entreprise : {str(e)}")
        return jsonify({"error": f"Erreur lors de l'enregistrement : {str(e)}"}), 500
