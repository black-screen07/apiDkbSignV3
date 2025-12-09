from flask import current_app, url_for, render_template
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
from pyhanko.sign.signers import PdfSignatureMetadata
from pyhanko.pdf_utils import images
from pyhanko import stamp

import tempfile
import os
from datetime import datetime
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.backends import default_backend
import json
from pathlib import Path
from PIL import Image
from io import BytesIO
import uuid
import requests
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from app.services.email_service import send_email
import random
import string
from app.models import User, Company, Document, Contact, DocumentConsent, Signer, CertTypeEnum, db, LineFlow, Flow


DRAFT_PDF_FOLDER = Path("documents/drafts")
DRAFT_PDF_FOLDER.mkdir(parents=True, exist_ok=True)

SIGNED_PDF_FOLDER = Path("documents/doc_signed")
SIGNED_PDF_FOLDER.mkdir(parents=True, exist_ok=True)

CERTIFICATE_FOLDER = Path("certificates/users")
SIGNATURE_FOLDER = Path("signatures/users")
COMPANY_SIGNATURE_FOLDER = Path("signatures/companies")


def mm_to_points(mm):
    return mm * 2.83465

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


def retrieve_certificates(user, company=None, document_id=None):
    """
    Détermine quel certificat utiliser (cachet serveur ou personne physique).
    
    Args:
        user: L'utilisateur ou le contact qui signe
        company: L'entreprise associée à l'utilisateur (si applicable)
        document_id: L'ID du document (nécessaire pour les contacts externes)
    
    Returns:
        tuple: (cert_path, key_path, cert_chain)
    """
    cert_path, key_path, cert_chain = None, None, []
    
    # Si c'est un contact externe
    if isinstance(user, Contact):
        if not document_id:
            raise ValueError("document_id est requis pour les contacts externes")
            
        # Utiliser le certificat de l'initiateur
        initiator = Signer.query.filter_by(document_id=document_id, priority=0).first()
        if not initiator:
            raise ValueError("Initiateur du document introuvable.")

        # Récupérer l'utilisateur initiateur
        initiator_user = User.query.get(initiator.signer_id)
        if not initiator_user:
            raise ValueError("Utilisateur initiateur introuvable.")

        # Récupérer l'entreprise de l'initiateur si c'est un employé
        initiator_company = None
        if initiator_user.account_type == "employee":
            initiator_company = Company.query.get(initiator_user.company_id)

        # Choix du certificat selon le type de compte de l'initiateur
        if initiator_user.account_type == "employee" and initiator_company:
            if initiator_company.cert_type == CertTypeEnum.CACHET_SERVEUR:
                cert_path = Path(initiator_company.cert_path)
                key_path = Path(initiator_company.key_path)
                cert_chain = [
                    'certificates/DKBS/ACDKBSMachines2024.cacert.pem',
                    'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
                ]
            else:  # PERSONNE_PHYSIQUE
                cert_path = CERTIFICATE_FOLDER / f"{initiator_user.email}_cert.crt"
                key_path = CERTIFICATE_FOLDER / f"{initiator_user.email}_cert.key"
                p12_path = CERTIFICATE_FOLDER / f"{initiator_user.email}_cert.p12"

                if not cert_path.exists() or not key_path.exists():
                    if not p12_path.exists():
                        raise FileNotFoundError(f"Certificat (.p12) non trouvé pour l'initiateur {initiator_user.email}.")
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
        else:  # individual
            cert_path = CERTIFICATE_FOLDER / f"{initiator_user.email}_cert.crt"
            key_path = CERTIFICATE_FOLDER / f"{initiator_user.email}_cert.key"
            p12_path = CERTIFICATE_FOLDER / f"{initiator_user.email}_cert.p12"

            if not cert_path.exists() or not key_path.exists():
                if not p12_path.exists():
                    raise FileNotFoundError(f"Certificat (.p12) non trouvé pour l'initiateur {initiator_user.email}.")
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
        # Pour les utilisateurs internes
        if hasattr(user, 'account_type'):
            if user.account_type == "employee" and company:
                if company.cert_type == CertTypeEnum.CACHET_SERVEUR:
                    cert_path = Path(company.cert_path)
                    key_path = Path(company.key_path)
                    cert_chain = [
                        'certificates/DKBS/ACDKBSMachines2024.cacert.pem',
                        'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
                    ]
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


def retrieve_document(user, document_id):
    document = Document.query.get(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    if document.user_id != user.id:
        raise ValueError("Vous n'avez pas la permission d'accéder à ce document.")
    return document


def parse_request_content(request):
    """
    Extrait les paramètres, l'URL du fichier ou le fichier directement depuis la requête.
    """
    params = {}
    file_url = None
    file = None

    if request.content_type == "application/json":
        try:
            params = request.json.get("params", {})
            file_url = request.json.get("file_url")
        except Exception as e:
            raise ValueError(f"Le JSON fourni est invalide ou manquant : {str(e)}")
    elif request.content_type.startswith("multipart/form-data"):
        raw_params = request.form.get("params", "{}")
        try:
            params = json.loads(raw_params)
            file_url = request.form.get("file_url")
            file = request.files.get("file")
        except json.JSONDecodeError as e:
            raise ValueError(f"Les paramètres JSON dans form-data sont invalides : {str(e)}")
    else:
        raise ValueError("Type de contenu non pris en charge.")

    if not isinstance(params, dict):
        raise ValueError("Les paramètres JSON sont mal structurés ou manquants.")

    return params, file_url, file


def load_signature_image(user):
    """
    Charge l'image de signature en fonction de 'current_img_sign'.
    Convertit en RGBA pour préserver la transparence (PyHanko supporte RGBA).
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
    
    # Convertir en RGBA pour garder la transparence (PyHanko supporte RGBA)
    # Ne PAS convertir en RGB car ça cache le texte du PDF en dessous
    if img.mode == 'P':
        # Convertir les images avec palette en RGBA
        img = img.convert('RGBA')
    elif img.mode in ('L', 'LA'):
        # Convertir niveaux de gris en RGBA
        img = img.convert('RGBA')
    elif img.mode == 'RGB':
        # Ajouter un canal alpha aux images RGB (opaque)
        img = img.convert('RGBA')
    # Si déjà RGBA, ne rien faire
    
    return img


def load_pdf(file, file_url):
    if file:
        # Lire le fichier directement depuis form-data
        return BytesIO(file.read())
    elif file_url:
        try:
            response = requests.get(file_url, stream=True)
            response.raise_for_status()
            if 'application/pdf' in response.headers.get('Content-Type', ''):
                return BytesIO(response.content)
            else:
                raise ValueError("L'URL ne renvoie pas un fichier PDF valide.")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Erreur lors du téléchargement du fichier : {str(e)}")
    else:
        raise ValueError("Aucun fichier PDF fourni ou URL invalide.")


def update_existing_document(document, params, relative_file_path):
    document.name = params.get("name", document.name)
    document.file_path = relative_file_path
    document.status = "signed"
    updated_at = params.get("updated_at")
    if updated_at:
        document.updated_at = updated_at


def create_new_document(user, params, relative_file_path):
    new_doc = Document(
        name=params.get("name", f"Document_{uuid.uuid4().hex}"),
        file_path=relative_file_path,
        status="Signed",
        user_id=user.id
    )
    description = params.get("description")
    if description:
        new_doc.description = description
    db.session.add(new_doc)
    return new_doc


def add_text_to_pdf(input_pdf_stream, text, page=None, x=50, y=100):
    """
    Ajoute un texte à un PDF.
    - Si page est None, ajoute le texte à toutes les pages.
    - Sinon, l'ajoute à la page spécifiée.
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(595.27, 841.89))
    can.setFont("Helvetica-Bold", 12)

    # On ne dessine ici qu'une fois si page != None
    if page is not None:
        can.drawString(mm_to_points(x), mm_to_points(y), text)
        can.save()
        packet.seek(0)
        new_pdf = PdfReader(packet)
    else:
        new_pdf = None

    packet.seek(0)
    existing_pdf = PdfReader(input_pdf_stream)
    output = PdfWriter()

    for i, page_content in enumerate(existing_pdf.pages):
        if page is None or i == page:
            if new_pdf is None:
                # On génère un nouveau "packet" à chaque page
                temp_packet = BytesIO()
                can_temp = canvas.Canvas(temp_packet, pagesize=(595.27, 841.89))
                can_temp.setFont("Helvetica-Bold", 12)
                can_temp.drawString(mm_to_points(x), mm_to_points(y), text)
                can_temp.save()
                temp_packet.seek(0)
                merged_pdf = PdfReader(temp_packet)
                page_content.merge_page(merged_pdf.pages[0])
            else:
                # Fusion directe si new_pdf est déjà préparé
                page_content.merge_page(new_pdf.pages[0])
        output.add_page(page_content)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def apply_stamp_to_pdf(input_pdf_stream, user, pages=None, x=50, y=100, width=100, height=50):
    """
    Ajoute un cachet (image) à un PDF.
    - Si pages est None, applique le cachet à toutes les pages.
    - Sinon, aux pages spécifiées dans la liste `pages`.
    """
    stamp_image = load_stamp_image(user)
    if not stamp_image:
        raise ValueError("Image du cachet introuvable ou non définie.")

    existing_pdf = PdfReader(input_pdf_stream)
    output = PdfWriter()

    for i, page_content in enumerate(existing_pdf.pages):
        if pages is None or i in pages:
            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=(595.27, 841.89))
            can.drawImage(
                stamp_image,
                mm_to_points(x), mm_to_points(y),
                width=mm_to_points(width),
                height=mm_to_points(height),
                mask='auto'
            )
            can.save()
            packet.seek(0)
            new_pdf = PdfReader(packet)
            page_content.merge_page(new_pdf.pages[0])
        output.add_page(page_content)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def load_stamp_image(user):
    """
    Charge l'image de cachet d'un utilisateur uniquement.
    """
    try:
        # Si vous souhaitez la même image que la signature, adaptez selon vos besoins
        if user.stamp_path:
            stamp_path = Path(user.stamp_path)
            if stamp_path.exists() and stamp_path.is_file():
                return stamp_path.as_posix()
        raise FileNotFoundError("Aucun cachet valide trouvé pour l'utilisateur.")
    except Exception as e:
        current_app.logger.error(f"Erreur lors du chargement de l'image du cachet : {str(e)}")
        raise


def add_qr_code_to_pdf(input_pdf_stream, qr_image_path, page_number, x, y, size):
    """
    Ajoute le QR code (déjà généré) à la page spécifiée d'un PDF.
    """
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(595.27, 841.89))
    can.drawImage(qr_image_path, x, y, width=size, height=size, mask='auto')
    can.save()

    packet.seek(0)
    new_pdf = PdfReader(packet)
    existing_pdf = PdfReader(input_pdf_stream)
    output = PdfWriter()

    for i in range(len(existing_pdf.pages)):
        page = existing_pdf.pages[i]
        if i == page_number:
            page.merge_page(new_pdf.pages[0])
        output.add_page(page)

    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def generate_qr_code_image(
    data,
    size,
    fill_color="blue",
    back_color="white",
    box_size=10,
    border=4,
    logo_path=None,
    logo_size_ratio=0.9,
    dpi=300
):
    """
    Génère une image QR code personnalisable avec éventuellement un logo au centre.
    """
    size_px = int(size / 25.4 * dpi)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGB")
    img = img.resize((size_px, size_px), Image.Resampling.LANCZOS)

    if logo_path:
        try:
            if logo_path.startswith("http://") or logo_path.startswith("https://"):
                response = requests.get(logo_path)
                response.raise_for_status()
                logo = Image.open(BytesIO(response.content))
            else:
                logo = Image.open(logo_path)

            logo_width = int(size_px * logo_size_ratio)
            logo = logo.resize((logo_width, logo_width), Image.Resampling.LANCZOS)
            x = (img.width - logo_width) // 2
            y = (img.height - logo_width) // 2
            img.paste(logo, (x, y), mask=logo if logo.mode == "RGBA" else None)
        except Exception as e:
            raise ValueError(f"Erreur lors de l'intégration du logo : {e}")

    return img


def update_signature_volumes(user, company, count):
    if user.account_type == "individual":
        # Utilisateur individuel : décompte dans la table user
        user.signature_volume_used += count
    elif user.account_type == "employee" and company:
        # Utilisateur employé : vérifier le cert_type de l'entreprise
        if company.cert_type == CertTypeEnum.CACHET_SERVEUR:
            # Cachet serveur : décompte UNIQUEMENT dans la table company
            company.signature_volume_used += count
        else:
            # Personne physique : décompte dans les deux tables (logique actuelle)
            user.signature_volume_used += count
            company.signature_volume_used += count





def get_user_company(user):
    """Récupère l'entreprise associée à l'utilisateur, le cas échéant."""
    if user.account_type == "employee" and user.company_id:
        company = Company.query.get(user.company_id)
        if not company:
            raise Exception("Entreprise associée introuvable.")
        return company
    return None


def validate_signature_volumes(user, company):
    """Vérifie que l'utilisateur (et son entreprise) disposent d'un volume de signature suffisant."""
    if user.account_type == "individual":
        # Utilisateur individuel : vérifier uniquement son volume personnel
        if user.signature_volume_used >= user.signature_volume:
            raise Exception("Votre volume de signatures est épuisé. Veuillez recharger votre compte.")
    elif user.account_type == "employee" and company:
        # Utilisateur employé : vérifier selon le cert_type de l'entreprise
        if company.cert_type == CertTypeEnum.CACHET_SERVEUR:
            # Cachet serveur : vérifier UNIQUEMENT le volume de l'entreprise
            if company.signature_volume_used >= company.signature_volume:
                raise Exception("Le volume de signatures de l'entreprise est épuisé. Veuillez contacter l'administrateur.")
        else:
            # Personne physique : vérifier les deux volumes (logique actuelle)
            if user.signature_volume_used >= user.signature_volume:
                raise Exception("Votre volume de signatures est épuisé. Veuillez contacter l'administrateur.")
            if company.signature_volume_used >= company.signature_volume:
                raise Exception("Le volume de signatures de l'entreprise est épuisé. Veuillez contacter l'administrateur.")


def validate_signature_params(params):
    """Vérifie que les paramètres obligatoires pour la signature sont présents."""
    if not params or "pages" not in params or not isinstance(params["pages"], list):
        raise Exception("Le paramètre 'pages' est obligatoire et doit être une liste.")


def process_document_consent(user, company, params):
    """
    Gère le consentement requis pour la signature.
    Retourne le document (s'il existe) ou None.
    """
    document = None
    requires_consent = False
    if user.account_type == "individual":
        requires_consent = user.with_consent
    elif user.account_type == "employee" and company:
        requires_consent = company.with_consent

    document_id = params.get("document_id")
    if requires_consent and not document_id:
        raise Exception("Le consentement est requis pour signer ce document, mais aucun document_id n'a été fourni.")

    if document_id:
        document = retrieve_document(user, document_id)
        if requires_consent:
            consent = DocumentConsent.query.filter_by(
                document_id=document_id,
                user_id=user.id,
                is_verified=True
            ).first()
            if not consent:
                raise Exception("Aucun consentement vérifié trouvé pour ce document. Veuillez confirmer votre consentement avant de signer.")
    return document


def create_pdf_signer(key_path, cert_path, cert_chain):
    """Crée et retourne un objet SimpleSigner pour la signature du PDF."""
    return signers.SimpleSigner.load(
        key_file=key_path,
        cert_file=cert_path,
        ca_chain_files=cert_chain
    )


def apply_optional_texts(pdf_buffer, params):
    """Ajoute les textes optionnels (paraphe, date, texte personnalisé) au PDF."""
    # Ajout du paraphe
    paraphe_text = params.get("paraphe_text")
    paraphe_position = params.get("paraphe_position", {"x": 50, "y": 100})
    if paraphe_text:
        page_index = paraphe_position.get("page")
        pdf_buffer = add_text_to_pdf(
            pdf_buffer,
            paraphe_text,
            page=page_index,
            x=paraphe_position.get("x", 50),
            y=paraphe_position.get("y", 100),
        )

    # Ajout de la date
    date_text = params.get("date_text")
    date_position = params.get("date_position", {"x": 50, "y": 200, "page": 0})
    if date_text:
        pdf_buffer = add_text_to_pdf(
            pdf_buffer,
            date_text,
            date_position.get("page", 0),
            date_position.get("x", 50),
            date_position.get("y", 200)
        )

    # Ajout d'un texte personnalisé
    custom_text = params.get("custom_text")
    custom_text_position = params.get("custom_text_position", {"x": 50, "y": 300, "page": 0})
    if custom_text:
        pdf_buffer = add_text_to_pdf(
            pdf_buffer,
            custom_text,
            custom_text_position.get("page", 0),
            custom_text_position.get("x", 50),
            custom_text_position.get("y", 300)
        )
    return pdf_buffer


def apply_stamp(pdf_buffer, user, params):
    """Ajoute un cachet au PDF si demandé."""
    stamp_pages = params.get("stamp_pages")
    stamp_position = params.get("stamp_position", {"x": 50, "y": 100, "width": 100, "height": 50})
    if stamp_pages:
        pdf_buffer = apply_stamp_to_pdf(
            input_pdf_stream=pdf_buffer,
            user=user,
            pages=stamp_pages,
            x=stamp_position.get("x", 50),
            y=stamp_position.get("y", 100),
            width=stamp_position.get("width", 100),
            height=stamp_position.get("height", 50)
        )
    return pdf_buffer


def prepare_pdf_paths(user, company):
    """Prépare le dossier de sauvegarde, le nom du fichier signé et l'URL finale."""
    if user.account_type == "employee" and company:
        subfolder = f"companies/{company.name.replace(' ', '_')}"
    else:
        subfolder = f"users/{user.email}"
    signed_pdf_folder = SIGNED_PDF_FOLDER / subfolder
    signed_pdf_folder.mkdir(parents=True, exist_ok=True)

    unique_filename = f"signed_pdf_{uuid.uuid4().hex}.pdf"
    signed_pdf_path = signed_pdf_folder / unique_filename
    relative_file_path = signed_pdf_path.relative_to(SIGNED_PDF_FOLDER).as_posix()

    full_signed_pdf_url = url_for(
        'sign_and_assign_bp.download_file',
        subfolder=subfolder,
        filename=unique_filename,
        _external=True
    )
    return full_signed_pdf_url, relative_file_path, signed_pdf_path


def apply_qr_codes(pdf_buffer, params, user, full_signed_pdf_url):
    """
    Génère et insère les QR codes dans le PDF.
    Met à jour les QR codes avec l'URL finale si besoin.
    """
    qr_code_positions = params.get("qrcodes", [])
    # Mise à jour de chaque QR code avec l'URL finale par défaut
    for qr_params in qr_code_positions:
        if not qr_params.get('data'):
            qr_params['data'] = full_signed_pdf_url

    for qr_params in qr_code_positions:
        try:
            page = qr_params.get("page", 0)
            x = mm_to_points(qr_params.get("x", 50))
            y = mm_to_points(qr_params.get("y", 150))
            size = mm_to_points(qr_params.get("size", 30))

            qr_data = qr_params['data']
            fill_color = qr_params.get("fill_color", "blue")
            back_color = qr_params.get("back_color", "white")
            logo_path = qr_params.get("logo_path")
            box_size = qr_params.get("box_size", 10)
            border = qr_params.get("border", 4)

            qr_code_image = generate_qr_code_image(
                qr_data,
                size=qr_params.get("size", 30),
                fill_color=fill_color,
                back_color=back_color,
                box_size=box_size,
                border=border,
                logo_path=logo_path
            )

            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                qr_code_image.save(tmp_file.name)
                tmp_file_path = tmp_file.name

            try:
                pdf_buffer = add_qr_code_to_pdf(pdf_buffer, tmp_file_path, page, x, y, size)
            finally:
                os.remove(tmp_file_path)

        except Exception as e:
            raise Exception(f"Erreur lors de l'ajout du QR code sur la page {page}: {str(e)}")
    return pdf_buffer


def add_signer_info_text(pdf_buffer, page_index, x, y, signer_info, box_width=150):
    """
    Ajoute les informations du signataire sous l'image de signature.
    
    Args:
        pdf_buffer: Buffer du PDF
        page_index: Index de la page
        x: Position X (en points)
        y: Position Y (en points) - position du bas de l'image
        signer_info: Dict avec name, sub_name, function, email
        box_width: Largeur de la zone de texte en points
    
    Returns:
        Buffer PDF modifié
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from PyPDF2 import PdfReader, PdfWriter
    
    # Créer un nouveau PDF avec le texte
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    # Configuration du texte
    font_name = "Helvetica"
    font_size = 8
    line_height = 10
    can.setFont(font_name, font_size)
    can.setFillColorRGB(0.2, 0.2, 0.2)  # Gris foncé
    
    # Position de départ (juste sous l'image)
    text_y = y - 5  # 5 points sous l'image
    
    # Construire les lignes de texte
    lines = []
    
    # Ligne 1: Nom Prénom
    if signer_info.get('name') or signer_info.get('sub_name'):
        full_name = f"{signer_info.get('sub_name', '')} {signer_info.get('name', '')}".strip()
        if full_name:
            lines.append(full_name)
    
    # Ligne 2: Fonction
    if signer_info.get('function'):
        lines.append(signer_info['function'])
    
    # Ligne 3: Email
    if signer_info.get('email'):
        lines.append(signer_info['email'])
    
    # Dessiner chaque ligne
    for i, line in enumerate(lines):
        y_pos = text_y - (i * line_height)
        can.drawString(x, y_pos, line)
    
    can.save()
    packet.seek(0)
    
    # Fusionner avec le PDF existant
    text_pdf = PdfReader(packet)
    existing_pdf = PdfReader(pdf_buffer)
    output = PdfWriter()
    
    for i in range(len(existing_pdf.pages)):
        page = existing_pdf.pages[i]
        if i == page_index:
            page.merge_page(text_pdf.pages[0])
        output.add_page(page)
    
    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def sign_pdf_pages(pdf_buffer, pages, signer, signer_stamp, signer_info=None, show_signer_info=False, custom_timestamp=None):
    """Applique les signatures sur les pages indiquées.
    
    Args:
        pdf_buffer: Buffer du PDF à signer
        pages: Liste des pages et positions de signature
        signer: Objet signataire PyHanko
        signer_stamp: Image de signature PIL
        signer_info: Dict avec les infos du signataire (name, sub_name, function, email)
        show_signer_info: Si True, affiche les infos du signataire sous l'image
        custom_timestamp: Timestamp personnalisé (string au format "DD/MM/YYYY à HH:MM:SS") ou None pour utiliser la date actuelle
    """
    current_app.logger.info(f"🎯 sign_pdf_pages appelée - signer_stamp: {type(signer_stamp)}, None? {signer_stamp is None}")
    if signer_stamp and hasattr(signer_stamp, 'size'):
        current_app.logger.info(f"🎯 Image reçue dans sign_pdf_pages: taille={signer_stamp.size}, mode={signer_stamp.mode}")
    else:
        current_app.logger.error(f"❌ PROBLÈME: signer_stamp n'est pas une image PIL valide!")
    
    intermediate_buffer = pdf_buffer
    
    # CRITIQUE: Ajouter TOUS les textes des infos signataires AVANT toutes les signatures
    # pour ne pas invalider les certificats
    if show_signer_info and signer_info:
        current_app.logger.info(f"📝 Ajout des textes d'informations AVANT les signatures")
        for page_params in pages:
            page_index = page_params.get("page", 0)
            signatures = page_params.get("signatures", [])
            
            for signature in signatures:
                try:
                    x = mm_to_points(signature.get("x", 50))
                    y = mm_to_points(signature.get("y", 100))
                    
                    intermediate_buffer = add_signer_info_text(
                        intermediate_buffer,
                        page_index,
                        x,
                        y,
                        signer_info
                    )
                    current_app.logger.info(f"✅ Texte ajouté pour page {page_index} à position ({x}, {y})")
                except Exception as e:
                    current_app.logger.error(f"⚠️ Erreur lors de l'ajout du texte: {str(e)}")
                    # Continue quand même
    
    # Maintenant appliquer toutes les signatures sur le PDF avec les textes
    for page_params in pages:
        page_index = page_params.get("page", 0)
        signatures = page_params.get("signatures", [])
        if not signatures or not isinstance(signatures, list):
            raise Exception(
                "Au moins une position de signature est requise. " +
                f"Les positions de signature pour la page {page_index} sont manquantes ou mal formatées."
            )

        for signature in signatures:
            try:
                x = mm_to_points(signature.get("x", 50))
                y = mm_to_points(signature.get("y", 100))
                
                pdf_writer = IncrementalPdfFileWriter(intermediate_buffer, strict=False)

                field_name = f"Signature_{uuid.uuid4().hex}"
                # Utiliser la même taille que dans signature_utils.py
                sig_field_spec = SigFieldSpec(
                    sig_field_name=field_name,
                    box=(x, y, x + 150, y + 100),
                    on_page=page_index
                )
                append_signature_field(pdf_writer, sig_field_spec)

                # Créer les métadonnées de signature avec les informations du signataire
                signature_name = None
                signature_reason = "Document signé électroniquement"
                signature_location = "DKB Sign Platform"
                
                # Ajouter les informations du signataire si disponibles
                if signer_info:
                    # Construire le nom complet pour l'affichage
                    display_name = signer_info.get('name', '')
                    if signer_info.get('sub_name'):
                        display_name += f" {signer_info['sub_name']}"
                    
                    # Nom avec fonction pour le champ name
                    full_name_with_function = display_name
                    if signer_info.get('function'):
                        full_name_with_function += f" - {signer_info['function']}"
                    
                    # Définir les métadonnées personnalisées
                    if full_name_with_function.strip():
                        signature_name = full_name_with_function.strip()
                    
                    # Créer un motif juridique complet avec timestamp
                    # Utiliser le timestamp personnalisé si fourni, sinon la date actuelle
                    if custom_timestamp:
                        current_timestamp = custom_timestamp
                    else:
                        current_timestamp = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
                    
                    # Construire les informations de contact
                    contact_info = []
                    if signer_info.get('email'):
                        contact_info.append(f"Email: {signer_info['email']}")
                    if signer_info.get('phone'):
                        contact_info.append(f"Tél: {signer_info['phone']}")
                    
                    contact_str = f" ({', '.join(contact_info)})" if contact_info else ""
                    
                    if signer_info.get('function') and display_name:
                        signature_reason = f"Document signé électroniquement par {display_name}, agissant en qualité de {signer_info['function']}{contact_str}, le {current_timestamp} via la plateforme DKB Sign"
                    elif display_name:
                        signature_reason = f"Document signé électroniquement par {display_name}{contact_str} le {current_timestamp} via la plateforme DKB Sign"
                    else:
                        signature_reason = f"Document signé électroniquement le {current_timestamp} via la plateforme DKB Sign"
                
                # Créer les métadonnées avec les paramètres du constructeur
                signature_metadata = PdfSignatureMetadata(
                    field_name=field_name,
                    name=signature_name,
                    reason=signature_reason,
                    location=signature_location
                )
                
                # Log critique avant création du stamp
                current_app.logger.info(f"🎨 Création du stamp PyHanko avec signer_stamp: {type(signer_stamp)}")
                if signer_stamp and hasattr(signer_stamp, 'size'):
                    current_app.logger.info(f"🎨 Image pour PyHanko: taille={signer_stamp.size}, mode={signer_stamp.mode}")
                
                pdf_signer = signers.PdfSigner(
                    signature_metadata,
                    signer=signer,
                    stamp_style=stamp.StaticStampStyle(
                        background=images.PdfImage(signer_stamp),
                        background_opacity=0.7,
                        border_width=0
                    )
                )
                
                current_app.logger.info(f"✅ PdfSigner créé avec succès pour page {page_index}")

                output_buffer = BytesIO()
                pdf_signer.sign_pdf(pdf_writer, output=output_buffer)
                intermediate_buffer = BytesIO(output_buffer.getvalue())
                
            except Exception as e:
                raise Exception(f"Erreur lors de la signature sur la page {page_index}: {str(e)}")
    return intermediate_buffer


def save_final_pdf(pdf_buffer, signed_pdf_path):
    """Enregistre le PDF final sur le disque."""
    with open(signed_pdf_path, 'wb') as output_file:
        output_file.write(pdf_buffer.getvalue())


def update_document_record(user, params, document, relative_file_path):
    """Met à jour ou crée un document en base de données."""
    if document:
        update_existing_document(document, params, relative_file_path)
    else:
        create_new_document(user, params, relative_file_path)


def notify_next_signer(document_id):
    """
    Débloque et notifie le prochain signataire selon la priorité.
    Ignore les signataires avec le statut "prepared".
    """
    try:
        # Récupérer tous les signataires triés par priorité
        signers_list = Signer.query.filter_by(document_id=document_id).order_by(Signer.priority).all()

        # Filtrer les signataires signés et en attente (ignorer les "prepared")
        active_signers = [s for s in signers_list if s.status != "prepared"]
        signed_signers = [s for s in active_signers if s.status == "signed"]

        # Trouver la plus haute priorité des documents signés
        current_priority = max([s.priority for s in signed_signers], default=0)

        # Trouver l'initiateur (priorité 0) pour le chemin du fichier
        initiator = Signer.query.filter_by(document_id=document_id, priority=0).first()
        if not initiator:
            return None

        initiator_user = User.query.get(initiator.signer_id)
        if not initiator_user:
            return None

        # Construire le sous-dossier en fonction du type de compte de l'initiateur
        if initiator_user.account_type == "employee" and initiator_user.company_id:
            initiator_company = Company.query.get(initiator_user.company_id)
            if not initiator_company:
                return None
            subfolder = f"companies/{initiator_company.name.replace(' ', '_')}/users/{initiator_user.email}"
        else:
            subfolder = f"users/{initiator_user.email}"

        # Si la priorité du signataire actuel est plus grande que max_signed_priority + 1,
        # vérifier s'il y a des signataires non "prepared" qui doivent signer avant
        next_priority = current_priority + 1

        # Trouver les prochains signataires en attente (ignorer les "prepared")
        next_signers = [s for s in active_signers if s.priority == next_priority and s.status == "pending"]

        for next_signer in next_signers:
            # Récupérer le document
            document = next_signer.document
            if not document:
                continue

            # Générer l'OTP pour le prochain signataire
            otp = ''.join(random.choices(string.digits, k=6))
            next_signer.otp = otp
            next_signer.otp_created_at = datetime.utcnow()
            db.session.commit()

            # Préparer le lien de signature
            sign_link = f"https://dkb-sign-ui.vercel.app/signed-docs/verify?uuid={next_signer.uuid}"

            # Récupérer les informations du signataire selon son type
            if next_signer.account_type == "external":
                signer = Contact.query.get(next_signer.signer_id)
                if signer:
                    recipient_email = signer.email
                    recipient_name = signer.name
            else:
                signer = User.query.get(next_signer.signer_id)
                if signer:
                    recipient_email = signer.email
                    recipient_name = signer.name if hasattr(signer, 'name') else signer.email

            if not signer:
                continue

            # CORRECTION: Les contacts externes reçoivent TOUJOURS le lien direct avec OTP
            # car ils n'ont pas de compte pour se connecter
            # Préparer le contenu de l'email (toujours avec lien direct pour notify_next_signer)
            subject = "Document à signer"
            body = f"Bonjour {recipient_name},\n\nVous avez un document à signer.\n\nVotre code OTP : {otp}\n\nLien de signature : {sign_link}"
            html = render_template(
                "sign_document_email.html",
                name=recipient_name,
                sign_url=sign_link,
                otp_code=otp,
                document_name=document.name,
                current_year=datetime.now().year
            )

            # Envoyer l'email
            try:
                current_app.logger.info(f"Tentative d'envoi d'email à {recipient_email}")
                send_email(
                    subject=subject,
                    recipient=recipient_email,
                    body=body,
                    html=html
                )
                current_app.logger.info(f"Email envoyé avec succès à {recipient_email}")
            except Exception as e:
                current_app.logger.error(f"Erreur lors de l'envoi de l'email: {str(e)}")
                return None

        return True

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la notification du prochain signataire: {str(e)}")
        return False


def notify_next_flow_signer(document_id, flow_id, current_signer_id=None):
    """
    Débloque et notifie le prochain signataire du workflow selon la priorité.
    Les priorités commencent à 0 (initiateur) et peuvent aller jusqu'à n'importe quel nombre.
    """
    try:
        from app.models import LineFlow, User, Contact, Document, Flow

        # Vérifier le flow
        flow = Flow.query.get(flow_id)
        if not flow:
            current_app.logger.info(f"Flow {flow_id} non trouvé")
            return None

        # Récupérer tous les line_flows triés par priorité
        line_flows = LineFlow.query.filter_by(flow_id=flow_id).order_by(LineFlow.priority).all()
        if not line_flows:
            current_app.logger.info(f"Aucun line_flow trouvé pour le flow {flow_id}")
            return None

        # Log de tous les line_flows pour debug
        for lf in line_flows:
            current_app.logger.info(f"LineFlow - ID: {lf.id}, Priority: {lf.priority}, Action Done: {lf.action_done}")

        # Récupérer le document
        document = Document.query.get(document_id)
        if not document:
            current_app.logger.info(f"Document {document_id} non trouvé")
            return None

        # Trouver la plus haute priorité des documents signés
        signed_flows = [lf for lf in line_flows if lf.action_done]
        
        # Si un signataire vient de signer, on l'ajoute aux signatures même si la BD n'est pas encore mise à jour
        if current_signer_id:
            current_signer = next((lf for lf in line_flows if lf.user_id == current_signer_id), None)
            if current_signer and current_signer not in signed_flows:
                signed_flows.append(current_signer)
                current_app.logger.info(f"Ajout du signataire actuel {current_signer_id} (priorité {current_signer.priority}) aux signatures")
        
        current_priority = max([lf.priority for lf in signed_flows], default=-1)
        current_app.logger.info(f"Plus haute priorité signée: {current_priority}")

        # Trouver la priorité suivante à notifier
        next_priority = current_priority + 1
        current_app.logger.info(f"Recherche des signataires de priorité {next_priority}")

        # Trouver les signataires de la priorité suivante qui n'ont pas encore signé
        next_flows = LineFlow.query.filter(
            LineFlow.flow_id == flow_id,
            LineFlow.priority == next_priority,
            LineFlow.action_done == False
        ).all()
        
        # Exclure le signataire actuel s'il est dans la liste
        if current_signer_id:
            next_flows = [nf for nf in next_flows if nf.user_id != current_signer_id]
        
        current_app.logger.info(f"Nombre de signataires suivants trouvés: {len(next_flows)}")

        for next_flow in next_flows:
            current_app.logger.info(f"Préparation notification pour signataire {next_flow.user_id} (priorité {next_flow.priority})")
            
            # Générer l'OTP pour le prochain signataire
            next_flow.generate_read_aprob_otp()
            db.session.commit()

            # Récupérer les informations du signataire selon son type
            if next_flow.account_type == "contact":
                signer = Contact.query.get(next_flow.user_id)
                if signer:
                    recipient_email = signer.email
                    recipient_name = signer.name
            else:
                signer = User.query.get(next_flow.user_id)
                if signer:
                    recipient_email = signer.email
                    recipient_name = signer.name if hasattr(signer, 'name') else signer.email

            if not signer:
                current_app.logger.info(f"Signataire {next_flow.user_id} non trouvé")
                continue

            # Construire la liste des actions à faire
            actions = "<ul>"
            for act in next_flow.actions:
                if act == "sign_doc":
                    actions += "<li>✍️ Signer le document</li>"
                elif act == "add_paraph":
                    actions += "<li>🖋️ Parapher le document</li>"
                elif act == "add_qrcode":
                    actions += "<li>🔳 Ajouter un QR code</li>"
                elif act == "add_stamp":
                    actions += "<li>🏢 Ajouter un cachet</li>"
                elif act == "add_date":
                    actions += "<li>📅 Ajouter la date</li>"
                elif act == "add_text":
                    actions += "<li>📝 Ajouter du texte</li>"
                elif act == "read_only":
                    actions += "<li>👀 Approbation de lecture</li>"
            actions += "</ul>"

            # Préparer le lien de signature
            sign_link = f"https://dkb-sign-ui.vercel.app/flow-docs/verify?flow_id={flow_id}&user_id={next_flow.user_id}"

            # Préparer le contenu de l'email
            subject = "Document à signer (Workflow)"
            body = f"""Bonjour {recipient_name},

Vous avez un document à signer dans le cadre d'un workflow.

Document : {document.name}
Actions à effectuer :
{actions}

Votre code OTP : {next_flow.read_aprob_otp}
Lien de signature : {sign_link}

Cordialement,
L'équipe DKB Sign"""

            template_data = {
                'name': recipient_name,
                'document_name': document.name,
                'workflow_name': flow.name if hasattr(flow, 'name') else "",
                'reference': flow.reference if hasattr(flow, 'reference') else "",
                'actions': actions,  # Changé de actions_list à actions pour correspondre au template
                'sign_url': sign_link,
                'otp_code': next_flow.read_aprob_otp,
                'current_year': datetime.now().year
            }

            # Envoyer l'email
            try:
                current_app.logger.info(f"Tentative d'envoi d'email à {recipient_email}")
                html = render_template('simple_notification_email.html', **template_data)
                send_email(
                    subject=subject,
                    recipient=recipient_email,
                    body=body,
                    html=html
                )
                current_app.logger.info(f"Email envoyé avec succès à {recipient_email}")
            except Exception as e:
                current_app.logger.error(f"Erreur lors de l'envoi de l'email: {str(e)}")
                return None

        return True

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la notification du prochain signataire du workflow: {str(e)}")
        return False