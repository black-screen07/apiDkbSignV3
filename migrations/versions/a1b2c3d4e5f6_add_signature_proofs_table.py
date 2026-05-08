"""Ajout des tables signature_proofs et signature_audit_events

Revision ID: a1b2c3d4e5f6
Revises: 54d7852a3bfd
Create Date: 2026-04-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '54d7852a3bfd'
branch_labels = None
depends_on = None


def upgrade():
    # ═══ Table signature_proofs ═══
    op.create_table('signature_proofs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('proof_id', sa.String(length=64), nullable=False),
        sa.Column('transaction_id', sa.String(length=64), nullable=False),

        # 1. Plateforme
        sa.Column('platform_name', sa.String(length=100), nullable=False, server_default='DKB-Sign'),
        sa.Column('platform_provider', sa.String(length=100), nullable=False, server_default='DKB Technologies'),
        sa.Column('platform_url', sa.String(length=255), nullable=True),
        sa.Column('api_version', sa.String(length=20), nullable=False, server_default='v3'),
        sa.Column('signature_engine_version', sa.String(length=50), nullable=False, server_default='PyHanko 0.25.x'),
        sa.Column('environment', sa.String(length=20), nullable=False, server_default='production'),

        # 2. Document
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('document_name', sa.String(length=255), nullable=False),
        sa.Column('document_type', sa.String(length=20), nullable=False, server_default='PDF'),
        sa.Column('document_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('document_page_count', sa.Integer(), nullable=True),
        sa.Column('document_version', sa.String(length=50), nullable=True),
        sa.Column('document_hash_original', sa.String(length=64), nullable=True),
        sa.Column('document_hash_signed', sa.String(length=64), nullable=True),
        sa.Column('document_created_at', sa.DateTime(), nullable=True),
        sa.Column('document_finalized_at', sa.DateTime(), nullable=True),
        sa.Column('document_status', sa.String(length=20), nullable=False, server_default='completed'),
        sa.Column('signed_file_path', sa.String(length=500), nullable=True),

        # 3. Signataire
        sa.Column('signer_id', sa.Integer(), nullable=False),
        sa.Column('signer_type', sa.String(length=20), nullable=False),
        sa.Column('signer_name', sa.String(length=255), nullable=False),
        sa.Column('signer_first_name', sa.String(length=255), nullable=True),
        sa.Column('signer_email', sa.String(length=255), nullable=False),
        sa.Column('signer_phone', sa.String(length=255), nullable=True),
        sa.Column('signer_organization', sa.String(length=255), nullable=True),
        sa.Column('signer_role', sa.String(length=50), nullable=True),
        sa.Column('id_method_email', sa.Boolean(), default=False),
        sa.Column('id_method_sms_otp', sa.Boolean(), default=False),
        sa.Column('id_method_identity_verified', sa.Boolean(), default=False),
        sa.Column('id_method_certificate', sa.Boolean(), default=False),
        sa.Column('id_method_oauth_sso', sa.Boolean(), default=False),

        # 4. Signature
        sa.Column('signed_at', sa.DateTime(), nullable=False),
        sa.Column('signature_type', sa.String(length=50), nullable=True),
        sa.Column('signature_method', sa.String(length=50), nullable=False),
        sa.Column('consent_explicit', sa.Boolean(), default=False),
        sa.Column('timestamp_utc', sa.String(length=50), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=True),
        sa.Column('signature_hash', sa.String(length=64), nullable=True),
        sa.Column('signature_page', sa.Integer(), nullable=True),
        sa.Column('signature_x', sa.Float(), nullable=True),
        sa.Column('signature_y', sa.Float(), nullable=True),
        sa.Column('signature_positions', sa.JSON(), nullable=True),

        # 5. Réseau
        sa.Column('ip_public', sa.String(length=50), nullable=True),
        sa.Column('ip_local', sa.String(length=50), nullable=True),
        sa.Column('ip_version', sa.String(length=10), nullable=True),
        sa.Column('ip_asn', sa.String(length=100), nullable=True),
        sa.Column('ip_isp', sa.String(length=255), nullable=True),

        # 6. Géolocalisation
        sa.Column('geo_latitude', sa.Float(), nullable=True),
        sa.Column('geo_longitude', sa.Float(), nullable=True),
        sa.Column('geo_country', sa.String(length=100), nullable=True),
        sa.Column('geo_region', sa.String(length=100), nullable=True),
        sa.Column('geo_city', sa.String(length=100), nullable=True),
        sa.Column('geo_postal_code', sa.String(length=20), nullable=True),
        sa.Column('geo_timezone', sa.String(length=50), nullable=True),
        sa.Column('geo_accuracy', sa.String(length=50), nullable=True),

        # 7. Appareil
        sa.Column('device_user_agent', sa.String(length=500), nullable=True),
        sa.Column('device_browser', sa.String(length=100), nullable=True),
        sa.Column('device_browser_version', sa.String(length=50), nullable=True),
        sa.Column('device_os', sa.String(length=100), nullable=True),
        sa.Column('device_os_version', sa.String(length=50), nullable=True),
        sa.Column('device_type', sa.String(length=50), nullable=True),
        sa.Column('device_fingerprint', sa.String(length=500), nullable=True),

        # 8. Consentement
        sa.Column('consent_text', sa.Text(), nullable=True),
        sa.Column('consent_accepted', sa.Boolean(), default=False),
        sa.Column('consent_timestamp', sa.DateTime(), nullable=True),
        sa.Column('consent_ip', sa.String(length=50), nullable=True),
        sa.Column('otp_verified', sa.Boolean(), default=False),
        sa.Column('otp_verified_at', sa.DateTime(), nullable=True),
        sa.Column('pin_verified', sa.Boolean(), default=False),

        # 10. Certificats
        sa.Column('cert_signer_subject', sa.String(length=500), nullable=True),
        sa.Column('cert_signer_issuer', sa.String(length=500), nullable=True),
        sa.Column('cert_signer_serial', sa.String(length=255), nullable=True),
        sa.Column('cert_signer_valid_from', sa.DateTime(), nullable=True),
        sa.Column('cert_signer_valid_to', sa.DateTime(), nullable=True),
        sa.Column('cert_signer_algorithm', sa.String(length=50), nullable=True),
        sa.Column('cert_signer_public_key', sa.Text(), nullable=True),
        sa.Column('cert_signer_type', sa.String(length=50), nullable=True),
        sa.Column('cert_platform_subject', sa.String(length=500), nullable=True),
        sa.Column('cert_chain', sa.Text(), nullable=True),

        # 11. Intégrité
        sa.Column('hash_document', sa.String(length=64), nullable=True),
        sa.Column('hash_signature', sa.String(length=64), nullable=True),
        sa.Column('hash_audit_trail', sa.String(length=64), nullable=True),
        sa.Column('hash_proof', sa.String(length=128), nullable=False),

        # 12. QR Code
        sa.Column('qr_verification_url', sa.String(length=500), nullable=True),
        sa.Column('qr_transaction_id', sa.String(length=64), nullable=True),
        sa.Column('qr_document_hash', sa.String(length=64), nullable=True),

        # Métadonnées
        sa.Column('company_name', sa.String(length=255), nullable=True),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('flow_id', sa.Integer(), nullable=True),
        sa.Column('flow_priority', sa.Integer(), nullable=True),
        sa.Column('batch_id', sa.String(length=36), nullable=True),
        sa.Column('proof_generated_at', sa.DateTime(), nullable=False),
        sa.Column('proof_pdf_path', sa.String(length=500), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.UniqueConstraint('proof_id'),
        sa.UniqueConstraint('transaction_id'),
    )

    op.create_index('idx_proof_document', 'signature_proofs', ['document_id'])
    op.create_index('idx_proof_signer', 'signature_proofs', ['signer_id', 'signer_type'])
    op.create_index('idx_proof_id', 'signature_proofs', ['proof_id'])
    op.create_index('idx_proof_transaction', 'signature_proofs', ['transaction_id'])

    # ═══ Table signature_audit_events ═══
    op.create_table('signature_audit_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('proof_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['proof_id'], ['signature_proofs.id']),
    )

    op.create_index('idx_audit_proof', 'signature_audit_events', ['proof_id'])
    op.create_index('idx_audit_type', 'signature_audit_events', ['event_type'])
    op.create_index('idx_audit_timestamp', 'signature_audit_events', ['timestamp'])


def downgrade():
    op.drop_index('idx_audit_timestamp', table_name='signature_audit_events')
    op.drop_index('idx_audit_type', table_name='signature_audit_events')
    op.drop_index('idx_audit_proof', table_name='signature_audit_events')
    op.drop_table('signature_audit_events')

    op.drop_index('idx_proof_transaction', table_name='signature_proofs')
    op.drop_index('idx_proof_id', table_name='signature_proofs')
    op.drop_index('idx_proof_signer', table_name='signature_proofs')
    op.drop_index('idx_proof_document', table_name='signature_proofs')
    op.drop_table('signature_proofs')
