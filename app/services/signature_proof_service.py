import hashlib
import uuid
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

from flask import current_app, request
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from app import db
from app.models import SignatureProof, SignatureAuditEvent, Document, User, Contact, Company

PROOF_PDF_FOLDER = Path("documents/proofs")
PROOF_PDF_FOLDER.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════
# UTILITAIRES
# ═══════════════════════════════════════════════════════

def compute_file_hash_sha256(file_path=None, file_bytes=None):
    """Calcule le hash SHA-256 d'un fichier."""
    sha256 = hashlib.sha256()
    if file_bytes:
        sha256.update(file_bytes if isinstance(file_bytes, bytes) else file_bytes.encode())
    elif file_path and os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
    else:
        return None
    return sha256.hexdigest()


def get_file_size(file_path=None, file_bytes=None):
    """Retourne la taille d'un fichier en bytes."""
    if file_bytes:
        return len(file_bytes) if isinstance(file_bytes, bytes) else None
    elif file_path and os.path.exists(file_path):
        return os.path.getsize(file_path)
    return None


def get_page_count(file_path=None, file_bytes=None):
    """Compte le nombre de pages d'un PDF."""
    try:
        if file_bytes:
            reader = PdfReader(BytesIO(file_bytes) if isinstance(file_bytes, bytes) else file_bytes)
        elif file_path and os.path.exists(file_path):
            reader = PdfReader(file_path)
        else:
            return None
        return len(reader.pages)
    except Exception:
        return None


def extract_certificate_info(cert_path):
    """Extrait les informations complètes du certificat X.509."""
    info = {}
    try:
        if not cert_path or not os.path.exists(cert_path):
            return info

        with open(cert_path, 'rb') as f:
            cert_data = f.read()

        certificate = None
        if cert_path.endswith('.p12') or cert_path.endswith('.pfx'):
            _, certificate, _ = pkcs12.load_key_and_certificates(
                cert_data, b"2468", default_backend()
            )
        else:
            certificate = x509.load_pem_x509_certificate(cert_data, default_backend())

        if certificate:
            info['subject'] = certificate.subject.rfc4514_string()
            info['issuer'] = certificate.issuer.rfc4514_string()
            info['serial'] = str(certificate.serial_number)
            info['valid_from'] = certificate.not_valid_before_utc if hasattr(certificate, 'not_valid_before_utc') else certificate.not_valid_before
            info['valid_to'] = certificate.not_valid_after_utc if hasattr(certificate, 'not_valid_after_utc') else certificate.not_valid_after

            # Algorithme de signature
            sig_algo = certificate.signature_algorithm_oid
            if sig_algo:
                algo_name = sig_algo.dotted_string
                if 'rsa' in str(certificate.signature_hash_algorithm).lower() or '1.2.840.113549' in algo_name:
                    info['algorithm'] = 'RSA'
                elif 'ec' in str(certificate.signature_hash_algorithm).lower() or '1.2.840.10045' in algo_name:
                    info['algorithm'] = 'ECDSA'
                else:
                    info['algorithm'] = algo_name

            # Clé publique
            try:
                public_key = certificate.public_key()
                pub_bytes = public_key.public_bytes(
                    encoding=Encoding.PEM,
                    format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.SubjectPublicKeyInfo
                )
                info['public_key'] = pub_bytes.decode('utf-8')
            except Exception:
                info['public_key'] = None

    except Exception as e:
        current_app.logger.warning(f"Impossible d'extraire les infos du certificat: {e}")
    return info


def parse_user_agent(ua_string):
    """Parse le User-Agent pour extraire navigateur, OS, type d'appareil."""
    info = {
        'browser': None, 'browser_version': None,
        'os': None, 'os_version': None,
        'device_type': 'desktop',
    }
    if not ua_string:
        return info

    # Détection du navigateur
    browsers = [
        (r'Chrome/(\d+[\.\d]*)', 'Chrome'),
        (r'Firefox/(\d+[\.\d]*)', 'Firefox'),
        (r'Safari/(\d+[\.\d]*)', 'Safari'),
        (r'Edg/(\d+[\.\d]*)', 'Edge'),
        (r'OPR/(\d+[\.\d]*)', 'Opera'),
    ]
    for pattern, name in browsers:
        match = re.search(pattern, ua_string)
        if match:
            info['browser'] = name
            info['browser_version'] = match.group(1)
            break

    # Détection OS
    os_patterns = [
        (r'Windows NT (\d+[\.\d]*)', 'Windows'),
        (r'Mac OS X (\d+[_\.\d]*)', 'macOS'),
        (r'Linux', 'Linux'),
        (r'Android (\d+[\.\d]*)', 'Android'),
        (r'iPhone OS (\d+[_\.\d]*)', 'iOS'),
        (r'iPad.*OS (\d+[_\.\d]*)', 'iPadOS'),
    ]
    for pattern, name in os_patterns:
        match = re.search(pattern, ua_string)
        if match:
            info['os'] = name
            info['os_version'] = match.group(1).replace('_', '.') if match.lastindex else None
            break

    # Type d'appareil
    if re.search(r'Mobile|Android|iPhone', ua_string, re.I):
        info['device_type'] = 'mobile'
    elif re.search(r'iPad|Tablet', ua_string, re.I):
        info['device_type'] = 'tablet'

    return info


def get_request_context():
    """Récupère toutes les informations contextuelles de la requête HTTP."""
    ctx = {
        'ip_public': None,
        'ip_local': None,
        'ip_version': None,
        'user_agent': None,
        'geo_data': {},
    }
    try:
        if request:
            forwarded = request.headers.get('X-Forwarded-For', '')
            if forwarded:
                ips = [ip.strip() for ip in forwarded.split(',')]
                ctx['ip_public'] = ips[0]
                if len(ips) > 1:
                    ctx['ip_local'] = ips[-1]
            else:
                ctx['ip_public'] = request.remote_addr

            # Déterminer IPv4 vs IPv6
            ip = ctx['ip_public'] or ''
            ctx['ip_version'] = 'IPv6' if ':' in ip else 'IPv4'

            ctx['user_agent'] = request.headers.get('User-Agent', '')

            # Géolocalisation envoyée par le client (headers optionnels)
            ctx['geo_data'] = {
                'latitude': request.headers.get('X-Geo-Latitude'),
                'longitude': request.headers.get('X-Geo-Longitude'),
                'country': request.headers.get('X-Geo-Country'),
                'region': request.headers.get('X-Geo-Region'),
                'city': request.headers.get('X-Geo-City'),
                'postal_code': request.headers.get('X-Geo-PostalCode'),
                'timezone': request.headers.get('X-Geo-Timezone'),
                'accuracy': request.headers.get('X-Geo-Accuracy'),
            }
    except RuntimeError:
        pass
    return ctx


# ═══════════════════════════════════════════════════════
# AUDIT TRAIL - Journal des événements
# ═══════════════════════════════════════════════════════

def log_audit_event(proof_id, event_type, details=None):
    """Enregistre un événement dans l'audit trail."""
    ctx = get_request_context()
    event = SignatureAuditEvent(
        proof_id=proof_id,
        event_type=event_type,
        timestamp=datetime.utcnow(),
        ip_address=ctx['ip_public'],
        user_agent=ctx['user_agent'],
        details=details,
    )
    db.session.add(event)
    return event


# ═══════════════════════════════════════════════════════
# CRÉATION DE LA PREUVE
# ═══════════════════════════════════════════════════════

def create_signature_proof(
    document_id,
    signer,
    signer_type,
    document_name,
    file_path_before=None,
    file_bytes_before=None,
    file_path_after=None,
    file_bytes_after=None,
    cert_path=None,
    cert_type=None,
    cert_chain_paths=None,
    signature_method='jwt',
    signature_type=None,
    signature_reason=None,
    signature_location=None,
    signature_positions=None,
    consent_accepted=False,
    consent_text=None,
    consent_timestamp=None,
    otp_verified=False,
    otp_verified_at=None,
    pin_verified=False,
    company=None,
    flow_id=None,
    flow_priority=None,
    batch_id=None,
    device_fingerprint=None,
    signer_role='signer',
    platform_url=None,
    environment='production',
):
    """
    Crée une preuve de signature électronique de classe mondiale.
    Collecte automatiquement toutes les métadonnées disponibles.
    """
    now = datetime.utcnow()
    proof = SignatureProof()

    # Identifiants uniques
    proof.proof_id = hashlib.sha256(
        f"{uuid.uuid4().hex}{now.isoformat()}{document_id}".encode()
    ).hexdigest()
    proof.transaction_id = uuid.uuid4().hex

    # ──── 1. PLATEFORME ────
    proof.platform_name = 'DKB-Sign'
    proof.platform_provider = 'DKB Technologies'
    proof.platform_url = platform_url
    proof.api_version = 'v3'
    proof.signature_engine_version = 'PyHanko 0.25.x'
    proof.environment = environment

    # ──── 2. DOCUMENT ────
    proof.document_id = document_id
    proof.document_name = document_name
    proof.document_type = 'PDF'
    proof.document_size_bytes = get_file_size(file_path_after, file_bytes_after)
    proof.document_page_count = get_page_count(file_path_after, file_bytes_after)
    proof.document_version = '1.0'
    proof.document_hash_original = compute_file_hash_sha256(file_path_before, file_bytes_before)
    proof.document_hash_signed = compute_file_hash_sha256(file_path_after, file_bytes_after)
    proof.document_created_at = now
    proof.document_finalized_at = now
    proof.document_status = 'completed'
    proof.signed_file_path = file_path_after

    # ──── 3. SIGNATAIRE ────
    proof.signer_type = signer_type
    proof.signer_role = signer_role

    if isinstance(signer, User):
        proof.signer_id = signer.id
        proof.signer_name = signer.name
        proof.signer_first_name = signer.sub_name
        proof.signer_email = signer.email
        proof.signer_phone = getattr(signer, 'phone', None)
        proof.signer_organization = company.name if company else None
        proof.id_method_email = True
        proof.id_method_certificate = bool(cert_path)
        if signature_method == 'api_key':
            proof.id_method_email = True
        elif signature_method == 'jwt':
            proof.id_method_email = True
    elif isinstance(signer, Contact):
        proof.signer_id = signer.id
        proof.signer_name = signer.name
        proof.signer_first_name = None
        proof.signer_email = signer.email
        proof.signer_phone = getattr(signer, 'phone', None)
        proof.signer_organization = getattr(signer, 'company_name', None)
        proof.id_method_email = True
    else:
        # Dict pour les signataires externes
        proof.signer_id = 0
        proof.signer_name = str(signer.get('name', 'Inconnu'))
        proof.signer_first_name = str(signer.get('first_name', ''))
        proof.signer_email = str(signer.get('email', ''))
        proof.signer_phone = str(signer.get('phone', ''))
        proof.signer_organization = str(signer.get('organization', ''))

    proof.id_method_sms_otp = otp_verified
    proof.id_method_identity_verified = pin_verified
    proof.id_method_certificate = bool(cert_path)

    # ──── 4. INFORMATIONS DE SIGNATURE ────
    proof.signed_at = now
    proof.signature_type = signature_type or 'certificate'
    proof.signature_method = signature_method
    proof.consent_explicit = consent_accepted
    proof.timestamp_utc = now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    proof.timezone = 'UTC'
    proof.signature_positions = signature_positions

    # Extraire page/x/y depuis les positions
    if signature_positions and isinstance(signature_positions, list) and len(signature_positions) > 0:
        first_pos = signature_positions[0]
        if isinstance(first_pos, dict):
            proof.signature_page = first_pos.get('page')
            sigs = first_pos.get('signatures', [])
            if sigs and isinstance(sigs, list) and len(sigs) > 0:
                proof.signature_x = sigs[0].get('x')
                proof.signature_y = sigs[0].get('y')

    # Hash de la signature (hash du document signé)
    proof.signature_hash = proof.document_hash_signed

    # ──── 5. RÉSEAU (IP) ────
    req_ctx = get_request_context()
    proof.ip_public = req_ctx['ip_public']
    proof.ip_local = req_ctx['ip_local']
    proof.ip_version = req_ctx['ip_version']
    # ASN et ISP : renseignés par headers ou enrichissement ultérieur
    # proof.ip_asn / proof.ip_isp restent NULL sauf si headers présents

    # ──── 6. GÉOLOCALISATION ────
    geo = req_ctx.get('geo_data', {})
    if geo.get('latitude'):
        proof.geo_latitude = float(geo['latitude'])
    if geo.get('longitude'):
        proof.geo_longitude = float(geo['longitude'])
    proof.geo_country = geo.get('country')
    proof.geo_region = geo.get('region')
    proof.geo_city = geo.get('city')
    proof.geo_postal_code = geo.get('postal_code')
    proof.geo_timezone = geo.get('timezone')
    proof.geo_accuracy = geo.get('accuracy')

    # ──── 7. APPAREIL ────
    ua_string = req_ctx.get('user_agent', '')
    ua_info = parse_user_agent(ua_string)
    proof.device_user_agent = ua_string
    proof.device_browser = ua_info['browser']
    proof.device_browser_version = ua_info['browser_version']
    proof.device_os = ua_info['os']
    proof.device_os_version = ua_info['os_version']
    proof.device_type = ua_info['device_type']
    proof.device_fingerprint = device_fingerprint

    # ──── 8. CONSENTEMENT LÉGAL ────
    proof.consent_text = consent_text or (
        "Je consens à signer ce document électroniquement. "
        "Je reconnais que ma signature électronique a la même valeur juridique "
        "qu'une signature manuscrite conformément au Règlement eIDAS (UE) n°910/2014."
    )
    proof.consent_accepted = consent_accepted
    proof.consent_timestamp = consent_timestamp or now
    proof.consent_ip = req_ctx['ip_public']
    proof.otp_verified = otp_verified
    proof.otp_verified_at = otp_verified_at
    proof.pin_verified = pin_verified

    # ──── 10. CERTIFICATS CRYPTOGRAPHIQUES ────
    if cert_path:
        cert_info = extract_certificate_info(cert_path)
        proof.cert_signer_subject = cert_info.get('subject')
        proof.cert_signer_issuer = cert_info.get('issuer')
        proof.cert_signer_serial = cert_info.get('serial')
        proof.cert_signer_valid_from = cert_info.get('valid_from')
        proof.cert_signer_valid_to = cert_info.get('valid_to')
        proof.cert_signer_algorithm = cert_info.get('algorithm')
        proof.cert_signer_public_key = cert_info.get('public_key')
        proof.cert_signer_type = cert_type

        # Charger la chaîne de certificats
        if cert_chain_paths:
            chain_pem = []
            for chain_path in cert_chain_paths:
                if os.path.exists(chain_path):
                    with open(chain_path, 'r') as f:
                        chain_pem.append(f.read())
            proof.cert_chain = '\n'.join(chain_pem) if chain_pem else None

    # Certificat plateforme (racine DKB)
    dkb_root = 'certificates/DKBS/ACDKBSRacine2024.cacert.pem'
    if os.path.exists(dkb_root):
        root_info = extract_certificate_info(dkb_root)
        proof.cert_platform_subject = root_info.get('subject')

    # ──── 11. HASHES D'INTÉGRITÉ ────
    proof.hash_document = proof.document_hash_signed
    proof.hash_signature = proof.signature_hash

    # Entreprise
    if company:
        proof.company_name = company.name
        proof.company_id = company.id

    # Workflow
    proof.flow_id = flow_id
    proof.flow_priority = flow_priority
    proof.batch_id = batch_id

    # Horodatage
    proof.proof_generated_at = now

    # ──── 12. QR CODE ────
    base_url = platform_url or ''
    proof.qr_verification_url = f"{base_url}/v3/proofs/verify-public/{proof.proof_id}"
    proof.qr_transaction_id = proof.transaction_id
    proof.qr_document_hash = proof.document_hash_signed

    # Calculer le hash d'intégrité de la preuve
    proof.compute_proof_hash()

    # Sauvegarder en base
    db.session.add(proof)
    db.session.flush()  # Pour obtenir l'ID

    # ──── 9. AUDIT TRAIL ────
    log_audit_event(proof.id, 'document_created', {'document_name': document_name})
    log_audit_event(proof.id, 'signature_added', {
        'signer_email': proof.signer_email,
        'method': signature_method,
        'type': proof.signature_type,
    })
    log_audit_event(proof.id, 'document_completed', {
        'status': 'completed',
        'hash': proof.document_hash_signed,
    })

    # Calculer le hash de l'audit trail
    proof.compute_audit_trail_hash()

    # Recalculer le hash global avec l'audit trail
    proof.compute_proof_hash()

    db.session.commit()

    # Générer le PDF de preuve
    try:
        pdf_path = generate_proof_pdf(proof)
        proof.proof_pdf_path = pdf_path
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Erreur génération PDF de preuve: {e}")

    return proof


# ═══════════════════════════════════════════════════════
# GÉNÉRATION DU PDF DE PREUVE — 12 SECTIONS
# ═══════════════════════════════════════════════════════

def _build_styles():
    """Construit tous les styles ReportLab pour le PDF."""
    base = getSampleStyleSheet()
    s = {}
    s['title'] = ParagraphStyle('ProofTitle', parent=base['Heading1'],
        fontSize=18, textColor=HexColor('#1a1a2e'), alignment=TA_CENTER,
        spaceAfter=4*mm, fontName='Helvetica-Bold')
    s['subtitle'] = ParagraphStyle('ProofSub', parent=base['Normal'],
        fontSize=9, textColor=HexColor('#6c757d'), alignment=TA_CENTER, spaceAfter=6*mm)
    s['section'] = ParagraphStyle('Section', parent=base['Heading2'],
        fontSize=11, textColor=HexColor('#0d6efd'), spaceBefore=5*mm,
        spaceAfter=2*mm, fontName='Helvetica-Bold')
    s['label'] = ParagraphStyle('Label', parent=base['Normal'],
        fontSize=8, textColor=HexColor('#6c757d'))
    s['value'] = ParagraphStyle('Value', parent=base['Normal'],
        fontSize=8.5, textColor=HexColor('#212529'), fontName='Helvetica-Bold')
    s['hash'] = ParagraphStyle('Hash', parent=base['Normal'],
        fontSize=6.5, textColor=HexColor('#495057'), fontName='Courier', wordWrap='CJK')
    s['normal'] = ParagraphStyle('ProofNormal', parent=base['Normal'],
        fontSize=8, textColor=HexColor('#495057'))
    s['footer'] = ParagraphStyle('Footer', parent=base['Normal'],
        fontSize=6.5, textColor=HexColor('#adb5bd'), alignment=TA_CENTER)
    s['legal'] = ParagraphStyle('Legal', parent=base['Normal'],
        fontSize=6.5, textColor=HexColor('#6c757d'), alignment=TA_CENTER, leading=9)
    s['integrity'] = ParagraphStyle('Integrity', parent=base['Heading2'],
        fontSize=11, textColor=HexColor('#198754'), spaceBefore=4*mm,
        spaceAfter=2*mm, fontName='Helvetica-Bold')
    s['event'] = ParagraphStyle('Event', parent=base['Normal'],
        fontSize=7, textColor=HexColor('#495057'))
    return s


def _make_table(data, s, col1=42*mm, col2=128*mm, bg_label='#f8f9fa'):
    """Crée une table formatée label/valeur."""
    rows = [
        [Paragraph(str(r[0]), s['label']), Paragraph(str(r[1] if r[1] else "—"), s['value'])]
        for r in data
    ]
    t = Table(rows, colWidths=[col1, col2])
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.25, HexColor('#e9ecef')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor(bg_label)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _make_hash_table(data, s):
    """Table spéciale pour les hashes."""
    rows = [
        [Paragraph(str(r[0]), s['label']), Paragraph(str(r[1] if r[1] else "—"), s['hash'])]
        for r in data
    ]
    t = Table(rows, colWidths=[42*mm, 128*mm])
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.25, HexColor('#e9ecef')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#fff3cd')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _fmt_dt(dt):
    """Formate une datetime."""
    if dt:
        return dt.strftime('%d/%m/%Y %H:%M:%S UTC')
    return "—"


def _yn(val):
    return "OUI" if val else "NON"


def generate_proof_pdf(proof):
    """Génère un PDF de preuve de signature complet — 12 sections."""
    proof_filename = f"proof_{proof.proof_id[:16]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    proof_dir = PROOF_PDF_FOLDER / str(proof.document_id or 'general')
    proof_dir.mkdir(parents=True, exist_ok=True)
    proof_path = str(proof_dir / proof_filename)

    s = _build_styles()

    doc = SimpleDocTemplate(
        proof_path, pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )

    el = []  # elements

    # ═══ EN-TÊTE ═══
    el.append(Paragraph("PREUVE DE SIGNATURE ELECTRONIQUE", s['title']))
    el.append(Paragraph("ELECTRONIC SIGNATURE PROOF CERTIFICATE", s['subtitle']))
    el.append(Paragraph(f"Generee le {_fmt_dt(proof.proof_generated_at)}", s['subtitle']))

    # IDs principaux
    id_data = [
        ["ID Preuve", proof.proof_id],
        ["ID Transaction", proof.transaction_id],
    ]
    el.append(_make_hash_table(id_data, s))
    el.append(Spacer(1, 3*mm))

    # ═══ 1. PLATEFORME ═══
    el.append(Paragraph("1. INFORMATIONS PLATEFORME", s['section']))
    el.append(_make_table([
        ["Nom", proof.platform_name],
        ["Fournisseur", proof.platform_provider],
        ["URL", proof.platform_url or "—"],
        ["Version API", proof.api_version],
        ["Moteur de signature", proof.signature_engine_version],
        ["ID Transaction", proof.transaction_id],
        ["Environnement", proof.environment],
    ], s))

    # ═══ 2. DOCUMENT ═══
    el.append(Paragraph("2. INFORMATIONS DOCUMENT", s['section']))
    el.append(_make_table([
        ["Document ID", str(proof.document_id or "—")],
        ["Nom", proof.document_name],
        ["Type", proof.document_type],
        ["Taille", f"{proof.document_size_bytes:,} octets" if proof.document_size_bytes else "—"],
        ["Pages", str(proof.document_page_count or "—")],
        ["Version", proof.document_version or "—"],
        ["Date de creation", _fmt_dt(proof.document_created_at)],
        ["Date de finalisation", _fmt_dt(proof.document_finalized_at)],
        ["Statut", proof.document_status],
    ], s))
    el.append(Spacer(1, 1*mm))
    el.append(Paragraph("Empreintes cryptographiques (SHA-256)", s['normal']))
    el.append(_make_hash_table([
        ["Hash original", proof.document_hash_original],
        ["Hash signe", proof.document_hash_signed],
    ], s))

    # ═══ 3. SIGNATAIRE ═══
    el.append(Paragraph("3. INFORMATIONS SIGNATAIRE", s['section']))
    el.append(Paragraph("Identite", s['normal']))
    el.append(_make_table([
        ["ID Signataire", str(proof.signer_id)],
        ["Nom", proof.signer_name],
        ["Prenom", proof.signer_first_name or "—"],
        ["Email", proof.signer_email],
        ["Telephone", proof.signer_phone or "—"],
        ["Organisation", proof.signer_organization or "—"],
        ["Role", proof.signer_role or "—"],
    ], s))
    el.append(Spacer(1, 1*mm))
    el.append(Paragraph("Methodes d'identification", s['normal']))
    el.append(_make_table([
        ["Email verification", _yn(proof.id_method_email)],
        ["SMS OTP", _yn(proof.id_method_sms_otp)],
        ["Identite verifiee", _yn(proof.id_method_identity_verified)],
        ["Certificat numerique", _yn(proof.id_method_certificate)],
        ["OAuth / SSO", _yn(proof.id_method_oauth_sso)],
    ], s))

    # ═══ 4. SIGNATURE ═══
    el.append(Paragraph("4. INFORMATIONS DE SIGNATURE", s['section']))
    el.append(_make_table([
        ["Horodatage", _fmt_dt(proof.signed_at)],
        ["Type de signature", proof.signature_type or "—"],
        ["Methode", proof.signature_method],
        ["Consentement explicite", _yn(proof.consent_explicit)],
        ["Horodatage UTC", proof.timestamp_utc or "—"],
        ["Fuseau horaire", proof.timezone or "—"],
        ["Page", str(proof.signature_page) if proof.signature_page is not None else "—"],
        ["Coordonnees X/Y", f"X={proof.signature_x}, Y={proof.signature_y}" if proof.signature_x else "—"],
    ], s))
    el.append(Spacer(1, 1*mm))
    el.append(_make_hash_table([["Hash signature", proof.signature_hash]], s))

    # ═══ 5. RÉSEAU ═══
    el.append(Paragraph("5. ADRESSE IP (PREUVE RESEAU)", s['section']))
    el.append(_make_table([
        ["IP publique", proof.ip_public or "—"],
        ["IP locale", proof.ip_local or "—"],
        ["Version", proof.ip_version or "—"],
        ["ASN", proof.ip_asn or "—"],
        ["ISP", proof.ip_isp or "—"],
    ], s))

    # ═══ 6. GÉOLOCALISATION ═══
    el.append(Paragraph("6. GEOLOCALISATION", s['section']))
    el.append(_make_table([
        ["Latitude", str(proof.geo_latitude) if proof.geo_latitude else "—"],
        ["Longitude", str(proof.geo_longitude) if proof.geo_longitude else "—"],
        ["Pays", proof.geo_country or "—"],
        ["Region", proof.geo_region or "—"],
        ["Ville", proof.geo_city or "—"],
        ["Code postal", proof.geo_postal_code or "—"],
        ["Fuseau horaire", proof.geo_timezone or "—"],
        ["Precision", proof.geo_accuracy or "—"],
    ], s))

    # ═══ PAGE BREAK ═══
    el.append(PageBreak())

    # ═══ 7. APPAREIL ═══
    el.append(Paragraph("7. INFORMATIONS APPAREIL", s['section']))
    el.append(_make_table([
        ["User-Agent", (proof.device_user_agent or "—")[:100]],
        ["Navigateur", proof.device_browser or "—"],
        ["Version navigateur", proof.device_browser_version or "—"],
        ["Systeme d'exploitation", proof.device_os or "—"],
        ["Version OS", proof.device_os_version or "—"],
        ["Type d'appareil", proof.device_type or "—"],
        ["Empreinte appareil", (proof.device_fingerprint or "—")[:50]],
    ], s))

    # ═══ 8. CONSENTEMENT ═══
    el.append(Paragraph("8. CONSENTEMENT LEGAL", s['section']))
    el.append(_make_table([
        ["Texte de consentement", (proof.consent_text or "—")[:120]],
        ["Accepte", _yn(proof.consent_accepted)],
        ["Horodatage", _fmt_dt(proof.consent_timestamp)],
        ["IP au moment du consentement", proof.consent_ip or "—"],
        ["OTP verifie", _yn(proof.otp_verified)],
        ["PIN verifie", _yn(proof.pin_verified)],
    ], s))

    # ═══ 9. AUDIT TRAIL ═══
    el.append(Paragraph("9. JOURNAL DES EVENEMENTS (AUDIT TRAIL)", s['section']))
    events = proof.audit_events or []
    if events:
        event_rows = [["Evenement", "Horodatage", "IP", "Details"]]
        for ev in events:
            details_str = json.dumps(ev.details, ensure_ascii=False)[:60] if ev.details else "—"
            event_rows.append([
                ev.event_type,
                _fmt_dt(ev.timestamp),
                ev.ip_address or "—",
                details_str,
            ])
        event_table = Table(
            [[Paragraph(str(c), s['label'] if i == 0 else s['event']) for c in row]
             for i, row in enumerate(event_rows)],
            colWidths=[35*mm, 40*mm, 30*mm, 65*mm],
        )
        event_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.25, HexColor('#e9ecef')),
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#e2e3e5')),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#ffffff')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        el.append(event_table)
    else:
        el.append(Paragraph("Aucun evenement enregistre.", s['normal']))

    # ═══ 10. CERTIFICATS ═══
    el.append(Paragraph("10. CERTIFICATS CRYPTOGRAPHIQUES", s['section']))
    el.append(Paragraph("Certificat du signataire", s['normal']))
    el.append(_make_table([
        ["Sujet", (proof.cert_signer_subject or "—")[:80]],
        ["Emetteur", (proof.cert_signer_issuer or "—")[:80]],
        ["Numero de serie", (proof.cert_signer_serial or "—")[:50]],
        ["Algorithme", proof.cert_signer_algorithm or "—"],
        ["Type", proof.cert_signer_type or "—"],
        ["Valide du", _fmt_dt(proof.cert_signer_valid_from)],
        ["Valide jusqu'au", _fmt_dt(proof.cert_signer_valid_to)],
    ], s))
    el.append(Spacer(1, 1*mm))
    el.append(_make_table([
        ["Certificat plateforme", (proof.cert_platform_subject or "—")[:80]],
        ["Chaine presente", _yn(bool(proof.cert_chain))],
    ], s))

    # ═══ 11. INTÉGRITÉ ═══
    el.append(Paragraph("11. VERIFICATION D'INTEGRITE", s['integrity']))
    el.append(Paragraph(
        "Les hashes ci-dessous garantissent l'integrite de chaque composant. "
        "Toute alteration rend les hashes invalides.",
        s['normal']
    ))
    el.append(Spacer(1, 1*mm))
    integrity_data = [
        ["Hash document (SHA-256)", proof.hash_document],
        ["Hash signature (SHA-256)", proof.hash_signature],
        ["Hash audit trail (SHA-256)", proof.hash_audit_trail],
        ["Hash preuve (SHA-512)", proof.hash_proof],
    ]
    rows = [
        [Paragraph(str(r[0]), s['label']), Paragraph(str(r[1] if r[1] else "—"), s['hash'])]
        for r in integrity_data
    ]
    it = Table(rows, colWidths=[48*mm, 122*mm])
    it.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#198754')),
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#d1e7dd')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    el.append(it)

    # ═══ 12. QR CODE ═══
    el.append(Paragraph("12. QR CODE DE VERIFICATION", s['section']))
    el.append(_make_table([
        ["URL de verification", proof.qr_verification_url or "—"],
        ["ID Transaction", proof.qr_transaction_id or "—"],
        ["Hash document", proof.qr_document_hash or "—"],
    ], s))

    # Générer un QR code image dans le PDF
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(proof.qr_verification_url or proof.proof_id)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        from reportlab.platypus import Image as RLImage
        el.append(Spacer(1, 2*mm))
        el.append(RLImage(qr_buffer, width=30*mm, height=30*mm))
    except Exception:
        pass

    # ═══ MENTION LÉGALE ═══
    el.append(Spacer(1, 8*mm))
    el.append(Paragraph(
        "Ce document constitue une preuve de signature electronique au sens du Reglement eIDAS (UE) n 910/2014, "
        "de l'ESIGN Act (USA), et des legislations nationales applicables. L'integrite de chaque composant "
        "(document, signature, audit trail, preuve) peut etre verifiee independamment via les hashes SHA-256/SHA-512 "
        "ci-dessus. Ce document a ete genere automatiquement par DKB-Sign et ne necessite pas de signature manuscrite.",
        s['legal']
    ))
    el.append(Spacer(1, 3*mm))
    el.append(Paragraph(
        f"DKB-Sign | Preuve de signature | {proof.proof_id} | Transaction {proof.transaction_id}",
        s['footer']
    ))

    doc.build(el)
    return proof_path


# ═══════════════════════════════════════════════════════
# REQUÊTES
# ═══════════════════════════════════════════════════════

def get_proof_by_id(proof_id):
    """Récupère une preuve par son identifiant."""
    return SignatureProof.query.filter_by(proof_id=proof_id).first()


def get_proofs_by_document(document_id):
    """Récupère toutes les preuves pour un document."""
    return SignatureProof.query.filter_by(document_id=document_id).order_by(
        SignatureProof.signed_at.asc()
    ).all()


def get_proofs_by_signer(signer_id, signer_type='user'):
    """Récupère toutes les preuves pour un signataire."""
    return SignatureProof.query.filter_by(
        signer_id=signer_id,
        signer_type=signer_type
    ).order_by(SignatureProof.signed_at.desc()).all()


def verify_proof_integrity(proof_id):
    """Vérifie l'intégrité d'une preuve."""
    proof = get_proof_by_id(proof_id)
    if not proof:
        return None, "Preuve introuvable."
    is_valid = proof.verify_integrity()
    return is_valid, "Preuve integre." if is_valid else "ALERTE: La preuve a ete alteree!"


def build_proof_urls(proof, api_prefix=''):
    """
    Construit les URLs complètes pour une preuve de signature.
    Retourne une URL directe vers le fichier PDF de preuve.

    Args:
        proof: L'objet SignatureProof
        api_prefix: '' pour les routes internes, 'publicapi_' pour les routes publiques v3

    Returns:
        dict avec les URLs complètes
    """
    from flask import url_for, request
    
    # Construire l'URL directe vers le PDF de preuve
    # Format: /v3/documents/proofs/<document_id>/<filename>
    proof_pdf_url = None
    if proof.proof_pdf_path:
        # Extraire le chemin relatif depuis proof_pdf_path
        # Ex: documents/proofs/123/proof_abc123_20250420_121500.pdf
        path_parts = proof.proof_pdf_path.replace('\\', '/').split('/')
        if len(path_parts) >= 3:
            # Prendre document_id et filename
            doc_folder = path_parts[-2]  # ex: "123" ou "general"
            filename = path_parts[-1]     # ex: "proof_abc123_20250420_121500.pdf"
            proof_pdf_url = url_for('publicapi_proof_bp.download_proof_file',
                                    doc_folder=doc_folder, filename=filename, _external=True)
    
    # URL publique de vérification (accessible sans authentification)
    public_verify_url = url_for('publicapi_proof_bp.verify_proof_public',
                                proof_id=proof.proof_id, _external=True)

    return {
        "proof_id": proof.proof_id,
        "transaction_id": proof.transaction_id,
        "signer_name": f"{proof.signer_name} {proof.signer_first_name or ''}".strip(),
        "proof_pdf_url": proof_pdf_url,
        "verify_url": public_verify_url,
    }
