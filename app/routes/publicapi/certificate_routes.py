from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, Company
import subprocess
import os
from pathlib import Path
from datetime import datetime, timedelta

certificate_bp = Blueprint('certificate_bp', __name__)

def run_openssl_command(command, cwd=None, input_data=None):
    """
    Exécute une commande OpenSSL et retourne le résultat
    """
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            cwd=cwd,
            input=input_data.encode() if input_data else None
        )
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Erreur OpenSSL: {stderr.decode()}")
        
        return stdout.decode()
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'exécution de la commande OpenSSL: {str(e)}")
        raise

@certificate_bp.route('/certificates/generate', methods=['POST'])
@jwt_required()
def generate_certificate():
    """
    Génère un certificat pour l'utilisateur connecté
    """
    try:
        # Récupérer l'utilisateur
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupérer les données du formulaire
        data = request.get_json()
        if not data:
            return jsonify({"error": "Données manquantes"}), 400

        # Créer le dossier pour les certificats
        cert_dir = Path(current_app.config['CERTIFICATES_FOLDER'])
        user_cert_dir = cert_dir / user.email.replace('@', '_at_')
        user_cert_dir.mkdir(parents=True, exist_ok=True)

        # Chemins des fichiers
        key_file = user_cert_dir / f"{user.email.split('@')[0]}.key"
        csr_file = user_cert_dir / f"{user.email.split('@')[0]}.csr"
        crt_file = user_cert_dir / f"{user.email.split('@')[0]}.crt"
        p12_file = user_cert_dir / f"{user.email.split('@')[0]}.p12"

        # 1. Générer la clé privée
        key_command = f'openssl genrsa -out "{key_file}" 2048'
        run_openssl_command(key_command)

        # 2. Générer la demande de certificat (CSR)
        # Préparer les informations du sujet
        subject_info = (
            f"/C=CM"
            f"/ST=Littoral"
            f"/L=Douala"
            f"/O={data.get('organization', 'DKBSign')}"
            f"/OU={data.get('unit', 'Digital Signature')}"
            f"/CN={user.email}"
            f"/emailAddress={user.email}"
        )
        
        csr_command = f'openssl req -new -key "{key_file}" -out "{csr_file}" -subj "{subject_info}"'
        run_openssl_command(csr_command)

        # 3. Signer le certificat avec l'AC
        # Calculer la date d'expiration (1 heure à partir de maintenant)
        expiry_date = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y%m%d%H%M%S")
        
        ca_cert = cert_dir / "ACDKBSPersonnes2024_ca_certificate.crt"
        ca_key = cert_dir / "ACDKBSPersonnes2024_ca_private_key.pem"
        
        sign_command = (
            f'openssl x509 -req '
            f'-CA "{ca_cert}" '
            f'-CAkey "{ca_key}" '
            f'-in "{csr_file}" '
            f'-out "{crt_file}" '
            f'-not_after "{expiry_date}Z" '
            f'-CAcreateserial'
        )
        run_openssl_command(sign_command)

        # 4. Créer le fichier PKCS#12
        p12_password = data.get('password', '')  # Mot de passe pour le fichier P12
        p12_command = (
            f'openssl pkcs12 -export '
            f'-in "{crt_file}" '
            f'-inkey "{key_file}" '
            f'-out "{p12_file}" '
            f'-password pass:{p12_password}'
        )
        run_openssl_command(p12_command)

        # Mettre à jour les chemins des certificats dans la base de données
        user.certificate_path = str(crt_file)
        user.private_key_path = str(key_file)
        user.p12_path = str(p12_file)
        
        # Si l'utilisateur est un employé, mettre à jour aussi l'entreprise
        if user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if company:
                company.certificate_path = str(crt_file)
                company.private_key_path = str(key_file)

        current_app.db.session.commit()

        return jsonify({
            "message": "Certificat généré avec succès",
            "certificate_path": str(crt_file),
            "p12_path": str(p12_file)
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la génération du certificat: {str(e)}")
        return jsonify({"error": f"Erreur lors de la génération du certificat: {str(e)}"}), 500
