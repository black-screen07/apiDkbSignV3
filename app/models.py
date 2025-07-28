from app import db
from datetime import datetime, timedelta
from sqlalchemy import Enum
import uuid
import secrets
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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
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

    def __init__(self, user_id, document_id, terms_version=None, batch_id=None):
        self.user_id = user_id
        self.document_id = document_id
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

    # Contraintes d'unicité par utilisateur ou entreprise
    __table_args__ = (
        db.UniqueConstraint('email', 'user_id', name='unique_email_per_user'),
        db.UniqueConstraint('email', 'company_id', name='unique_email_per_company'),
    )

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