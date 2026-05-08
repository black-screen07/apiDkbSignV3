import requests
from flask import Blueprint, request, jsonify, url_for, send_from_directory, current_app, render_template
from flask_jwt_extended import jwt_required, get_jwt_identity
from pathlib import Path
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from pyhanko.sign.signers import PdfSignatureMetadata
from pyhanko.pdf_utils import images
from io import BytesIO
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
from PIL import Image
import uuid
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from pyhanko.stamp import StaticStampStyle
import tempfile
import os
from datetime import datetime
from app.models import User, Company, Document, CertTypeEnum, db, Flow, LineFlow, Contact
from app.services.email_service import send_email
from app.services.signature_proof_service import create_signature_proof, build_proof_urls
from app.utils.signature_utils import (
    retrieve_certificates,
    load_signature_image,
    update_signature_volumes,
    add_qr_code_to_pdf,
    generate_qr_code_image,
    apply_qr_codes
)

flow_signature_bp = Blueprint('flow_signature_bp', __name__)


def get_base_path():
    """Get the absolute base path for file storage"""
    return Path(current_app.root_path).parent


# Chemin vers le dossier des PDF signés
SIGNED_PDF_FOLDER = None  # Will be initialized when the app context is available
_PATHS_INITIALIZED = False

# Chemin vers les certificats et signatures
CERTIFICATE_FOLDER = Path("certificates/users")
SIGNATURE_FOLDER = Path("signatures/users")
COMPANY_SIGNATURE_FOLDER = Path("signatures/companies")


@flow_signature_bp.before_app_request
def initialize_paths():
    """Initialize paths when the app context is available"""
    global SIGNED_PDF_FOLDER, _PATHS_INITIALIZED
    if not _PATHS_INITIALIZED:
        SIGNED_PDF_FOLDER = get_base_path() / "documents" / "doc_signed"
        SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)
        _PATHS_INITIALIZED = True


def mm_to_points(mm):
    """Convertit des millimètres en points PDF."""
    return mm * 2.83465


def load_cert_chain():
    """Charge la chaîne de certificats DKBS (exemple)."""
    intermediate_cert_path = 'certificates/DKBS/ACDKBSPersonnes2024.cacert.pem'
    root_cert_path = 'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
    return [intermediate_cert_path, root_cert_path]


def extract_certificate_and_key(p12_path, password, cert_output_path, key_output_path):
    with open(p12_path, 'rb') as p12_file:
        p12_data = p12_file.read()

    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        p12_data, password, default_backend()
    )

    # Enregistrer le certificat au format .crt
    with open(cert_output_path, 'wb') as cert_file:
        cert_file.write(certificate.public_bytes(Encoding.PEM))

    # Enregistrer la clé privée au format .key
    with open(key_output_path, 'wb') as key_file:
        key_file.write(
            private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption()
            )
        )


def retrieve_certificates(user, company):
    """
    Récupère ou extrait les certificats nécessaires selon le type de compte (individuel ou employé) et l'entreprise.
    """
    cert_path, key_path, cert_chain = None, None, []

    if user.account_type == "employee" and company:
        if company.cert_type == CertTypeEnum.CACHET_SERVEUR:
            cert_path = Path(company.cert_path)
            key_path = Path(company.key_path)
            cert_chain = [
                'certificates/DKBS/ACDKBSPersonnes2024.cacert.pem',
                'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
            ]
            if not cert_path.exists() or not key_path.exists():
                raise FileNotFoundError(f"Certificat ou clé privée introuvable pour l'entreprise : {company.name}.")
        elif company.cert_type == CertTypeEnum.PERSONNE_PHYSIQUE:
            cert_path = CERTIFICATE_FOLDER / f"{user.email}_cert.crt"
            key_path = CERTIFICATE_FOLDER / f"{user.email}_cert.key"
            p12_path = CERTIFICATE_FOLDER / f"{user.email}_cert.p12"

            if not cert_path.exists() or not key_path.exists():
                if not p12_path.exists():
                    raise FileNotFoundError(f"Certificat (.p12) non trouvé pour l'utilisateur {user.email}.")
                extract_certificate_and_key(
                    p12_path=p12_path,
                    password=b"2468",
                    cert_output_path=cert_path,
                    key_output_path=key_path
                )
            cert_chain = [
                'certificates/DKBS/ACDKBSPersonnes2024.cacert.pem',
                'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
            ]

    elif user.account_type == "individual":
        cert_path = CERTIFICATE_FOLDER / f"{user.email}_cert.crt"
        key_path = CERTIFICATE_FOLDER / f"{user.email}_cert.key"
        p12_path = CERTIFICATE_FOLDER / f"{user.email}_cert.p12"

        if not cert_path.exists() or not key_path.exists():
            if not p12_path.exists():
                raise FileNotFoundError(f"Certificat (.p12) non trouvé pour l'utilisateur {user.email}.")

            extract_certificate_and_key(
                p12_path=p12_path,
                password=b"2468",
                cert_output_path=cert_path,
                key_output_path=key_path
            )
        cert_chain = [
            'certificates/DKBS/ACDKBSPersonnes2024.cacert.pem',
            'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
        ]
    else:
        raise ValueError("Type de compte ou entreprise invalide.")

    return cert_path, key_path, cert_chain


def load_signature_image(user):
    """
    Charge l'image de signature en fonction de 'current_img_sign'.
    Applique le pipeline complet: RGBA, trim, upscale haute résolution, netteté.
    """
    if user.current_img_sign == "img":
        signature_path = Path(user.img_sign_path)
    elif user.current_img_sign == "pad":
        signature_path = Path(user.pad_sign_path)
    elif user.current_img_sign == "name":
        signature_path = Path(user.name_sign_path)
    else:
        raise ValueError("Valeur de 'current_img_sign' invalide.")

    if not signature_path.exists():
        raise FileNotFoundError(f"Image de signature introuvable : {signature_path}")

    img = Image.open(signature_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    # NOTE: Ne PAS appeler prepare_signature_image ici.
    # Le code de signature le fait déjà. Un double traitement dégrade la qualité.
    return img


def load_stamp_image(user):
    """
    Charge l'image de cachet d'un utilisateur uniquement.
    """
    try:
        if user.stamp_path:
            stamp_path = Path(user.stamp_path)
            if stamp_path.exists() and stamp_path.is_file():
                return stamp_path.as_posix()
        raise FileNotFoundError("Aucun cachet valide trouvé pour l'utilisateur.")
    except Exception as e:
        current_app.logger.error(f"Erreur lors du chargement de l'image du cachet : {str(e)}")
        raise


def add_text_to_pdf(input_pdf_stream, text, page=None, x=50, y=100):
    """
    Ajoute un texte à un PDF *sur une seule page* (ou sur toutes si page=None).
    Retourne un flux BytesIO du PDF modifié.
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(595.27, 841.89))
    can.setFont("Helvetica-Bold", 12)

    # Dessine le texte si la page est spécifiée
    if page is not None:
        can.drawString(mm_to_points(x), mm_to_points(y), text)
        can.save()
        packet.seek(0)
        new_pdf = PdfReader(packet)
    else:
        # On n'écrit rien ici, car la fusion se fera page par page plus bas
        can.save()
        packet.seek(0)
        new_pdf = None

    packet.seek(0)
    existing_pdf = PdfReader(input_pdf_stream)
    output = PdfWriter()

    for i, page_content in enumerate(existing_pdf.pages):
        if page is None or i == page:
            if new_pdf is None:
                # Génère un "packet" à la volée pour chaque page si page=None
                temp_packet = BytesIO()
                can_temp = canvas.Canvas(temp_packet, pagesize=(595.27, 841.89))
                can_temp.setFont("Helvetica-Bold", 12)
                can_temp.drawString(mm_to_points(x), mm_to_points(y), text)
                can_temp.save()
                temp_packet.seek(0)
                merged_pdf = PdfReader(temp_packet)
                page_content.merge_page(merged_pdf.pages[0])
            else:
                # Fusion directe si un new_pdf statique est déjà prêt
                page_content.merge_page(new_pdf.pages[0])
        output.add_page(page_content)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def apply_stamp_to_pdf(input_pdf_stream, user, pages=None, x=50, y=100, width=100, height=50):
    """
    Ajoute un tampon (image) à un PDF.
    - Si `pages` est None, applique le tampon à toutes les pages.
    - Sinon, applique le tampon aux pages spécifiées dans la liste `pages`.
    Retourne un flux BytesIO du PDF modifié.
    """
    stamp_image_path = load_stamp_image(user)
    if not stamp_image_path:
        raise ValueError("Aucune image de tampon trouvée ou chemin non valide.")

    existing_pdf = PdfReader(input_pdf_stream)
    output = PdfWriter()

    for i, page_content in enumerate(existing_pdf.pages):
        if pages is None or i in pages:
            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=(595.27, 841.89))
            # Attention : l'origine (0,0) de reportlab est en bas à gauche.
            # Pour aligner sur la même logique (x, y) du haut vers le bas, ajustez selon la taille de la page.
            # ICI, on considère un A4 vertical (595.27, 841.89).
            can.drawImage(
                stamp_image_path,
                x,
                y,
                width=mm_to_points(width),
                height=mm_to_points(height),
                mask='auto'
            )
            can.save()

            packet.seek(0)
            temp_pdf = PdfReader(packet)
            page_content.merge_page(temp_pdf.pages[0])

        output.add_page(page_content)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def add_image_to_pdf(input_pdf_stream, image_bytes, page, x, y, width=50, height=50):
    """
    Ajoute une image (en bytes) à un PDF sur une page spécifique.
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(595.27, 841.89))
    can.drawImage(
        image_bytes,
        mm_to_points(x), mm_to_points(y),
        width=mm_to_points(width),
        height=mm_to_points(height),
        mask='auto'
    )
    can.save()

    packet.seek(0)
    new_pdf = PdfReader(packet)
    existing_pdf = PdfReader(input_pdf_stream)
    output = PdfWriter()

    for i in range(len(existing_pdf.pages)):
        page_content = existing_pdf.pages[i]
        if i == page:
            page_content.merge_page(new_pdf.pages[0])
        output.add_page(page_content)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def update_signature_volumes(user, company, count):
    """
    Met à jour le volume de signatures consommées.
    """
    if user.account_type == "individual":
        user.signature_volume_used += count
    elif user.account_type == "employee" and company:
        user.signature_volume_used += count
        company.signature_volume_used += count


@flow_signature_bp.route('/documents/doc_signed/<path:subfolder>/<filename>', methods=['GET'])
def download_file(subfolder, filename):
    """
    Endpoint pour télécharger un fichier signé en fonction du sous-dossier.
    """
    # Initialize paths if not already done
    if SIGNED_PDF_FOLDER is None:
        initialize_paths()

    file_path = SIGNED_PDF_FOLDER / subfolder / filename
    if not file_path.exists():
        current_app.logger.error(f"File not found: {file_path}")
        return jsonify({"error": f"Fichier introuvable: {file_path}"}), 404

    try:
        return send_from_directory(file_path.parent, file_path.name)
    except Exception as e:
        current_app.logger.error(f"Error serving file {file_path}: {str(e)}")
        return jsonify({"error": f"Erreur lors de l'accès au fichier: {str(e)}"}), 500


@flow_signature_bp.route('flows/<int:flow_id>/sign-pdf', methods=['POST'])
@jwt_required()
def sign_pdf(flow_id):
    """
    Endpoint pour signer un document dans un flow.
    Permet désormais le placement du QR code, de la date,
    du custom_text et du cachet sur plusieurs pages.
    """
    try:
        current_user_email = get_jwt_identity()
        current_app.logger.info(f"User {current_user_email} attempting to sign PDF in flow {flow_id}")

        # Récupérer l'utilisateur
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupération des données JSON
        data = request.get_json()
        if not data:
            return jsonify({"error": "Aucune donnée JSON fournie"}), 400
        if "file_url" not in data:
            return jsonify({"error": "Le champ 'file_url' est requis"}), 400
        if "params" not in data:
            return jsonify({"error": "Le champ 'params' est requis"}), 400

        file_url = data["file_url"]
        params = data["params"]

        # Vérifier le flow
        flow = Flow.query.get(flow_id)
        if not flow:
            return jsonify({"error": "Flow introuvable"}), 404

        # Vérifier que l'utilisateur est le signataire actuel
        line_flow = LineFlow.query.filter_by(
            flow_id=flow_id,
            user_id=user.id,
            action_done=False
        ).first()
        if not line_flow:
            return jsonify({"error": "Vous n'êtes pas autorisé à signer ce document"}), 403

        # Vérifier que l'OTP a été validé
        if not line_flow.verified_read_aprob:
            return jsonify({"error": "Veuillez d'abord valider le code OTP"}), 400

        # Récupérer le document
        document = Document.query.get(flow.document_id)
        if not document:
            return jsonify({"error": "Document introuvable"}), 404

        # Récupérer le fichier PDF depuis file_url
        try:
            response = requests.get(file_url)
            response.raise_for_status()
            file_content = response.content
        except requests.RequestException as e:
            return jsonify({"error": f"Erreur lors de la récupération du fichier: {str(e)}"}), 500

        # Récupérer l'initiateur du flow (priority=0)
        initiator_line = LineFlow.query.filter_by(flow_id=flow_id, priority=0).first()
        if not initiator_line:
            return jsonify({"error": "Initiateur du flow introuvable"}), 404

        initiator = User.query.get(initiator_line.user_id)
        if not initiator:
            return jsonify({"error": "Utilisateur initiateur introuvable"}), 404

        # Détermine le sous-dossier pour le stockage du PDF signé
        company = None
        if initiator.account_type == "employee" and initiator.company_id:
            company = Company.query.get(initiator.company_id)

        subfolder = (
            f"companies/{company.name.replace(' ', '_')}" if initiator.account_type == "employee" and company
            else f"users/{initiator.email}"
        )

        # Vérifier si un signataire a déjà signé
        has_signed = LineFlow.query.filter_by(flow_id=flow_id, status="signed").first() is not None

        # Si le document a déjà été signé, utiliser son chemin existant
        if has_signed and document.file_path:
            # Utiliser le chemin existant
            subfolder_path = SIGNED_PDF_FOLDER / Path(document.file_path).parent
            signed_pdf_path = SIGNED_PDF_FOLDER / document.file_path
            
            # Générer l'URL de téléchargement à partir du chemin existant
            download_url = url_for(
                'flow_signature_bp.download_file',
                subfolder=str(Path(document.file_path).parent).replace('\\', '/'),
                filename=Path(document.file_path).name,
                _external=True
            )
        else:
            # Première signature : créer un nouveau chemin
            signed_pdf_folder = SIGNED_PDF_FOLDER / subfolder
            signed_pdf_folder.mkdir(parents=True, exist_ok=True)

            # Générer un nom unique pour le PDF signé
            unique_id = uuid.uuid4().hex
            unique_filename = f"signed_pdf_{unique_id}.pdf"
            signed_pdf_path = signed_pdf_folder / unique_filename

            # Générer l'URL de téléchargement pour le nouveau fichier
            download_url = url_for(
                'flow_signature_bp.download_file',
                subfolder=subfolder,
                filename=unique_filename,
                _external=True
            )

        # On va travailler en mémoire avant de sauvegarder
        input_pdf_buffer = BytesIO(file_content)

        # Actions autorisées pour ce signataire
        actions = line_flow.actions or []
        current_app.logger.info(f"Actions autorisées: {actions}")
        current_app.logger.info(f"Paramètres reçus: {params}")

        # Définition des champs requis pour chaque type d'élément
        required_fields = {
            "paraphe": ["x", "y", "text"],  # page est optionnel
            "date": ["x", "y"],  # page est optionnel, text sera la date actuelle
            "custom_text": ["x", "y", "text"],  # page est optionnel
            "stamp": ["x", "y"],  # page, width et height sont optionnels
            "qrcode": ["x", "y", "data"]  # page, width, height et autres paramètres sont optionnels
        }

        # Vérifier la structure des éléments fournis (sans les rendre obligatoires)
        positions = params.get("positions", {})
        for element_name, element_data in positions.items():
            if element_name in required_fields:
                # Si c'est une liste, vérifier chaque élément
                if isinstance(element_data, list):
                    for idx, item in enumerate(element_data):
                        missing_fields = [field for field in required_fields[element_name] if field not in item]
                        if missing_fields:
                            return jsonify({
                                "error": f"Champs manquants dans '{element_name}[{idx}]': {', '.join(missing_fields)}"
                            }), 400
                # Si c'est un dictionnaire unique, vérifier ses champs
                elif isinstance(element_data, dict):
                    missing_fields = [field for field in required_fields[element_name] if field not in element_data]
                    if missing_fields:
                        return jsonify({
                            "error": f"Champs manquants dans '{element_name}': {', '.join(missing_fields)}"
                        }), 400
                else:
                    return jsonify({
                        "error": f"Format invalide pour '{element_name}'. Attendu: objet ou liste d'objets"
                    }), 400

        ##################
        # 1. Ajouter le paraphe (si autorisé) -> "add_paraph"
        ##################
        if "add_paraph" in actions:
            paraphe_data = params.get("positions", {}).get("paraphe")
            if paraphe_data:  # Ne procéder que si les données sont fournies
                # Dans le code original, on attendait "positions" -> "paraphe".
                # On peut l'élargir pour accepter un tableau (plusieurs positions).
                if isinstance(paraphe_data, dict):
                    # On le transforme en liste à un élément pour gérer de la même manière
                    paraphe_data = [paraphe_data]
                if not isinstance(paraphe_data, list):
                    paraphe_data = []

                for para_pos in paraphe_data:
                    try:
                        text = str(para_pos["text"])
                        x = float(para_pos["x"])
                        y = float(para_pos["y"])
                        page = para_pos.get("page")  # Peut être None

                        current_app.logger.info(
                            f"Ajout du paraphe: text={text}, page={page}, x={x}, y={y}"
                        )
                        output_buffer = add_text_to_pdf(
                            input_pdf_buffer,
                            text,
                            page if page is not None else None,
                            x,
                            y
                        )
                        input_pdf_buffer = BytesIO(output_buffer.getvalue())

                    except Exception as e:
                        current_app.logger.error(f"Erreur lors de l'ajout du paraphe: {str(e)}")

        ##################
        # 2. Ajouter la date (si autorisé) -> "add_date"
        ##################
        if "add_date" in actions:
            # Par cohérence, on va accepter params["date"] comme un tableau de positions OU un dict unique.
            date_data = params.get("positions", {}).get("date")
            if date_data:  # Ne procéder que si les données sont fournies
                # Si c'est une liste, on traite chaque élément
                if isinstance(date_data, dict):
                    # On vérifie s'il y a la clé "positions" ou non
                    if "positions" in date_data and isinstance(date_data["positions"], list):
                        date_positions = date_data["positions"]
                    else:
                        # Cas : le dict lui-même représente une unique position
                        date_positions = [date_data]
                elif isinstance(date_data, list):
                    date_positions = date_data
                else:
                    date_positions = []

                current_date_str = datetime.now().strftime("%d/%m/%Y")

                for dpos in date_positions:
                    try:
                        page = dpos.get("page")  # peut être None
                        x = float(dpos.get("x", 50))
                        y = float(dpos.get("y", 100))
                        output_buffer = add_text_to_pdf(
                            input_pdf_buffer,
                            current_date_str,
                            page,
                            x,
                            y
                        )
                        input_pdf_buffer = BytesIO(output_buffer.getvalue())
                        current_app.logger.info(
                            f"Date ajoutée à la position: page={page}, x={x}, y={y}"
                        )
                    except Exception as e:
                        current_app.logger.error(f"Erreur lors de l'ajout de la date: {str(e)}")

        ##################
        # 3. Ajouter le texte personnalisé (si autorisé) -> "add_custom_text"
        ##################
        if "add_custom_text" in actions:
            # Dans le code original, on attendait "positions" -> "custom_text".
            # On peut l'élargir pour accepter un tableau (plusieurs positions).
            custom_data = params.get("positions", {}).get("custom_text")
            if custom_data:  # Ne procéder que si les données sont fournies
                if isinstance(custom_data, dict):
                    custom_data = [custom_data]
                if not isinstance(custom_data, list):
                    custom_data = []

                for cpos in custom_data:
                    try:
                        text = str(cpos["text"])
                        page = cpos.get("page")  # Peut être None
                        x = float(cpos["x"])
                        y = float(cpos["y"])

                        output_buffer = add_text_to_pdf(
                            input_pdf_buffer,
                            text,
                            None if page is None else int(page),
                            x,
                            y
                        )
                        input_pdf_buffer = BytesIO(output_buffer.getvalue())
                        current_app.logger.info(
                            f"Texte personnalisé ajouté page={page}, x={x}, y={y}, text={text}"
                        )
                    except Exception as e:
                        current_app.logger.error(f"Erreur lors de l'ajout du texte personnalisé: {str(e)}")

        ##################
        # 4. Ajouter le tampon (cachet) (si autorisé) -> "add_stamp"
        ##################
        if "add_stamp" in actions:
            stamp_data = params.get("stamp")  # Chercher à la racine de params
            if stamp_data:  # Ne procéder que si les données sont fournies
                if isinstance(stamp_data, dict):
                    stamp_data = [stamp_data]
                if not isinstance(stamp_data, list):
                    stamp_data = []

                for spos in stamp_data:
                    try:
                        page = spos.get("page")
                        x = float(spos["x"])
                        y = float(spos["y"])
                        width = float(spos.get("width", 50))
                        height = float(spos.get("height", 25))

                        output_buffer = apply_stamp_to_pdf(
                            input_pdf_buffer,
                            user,
                            [page] if page is not None else None,
                            x,
                            y,
                            width,
                            height
                        )
                        input_pdf_buffer = BytesIO(output_buffer.getvalue())
                        current_app.logger.info(
                            f"Tampon ajouté à la position: page={page}, x={x}, y={y}"
                        )
                    except Exception as e:
                        current_app.logger.error(f"Erreur lors de l'ajout du tampon: {str(e)}")

        # Convertir les paramètres qrcode en format qrcodes pour apply_qr_codes
        if not has_signed:  # Ne préparer le QR code que si personne n'a signé
            qrcode_data = params.get("qrcode", [])
            if isinstance(qrcode_data, dict):
                qrcode_data = [qrcode_data]
            
            params["qrcodes"] = [{
                "page": qr.get("page", 0),
                "x": float(qr.get("x", 50)),
                "y": float(qr.get("y", 150)),
                "size": float(qr.get("width", 30)),
                "data": download_url,  # Utiliser la même URL que celle retournée
                "box_size": int(qr.get("box_size", 10)),
                "border": int(qr.get("border", 4)),
                "fill_color": qr.get("fill_color", "blue"),
                "back_color": qr.get("back_color", "white")
            } for qr in qrcode_data]

            # Appliquer le QR code avec l'URL complète du document
            input_pdf_buffer = apply_qr_codes(input_pdf_buffer, params, user, download_url)

        # Sauvegarder le PDF modifié
        with open(signed_pdf_path, 'wb') as f:
            f.write(input_pdf_buffer.getvalue())

        # Mettre à jour le document dans la base de données avec le chemin
        if not has_signed:
            # Seulement mettre à jour le chemin lors de la première signature
            document.file_path = str(signed_pdf_path.relative_to(SIGNED_PDF_FOLDER))

        # Mettre à jour le statut du LineFlow actuel
        if user.account_type == "employee":
            current_line_flow = LineFlow.query.filter_by(
                flow_id=flow_id,
                user_id=user.id,
                account_type="employee"
            ).first()
        else:
            current_line_flow = LineFlow.query.filter_by(
                flow_id=flow_id,
                user_id=user.id,  # On utilise user_id pour les deux types de signataires
                account_type="contact"
            ).first()

        if current_line_flow:
            current_line_flow.status = "signed"
            current_line_flow.action_done = True
            current_line_flow.signed_at = datetime.utcnow()
            db.session.commit()
            current_app.logger.info(f"LineFlow {current_line_flow.id} mis à jour - status: signed, action_done: True")

        # Vérifier si toutes les actions du flow sont terminées
        all_line_flows = LineFlow.query.filter_by(flow_id=flow_id).all()
        if all(lf.action_done for lf in all_line_flows):
            flow.action_done = True
            document.status = "signed"
            db.session.commit()
            #current_app.logger.info(f"Document {document.id} marqué comme signé (tous ont terminé)")

            # Envoyer les notifications finales dans tous les cas
            try:
                for lf in all_line_flows:
                    current_app.logger.info(f"Traitement du LineFlow {lf.id} - Type: {lf.account_type}")
                    
                    participant = None
                    if lf.account_type == "contact":
                        participant = Contact.query.get(lf.user_id)  # On utilise user_id pour les deux types de signataires
                        current_app.logger.info(f"Contact trouvé: {participant.email if participant else 'Non trouvé'}")
                    else:
                        participant = User.query.get(lf.user_id)
                        current_app.logger.info(f"Utilisateur trouvé: {participant.email if participant else 'Non trouvé'}")

                    if participant:
                        subject = f"Document final signé - {document.name}"
                        template_data = {
                            'name': participant.name,
                            'document_name': document.name,
                            'workflow_name': flow.workflow.name if flow.workflow else '',
                            'reference': flow.reference or '',
                            'download_url': download_url,
                            'completion_date': datetime.utcnow().strftime("%d/%m/%Y à %H:%M"),
                            'current_year': datetime.utcnow().year
                        }
                        
                        current_app.logger.info(f"Préparation du mail pour {participant.email}")
                        current_app.logger.info(f"Template data: {template_data}")
                        
                        body = f"Bonjour {participant.name},\n\nLe document {document.name} est désormais entièrement signé.\nTéléchargez-le ici : {download_url}\n\nCordialement,\nL'équipe DKBSign"
                        try:
                            html = render_template('flow_completed_notification.html', **template_data)
                            current_app.logger.info(f"Template HTML généré avec succès")
                        except Exception as template_error:
                            current_app.logger.error(f"Erreur lors du rendu du template: {str(template_error)}")
                            raise

                        try:
                            send_email(subject, participant.email, body, html)
                            current_app.logger.info(f"Mail envoyé avec succès à {participant.email}")
                        except Exception as email_error:
                            current_app.logger.error(f"Erreur lors de l'envoi du mail: {str(email_error)}")
                            raise
                        
                        if hasattr(participant, 'phone') and participant.phone:
                            clean_phone = ''.join(filter(str.isdigit, participant.phone))
                            if clean_phone:
                                whatsapp_message = f"Bonjour {participant.name},\n\nLe document {document.name} est entièrement signé.\nTéléchargez-le ici : {download_url}"
                                #send_whatsapp_notification(clean_phone, whatsapp_message)
            except Exception as e:
                current_app.logger.error(f"Erreur lors de l'envoi des notifications finales: {str(e)}")
                current_app.logger.error(f"Type d'erreur: {e.__class__.__name__}")
                current_app.logger.error(f"Details: {str(e)}")
                # Ne pas bloquer le processus si l'envoi des mails échoue
                pass

        ##################
        # 5bis. Ajouter la signature si autorisée -> "sign_doc"
        ##################
        if "sign_doc" in actions and params.get("pages"):
            cert_path, key_path, cert_chain = retrieve_certificates(user, company)
            if not cert_path or not key_path:
                return jsonify({"error": "Certificat ou clé privée introuvable"}), 400

            signer = signers.SimpleSigner.load(
                key_file=key_path,
                cert_file=cert_path,
                ca_chain_files=cert_chain
            )
            signer_stamp = load_signature_image(user)
            
            # Calculer la taille de boîte personnalisée si fournie
            flow_signature_size = params.get('signature_size')
            box_width = 250
            box_height = 80
            if flow_signature_size and isinstance(flow_signature_size, dict):
                custom_w = flow_signature_size.get('width')
                custom_h = flow_signature_size.get('height')
                if custom_w and int(custom_w) > 0:
                    box_width = int(custom_w)
                if custom_h and int(custom_h) > 0:
                    box_height = int(custom_h)

            # Pipeline qualité UNE SEULE FOIS avant la boucle de signatures
            from app.utils.signature_utils import prepare_signature_image
            if signer_stamp is not None and isinstance(signer_stamp, Image.Image):
                signer_stamp = prepare_signature_image(signer_stamp, target_box_width=box_width)

            # Calculer la hauteur selon le ratio de l'image si pas de height explicite
            if signer_stamp is not None and isinstance(signer_stamp, Image.Image):
                img_w, img_h = signer_stamp.size
                if img_w > 0 and img_h > 0:
                    if not (flow_signature_size and isinstance(flow_signature_size, dict) and flow_signature_size.get('height')):
                        box_height = int(box_width * (img_h / img_w))
                        box_height = max(40, min(200, box_height))

            # Recharger le PDF
            with open(signed_pdf_path, 'rb') as f:
                input_pdf_buffer = BytesIO(f.read())

            # Parcourir les pages à signer
            for page_params in params["pages"]:
                if not isinstance(page_params, dict):
                    continue

                page = page_params.get("page", 0)
                signatures = page_params.get("signatures", [])

                for sig_pos in signatures:
                    if not isinstance(sig_pos, dict):
                        continue

                    x = mm_to_points(sig_pos.get("x", 50))
                    y = mm_to_points(sig_pos.get("y", 100))

                    pdf_writer = IncrementalPdfFileWriter(input_pdf_buffer, strict=False)
                    field_name = f"Signature_{uuid.uuid4().hex}"
                    sig_field_spec = SigFieldSpec(
                        sig_field_name=field_name,
                        box=(x, y, x + box_width, y + box_height),
                        on_page=page
                    )
                    append_signature_field(pdf_writer, sig_field_spec)

                    pdf_signer = signers.PdfSigner(
                        PdfSignatureMetadata(
                            field_name=field_name,
                            name='Signature',
                            location='France'
                        ),
                        signer=signer,
                        stamp_style=StaticStampStyle(
                            background=images.PdfImage(signer_stamp),
                            background_opacity=0.9,
                            border_width=0
                        )
                    )

                    output_buffer = BytesIO()
                    pdf_signer.sign_pdf(pdf_writer, output=output_buffer)
                    input_pdf_buffer = BytesIO(output_buffer.getvalue())

            # Sauvegarder le PDF final avec la signature
            with open(signed_pdf_path, 'wb') as f:
                f.write(input_pdf_buffer.getvalue())

            # Mettre à jour le volume de signatures
            update_signature_volumes(user, company, 1)

        # Marquer la LineFlow comme terminée
        line_flow.action_done = True
        line_flow.status = "signed"

        # Trouver le prochain signataire
        next_line_flow = LineFlow.query.filter(
            LineFlow.flow_id == flow.id,
            LineFlow.priority > line_flow.priority,
            LineFlow.status != "signed"
        ).order_by(LineFlow.priority).first()

        if next_line_flow:
            flow.current_priority = next_line_flow.priority

            # Récupérer l'info du prochain signataire (User ou Contact)
            if next_line_flow.account_type == "contact":
                next_signer = Contact.query.get(next_line_flow.user_id)  # On utilise user_id pour les deux types de signataires
                recipient_email = next_signer.email
                recipient_name = next_signer.name
            else:
                next_signer = User.query.get(next_line_flow.user_id)
                recipient_email = next_signer.email
                recipient_name = next_signer.name

            # Construire la liste des actions à faire
            actions_list = "<ul>"
            for act in next_line_flow.actions:
                if act == "sign_doc":
                    actions_list += "<li>✍️ Signer le document</li>"
                elif act == "add_paraph":
                    actions_list += "<li>🖋️ Parapher le document</li>"
                elif act == "add_qrcode":
                    actions_list += "<li>🔳 Ajouter un QR code</li>"
                elif act == "add_stamp":
                    actions_list += "<li>📝 Ajouter un cachet</li>"
                elif act == "add_date":
                    actions_list += "<li>📅 Ajouter la date</li>"
                elif act == "add_custom_text":
                    actions_list += "<li>📝 Ajouter un texte personnalisé</li>"
                elif act == "read_only":
                    actions_list += "<li>👀 Aprobation de lecture</li>"
            actions_list += "</ul>"

            subject = "Action Required"
            body = f"Bonjour {recipient_name},\n\nVous avez une action requise pour le document {document.name}.\n\nActions requises:\n{actions_list}\n\nCordialement,\nL'equipe DKBSign"
            template_data = {
                'name': recipient_name,
                'document_name': flow.document.name,
                'workflow_name': flow.workflow.name,
                'reference': flow.reference,
                'actions': actions_list,
                'current_year': datetime.utcnow().year
            }
            html_content = render_template('simple_notification_email.html', **template_data)
            send_email(
                subject=subject,
                recipient=recipient_email,
                body=body,
                html=html_content
            )

        db.session.commit()

        # Génération de la preuve de signature
        proof = create_signature_proof(
            document_id=document.id,
            signer=user,
            signer_type='user',
            document_name=document.name,
            signature_method='jwt',
            company=company,
            flow_id=flow_id,
            flow_priority=line_flow.priority if line_flow else None,
        )

        return jsonify({
            "message": "Document signé avec succès",
            "flow_id": flow_id,
            "document_id": document.id,
            "download_url": download_url,
            "proof": build_proof_urls(proof) if proof else None
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la signature: {str(e)}")
        return jsonify({"error": str(e)}), 500


@flow_signature_bp.route('flows/<int:flow_id>/send-otp', methods=['POST'])
@jwt_required()
def send_otp(flow_id):
    """
    Envoie un code OTP au signataire actuel du flow.
    Le code OTP est valide pendant 5 minutes.
    """
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Vérifier le signataire actuel
        next_line = LineFlow.query.filter_by(
            flow_id=flow_id,
            action_done=False
        ).order_by(LineFlow.priority).first()

        if not next_line or next_line.user_id != user.id:
            return jsonify({"error": "Vous n'êtes pas le prochain signataire dans l'ordre de priorité"}), 403

        current_line = LineFlow.query.filter_by(
            flow_id=flow_id,
            user_id=user.id,
            action_done=False
        ).first()
        if not current_line:
            return jsonify({"error": "Vous n'êtes pas autorisé à signer ce document"}), 403

        # Générer un code OTP
        current_line.generate_read_aprob_otp()
        db.session.commit()

        # Envoi du mail
        try:
            send_email(
                subject="Code de vérification pour signature",
                recipient=user.email,
                body=f"Votre code de vérification est : {current_line.read_aprob_otp}",
                html=render_template(
                    "otp_notification.html",
                    otp=current_line.read_aprob_otp,
                    document_name="Document à signer"
                )
            )
        except Exception as email_error:
            current_app.logger.error(f"Erreur lors de l'envoi de l'email OTP : {str(email_error)}")
            return jsonify({"error": f"Erreur lors de l'envoi de l'email : {str(email_error)}"}), 500

        return jsonify({"message": "Code de vérification envoyé avec succès"})

    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'OTP : {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Erreur lors de la génération du code : {str(e)}"}), 500


@flow_signature_bp.route('flows/<int:flow_id>/verify-otp', methods=['POST'])
@jwt_required()
def verify_otp(flow_id):
    """
    Vérifie le code OTP fourni par le signataire et applique les actions autorisées.
    """
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        next_line = LineFlow.query.filter_by(
            flow_id=flow_id,
            action_done=False
        ).order_by(LineFlow.priority).first()

        if not next_line or next_line.user_id != user.id:
            return jsonify({"error": "Vous n'êtes pas le prochain signataire dans l'ordre de priorité"}), 403

        current_line = LineFlow.query.filter_by(
            flow_id=flow_id,
            user_id=user.id,
            action_done=False
        ).first()
        if not current_line:
            return jsonify({"error": "Vous n'êtes pas autorisé à signer ce document"}), 403

        data = request.get_json()
        if not data:
            return jsonify({"error": "Données manquantes"}), 400
        if 'otp_code' not in data:
            return jsonify({"error": "Code OTP manquant"}), 400

        if not current_line.verify_read_aprob_otp(data['otp_code']):
            return jsonify({"error": "Code OTP invalide ou expiré"}), 400

        return jsonify({
            "message": "Code OTP validé avec succès",
            "flow_id": flow_id
        })

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la vérification de l'OTP : {str(e)}")
        return jsonify({"error": f"Erreur lors de la vérification du code : {str(e)}"}), 500


@flow_signature_bp.route('flows/<int:flow_id>/deny', methods=['POST'])
@jwt_required()
def deny_flow_actions(flow_id):
    """
    Refuse les actions assignées dans un flow. Met le status à 'denied' et arrête le flow.
    """
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        flow = Flow.query.get(flow_id)
        if not flow:
            return jsonify({"error": "Flow non trouvé"}), 404

        current_line = LineFlow.query.filter_by(
            flow_id=flow_id,
            user_id=user.id,
            action_done=False
        ).first()

        if not current_line:
            return jsonify({"error": "Vous n'êtes pas autorisé à refuser ce document"}), 403

        data = request.get_json()
        denial_reason = data.get('reason', 'Aucune raison fournie')

        current_line.status = 'denied'
        current_line.denial_reason = denial_reason
        current_line.denial_date = datetime.utcnow()

        flow.status = 'denied'
        flow.current_priority = None  # Le flow s'arrête
        db.session.commit()

        # Notifier les participants
        all_line_flows = LineFlow.query.filter_by(flow_id=flow_id).all()
        notified_emails = set()
        base_template_data = {
            'participant_name': user.name,
            'document_name': flow.document.name,
            'workflow_name': flow.workflow.name,
            'reference': flow.reference,
            'denial_reason': denial_reason,
            'denial_date': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'current_year': datetime.utcnow().year
        }

        for lf in all_line_flows:
            participant = None
            if lf.account_type == "contact":
                participant = Contact.query.get(lf.user_id)  # On utilise user_id pour les deux types de signataires
            else:
                participant = User.query.get(lf.user_id)

            if participant and participant.email not in notified_emails:
                notified_emails.add(participant.email)

                if participant.id == user.id:
                    subject = f"Confirmation de votre refus - {flow.document.name}"
                    body = f"""Bonjour {participant.name},

Nous confirmons que vous avez refusé d'effectuer les actions requises dans le workflow "{flow.workflow.name}".

Détails de votre refus :
- Document : {flow.document.name}
- Référence : {flow.reference}
- Date du refus : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Raison du refus :
"{denial_reason}"

Le créateur du workflow et les autres participants ont été informés.
"""
                    template_data = base_template_data.copy()
                    template_data['name'] = participant.name
                    template_data['is_denier'] = True
                    html = render_template('flow_denied_notification.html', **template_data)
                    
                    send_email(subject, participant.email, body, html)
                    current_app.logger.info(f"Confirmation de refus envoyée à {participant.email}")
                else:
                    subject = f"Action refusée - {flow.document.name}"
                    body = f"""Bonjour {participant.name},

Le participant {user.name} a refusé d'effectuer les actions requises dans le workflow "{flow.workflow.name}".

Détails :
- Document : {flow.document.name}
- Référence : {flow.reference}
- Date du refus : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Raison du refus :
"{denial_reason}"
"""
                    template_data = base_template_data.copy()
                    template_data['name'] = participant.name
                    template_data['is_denier'] = False
                    html = render_template('flow_denied_notification.html', **template_data)

                    send_email(subject, participant.email, body, html)
                    current_app.logger.info(f"Notification de refus envoyée à {participant.email}")

        # Notifier le créateur s'il n'est pas déjà dans la liste
        creator = User.query.get(flow.workflow.user_id)
        if creator and creator.email not in notified_emails:
            template_data = base_template_data.copy()
            template_data['name'] = creator.name
            template_data['is_denier'] = False

            subject = f"Action refusée - {flow.document.name}"
            body = f"""Bonjour {creator.name},

Le participant {user.name} a refusé d'effectuer les actions requises dans le workflow "{flow.workflow.name}".

Détails :
- Document : {flow.document.name}
- Référence : {flow.reference}
- Date du refus : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Raison du refus :
"{denial_reason}"

En tant que créateur du workflow, vous pouvez examiner la situation.
"""
            html = render_template('flow_denied_notification.html', **template_data)
            send_email(subject, creator.email, body, html)
            current_app.logger.info(f"Notification de refus envoyée au créateur {creator.email}")

        return jsonify({
            "message": "Actions refusées avec succès",
            "flow_id": flow_id,
            "status": "denied",
            "reason": denial_reason
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors du refus des actions: {str(e)}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
