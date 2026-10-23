"""Initial investigation, record and append-only event storage."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('investigations',sa.Column('id',sa.String(),primary_key=True),sa.Column('status',sa.String(),nullable=False),sa.Column('payload',sa.Text(),nullable=False))
    op.create_table('records',sa.Column('id',sa.String(),primary_key=True),sa.Column('investigation_id',sa.String(),sa.ForeignKey('investigations.id'),nullable=False),sa.Column('kind',sa.String(),nullable=False),sa.Column('payload',sa.Text(),nullable=False))
    op.create_index('ix_records_investigation_id','records',['investigation_id'])
    op.create_table('events',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),sa.Column('investigation_id',sa.String(),sa.ForeignKey('investigations.id'),nullable=False),sa.Column('payload',sa.Text(),nullable=False))
    op.create_index('ix_events_investigation_id','events',['investigation_id'])

def downgrade():
    op.drop_table('events'); op.drop_table('records'); op.drop_table('investigations')
