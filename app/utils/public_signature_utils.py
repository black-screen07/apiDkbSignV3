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
from reportlab.lib.colors import HexColor
from app.services.email_service import send_email
import random
import string
from app.models import User, Company, Document, Contact, DocumentConsent, Signer, CertTypeEnum, db, LineFlow, Flow
from PIL import ImageDraw, ImageFont


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


def retrieve_certificates_by_email(signer_email, company):
    """
    Récupère les certificats d'un signataire employé à partir de son email.
    Utilisé pour les entreprises avec cert_type=PERSONNE_PHYSIQUE dans l'API publique.
    
    L'entreprise est connue via le token de l'admin authentifié (API key).
    Le certificat P12 est cherché dans:
        certificates/companies/{company_name}/employees/{email}.p12
    
    Args:
        signer_email: Email du signataire dont on cherche le certificat P12
        company: L'entreprise (déjà récupérée via le token admin de l'API publique)
    
    Returns:
        tuple: (cert_path, key_path, cert_chain) ou lève une exception si introuvable
    """
    from werkzeug.utils import secure_filename
    
    if not company:
        raise ValueError("Entreprise requise pour récupérer le certificat d'un employé.")
    
    safe_company_name = secure_filename(company.name)
    employee_cert_folder = Path("certificates/companies") / safe_company_name / "employees"
    
    p12_path = employee_cert_folder / f"{signer_email}.p12"
    cert_path = employee_cert_folder / f"{signer_email}.crt"
    key_path = employee_cert_folder / f"{signer_email}.key"
    
    # Extraire le certificat et la clé depuis le P12 si nécessaire
    if not cert_path.exists() or not key_path.exists():
        if not p12_path.exists():
            raise FileNotFoundError(
                f"Certificat (.p12) non trouvé pour le signataire {signer_email}. "
                f"Chemin attendu: {p12_path}"
            )
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


def trim_transparent_padding(img, margin=10):
    """
    Supprime l'espace transparent (ou blanc) autour de la partie visible de l'image.
    Cela permet à la signature visible de mieux remplir la boîte PDF,
    et réduit l'écart visuel entre la signature et le texte en dessous.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    
    if bbox is None:
        return img
    
    left = max(0, bbox[0] - margin)
    upper = max(0, bbox[1] - margin)
    right = min(img.width, bbox[2] + margin)
    lower = min(img.height, bbox[3] + margin)
    
    return img.crop((left, upper, right, lower))


def prepare_signature_image(img, target_box_width=250, dpi_factor=6):
    """
    Prépare une image de signature pour une intégration nette dans le PDF.
    
    Problème résolu:
        PyHanko étire l'image pour remplir la boîte de signature PDF.
        Si l'image source est trop petite, cet étirement crée du flou/pixelisation.
        Si le ratio n'est pas respecté, l'image est déformée.
        De plus, PdfImage peut appliquer une compression JPEG lossy qui dégrade la qualité.
    
    Solution:
        1. Convertir en RGBA pour la transparence
        2. Recadrer le padding transparent (trim)
        3. Upscaler à haute résolution en respectant le ratio d'aspect
        4. Appliquer un filtre de netteté pour compenser toute perte
    
    Args:
        img: Image PIL source
        target_box_width: Largeur de la boîte PDF en points (défaut 250)
        dpi_factor: Multiplicateur de résolution (défaut 6 = ~432 DPI effectif)
    
    Returns:
        Image PIL optimisée, prête pour PyHanko
    """
    from PIL import ImageFilter
    
    # 1. Convertir en RGBA pour garder la transparence
    if img.mode == 'P':
        img = img.convert('RGBA')
    elif img.mode in ('L', 'LA'):
        img = img.convert('RGBA')
    elif img.mode == 'RGB':
        img = img.convert('RGBA')
    
    # 2. Recadrer le padding transparent autour du contenu visible
    img = trim_transparent_padding(img)
    
    # 3. Calculer la taille cible en pixels pour une résolution nette
    # target_box_width en points * dpi_factor = pixels nécessaires
    # Ex: 250 pts * 6 = 1500 pixels de large minimum
    min_pixel_width = int(target_box_width * dpi_factor)
    
    if img.width < min_pixel_width:
        scale_factor = min_pixel_width / img.width
        new_width = int(img.width * scale_factor)
        new_height = int(img.height * scale_factor)
        # LANCZOS est le meilleur filtre pour l'upscaling (anti-aliasing de haute qualité)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # 4. Appliquer un filtre de netteté pour compenser le flou d'interpolation
    # UnsharpMask(radius, percent, threshold) - plus agressif pour contrer la compression PDF
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
    
    return img


def pil_image_to_pdf_image(img):
    """
    Convertit une image PIL en PdfImage via un buffer PNG lossless.
    
    CRITIQUE: Passer directement un objet PIL à PdfImage peut déclencher
    une compression JPEG (DCTDecode) lossy qui dégrade la qualité.
    En sauvegardant d'abord en PNG (FlateDecode = sans perte), on force
    PyHanko à préserver la qualité originale de l'image.
    
    Args:
        img: Image PIL (idéalement déjà traitée par prepare_signature_image)
    
    Returns:
        PdfImage prête pour StaticStampStyle.background
    """
    from pyhanko.pdf_utils import images as pdf_images
    
    # Sauvegarder en PNG lossless puis recharger en PIL Image
    # Cela force les données internes en format PNG (pas JPEG)
    # PdfImage attend un objet PIL Image, pas un BytesIO
    png_buffer = BytesIO()
    img.save(png_buffer, format='PNG', optimize=False)
    png_buffer.seek(0)
    png_img = Image.open(png_buffer)
    png_img.load()  # Forcer le chargement complet en mémoire
    return pdf_images.PdfImage(png_img)


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
    
    # Convertir en RGBA pour la transparence
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # NOTE: Ne PAS appeler prepare_signature_image ici.
    # sign_pdf_pages le fait déjà. Un double traitement dégrade la qualité.
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

    if back_color == "transparent":
        img = qr.make_image(fill_color=fill_color, back_color="white").convert("RGBA")
        # Rendre le fond blanc transparent
        datas = img.getdata()
        new_data = []
        for item in datas:
            # Pixels blancs ou quasi-blancs -> transparent
            if item[0] > 230 and item[1] > 230 and item[2] > 230:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        img.putdata(new_data)
    else:
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
            # Personne physique : décompte UNIQUEMENT dans la table company
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
            # Personne physique : vérifier UNIQUEMENT le volume de l'entreprise
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


def create_signed_by_sticker(signature_image, sticker_path="documents/sticker.jpeg"):
    """
    Ajoute le sticker "Signed by" (déjà designé sur Photoshop) à côté de la signature.
    
    Args:
        signature_image: Image PIL de la signature
        sticker_path: Chemin vers le sticker DKB Sign (avec design Photoshop)
    
    Returns:
        Image PIL composite avec signature + sticker
    """
    try:
        current_app.logger.info(f"🎨 Ajout du sticker Photoshop - Signature: {signature_image.size}")
        
        # Vérifier et construire le chemin absolu du sticker
        from pathlib import Path
        import os
        
        if not os.path.isabs(sticker_path):
            base_dir = Path(__file__).parent.parent.parent
            sticker_path = base_dir / sticker_path
        
        sticker_path = Path(sticker_path)
        
        if not sticker_path.exists():
            raise FileNotFoundError(f"Le fichier sticker n'existe pas: {sticker_path}")
        
        # Charger le sticker Photoshop
        sticker_logo = Image.open(sticker_path)
        current_app.logger.info(f"✅ Sticker chargé: {sticker_logo.size}, mode: {sticker_logo.mode}")
        
        # Convertir en RGBA pour la transparence
        if sticker_logo.mode != 'RGBA':
            sticker_logo = sticker_logo.convert('RGBA')
        
        # Le sticker est déjà vertical (300x900) - pas de rotation nécessaire
        current_app.logger.info(f"� Sticker déjà vertical: {sticker_logo.size}")
        
        # Dimensions de la signature (à préserver ABSOLUMENT)
        sig_width, sig_height = signature_image.size
        current_app.logger.info(f"📏 Signature originale (NON MODIFIÉE): {sig_width}x{sig_height}")
        
        # Dimensions du sticker (300x900 - déjà vertical)
        sticker_width, sticker_height = sticker_logo.size
        current_app.logger.info(f"📏 Sticker dimensions: {sticker_width}x{sticker_height}")
        
        # Redimensionner le sticker à la même hauteur que la signature
        # Utiliser 100% de la hauteur de la signature pour qu'il soit bien visible
        target_sticker_height = sig_height
        aspect_ratio = sticker_width / sticker_height
        sticker_height_resized = target_sticker_height
        sticker_width_resized = int(target_sticker_height * aspect_ratio)
        
        sticker_logo = sticker_logo.resize((sticker_width_resized, sticker_height_resized), Image.Resampling.LANCZOS)
        current_app.logger.info(f"📏 Sticker redimensionné à 100% hauteur signature: {sticker_width_resized}x{sticker_height_resized}")
        
        # Pas d'espacement entre sticker et signature (collés)
        spacing = 0
        
        # Créer l'image composite simple (sticker + signature)
        total_width = sticker_width_resized + spacing + sig_width
        total_height = max(sig_height, sticker_height_resized)
        composite = Image.new('RGBA', (total_width, total_height), (255, 255, 255, 0))
        
        # Coller le sticker à gauche (centré verticalement)
        sticker_y = (total_height - sticker_height_resized) // 2
        composite.paste(sticker_logo, (0, sticker_y), sticker_logo)
        current_app.logger.info(f"✅ Sticker collé à (0, {sticker_y})")
        
        # Coller la signature à droite (centrée verticalement)
        sig_x = sticker_width_resized + spacing
        sig_y = (total_height - sig_height) // 2
        composite.paste(signature_image, (sig_x, sig_y), signature_image if signature_image.mode == 'RGBA' else None)
        current_app.logger.info(f"✅ Signature collée à ({sig_x}, {sig_y})")
        
        current_app.logger.info(f"✅✅✅ Composite créé avec succès: {total_width}x{total_height}px")
        return composite
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        current_app.logger.error(f"❌ ERREUR sticker: {str(e)}")
        current_app.logger.error(f"Traceback: {error_trace}")
        raise Exception(f"Échec de création du sticker: {str(e)}") from e


def add_signer_details_to_pdf(
    pdf_buffer,
    page_index,
    signer_name,
    signer_function,
    signer_grade,
    details_x,
    details_y,
    special_mention=None,
    special_mention_x=None,
    special_mention_y=None,
):
    """
    Ajoute les informations du signataire de manière élégante et professionnelle.

    Mise en page (de haut en bas) :
        [Mention spéciale optionnelle]   ← italique 10pt, juste au-dessus de la signature image
        ✍ (signature manuscrite/image rendue par PyHanko)
        Prénom NOM                        ← Helvetica-Bold 10pt
        ─────────────                     ← trait fin
        Fonction Grade                    ← Helvetica-Oblique 8.5pt (valeur du grade, sans libellé)

    Exemple avec mention spéciale (acte administratif officiel) :
        Pour le Préfet et par Ordre
        Le Secrétaire Général 1
        ✍ (signature)
        ZAN Bi Goré Adolphe
        ──────────────────
        Préfet Hors Grade

    Args:
        pdf_buffer: Buffer du PDF
        page_index: Index de la page (0-based)
        signer_name: Nom complet du signataire (ex: "Jean DUPONT")
        signer_function: Fonction du signataire (ex: "Préfet")
        signer_grade: Valeur du grade telle qu'elle doit apparaître (ex: "Hors Grade").
            Le libellé "Grade" n'est PAS ajouté — seule la valeur est imprimée.
        details_x: Position X en points PDF (ancrage du bloc nom)
        details_y: Position Y en points PDF (ligne de base du nom)
        special_mention: Mention protocolaire optionnelle rendue au-dessus de la signature
            image (ex: "Pour le Préfet et par Ordre\nLe Secrétaire Général 1").
            Les sauts de ligne explicites (\n) sont respectés.
        special_mention_x: Position X (en POINTS PDF) du bloc mention spéciale.
            Si None, on s'aligne sur details_x (même colonne que le nom).
        special_mention_y: Position Y (en POINTS PDF) de la ligne de base de la DERNIÈRE
            ligne de la mention (la plus basse, juste au-dessus de la signature image).
            Si None, on calcule automatiquement details_y + ~95pt pour passer au-dessus
            de la signature image.

    Returns:
        Buffer PDF modifié
    """
    from reportlab.pdfgen import canvas
    from PyPDF2 import PdfReader, PdfWriter

    # Lire le PDF existant pour obtenir les dimensions de la page
    existing_pdf = PdfReader(pdf_buffer)
    page = existing_pdf.pages[page_index]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)

    # Créer un PDF overlay
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))

    # ── Mention spéciale (optionnelle), rendue AU-DESSUS de la signature image ──
    # Position :
    #   - special_mention_x / special_mention_y (en points PDF) si fournis,
    #   - sinon fallback automatique : aligné sur le nom en X, et ~95pt au-dessus de
    #     details_y en Y pour passer au-dessus de la signature image (≈ 33mm).
    # Style : Helvetica-Oblique 10pt, gris anthracite (#2E2E2E), interligne 12pt.
    # Les lignes sont rendues du bas vers le haut, donc special_mention_y correspond à
    # la baseline de la DERNIÈRE ligne (la plus proche de la signature image).
    if special_mention and str(special_mention).strip():
        mention_font = "Helvetica-Oblique"
        mention_size = 10
        mention_leading = 12
        mention_lines = [ln.strip() for ln in str(special_mention).splitlines() if ln.strip()]

        if mention_lines:
            can.setFont(mention_font, mention_size)
            can.setFillColorRGB(0.180, 0.180, 0.180)  # #2E2E2E

            # Position X : valeur explicite ou alignement sur le nom
            mention_x = special_mention_x if special_mention_x is not None else details_x

            # Position Y de la dernière ligne (la plus basse) : valeur explicite, sinon
            # défaut = details_y + ~95pt (au-dessus de la signature image typique).
            if special_mention_y is not None:
                last_line_baseline = special_mention_y
            else:
                gap_above_signature = 95  # ≈ 33mm, hauteur typique d'une signature image
                last_line_baseline = details_y + gap_above_signature

            # On rend les lignes du bas vers le haut. La 1re itération (i=0) est la dernière
            # ligne saisie par l'utilisateur, posée sur last_line_baseline. Les lignes
            # précédentes remontent par incréments de mention_leading.
            for i, line in enumerate(reversed(mention_lines)):
                line_y = last_line_baseline + i * mention_leading
                can.drawString(mention_x, line_y, line)

    # ── Ligne 1 : Prénom Nom ──
    # Police Helvetica-Bold, 10pt, noir profond (#1A1A1A)
    name_font = "Helvetica-Bold"
    name_size = 10
    can.setFont(name_font, name_size)
    can.setFillColorRGB(0.102, 0.102, 0.102)  # #1A1A1A

    # Dessiner le nom
    name_y = details_y
    can.drawString(details_x, name_y, signer_name)

    # ── Trait de séparation fin et discret ──
    separator_y = name_y - 5
    name_width = can.stringWidth(signer_name, name_font, name_size)
    can.setStrokeColorRGB(0.65, 0.65, 0.65)  # Gris clair
    can.setLineWidth(0.4)
    can.line(details_x, separator_y, details_x + name_width, separator_y)

    # ── Ligne 2 : Fonction (et valeur du grade, sans libellé) ──
    # Police Helvetica-Oblique, 8.5pt, gris élégant (#4A4A4A)
    # NB : on n'imprime pas le mot "Grade", uniquement la valeur (ex: "Préfet Hors Grade").
    func_font = "Helvetica-Oblique"
    func_size = 8.5
    can.setFont(func_font, func_size)
    can.setFillColorRGB(0.290, 0.290, 0.290)  # #4A4A4A

    # Construire la ligne fonction + valeur du grade (séparateur espace)
    detail_line = ""
    if signer_function and signer_grade:
        detail_line = f"{signer_function} {signer_grade}"
    elif signer_function:
        detail_line = signer_function
    elif signer_grade:
        detail_line = signer_grade

    if detail_line:
        func_y = separator_y - 10
        can.drawString(details_x, func_y, detail_line)

    can.save()
    packet.seek(0)
    
    # Fusionner avec le PDF existant
    text_pdf = PdfReader(packet)
    pdf_buffer.seek(0)
    existing_pdf = PdfReader(pdf_buffer)
    output = PdfWriter()
    
    for i in range(len(existing_pdf.pages)):
        p = existing_pdf.pages[i]
        if i == page_index:
            p.merge_page(text_pdf.pages[0])
        output.add_page(p)
    
    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def add_legal_mention_to_pdf(pdf_buffer, page_index, signer_name, signer_function, grade, mention_x=None, mention_y=None):
    """
    Ajoute une mention légale sur la page.
    
    Texte: "Ce document est signé électroniquement selon les normes de confidentialité 
    et de sécurité de l'ARTCI et l'ANSSI, par {signer_name} {signer_function} de grade {grade}"
    
    Args:
        pdf_buffer: Buffer du PDF
        page_index: Index de la page
        signer_name: Nom complet du signataire
        signer_function: Fonction du signataire
        grade: Grade du signataire
        mention_x: Position X en points (optionnel, centré si None)
        mention_y: Position Y en points (optionnel, bas de page si None)
    
    Returns:
        Buffer PDF modifié
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from PyPDF2 import PdfReader, PdfWriter
    
    # Lire le PDF existant pour obtenir les dimensions de la page
    existing_pdf = PdfReader(pdf_buffer)
    page = existing_pdf.pages[page_index]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    # Construire le texte de la mention
    function_part = f" {signer_function}" if signer_function else ""
    mention_text = (
        f" Ce document est signé électroniquement selon les lois fixées par la législation et la réglementation en vigueur."
    )
    
    # Créer un PDF overlay avec le texte
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Configuration du texte
    font_name = "Helvetica"
    font_size = 7
    can.setFont(font_name, font_size)
    can.setFillColorRGB(0.3, 0.3, 0.3)  # Gris foncé
    
    # Découper le texte en lignes si trop long pour la largeur de page
    max_text_width = page_width - 80  # Marges de 40 pts de chaque côté
    words = mention_text.split(' ')
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        if can.stringWidth(test_line, font_name, font_size) <= max_text_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    
    line_height = font_size + 2
    
    if mention_x is not None and mention_y is not None:
        # Position personnalisée (x, y en points PDF)
        y_start = mention_y
        for i, line in enumerate(lines):
            y_pos = y_start - (i * line_height)
            can.drawString(mention_x, y_pos, line)
    else:
        # Position par défaut: centré en bas de page, 20 pts au-dessus du bord inférieur
        y_start = 20 + (len(lines) - 1) * line_height
        for i, line in enumerate(lines):
            text_width = can.stringWidth(line, font_name, font_size)
            x_pos = (page_width - text_width) / 2  # Centrer horizontalement
            y_pos = y_start - (i * line_height)
            can.drawString(x_pos, y_pos, line)
    
    can.save()
    packet.seek(0)
    
    # Fusionner avec le PDF existant
    text_pdf = PdfReader(packet)
    pdf_buffer.seek(0)
    existing_pdf = PdfReader(pdf_buffer)
    output = PdfWriter()
    
    for i in range(len(existing_pdf.pages)):
        p = existing_pdf.pages[i]
        if i == page_index:
            p.merge_page(text_pdf.pages[0])
        output.add_page(p)
    
    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def add_vertical_text_to_pdf(pdf_buffer, page_index, text, font_size=6, margin_right=8, color=(0.3, 0.3, 0.3), y_start_ratio=None):
    """
    Ajoute un texte vertical le long du bord droit du document PDF.
    Le texte est pivoté à 90° et positionné verticalement sur la page.
    
    Args:
        pdf_buffer: Buffer du PDF
        page_index: Index de la page
        text: Texte à afficher verticalement
        font_size: Taille de police (défaut: 6)
        margin_right: Marge depuis le bord droit en points (défaut: 8)
        color: Tuple RGB pour la couleur du texte (défaut: gris foncé)
        y_start_ratio: Position de départ en ratio de la hauteur (0.0=bas, 1.0=haut).
                        Si None, le texte est centré verticalement.
    
    Returns:
        Buffer PDF modifié
    """
    from reportlab.pdfgen import canvas
    from PyPDF2 import PdfReader, PdfWriter
    
    existing_pdf = PdfReader(pdf_buffer)
    page = existing_pdf.pages[page_index]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    font_name = "Helvetica"
    can.setFont(font_name, font_size)
    can.setFillColorRGB(*color)
    
    # Calculer la largeur du texte pour le centrer verticalement
    text_width = can.stringWidth(text, font_name, font_size)
    
    # Position X: bord droit moins la marge
    x_pos = page_width - margin_right
    
    # Position Y: centrer ou positionner selon y_start_ratio
    if y_start_ratio is not None:
        y_pos = page_height * y_start_ratio - text_width
        y_pos = max(10, y_pos)  # Ne pas sortir de la page
    else:
        y_pos = (page_height - text_width) / 2
    
    # Sauvegarder l'état, pivoter de 90° et dessiner le texte
    can.saveState()
    can.translate(x_pos, y_pos)
    can.rotate(90)
    can.drawString(0, 0, text)
    can.restoreState()
    
    can.save()
    packet.seek(0)
    
    # Fusionner avec le PDF existant
    text_pdf = PdfReader(packet)
    pdf_buffer.seek(0)
    existing_pdf = PdfReader(pdf_buffer)
    output = PdfWriter()
    
    for i in range(len(existing_pdf.pages)):
        p = existing_pdf.pages[i]
        if i == page_index:
            p.merge_page(text_pdf.pages[0])
        output.add_page(p)
    
    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream


def add_signer_info_text(pdf_buffer, page_index, x, y, signer_info, box_width=250):
    """
    Ajoute les informations du signataire à droite de l'image de signature.
    
    Args:
        pdf_buffer: Buffer du PDF
        page_index: Index de la page
        x: Position X (en points) - position gauche de l'image
        y: Position Y (en points) - position bas de l'image
        signer_info: Dict avec name, sub_name, function, email
        box_width: Largeur de la zone de texte en points (150 = largeur signature)
    
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
    
    # Construire les lignes de texte d'abord pour calculer la hauteur totale
    lines = []
    
    # Ligne 1: "Digital signed by DKBSIGN" (toujours affichée)
    lines.append("Digital signed by DKBSIGN")
    
    # Ligne 2: Nom Prénom
    if signer_info.get('name') or signer_info.get('sub_name'):
        full_name = f"{signer_info.get('sub_name', '')} {signer_info.get('name', '')}".strip()
        if full_name:
            lines.append(full_name)
    
    # Ligne 3: Fonction
    if signer_info.get('function'):
        lines.append(signer_info['function'])
    
    # Ligne 4: Email
    if signer_info.get('email'):
        lines.append(signer_info['email'])
    
    # Position du texte juste en dessous de la signature
    text_x = x  # Aligné avec le bord gauche de la signature
    text_y = y - 10  # 10 points en dessous de la signature
    
    # Dessiner chaque ligne
    for i, line in enumerate(lines):
        y_pos = text_y - (i * line_height)
        can.drawString(text_x, y_pos, line)
    
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


def sign_pdf_pages(pdf_buffer, pages, signer, signer_stamp, signer_info=None, show_signer_info=False, custom_timestamp=None, signature_size=None):
    """Applique les signatures sur les pages indiquées.
    
    Args:
        pdf_buffer: Buffer du PDF à signer
        pages: Liste des pages et positions de signature
        signer: Objet signataire PyHanko
        signer_stamp: Image de signature PIL
        signer_info: Dict avec les infos du signataire (name, sub_name, function, email)
        show_signer_info: Si True, affiche les infos du signataire sous l'image
        custom_timestamp: Timestamp personnalisé (string au format "DD/MM/YYYY à HH:MM:SS") ou None pour utiliser la date actuelle
        signature_size: Dict optionnel avec 'width' et/ou 'height' en points pour personnaliser la taille de la boîte de signature
    """
    current_app.logger.info(f"🎯 sign_pdf_pages appelée - signer_stamp: {type(signer_stamp)}, None? {signer_stamp is None}")
    if signer_stamp is not None and isinstance(signer_stamp, Image.Image):
        current_app.logger.info(f"🎯 Image reçue dans sign_pdf_pages: taille={signer_stamp.size}, mode={signer_stamp.mode}")
    else:
        current_app.logger.info(f"📥 signer_stamp reçu de type {type(signer_stamp).__name__}, sera converti en PIL Image")
    
    # IMPORTANT: Appliquer le sticker "Signed by" UNE SEULE FOIS au début, AVANT toute signature
    # TEMPORAIREMENT DÉSACTIVÉ - À réactiver plus tard
    # if signer_stamp is not None:
    #     try:
    #         current_app.logger.info(f"🎨 Application du sticker 'Signed by' à l'image de signature...")
    #         signer_stamp = create_signed_by_sticker(signer_stamp)
    #         current_app.logger.info(f"✅ Sticker appliqué - Nouvelle taille: {signer_stamp.size}")
    #     except Exception as sticker_error:
    #         import traceback
    #         error_msg = f"ERREUR STICKER: {str(sticker_error)}\n{traceback.format_exc()}"
    #         current_app.logger.error(f"❌ {error_msg}")
    #         # Re-lever l'erreur pour qu'elle soit capturée par le gestionnaire principal
    #         raise Exception(f"Erreur lors de l'application du sticker: {str(sticker_error)}") from sticker_error
    # else:
    #     current_app.logger.warning(f"⚠️ signer_stamp est None, impossible d'appliquer le sticker")
    
    intermediate_buffer = pdf_buffer
    
    # Convertir signer_stamp en objet PIL Image si nécessaire (BytesIO, chemin, etc.)
    if signer_stamp is not None and not isinstance(signer_stamp, Image.Image):
        if isinstance(signer_stamp, (str, bytes, os.PathLike)):
            signer_stamp = Image.open(signer_stamp)
            current_app.logger.info(f"📂 Image chargée depuis chemin: {signer_stamp.size}")
        elif isinstance(signer_stamp, BytesIO):
            signer_stamp.seek(0)
            signer_stamp = Image.open(signer_stamp)
            current_app.logger.info(f"📂 Image chargée depuis BytesIO: {signer_stamp.size}")
    
    # Calculer la taille de boîte en respectant le ratio de l'image
    # Utiliser signature_size si fourni, sinon valeurs par défaut
    box_width = 250  # Valeur par défaut
    box_height = 80  # Valeur par défaut si pas d'image
    
    if signature_size and isinstance(signature_size, dict):
        custom_width = signature_size.get('width')
        custom_height = signature_size.get('height')
        if custom_width and int(custom_width) > 0:
            box_width = int(custom_width)
        if custom_height and int(custom_height) > 0:
            box_height = int(custom_height)
        current_app.logger.info(f"📏 Taille personnalisée demandée: {box_width}x{box_height} pts")
    
    # Pipeline qualité: RGBA + trim + upscale haute résolution + netteté
    # Passer box_width pour que l'upscale cible la bonne largeur
    if signer_stamp is not None and isinstance(signer_stamp, Image.Image):
        signer_stamp = prepare_signature_image(signer_stamp, target_box_width=box_width)
        current_app.logger.info(f"📏 Image après prepare_signature_image: {signer_stamp.size}, mode={signer_stamp.mode}")
    
    if signer_stamp is not None and isinstance(signer_stamp, Image.Image):
        img_width, img_height = signer_stamp.size
        if img_width > 0 and img_height > 0:
            aspect_ratio = img_height / img_width
            # Si seule la largeur est personnalisée (pas de height explicite), calculer la hauteur selon le ratio
            if not (signature_size and isinstance(signature_size, dict) and signature_size.get('height')):
                box_height = int(box_width * aspect_ratio)
                box_height = max(40, min(200, box_height))
            current_app.logger.info(f"📏 Boîte finale: {box_width}x{box_height} pts (image: {img_width}x{img_height}, ratio: {aspect_ratio:.2f})")
    
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
    
    # Ajouter les détails du signataire (nom, fonction, grade) si demandé (AVANT les signatures numériques)
    # Supporte une position par page (pages[].signer_details_x/y) avec fallback sur la position globale (signer_info)
    if signer_info and signer_info.get('show_signer_details') is True:
        # Position globale (fallback)
        global_details_x = signer_info.get('signer_details_x')
        global_details_y = signer_info.get('signer_details_y')
        
        # Construire le nom complet
        details_name = signer_info.get('name', '')
        if signer_info.get('sub_name'):
            details_name = f"{signer_info['sub_name']} {details_name}".strip()
        if not details_name:
            details_name = "Signataire"
        
        details_function = signer_info.get('function', '')
        details_grade = signer_info.get('grade', '')
        # Mention protocolaire optionnelle (ex: "Pour le Préfet et par Ordre\nLe Secrétaire Général 1")
        details_special_mention = signer_info.get('special_mention') or None
        # Position globale optionnelle de la mention spéciale (en mm). Si non fournie,
        # add_signer_details_to_pdf calcule un offset automatique au-dessus de la signature.
        global_special_mention_x = signer_info.get('special_mention_x')
        global_special_mention_y = signer_info.get('special_mention_y')

        # Parcourir chaque page pour appliquer les détails avec position spécifique ou globale
        processed_pages = set()
        for page_params in pages:
            page_idx = page_params.get("page", 0)
            if page_idx in processed_pages:
                continue
            processed_pages.add(page_idx)

            # Priorité : position définie au niveau de la page > position globale
            page_details_x = page_params.get('signer_details_x', global_details_x)
            page_details_y = page_params.get('signer_details_y', global_details_y)
            # Mention spéciale : niveau page > niveau global
            page_special_mention = page_params.get('special_mention', details_special_mention)
            page_special_mention_x = page_params.get('special_mention_x', global_special_mention_x)
            page_special_mention_y = page_params.get('special_mention_y', global_special_mention_y)

            if page_details_x is not None and page_details_y is not None:
                details_x_pts = mm_to_points(float(page_details_x))
                details_y_pts = mm_to_points(float(page_details_y))
                # Convertir mm → points uniquement si la valeur est fournie (sinon None
                # pour laisser add_signer_details_to_pdf calculer le défaut).
                special_x_pts = (
                    mm_to_points(float(page_special_mention_x))
                    if page_special_mention_x is not None else None
                )
                special_y_pts = (
                    mm_to_points(float(page_special_mention_y))
                    if page_special_mention_y is not None else None
                )
                try:
                    intermediate_buffer = add_signer_details_to_pdf(
                        intermediate_buffer,
                        page_idx,
                        details_name,
                        details_function,
                        details_grade,
                        details_x_pts,
                        details_y_pts,
                        special_mention=page_special_mention,
                        special_mention_x=special_x_pts,
                        special_mention_y=special_y_pts,
                    )
                    if page_special_mention:
                        pos_label = (
                            f"(x={page_special_mention_x}, y={page_special_mention_y} mm)"
                            if page_special_mention_x is not None or page_special_mention_y is not None
                            else "(auto)"
                        )
                        mention_log = f" | mention='{page_special_mention}' {pos_label}"
                    else:
                        mention_log = ""
                    current_app.logger.info(f"🏛️ Détails signataire ajoutés page {page_idx}: {details_name} | {details_function} grade {details_grade} (pos: {page_details_x},{page_details_y} mm){mention_log}")
                except Exception as e:
                    current_app.logger.error(f"⚠️ Erreur ajout détails signataire page {page_idx}: {str(e)}")
            else:
                current_app.logger.warning(f"⚠️ show_signer_details=True mais signer_details_x/y non fournis pour page {page_idx}, ignoré")
    
    # Ajouter la mention légale en bas de page si demandée (AVANT les signatures numériques)
    if signer_info and signer_info.get('show_legal_mention') is True and signer_info.get('grade'):
        # Construire le nom complet du signataire
        mention_name = signer_info.get('name', '')
        if signer_info.get('sub_name'):
            mention_name = f"{signer_info['sub_name']} {mention_name}".strip()
        if not mention_name:
            mention_name = "Signataire"
        
        mention_grade = signer_info['grade']
        mention_function = signer_info.get('function', '')
        
        # Position personnalisée de la mention (en mm, converti en points)
        raw_mention_x = signer_info.get('legal_mention_x')
        raw_mention_y = signer_info.get('legal_mention_y')
        mention_x_pts = mm_to_points(float(raw_mention_x)) if raw_mention_x is not None else None
        mention_y_pts = mm_to_points(float(raw_mention_y)) if raw_mention_y is not None else None
        
        # Collecter les pages uniques concernées par les signatures
        signed_pages = set()
        for page_params in pages:
            signed_pages.add(page_params.get("page", 0))
        
        for page_idx in signed_pages:
            try:
                intermediate_buffer = add_legal_mention_to_pdf(
                    intermediate_buffer,
                    page_idx,
                    mention_name,
                    mention_function,
                    mention_grade,
                    mention_x=mention_x_pts,
                    mention_y=mention_y_pts
                )
                current_app.logger.info(f"📜 Mention légale ajoutée page {page_idx} pour {mention_name} {mention_function} (grade: {mention_grade}, pos: x={raw_mention_x}, y={raw_mention_y})")
            except Exception as e:
                current_app.logger.error(f"⚠️ Erreur lors de l'ajout de la mention légale page {page_idx}: {str(e)}")
    
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
                sig_field_spec = SigFieldSpec(
                    sig_field_name=field_name,
                    box=(x, y, x + box_width, y + box_height),
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
                    
                    # Utiliser le type de document si fourni, sinon "Document"
                    doc_type_label = signer_info.get('document_type', '').strip()
                    doc_prefix = doc_type_label if doc_type_label else "Document"
                    
                    if signer_info.get('function') and display_name:
                        signature_reason = f"{doc_prefix} signé électroniquement par {display_name}, agissant en qualité de {signer_info['function']}{contact_str}, le {current_timestamp} via la plateforme DKB Sign"
                    elif display_name:
                        signature_reason = f"{doc_prefix} signé électroniquement par {display_name}{contact_str} le {current_timestamp} via la plateforme DKB Sign"
                    else:
                        signature_reason = f"{doc_prefix} signé électroniquement le {current_timestamp} via la plateforme DKB Sign"
                
                # Créer les métadonnées avec les paramètres du constructeur
                signature_metadata = PdfSignatureMetadata(
                    field_name=field_name,
                    name=signature_name,
                    reason=signature_reason,
                    location=signature_location
                )
                
                # Créer le PdfSigner avec l'image de signature (qui a déjà le sticker appliqué au début)
                current_app.logger.info(f"🎨 Création du stamp PyHanko avec signer_stamp: {type(signer_stamp)}")
                if signer_stamp is not None and isinstance(signer_stamp, Image.Image):
                    current_app.logger.info(f"🎨 Image pour PyHanko: taille={signer_stamp.size}, mode={signer_stamp.mode}")
                
                pdf_signer = signers.PdfSigner(
                    signature_metadata,
                    signer=signer,
                    stamp_style=stamp.StaticStampStyle(
                        background=images.PdfImage(signer_stamp),
                        background_opacity=0.9,
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