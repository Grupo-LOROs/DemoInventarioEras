from alembic import op
import sqlalchemy as sa

revision = '0002_add_policy_discrepancy'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('products') as batch:
        batch.add_column(sa.Column('min_stock', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('max_stock', sa.Integer(), nullable=True))
    op.create_table('discrepancy_resolutions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('discrepancy_type', sa.String(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('stock_at', sa.Integer(), nullable=True),
        sa.Column('unit_cost_at', sa.Float(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
    )

def downgrade():
    op.drop_table('discrepancy_resolutions')
    with op.batch_alter_table('products') as batch:
        batch.drop_column('min_stock')
        batch.drop_column('max_stock')
