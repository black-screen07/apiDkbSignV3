from app import db
from datetime import datetime, timedelta
from sqlalchemy import Enum
import uuid
import secrets
import hashlib
from sqlalchemy.orm import validates


class CertTypeEnum:
    CACHET_SERVEUR = "cachetServeur"
    PERSONNE_PHYSIQUE = "personnePhysique"


class UrgencyEnum:
    NORMAL = "normal"
    URGENT = "urgent"
    TRES_URGENT = "tres_urgent"


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(255), nullable=False)
    country = db.Column(db.String(255), nullable=False)
    cert_path = db.Column(db.String(255), nullable=True)
    key_path = db.Column(db.String(255), nullable=True)
    cert_type = db.Column(
        Enum(CertTypeEnum.CACHET_SERVEUR, CertTypeEnum.PERSONNE_PHYSIQUE, name="cert_type_enum"),
        nullable=False
    )
    signature_volume = db.Column(db.Integer, default=0, nullable=True)
    signature_volume_used = db.Column(db.Integer, default=0)
    with_consent = db.Column(db.Boolean, nullable=False, default=True)
    archived = db.Column(db.Boolean, nullable=True, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    employees = db.relationship('User', backref='company', lazy=True)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uuid = db.Column(db.String(255), unique=True, nullable=True)  # Ajout du champ uuid
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    sub_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(255), nullable=False)
    country = db.Column(db.String(255), nullable=False)
    #language = db.Column(db.String(255), nullable=False) #langue du user
    cni_number = db.Column(db.String(255), nullable=True)
    account_type = db.Column(db.String(20), nullable=False)  # "individual" ou "employee"
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Null pour les individus
    cert_path = db.Column(db.String(255), nullable=True)  # Chemin du certificat .p12 ou .crt
    img_sign_path = db.Column(db.String(255), nullable=True)
    name_sign_path = db.Column(db.String(255), nullable=True)
    pad_sign_path = db.Column(db.String(255), nullable=True)
    current_img_sign = db.Column(db.String(10), nullable=True) # img, name, pad
    name_sign = db.Column(db.String(255), nullable=True)
    stamp_path = db.Column(db.String(255), nullable=True)
    signature_volume = db.Column(db.Integer, default=0, nullable=True)
    signature_volume_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sign_roles = db.Column(db.JSON, nullable=False, default=list)
    with_consent = db.Column(db.Boolean, nullable=True, default=True)
    archived = db.Column(db.Boolean, nullable=True, default=False)
    pin_code = db.Column(db.String(4))  # Code PIN pour la signature
    pin_created_at = db.Column(db.DateTime)  # Date de création du PIN
    
    # Champs pour l'authentification par API key (Public API)
    api_key = db.Column(db.String(64), unique=True, nullable=True)  # Clé API pour l'authentification
    api_key_created_at = db.Column(db.DateTime, nullable=True)  # Date de création de la clé API
    api_key_active = db.Column(db.Boolean, default=True, nullable=True)  # Statut de la clé API

    # Relation avec les certificats et les documents signés
    certificates = db.relationship('Certificate', backref='user', lazy=True)
    documents = db.relationship('Document', backref='user', lazy=True)

    def verify_pin(self, pin_code):
        """
        Vérifie si le code PIN fourni est valide.
        """
        if not self.pin_code:
            return False, "Aucun code PIN n'a été défini pour cet utilisateur."
            
        if not self.pin_created_at:
            return False, "La date de création du PIN est manquante."
            
        # Vérifier que le PIN a 4 chiffres
        if not pin_code or len(pin_code) != 4 or not pin_code.isdigit():
            return False, "Le code PIN doit être composé de 4 chiffres."
            
        if self.pin_code != pin_code:
            return False, "Code PIN invalide."
            
        return True, "Code PIN valide."
    
    def generate_api_key(self):
        """
        Génère une nouvelle clé API pour l'utilisateur.
        """
        self.api_key = secrets.token_urlsafe(48)  # Génère une clé de 64 caractères
        self.api_key_created_at = datetime.utcnow()
        self.api_key_active = True
        return self.api_key
    
    def deactivate_api_key(self):
        """
        Désactive la clé API actuelle de l'utilisateur.
        """
        self.api_key_active = False
    
    def is_api_key_valid(self):
        """
        Vérifie si la clé API de l'utilisateur est valide et active.
        """
        return self.api_key and self.api_key_active


class Certificate(db.Model):
    __tablename__ = 'certificates'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='pending')  # Statut : drafts, pending, signed, archived, refused, etc.
    batch_id = db.Column(db.String(36), nullable=True)
    batch_name = db.Column(db.String(255), nullable=True)  # nom du dossier
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    pdf_metadata = db.Column(db.JSON, nullable=True)  # Métadonnées du document
    is_workflow = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relation avec les signatures
    signatures = db.relationship('Signature', backref='document', lazy=True)


class Signature(db.Model):
    __tablename__ = 'signatures'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    signer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    signature_image = db.Column(db.String(255))  # Base64 ou chemin de l'image
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relation avec le signataire
    signer = db.relationship('User', backref='signatures')


class Draft(db.Model):
    __tablename__ = 'drafts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Optionnel : description ou note
    file_path = db.Column(db.String(255), nullable=True)  # Si un fichier est lié
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        nullable=False)  # Utilisateur ayant créé le brouillon
    status = db.Column(db.String(50), default="drafts")  # Par défaut "drafts"
    batch_id = db.Column(db.String(36), nullable=True)  # UUID pour regrouper les document dans un dossier
    batch_name = db.Column(db.String(255), nullable=True) #nom du dossier
    pdf_metadata = db.Column(db.JSON, nullable=True)  # Métadonnées du document
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='drafts')


class DocumentConsent(db.Model):
    __tablename__ = 'document_consents'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    batch_id = db.Column(db.String(36), nullable=True)  # UUID pour regrouper les consentements
    consented_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    terms_version = db.Column(db.String(50), nullable=True)  # Version des conditions acceptées, facultatif

    # OTP-related fields
    otp_code = db.Column(db.String(10), nullable=True)
    otp_sent_at = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verified_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='document_consents', lazy=True)
    document = db.relationship('Document', backref='consents', lazy=True)

    def __init__(self, user_id=None, document_id=None, terms_version=None, batch_id=None, email=None):
        self.user_id = user_id
        self.document_id = document_id
        self.email = email
        self.terms_version = terms_version
        self.batch_id = batch_id
        self.consented_at = datetime.utcnow()
        self.generate_otp()

    def generate_otp(self):
        """Génère un OTP et met à jour la date d'envoi."""
        # Exemple simple : un code 6 chiffres aléatoires. Vous pouvez rendre cela plus sophistiqué.
        self.otp_code = ''.join(secrets.choice("0123456789") for _ in range(6))
        self.otp_sent_at = datetime.utcnow()

    def verify_otp(self, code: str):
        """Vérifie le code OTP fourni par l'utilisateur."""
        # Vous pouvez ajouter plus de logique, par ex. vérifier si l'OTP a expiré.
        # Par exemple, si l'OTP est valide 10 minutes :
        # if self.otp_sent_at < datetime.utcnow() - timedelta(minutes=10):
        #     return False, "L'OTP a expiré."
        #
        # Vérifiez le code
        if code == self.otp_code:
            self.is_verified = True
            self.verified_at = datetime.utcnow()
            return True, "OTP validé avec succès."
        else:
            return False, "OTP invalide."


class Contact(db.Model):
    __tablename__ = 'contacts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Propriétaire du contact
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Lien avec la société
    name = db.Column(db.String(100), nullable=False)  # Nom du contact
    email = db.Column(db.String(100), nullable=False)  # Email, non unique globalement mais unique par contexte
    phone = db.Column(db.String(20), nullable=True)  # Numéro de téléphone
    address = db.Column(db.String(255), nullable=True)  # Adresse optionnelle
    company_name = db.Column(db.String(100), nullable=True)  # Nom de la société du contact, si applicable
    notes = db.Column(db.Text, nullable=True)  # Notes ou commentaires sur le contact
    account_type = db.Column(db.String(20), nullable=False, default='external')  # "individual", "employee" ou "external"
    user_account_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Lien vers le compte DKB-Sign associé
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Date de création
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Date de mise à jour

    # Relations avec l'utilisateur propriétaire et l'entreprise
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('owned_contacts', lazy=True))
    company = db.relationship('Company', backref=db.backref('contacts', lazy=True))
    # Relation avec le compte DKB-Sign associé
    associated_account = db.relationship('User', foreign_keys=[user_account_id], backref=db.backref('contact_links', lazy=True))


class Signer(db.Model):
    __tablename__ = 'signers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)  # Lien avec le document
    signer_id = db.Column(db.Integer, nullable=False)  # ID du signataire (utilisateur ou contact)
    account_type = db.Column(db.String(20), nullable=False)  # Type du signataire ('user' ou 'contact')
    status = db.Column(db.String(20), default="pending")  # Statut (pending, signed, declined, etc.)
    email_status = db.Column(db.String(20), default="pending")
    role = db.Column(db.String(50), nullable=True)  # Rôle du signataire (signataire principal, observateur, etc.)
    signed_at = db.Column(db.DateTime, nullable=True)  # Date de signature
    positions = db.Column(db.JSON, nullable=True)  # Ex: [{"page": 1, "x": 100, "y": 200, "width": 150, "height": 50}]
    qr_positions = db.Column(db.JSON, nullable=True)
    priority = db.Column(db.Integer, default=1)  # Ordre de priorité (1 = premier à signer)
    email_sent = db.Column(db.Boolean, default=False)  # Indique si une notification a été envoyée
    reminder_sent = db.Column(db.Boolean, default=False)  # Indique si un rappel a été envoyé
    notes = db.Column(db.Text, nullable=True)  # Notes spécifiques pour ce signataire
    otp_code = db.Column(db.String(10), nullable=True)
    otp_sent_at = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Date de création
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Date de mise à jour
    deadline = db.Column(db.DateTime, nullable=True)
    uuid = db.Column(db.String(255), unique=True, nullable=True)
    batch_uuid = db.Column(db.String(255), nullable=True)  # Nouveau champ
    urgency = db.Column(
        Enum(UrgencyEnum.NORMAL, UrgencyEnum.URGENT, UrgencyEnum.TRES_URGENT, name="urgency_enum"),
        nullable=False,
        default=UrgencyEnum.NORMAL
    )
    document = db.relationship('Document', backref=db.backref('signers', lazy=True))

    def generate_otp(self):
        """Génère un OTP et met à jour la date d'envoi."""
        # Exemple simple : un code 6 chiffres aléatoires. Vous pouvez rendre cela plus sophistiqué.
        self.otp_code = ''.join(secrets.choice("0123456789") for _ in range(6))
        self.otp_sent_at = datetime.utcnow()

    def verify_otp(self, code: str):
        """Vérifie le code OTP fourni par l'utilisateur."""
        # Vérifiez le code
        if code == self.otp_code:
            self.is_verified = True
            self.verified_at = datetime.utcnow()
            return True, "OTP validé avec succès."
        else:
            return False, "OTP invalide."


class Workflow(db.Model):
    __tablename__ = 'workflows'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)  # Nom unique du workflow
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Créateur du workflow
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Date de création
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Date de mise à jour

    # Relations
    user = db.relationship('User', backref=db.backref('workflows', lazy=True))


class WorkflowUser(db.Model):
    __tablename__ = 'workflow_users'

    VALID_ACTIONS = [
        "sign_doc",
        "add_paraph",
        "add_qrcode",
        "add_stamp",
        "add_date",
        "add_custom_text",
        "read_only",
        "upload_file",
    ]

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('workflows.id'), nullable=False)  # Relation avec Workflow
    user_id = db.Column(db.Integer, nullable=False)  # ID qui peut référencer soit un User soit un Contact
    priority = db.Column(db.Integer, nullable=False)  # Niveau de priorité
    actions = db.Column(db.JSON, nullable=True)  # Actions associées au workflow (format JSON)
    account_type = db.Column(db.String(20), nullable=False)  # Type de compte (employee, individual, external)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Date de création
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Date de mise à jour

    @validates('actions')
    def validate_actions(self, key, value):
        """
        Valide que toutes les actions dans le champ `actions` sont parmi les valeurs autorisées.
        """
        if not isinstance(value, list):
            raise ValueError("Le champ 'actions' doit être une liste.")

        for action in value:
            if action not in self.VALID_ACTIONS:
                raise ValueError(f"Action invalide : {action}. Actions autorisées : {', '.join(self.VALID_ACTIONS)}")

        return value

    @validates('account_type')
    def validate_account_type(self, key, value):
        """
        Valide que le type de compte est valide.
        """
        valid_types = ['employee', 'individual', 'external']
        if value not in valid_types:
            raise ValueError(f"Type de compte invalide : {value}. Types autorisés : {', '.join(valid_types)}")
        return value


class Flow(db.Model):
    __tablename__ = 'flows'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('workflows.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    reference = db.Column(db.String(255), nullable=True)
    deadline = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    action_done = db.Column(db.Boolean, default=False, nullable=False)  # Indique si toutes les actions du flow sont terminées
    current_priority = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default="pending")  # Statut (pending, signed, denied, etc.)

    # Relations
    document = db.relationship('Document', backref=db.backref('flows', lazy=True))
    workflow = db.relationship('Workflow', backref=db.backref('flows', lazy=True))


class LineFlow(db.Model):
    __tablename__ = 'line_flows'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    flow_id = db.Column(db.Integer, db.ForeignKey('flows.id'), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    account_type = db.Column(db.String(255), nullable=True)
    actions = db.Column(db.JSON, nullable=True)  # Actions en JSON
    sign_position = db.Column(db.JSON, nullable=True)  # Positions de signature en JSON
    action_done = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(20), default="pending")  # Statut (pending, signed, declined, etc.)
    denial_reason = db.Column(db.Text, nullable=True)  # Raison du refus
    denial_date = db.Column(db.DateTime, nullable=True)  # Date du refus
    read_aprob_otp = db.Column(db.String(10), nullable=True)  # Code OTP pour l'approbation de lecture
    verified_read_aprob = db.Column(db.Boolean, default=False, nullable=False)  # Statut de vérification de l'approbation de lecture

    def generate_read_aprob_otp(self):
        """
        Génère un code OTP pour l'approbation de lecture et met à jour la base de données.
        """
        self.read_aprob_otp = ''.join(secrets.choice('0123456789') for _ in range(6))
        db.session.commit()
        return self.read_aprob_otp

    def verify_read_aprob_otp(self, code: str) -> bool:
        """
        Vérifie le code OTP fourni pour l'approbation de lecture.
        
        Args:
            code (str): Le code OTP à vérifier
            
        Returns:
            bool: True si le code est valide, False sinon
        """
        if self.read_aprob_otp and code == self.read_aprob_otp:
            self.verified_read_aprob = True
            self.read_aprob_otp = None  # Réinitialise le code OTP après vérification
            db.session.commit()
            return True
        return False


class UserDevice(db.Model):
    __tablename__ = 'user_devices'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_agent = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(50), nullable=False)
    device_fingerprint = db.Column(db.String(500), nullable=False)  # Empreinte unique de l'appareil
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    is_blocked = db.Column(db.Boolean, default=False)
    block_token = db.Column(db.String(100), unique=True)
    approve_token = db.Column(db.String(100), unique=True)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'accepted', 'blocked'
    device_name = db.Column(db.String(100))  # Nom donné par l'utilisateur à son appareil

    # Index pour accélérer les recherches
    __table_args__ = (
        db.Index('idx_user_device_fingerprint', 'user_id', 'device_fingerprint'),
        db.Index('idx_user_device_status', 'user_id', 'status'),
    )


class SignatureProof(db.Model):
    """
    Preuve de signature électronique de classe mondiale.
    Conforme eIDAS, ESIGN Act, ZertES.
    Stocke l'intégralité des métadonnées cryptographiques, contextuelles,
    réseau, appareil, géolocalisation et audit trail.
    """
    __tablename__ = 'signature_proofs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proof_id = db.Column(db.String(64), unique=True, nullable=False)
    transaction_id = db.Column(db.String(64), unique=True, nullable=False)  # ID de transaction global

    # ──────────────────────────────────────────────
    # 1. INFORMATIONS PLATEFORME
    # ──────────────────────────────────────────────
    platform_name = db.Column(db.String(100), nullable=False, default='DKB-Sign')
    platform_provider = db.Column(db.String(100), nullable=False, default='DKB Technologies')
    platform_url = db.Column(db.String(255), nullable=True)
    api_version = db.Column(db.String(20), nullable=False, default='v3')
    signature_engine_version = db.Column(db.String(50), nullable=False, default='PyHanko 0.25.x')
    environment = db.Column(db.String(20), nullable=False, default='production')  # production / sandbox

    # ──────────────────────────────────────────────
    # 2. INFORMATIONS DOCUMENT
    # ──────────────────────────────────────────────
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    document_name = db.Column(db.String(255), nullable=False)
    document_type = db.Column(db.String(20), nullable=False, default='PDF')
    document_size_bytes = db.Column(db.BigInteger, nullable=True)
    document_page_count = db.Column(db.Integer, nullable=True)
    document_version = db.Column(db.String(50), nullable=True, default='1.0')
    document_hash_original = db.Column(db.String(64), nullable=True)     # SHA-256 du document original
    document_hash_signed = db.Column(db.String(64), nullable=True)       # SHA-256 du document signé
    document_created_at = db.Column(db.DateTime, nullable=True)
    document_finalized_at = db.Column(db.DateTime, nullable=True)
    document_status = db.Column(db.String(20), nullable=False, default='completed')  # completed / declined / expired
    signed_file_path = db.Column(db.String(500), nullable=True)

    # ──────────────────────────────────────────────
    # 3. INFORMATIONS SIGNATAIRE
    # ──────────────────────────────────────────────
    signer_id = db.Column(db.Integer, nullable=False)
    signer_type = db.Column(db.String(20), nullable=False)  # user / contact / external
    signer_name = db.Column(db.String(255), nullable=False)
    signer_first_name = db.Column(db.String(255), nullable=True)
    signer_email = db.Column(db.String(255), nullable=False)
    signer_phone = db.Column(db.String(255), nullable=True)
    signer_organization = db.Column(db.String(255), nullable=True)
    signer_role = db.Column(db.String(50), nullable=True, default='signer')  # signer / approver

    # Méthodes d'identification utilisées
    id_method_email = db.Column(db.Boolean, default=False)
    id_method_sms_otp = db.Column(db.Boolean, default=False)
    id_method_identity_verified = db.Column(db.Boolean, default=False)
    id_method_certificate = db.Column(db.Boolean, default=False)
    id_method_oauth_sso = db.Column(db.Boolean, default=False)

    # ──────────────────────────────────────────────
    # 4. INFORMATIONS DE SIGNATURE
    # ──────────────────────────────────────────────
    signed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    signature_type = db.Column(db.String(50), nullable=True)  # drawn / typed / click-to-sign / certificate
    signature_method = db.Column(db.String(50), nullable=False)  # api_key / jwt / otp / flow
    consent_explicit = db.Column(db.Boolean, default=False)
    timestamp_utc = db.Column(db.String(50), nullable=True)
    timezone = db.Column(db.String(50), nullable=True)
    signature_hash = db.Column(db.String(64), nullable=True)  # SHA-256 de la signature elle-même
    signature_page = db.Column(db.Integer, nullable=True)
    signature_x = db.Column(db.Float, nullable=True)
    signature_y = db.Column(db.Float, nullable=True)
    signature_positions = db.Column(db.JSON, nullable=True)  # Toutes les positions si multi-pages

    # ──────────────────────────────────────────────
    # 5. ADRESSE IP (PREUVE RÉSEAU)
    # ──────────────────────────────────────────────
    ip_public = db.Column(db.String(50), nullable=True)
    ip_local = db.Column(db.String(50), nullable=True)
    ip_version = db.Column(db.String(10), nullable=True)  # IPv4 / IPv6
    ip_asn = db.Column(db.String(100), nullable=True)      # Autonomous System Number
    ip_isp = db.Column(db.String(255), nullable=True)      # Fournisseur internet

    # ──────────────────────────────────────────────
    # 6. GÉOLOCALISATION
    # ──────────────────────────────────────────────
    geo_latitude = db.Column(db.Float, nullable=True)
    geo_longitude = db.Column(db.Float, nullable=True)
    geo_country = db.Column(db.String(100), nullable=True)
    geo_region = db.Column(db.String(100), nullable=True)
    geo_city = db.Column(db.String(100), nullable=True)
    geo_postal_code = db.Column(db.String(20), nullable=True)
    geo_timezone = db.Column(db.String(50), nullable=True)
    geo_accuracy = db.Column(db.String(50), nullable=True)

    # ──────────────────────────────────────────────
    # 7. INFORMATIONS APPAREIL
    # ──────────────────────────────────────────────
    device_user_agent = db.Column(db.String(500), nullable=True)
    device_browser = db.Column(db.String(100), nullable=True)
    device_browser_version = db.Column(db.String(50), nullable=True)
    device_os = db.Column(db.String(100), nullable=True)
    device_os_version = db.Column(db.String(50), nullable=True)
    device_type = db.Column(db.String(50), nullable=True)  # desktop / mobile / tablet
    device_fingerprint = db.Column(db.String(500), nullable=True)

    # ──────────────────────────────────────────────
    # 8. CONSENTEMENT LÉGAL
    # ──────────────────────────────────────────────
    consent_text = db.Column(db.Text, nullable=True)
    consent_accepted = db.Column(db.Boolean, default=False)
    consent_timestamp = db.Column(db.DateTime, nullable=True)
    consent_ip = db.Column(db.String(50), nullable=True)
    otp_verified = db.Column(db.Boolean, default=False)
    otp_verified_at = db.Column(db.DateTime, nullable=True)
    pin_verified = db.Column(db.Boolean, default=False)

    # ──────────────────────────────────────────────
    # 10. CERTIFICATS CRYPTOGRAPHIQUES
    # ──────────────────────────────────────────────
    cert_signer_subject = db.Column(db.String(500), nullable=True)
    cert_signer_issuer = db.Column(db.String(500), nullable=True)
    cert_signer_serial = db.Column(db.String(255), nullable=True)
    cert_signer_valid_from = db.Column(db.DateTime, nullable=True)
    cert_signer_valid_to = db.Column(db.DateTime, nullable=True)
    cert_signer_algorithm = db.Column(db.String(50), nullable=True)  # RSA / ECDSA
    cert_signer_public_key = db.Column(db.Text, nullable=True)
    cert_signer_type = db.Column(db.String(50), nullable=True)  # cachetServeur / personnePhysique
    cert_platform_subject = db.Column(db.String(500), nullable=True)
    cert_chain = db.Column(db.Text, nullable=True)  # Chaîne de certificats complète (PEM)

    # ──────────────────────────────────────────────
    # 11. VÉRIFICATION D'INTÉGRITÉ
    # ──────────────────────────────────────────────
    hash_document = db.Column(db.String(64), nullable=True)     # SHA-256
    hash_signature = db.Column(db.String(64), nullable=True)    # SHA-256
    hash_audit_trail = db.Column(db.String(64), nullable=True)  # SHA-256
    hash_proof = db.Column(db.String(128), nullable=False)      # SHA-512 de la preuve complète

    # ──────────────────────────────────────────────
    # 12. QR CODE DE VÉRIFICATION
    # ──────────────────────────────────────────────
    qr_verification_url = db.Column(db.String(500), nullable=True)
    qr_transaction_id = db.Column(db.String(64), nullable=True)
    qr_document_hash = db.Column(db.String(64), nullable=True)

    # ──────────────────────────────────────────────
    # MÉTADONNÉES DE LA PREUVE
    # ──────────────────────────────────────────────
    company_name = db.Column(db.String(255), nullable=True)
    company_id = db.Column(db.Integer, nullable=True)
    flow_id = db.Column(db.Integer, nullable=True)
    flow_priority = db.Column(db.Integer, nullable=True)
    batch_id = db.Column(db.String(36), nullable=True)
    proof_generated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    proof_pdf_path = db.Column(db.String(500), nullable=True)

    # Relations
    document = db.relationship('Document', backref=db.backref('signature_proofs', lazy=True))
    audit_events = db.relationship('SignatureAuditEvent', backref='proof', lazy=True,
                                   order_by='SignatureAuditEvent.timestamp')

    __table_args__ = (
        db.Index('idx_proof_document', 'document_id'),
        db.Index('idx_proof_signer', 'signer_id', 'signer_type'),
        db.Index('idx_proof_id', 'proof_id'),
        db.Index('idx_proof_transaction', 'transaction_id'),
    )

    def compute_proof_hash(self):
        """Calcule le hash SHA-512 de toutes les données critiques de la preuve."""
        data = (
            f"{self.proof_id}|{self.transaction_id}|"
            f"{self.document_id}|{self.document_name}|"
            f"{self.document_hash_original or ''}|{self.document_hash_signed or ''}|"
            f"{self.signer_id}|{self.signer_type}|{self.signer_name}|{self.signer_email}|"
            f"{self.cert_signer_serial or ''}|"
            f"{self.signed_at.isoformat() if self.signed_at else ''}|"
            f"{self.consent_accepted}|{self.otp_verified}|{self.pin_verified}|"
            f"{self.signature_method}|{self.signature_hash or ''}|"
            f"{self.ip_public or ''}|"
            f"{self.hash_audit_trail or ''}"
        )
        self.hash_proof = hashlib.sha512(data.encode('utf-8')).hexdigest()
        return self.hash_proof

    def compute_audit_trail_hash(self):
        """Calcule le hash SHA-256 de l'audit trail lié à cette preuve."""
        events = SignatureAuditEvent.query.filter_by(proof_id=self.id).order_by(
            SignatureAuditEvent.timestamp.asc()
        ).all()
        trail_data = '|'.join(
            f"{e.event_type}:{e.timestamp.isoformat()}:{e.ip_address or ''}"
            for e in events
        )
        self.hash_audit_trail = hashlib.sha256(trail_data.encode('utf-8')).hexdigest()
        return self.hash_audit_trail

    def verify_integrity(self):
        """Vérifie que la preuve n'a pas été altérée."""
        original_hash = self.hash_proof
        self.compute_proof_hash()
        is_valid = original_hash == self.hash_proof
        if not is_valid:
            self.hash_proof = original_hash
        return is_valid

    def to_dict(self):
        """Sérialise la preuve complète en dictionnaire."""
        return {
            "proof_id": self.proof_id,
            "transaction_id": self.transaction_id,
            # 1. Plateforme
            "platform": {
                "name": self.platform_name,
                "provider": self.platform_provider,
                "url": self.platform_url,
                "api_version": self.api_version,
                "signature_engine_version": self.signature_engine_version,
                "environment": self.environment,
            },
            # 2. Document
            "document": {
                "id": self.document_id,
                "name": self.document_name,
                "type": self.document_type,
                "size_bytes": self.document_size_bytes,
                "page_count": self.document_page_count,
                "version": self.document_version,
                "hash_original": self.document_hash_original,
                "hash_signed": self.document_hash_signed,
                "created_at": self.document_created_at.isoformat() if self.document_created_at else None,
                "finalized_at": self.document_finalized_at.isoformat() if self.document_finalized_at else None,
                "status": self.document_status,
            },
            # 3. Signataire
            "signer": {
                "id": self.signer_id,
                "type": self.signer_type,
                "name": self.signer_name,
                "first_name": self.signer_first_name,
                "email": self.signer_email,
                "phone": self.signer_phone,
                "organization": self.signer_organization,
                "role": self.signer_role,
                "identification_methods": {
                    "email_verification": self.id_method_email,
                    "sms_otp": self.id_method_sms_otp,
                    "identity_verified": self.id_method_identity_verified,
                    "digital_certificate": self.id_method_certificate,
                    "oauth_sso": self.id_method_oauth_sso,
                },
            },
            # 4. Signature
            "signature": {
                "timestamp": self.signed_at.isoformat() if self.signed_at else None,
                "type": self.signature_type,
                "method": self.signature_method,
                "consent_explicit": self.consent_explicit,
                "timestamp_utc": self.timestamp_utc,
                "timezone": self.timezone,
                "hash": self.signature_hash,
                "page": self.signature_page,
                "x": self.signature_x,
                "y": self.signature_y,
                "positions": self.signature_positions,
            },
            # 5. Réseau
            "network": {
                "ip_public": self.ip_public,
                "ip_local": self.ip_local,
                "ip_version": self.ip_version,
                "asn": self.ip_asn,
                "isp": self.ip_isp,
            },
            # 6. Géolocalisation
            "geolocation": {
                "latitude": self.geo_latitude,
                "longitude": self.geo_longitude,
                "country": self.geo_country,
                "region": self.geo_region,
                "city": self.geo_city,
                "postal_code": self.geo_postal_code,
                "timezone": self.geo_timezone,
                "accuracy": self.geo_accuracy,
            },
            # 7. Appareil
            "device": {
                "user_agent": self.device_user_agent,
                "browser": self.device_browser,
                "browser_version": self.device_browser_version,
                "os": self.device_os,
                "os_version": self.device_os_version,
                "type": self.device_type,
                "fingerprint": self.device_fingerprint,
            },
            # 8. Consentement
            "consent": {
                "text": self.consent_text,
                "accepted": self.consent_accepted,
                "timestamp": self.consent_timestamp.isoformat() if self.consent_timestamp else None,
                "ip": self.consent_ip,
                "otp_verified": self.otp_verified,
                "otp_verified_at": self.otp_verified_at.isoformat() if self.otp_verified_at else None,
                "pin_verified": self.pin_verified,
            },
            # 9. Audit Trail
            "audit_trail": [e.to_dict() for e in self.audit_events] if self.audit_events else [],
            # 10. Certificats
            "certificates": {
                "signer": {
                    "subject": self.cert_signer_subject,
                    "issuer": self.cert_signer_issuer,
                    "serial": self.cert_signer_serial,
                    "valid_from": self.cert_signer_valid_from.isoformat() if self.cert_signer_valid_from else None,
                    "valid_to": self.cert_signer_valid_to.isoformat() if self.cert_signer_valid_to else None,
                    "algorithm": self.cert_signer_algorithm,
                    "type": self.cert_signer_type,
                },
                "platform": {
                    "subject": self.cert_platform_subject,
                },
                "chain_present": bool(self.cert_chain),
            },
            # 11. Intégrité
            "integrity": {
                "hash_document": self.hash_document,
                "hash_signature": self.hash_signature,
                "hash_audit_trail": self.hash_audit_trail,
                "hash_proof": self.hash_proof,
                "is_valid": self.verify_integrity(),
            },
            # 12. QR Code
            "qr_verification": {
                "url": self.qr_verification_url,
                "transaction_id": self.qr_transaction_id,
                "document_hash": self.qr_document_hash,
            },
            # Métadonnées
            "company": {
                "name": self.company_name,
                "id": self.company_id,
            } if self.company_name else None,
            "workflow": {
                "flow_id": self.flow_id,
                "priority": self.flow_priority,
                "batch_id": self.batch_id,
            } if self.flow_id else None,
            "proof_generated_at": self.proof_generated_at.isoformat() if self.proof_generated_at else None,
        }


class SignatureAuditEvent(db.Model):
    """
    Journal complet des événements liés à une signature.
    Chaque action (création, envoi email, consultation, OTP, signature, etc.)
    est enregistrée avec horodatage, IP et détails.
    """
    __tablename__ = 'signature_audit_events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proof_id = db.Column(db.Integer, db.ForeignKey('signature_proofs.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    # Types: document_created, email_sent, email_opened, link_clicked,
    #        document_viewed, otp_sent, otp_verified, consent_given,
    #        signature_added, document_completed, document_declined
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    details = db.Column(db.JSON, nullable=True)  # Détails supplémentaires

    __table_args__ = (
        db.Index('idx_audit_proof', 'proof_id'),
        db.Index('idx_audit_type', 'event_type'),
        db.Index('idx_audit_timestamp', 'timestamp'),
    )

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": self.details,
        }