from flask import Blueprint, request, jsonify, render_template, url_for, current_app
from flask_jwt_extended import create_access_token
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from app.services.email_service import send_email
import uuid
import logging
import json
import base64
import os
from werkzeug.utils import secure_filename
import random
import string
from datetime import datetime, timedelta
import jwt
from app.models import User, Company, db, UserDevice
from user_agents import parse
import secrets
from sqlalchemy import or_, and_  # Ajout de l'import and_


auth_bp = Blueprint('auth', __name__)

# Répertoires
CERTIFICATES_PATH = Path("certificates")
SIGNATURES_PATH = Path("signatures")


@auth_bp.route('/register/individual', methods=['POST'])
def register_individual():
    """
    Crée un compte utilisateur individuel.
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
        name = data.get('name')  # Nom

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
        if not email or not cert_file or not name:
            return jsonify({"error": "Les champs obligatoires (email, cert, name) doivent être remplis."}), 400

        # Création des répertoires pour les certificats et signatures
        user_cert_path = CERTIFICATES_PATH / "users"
        user_cert_path.mkdir(parents=True, exist_ok=True)

        user_sign_path = SIGNATURES_PATH / "users" / email
        user_sign_path.mkdir(parents=True, exist_ok=True)

        # Définition des chemins de sauvegarde
        cert_path = user_cert_path / f"{email}_cert.p12"
        img_sign_path = user_sign_path / f"{email}_img.png" if img_sign_file else None
        name_sign_path = user_sign_path / f"{email}_name.png" if name_sign_file else None
        pad_sign_path = user_sign_path / f"{email}_pad.png" if pad_sign_file else None
        stamp_path = user_sign_path / f"{email}_stamp.png" if stamp_file else None

        # Sauvegarde des fichiers sur le disque
        cert_file.save(cert_path)
        if img_sign_file:
            img_sign_file.save(img_sign_path)
        if name_sign_file:
            name_sign_file.save(name_sign_path)
        if pad_sign_file:
            pad_sign_file.save(pad_sign_path)
        if stamp_file:
            stamp_file.save(stamp_path)

        # Création du nouvel utilisateur dans la base de données
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
            cert_path=str(cert_path),
            img_sign_path=str(img_sign_path) if img_sign_path else None,
            name_sign_path=str(name_sign_path) if name_sign_path else None,
            pad_sign_path=str(pad_sign_path) if pad_sign_path else None,
            stamp_path=str(stamp_path) if stamp_path else None,
            signature_volume=signature_volume,
            name_sign=name_sign,
            current_img_sign=current_img_sign,
            signature_volume_used=0,
            sign_roles=sign_roles,
            with_consent=with_consent,
            uuid=str(uuid.uuid4())
        )
        db.session.add(new_user)
        db.session.commit()

        # Génération du lien pour définir le mot de passe
        reset_url = f"https://dkb-sign-ui.vercel.app/auth/new-password?uuid={new_user.uuid}"

        subject = "Définissez votre mot de passe"
        body = f"Bonjour {name},\n\nVeuillez cliquer sur le lien suivant pour définir votre mot de passe : {reset_url}"

        # Rendu du template HTML pour l'email
        html = render_template(
            'password_reset_email.html',
            name=name,
            reset_url=reset_url,
            current_year=datetime.now().year
        )

        send_email(subject, email, body, html)

        return jsonify({
            "message": "Compte individuel créé avec succès. Un email a été envoyé pour définir le mot de passe.",
            "reset_link": reset_url
        }), 201

    except Exception as e:
        logging.error(f"Erreur lors de l'enregistrement de l'utilisateur : {str(e)}")

        # Nettoyage des fichiers en cas d'erreur
        if 'cert_path' in locals() and cert_path.exists():
            cert_path.unlink()
        if 'img_sign_path' in locals() and img_sign_path and img_sign_path.exists():
            img_sign_path.unlink()
        if 'name_sign_path' in locals() and name_sign_path and name_sign_path.exists():
            name_sign_path.unlink()
        if 'pad_sign_path' in locals() and pad_sign_path and pad_sign_path.exists():
            pad_sign_path.unlink()

        return jsonify({"error": f"Erreur lors de l'enregistrement : {str(e)}"}), 500


@auth_bp.route('/register/company', methods=['POST'])
def register_company():
    """
    Enregistrement d'une entreprise avec ou sans certificat .crt et clé .key.
    """
    data = request.form
    name = data.get('name')
    phone = data.get('phone')
    email = data.get('email')
    address = data.get('address')
    city = data.get('city')
    country = data.get('country')
    cert_type = data.get('cert_type')  # `cachetServeur` ou `personnePhysique`
    cert_file = request.files.get('cert')
    key_file = request.files.get('key')
    signature_volume = data.get('signature_volume')
    with_consent = data.get('with_consent', 'true').lower() == 'true'

    if not name or not phone or not email or not cert_type:
        return jsonify({"error": "Les champs 'name', 'phone', 'email', et 'cert_type' sont obligatoires"}), 400

    # Formater le nom de l'entreprise pour éviter les espaces dans les noms de dossiers
    safe_company_name = name.replace(" ", "_")

    # Créer un dossier dédié pour l'entreprise
    company_folder = CERTIFICATES_PATH / "companies" / safe_company_name
    company_folder.mkdir(parents=True, exist_ok=True)

    # Initialiser les chemins
    cert_path = None
    key_path = None

    try:
        # Sauvegarder les fichiers de certificat et de clé (si fournis)
        if cert_file:
            cert_path = company_folder / "cert.crt"
            cert_file.save(cert_path)
        if key_file:
            key_path = company_folder / "cert.key"
            key_file.save(key_path)

        # Créer une nouvelle entreprise dans la base de données
        new_company = Company(
            name=name,
            phone=phone,
            email=email,
            address=address,
            city=city,
            country=country,
            cert_type=cert_type,
            cert_path=str(cert_path) if cert_path else None,
            key_path=str(key_path) if key_path else None,
            signature_volume=signature_volume,
            with_consent=with_consent
        )
        db.session.add(new_company)
        db.session.commit()

    except Exception as e:
        # Supprimer le dossier en cas d'erreur
        if company_folder.exists():
            for file in company_folder.iterdir():
                file.unlink(missing_ok=True)
            company_folder.rmdir()
        return jsonify({"error": f"Erreur lors de l'enregistrement : {str(e)}"}), 500

    return jsonify({"message": "Entreprise créée avec succès"}), 201


@auth_bp.route('/register/employee', methods=['POST'])
def register_employee():
    """
    Ajout d'un employé dans une entreprise avec gestion des fichiers, rôles, et envoi d'un email pour définir le mot de passe.
    """
    try:
        data = request.form
        cert_file = request.files.get('cert')
        img_sign_file = request.files.get('img_sign_file')
        name_sign_file = request.files.get('name_sign_file')
        pad_sign_file = request.files.get('pad_sign_file')

        # Champs obligatoires
        email = data.get('email')
        name = data.get('name')  # Nom de l'employé
        company_id = data.get('company_id')

        # Champs optionnels
        sub_name = data.get('sub_name')  # Prénom
        phone = data.get('phone')
        address = data.get('address')
        city = data.get('city')
        country = data.get('country')
        cni_number = data.get('cni_number')
        sign_roles_raw = data.get('sign_roles', '[]')
        name_sign = data.get('name_sign')
        current_img_sign = data.get('current_img_sign')

        # Vérification des champs obligatoires
        if not all([email, name, company_id]):
            return jsonify({"error": "Les champs 'email', 'name' et 'company_id' sont obligatoires."}), 400

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

        # Création des dossiers pour l'employé
        safe_company_name = secure_filename(company.name)
        employee_cert_path = CERTIFICATES_PATH / "companies" / safe_company_name / "employees"
        employee_cert_path.mkdir(parents=True, exist_ok=True)

        employee_sign_path = SIGNATURES_PATH / "companies" / safe_company_name / "employees" / email
        employee_sign_path.mkdir(parents=True, exist_ok=True)

        # Définition des chemins pour les fichiers
        cert_path = employee_cert_path / f"{secure_filename(email)}_cert.p12"
        img_sign_path = employee_sign_path / "img_sign.png"
        name_sign_path = employee_sign_path / "name_sign.png"
        pad_sign_path = employee_sign_path / "pad_sign.png"

        # Sauvegarder les fichiers s'ils sont fournis
        if cert_file:
            cert_file.save(cert_path)
        if img_sign_file:
            img_sign_file.save(img_sign_path)
        if name_sign_file:
            name_sign_file.save(name_sign_path)
        if pad_sign_file:
            pad_sign_file.save(pad_sign_path)

        # Ajouter l'employé à la base de données
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
            company_id=company.id,
            cert_path=str(cert_path) if cert_file else None,
            img_sign_path=str(img_sign_path) if img_sign_file else None,
            name_sign_path=str(name_sign_path) if name_sign_file else None,
            pad_sign_path=str(pad_sign_path) if pad_sign_file else None,
            sign_roles=sign_roles,
            name_sign=name_sign,
            current_img_sign=current_img_sign,
            uuid=str(uuid.uuid4())  # Générer un UUID unique pour l'utilisateur
        )
        db.session.add(new_employee)
        db.session.commit()

        # Générer un lien pour définir le mot de passe basé sur l'UUID
        reset_url = f"https://dkb-sign-ui.vercel.app/auth/new-password?uuid={new_employee.uuid}"  # À adapter selon votre frontend

        # Envoi de l'email pour définir le mot de passe
        subject = "Définir votre mot de passe"
        body = f"Bonjour {name},\n\nVeuillez cliquer sur le lien suivant pour définir votre mot de passe : {reset_url}"
        html = render_template(
            'password_reset_email.html',
            name=name,
            reset_url=reset_url,
            current_year=datetime.now().year
        )

        send_email(subject, email, body, html)

        return jsonify({
            "message": "Employé ajouté avec succès. Un email a été envoyé pour définir le mot de passe.",
            "reset_link": reset_url
        }), 201

    except Exception as e:
        logging.error(f"Erreur lors de l'enregistrement de l'employé : {str(e)}")

        # Nettoyage en cas d'erreur
        if 'cert_path' in locals() and cert_path.exists():
            cert_path.unlink()
        if 'img_sign_path' in locals() and img_sign_path.exists():
            img_sign_path.unlink()
        if 'name_sign_path' in locals() and name_sign_path.exists():
            name_sign_path.unlink()
        if 'pad_sign_path' in locals() and pad_sign_path.exists():
            pad_sign_path.unlink()

        return jsonify({"error": f"Erreur lors de l'enregistrement : {str(e)}"}), 500


@auth_bp.route('/check-password-set', methods=['GET'])
def check_password_set():
    """
    Vérifie si l'utilisateur a défini son mot de passe pour la première fois après la création du compte.
    """
    user_uuid = request.args.get('uuid')

    # Vérifier que l'UUID est fourni
    if not user_uuid:
        return jsonify({"error": "UUID est obligatoire."}), 400

    try:
        # Rechercher l'utilisateur par UUID
        user = User.query.filter_by(uuid=user_uuid).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable avec cet UUID."}), 404

        # Vérifier si le mot de passe est défini
        if user.password_hash:
            return jsonify({"password_set": True}), 200
        else:
            return jsonify({"password_set": False}), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la vérification du mot de passe : {str(e)}"}), 500


@auth_bp.route('/set-password', methods=['POST'])
def set_password():
    data = request.json
    user_uuid = data.get('uuid')
    new_password = data.get('password')

    if not user_uuid or not new_password:
        return jsonify({"error": "UUID et mot de passe sont obligatoires."}), 400

    try:
        user = User.query.filter_by(uuid=user_uuid).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable avec cet UUID."}), 404

        hashed_password = generate_password_hash(new_password)
        user.password_hash = hashed_password
        
        # Générer un PIN de 4 chiffres
        pin_code = ''.join(random.choices(string.digits, k=4))
        user.pin_code = pin_code
        user.pin_created_at = datetime.utcnow()
        
        db.session.commit()

        # Envoyer le PIN par email
        subject = "Votre code PIN de signature - DKB-Sign"
        body = (
            f"Bonjour {user.name},\n\n"
            f"Votre mot de passe a été modifié avec succès.\n"
            f"Voici votre code PIN de 4 chiffres pour signer vos documents : {pin_code}\n\n"
            f"Conservez ce code précieusement, il vous sera demandé à chaque signature de document.\n\n"
            f"Cordialement,\nL'équipe DKB-Sign"
        )
        html = render_template(
            'pin_code_email.html',
            pin_code=pin_code,
            current_year=datetime.now().year
        )

        send_email(subject, user.email, body, html)

        return jsonify({
            "message": "Mot de passe défini avec succès. Un email contenant votre code PIN vous a été envoyé."
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la mise à jour du mot de passe : {str(e)}"}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"error": "Email et mot de passe sont requis."}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"error": "Identifiants invalides."}), 401

        if not user.password_hash:
            return jsonify({
                "error": "Mot de passe non défini. Veuillez le définir avant de vous connecter.",
                "password_set": False,
                "reset_link": f"https://dkb-sign-ui.vercel.app/auth/new-password?uuid={user.uuid}"
            }), 403

        if not check_password_hash(user.password_hash, password):
            return jsonify({"error": "Identifiants invalides."}), 401

        # Création du token JWT
        token = create_access_token(identity=user.email)
        
        # Construction de la réponse
        response = {
            "message": "Connexion réussie.",
            "access_token": token,
            "user": {
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
                "sign_roles": user.sign_roles,
                "img_sign_files": {
                    "current_img_sign": user.current_img_sign,
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
        }

        # Ajouter les informations de l'entreprise si c'est un employé
        if user.account_type == "employee":
            company = Company.query.get(user.company_id)
            if company:
                response["user"]["company"] = {
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
                    "with_consent": company.with_consent,
                    "created_at": company.created_at.strftime('%Y-%m-%d %H:%M:%S') if company.created_at else None
                }
            else:
                return jsonify({"error": "L'utilisateur est un employé mais n'est lié à aucune entreprise."}), 400

            response["message"] = "Connexion réussie en tant qu'employé."

        elif user.account_type == "admin":
            response["message"] = "Connexion réussie en tant qu'administrateur."

        elif user.account_type == "individual":
            response["message"] = "Connexion réussie en tant qu'utilisateur individuel."

        else:
            return jsonify({"error": "Type de compte inconnu."}), 400

        return jsonify(response), 200

    except KeyError as e:
        print(f"ERROR - Missing key: {str(e)}")
        return jsonify({"error": "Données manquantes ou mal formatées."}), 400

    except Exception as e:
        print(f"ERROR - Login failed: {str(e)}")
        return jsonify({"error": "Une erreur inattendue est survenue. Veuillez réessayer."}), 500


@auth_bp.route('/verify-pin', methods=['POST'])
def verify_pin():
    """
    Vérifie le code PIN d'un utilisateur.
    Requiert un JSON avec l'UUID de l'utilisateur et le code PIN.
    """
    data = request.json
    user_uuid = data.get('uuid')
    pin_code = data.get('pin_code')

    if not user_uuid or not pin_code:
        return jsonify({"error": "UUID et code PIN sont obligatoires."}), 400

    try:
        user = User.query.filter_by(uuid=user_uuid).first()
        if not user:
            return jsonify({"error": "Utilisateur introuvable avec cet UUID."}), 404

        # Utiliser la méthode verify_pin du modèle User
        is_valid, message = user.verify_pin(pin_code)
        
        if not is_valid:
            return jsonify({"error": message}), 400

        return jsonify({
            "message": message,
            "is_valid": True
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la vérification du code PIN : {str(e)}"}), 500


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    Route pour demander la réinitialisation du mot de passe.
    Envoie un email avec un lien de réinitialisation contenant un token JWT.
    """
    try:
        data = request.get_json()
        email = data.get('email')
        
        logging.info(f"Demande de réinitialisation du mot de passe pour l'email: {email}")
        
        if not email:
            logging.warning("L'email est requis")
            return jsonify({"error": "L'email est requis"}), 400
            
        user = User.query.filter_by(email=email).first()
        if not user:
            logging.info("L'utilisateur n'existe pas pour l'email fourni")
            # Pour des raisons de sécurité, ne pas indiquer si l'email existe ou non
            return jsonify({"message": "Si l'adresse email existe, vous recevrez un lien de réinitialisation"}), 200
            
        # Générer un token JWT valide pendant 1 heure
        reset_token = jwt.encode(
            {
                'user_id': user.id,
                'exp': datetime.utcnow() + timedelta(hours=1)
            },
            current_app.config['JWT_SECRET_KEY'],
            algorithm='HS256'
        )

        # Préparer le lien de réinitialisation
        reset_link = f"https://dkb-sign-ui.vercel.app/auth/reset-password?token={reset_token}"
        
        # Préparer et envoyer l'email
        html_content = render_template(
            'reset_password.html',
            user_name=user.name,
            reset_link=reset_link
        )
        
        send_email(
            subject="Réinitialisation de votre mot de passe",
            recipient=user.email,
            body="Pour réinitialiser votre mot de passe, cliquez sur le lien suivant : " + reset_link,
            html=html_content
        )
        
        logging.info(f"Email de réinitialisation envoyé à {user.email}")
        return jsonify({
            "message": "Email de réinitialisation envoyé avec succès",
        }), 200
        
    except Exception as e:
        logging.error(f"Erreur lors de la demande de réinitialisation du mot de passe: {str(e)}")
        return jsonify({"error": "Une erreur est survenue lors de la demande de réinitialisation"}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    Route pour réinitialiser le mot de passe avec un token valide.
    Requiert le nouveau mot de passe et sa confirmation.
    """
    try:
        data = request.get_json()
        token = data.get('token')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        if not token or not new_password or not confirm_password:
            return jsonify({
                "error": "Le token, le nouveau mot de passe et sa confirmation sont requis"
            }), 400
        
        if new_password != confirm_password:
            return jsonify({
                "error": "Le nouveau mot de passe et sa confirmation ne correspondent pas"
            }), 400
            
        # Vérifier la complexité du mot de passe
        if len(new_password) < 8:
            return jsonify({
                "error": "Le mot de passe doit contenir au moins 8 caractères"
            }), 400
            
        try:
            # Vérifier et décoder le token
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=['HS256']
            )
            user_id = payload.get('user_id')
            
            user = User.query.get(user_id)
            if not user:
                return jsonify({"error": "Utilisateur non trouvé"}), 404
                
            # Mettre à jour le mot de passe
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            
            return jsonify({
                "message": "Votre mot de passe a été réinitialisé avec succès",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "sub_name": user.sub_name,
                    "phone": user.phone,
                    "address": user.address,
                    "city": user.city,
                    "country": user.country
                }
            }), 200
            
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Le lien de réinitialisation a expiré"}), 400
        except jwt.InvalidTokenError:
            return jsonify({"error": "Le lien de réinitialisation est invalide"}), 400
            
    except Exception as e:
        logging.error(f"Erreur lors de la réinitialisation du mot de passe: {str(e)}")
        return jsonify({"error": "Une erreur est survenue lors de la réinitialisation"}), 500


@auth_bp.route('/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """
    Met à jour les informations du profil utilisateur.
    """
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
            
        data = request.get_json()
        
        # Mettre à jour les champs si fournis
        if 'name' in data:
            user.name = data['name']
        if 'sub_name' in data:
            user.sub_name = data['sub_name']
        if 'phone' in data:
            user.phone = data['phone']
        if 'address' in data:
            user.address = data['address']
        if 'city' in data:
            user.city = data['city']
        if 'country' in data:
            user.country = data['country']
        
        db.session.commit()
        
        return jsonify({
            "message": "Profil mis à jour avec succès.",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "sub_name": user.sub_name,
                "phone": user.phone,
                "address": user.address,
                "city": user.city,
                "country": user.country
            }
        }), 200
    except Exception as e:
        logging.error(f"Erreur lors de la mise à jour du profil: {str(e)}")
        return jsonify({"error": "Une erreur est survenue lors de la mise à jour du profil."}), 500


def get_device_fingerprint(user_agent_info, ip_address):
    """
    Crée une empreinte unique pour l'appareil en utilisant :
    - La famille du navigateur (Chrome, Firefox, etc.)
    - La version exacte du navigateur
    - Le système d'exploitation et sa version
    - Le type d'appareil (mobile, tablette, PC)
    - L'adresse IP
    """
    # Extraire toutes les informations disponibles
    browser = f"{user_agent_info.browser.family} {user_agent_info.browser.version_string}"
    os = f"{user_agent_info.os.family} {user_agent_info.os.version_string}"
    device = user_agent_info.device.family
    
    # Vérifier les caractéristiques de l'appareil
    is_mobile = user_agent_info.is_mobile
    is_tablet = user_agent_info.is_tablet
    is_pc = user_agent_info.is_pc
    
    # Créer une liste de toutes les caractéristiques
    features = [
        browser,
        os,
        device,
        f"mobile:{is_mobile}",
        f"tablet:{is_tablet}",
        f"pc:{is_pc}",
        ip_address
    ]
    
    # Créer une chaîne unique avec toutes les caractéristiques
    fingerprint = "|".join(str(f) for f in features)
    
    # Créer un hash de cette chaîne pour avoir une empreinte plus courte
    import hashlib
    return hashlib.sha256(fingerprint.encode()).hexdigest()


def get_base64_encoded_image(file_path):
    """Convertit le contenu d'un fichier image en base64."""
    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return None


def generate_block_token():
    return secrets.token_urlsafe(32)


@auth_bp.route('/approve-device/<token>', methods=['GET'])
def approve_device(token):
    """Approuver un nouvel appareil"""
    device = UserDevice.query.filter_by(approve_token=token).first()
    
    if not device:
        return render_template('error.html', 
                             message="Token invalide ou expiré",
                             description="Ce lien n'est plus valide. Veuillez réessayer de vous connecter.")

    try:
        device.status = 'accepted'
        device.approve_token = None  # Invalider le token après utilisation
        device.block_token = None    # Invalider aussi le token de blocage
        db.session.commit()
        
        return render_template('device_approved.html',
                             device_name=device.device_name,
                             login_time=device.last_login.strftime('%d/%m/%Y à %H:%M'))
    
    except Exception as e:
        db.session.rollback()
        print(f"ERROR - Failed to approve device: {str(e)}")
        return render_template('error.html',
                             message="Erreur lors de l'approbation",
                             description="Une erreur est survenue. Veuillez réessayer plus tard.")


@auth_bp.route('/block-device/<token>', methods=['GET'])
def block_device(token):
    """Bloquer un appareil suspect"""
    device = UserDevice.query.filter_by(block_token=token).first()
    
    if not device:
        return render_template('error.html',
                             message="Token invalide ou expiré",
                             description="Ce lien n'est plus valide.")

    try:
        device.status = 'blocked'
        device.approve_token = None  # Invalider le token d'approbation
        device.block_token = None    # Invalider le token après utilisation
        db.session.commit()
        
        return render_template('device_blocked_confirmation.html',
                             device_name=device.device_name)
    
    except Exception as e:
        db.session.rollback()
        print(f"ERROR - Failed to block device: {str(e)}")
        return render_template('error.html',
                             message="Erreur lors du blocage",
                             description="Une erreur est survenue. Veuillez réessayer plus tard.")


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()  # Requiert un token JWT pour s'assurer que l'utilisateur est authentifié
def change_password():
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({"error": "Les champs 'current_password' et 'new_password' sont obligatoires."}), 400

    try:
        # Récupérer l'utilisateur authentifié
        user_email = get_jwt_identity()
        user = User.query.filter_by(email=user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier le mot de passe actuel
        if not check_password_hash(user.password_hash, current_password):
            return jsonify({"error": "Le mot de passe actuel est incorrect."}), 401

        # Mettre à jour le mot de passe avec le nouveau
        hashed_password = generate_password_hash(new_password)
        user.password_hash = hashed_password
        db.session.commit()

        # Envoyer un email de confirmation
        subject = "Modification de votre mot de passe - DKB-Sign"
        body = (
            f"Bonjour {user.name},\n\n"
            f"Votre mot de passe a été modifié avec succès.\n\n"
            f"Si vous n'êtes pas à l'origine de cette modification, veuillez nous contacter immédiatement.\n\n"
            f"Cordialement,\nL'équipe DKB-Sign"
        )
        html = render_template(
            'password_change_confirmation.html',
            user_name=user.name,
            current_year=datetime.now().year
        )

        send_email(subject, user.email, body, html)

        return jsonify({
            "message": "Votre mot de passe a été modifié avec succès. Un email de confirmation vous a été envoyé."
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la modification du mot de passe : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@auth_bp.route('/generate-app-key', methods=['POST'])
@jwt_required()
def generate_app_key():
    """
    Génère une clé API (app_key) pour l'utilisateur authentifié.
    Cette clé sera utilisée pour l'authentification dans les routes de l'API publique.
    """
    try:
        # Récupérer l'utilisateur authentifié
        user_email = get_jwt_identity()
        user = User.query.filter_by(email=user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Générer une nouvelle clé API
        api_key = user.generate_api_key()
        db.session.commit()

        # Envoyer un email de notification
        subject = "Nouvelle clé API générée - DKB-Sign"
        body = (
            f"Bonjour {user.name},\n\n"
            f"Une nouvelle clé API a été générée pour votre compte.\n\n"
            f"Clé API : {api_key}\n\n"
            f"Cette clé vous permet d'accéder aux API publiques de DKB-Sign.\n"
            f"Gardez cette clé en sécurité et ne la partagez pas.\n\n"
            f"Si vous n'êtes pas à l'origine de cette génération, veuillez nous contacter immédiatement.\n\n"
            f"Cordialement,\nL'équipe DKB-Sign"
        )
        html = render_template(
            'api_key_generated.html',
            user_name=user.name,
            api_key=api_key,
            current_year=datetime.now().year
        )

        try:
            send_email(subject, user.email, body, html)
        except Exception as email_error:
            current_app.logger.warning(f"Erreur lors de l'envoi de l'email de notification : {str(email_error)}")

        return jsonify({
            "message": "Clé API générée avec succès.",
            "api_key": api_key,
            "created_at": user.api_key_created_at.isoformat(),
            "active": user.api_key_active
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la génération de la clé API : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@auth_bp.route('/deactivate-app-key', methods=['POST'])
@jwt_required()
def deactivate_app_key():
    """
    Désactive la clé API de l'utilisateur authentifié.
    """
    try:
        # Récupérer l'utilisateur authentifié
        user_email = get_jwt_identity()
        user = User.query.filter_by(email=user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        if not user.api_key:
            return jsonify({"error": "Aucune clé API n'est définie pour cet utilisateur."}), 400

        # Désactiver la clé API
        user.deactivate_api_key()
        db.session.commit()

        return jsonify({
            "message": "Clé API désactivée avec succès."
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la désactivation de la clé API : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500


@auth_bp.route('/app-key-status', methods=['GET'])
@jwt_required()
def app_key_status():
    """
    Récupère le statut de la clé API de l'utilisateur authentifié.
    """
    try:
        # Récupérer l'utilisateur authentifié
        user_email = get_jwt_identity()
        user = User.query.filter_by(email=user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        if not user.api_key:
            return jsonify({
                "has_api_key": False,
                "message": "Aucune clé API n'est définie pour cet utilisateur."
            }), 200

        return jsonify({
            "has_api_key": True,
            "api_key": user.api_key,
            "created_at": user.api_key_created_at.isoformat() if user.api_key_created_at else None,
            "active": user.api_key_active
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération du statut de la clé API : {str(e)}")
        return jsonify({"error": f"Une erreur est survenue : {str(e)}"}), 500
