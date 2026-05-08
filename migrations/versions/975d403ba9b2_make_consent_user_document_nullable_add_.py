"""make consent user/document nullable, add email

Revision ID: 975d403ba9b2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08 19:37:47.764315

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '975d403ba9b2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('document_consents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=255), nullable=True))
        batch_op.alter_column('user_id',
               existing_type=mysql.INTEGER(),
               nullable=True)
        batch_op.alter_column('document_id',
               existing_type=mysql.INTEGER(),
               nullable=True)
        batch_op.create_index(batch_op.f('ix_document_consents_email'), ['email'], unique=False)


def downgrade():
    with op.batch_alter_table('document_consents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_document_consents_email'))
        batch_op.alter_column('document_id',
               existing_type=mysql.INTEGER(),
               nullable=False)
        batch_op.alter_column('user_id',
               existing_type=mysql.INTEGER(),
               nullable=False)
        batch_op.drop_column('email')
