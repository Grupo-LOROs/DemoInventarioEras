from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', sa.String(), server_default='user'),
        sa.Column('created_at', sa.DateTime(), nullable=True)
    )
    op.create_table('product_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True)
    )
    op.create_table('products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('id_code', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('unit_cost', sa.Float(), nullable=True),
        sa.Column('product_type_id', sa.Integer(), sa.ForeignKey('product_types.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_table('inventory_movements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('movement_type', sa.String(), nullable=False),
        sa.Column('movement_reason', sa.String(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_cost', sa.Float(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('moved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

def downgrade():
    op.drop_table('inventory_movements')
    op.drop_table('products')
    op.drop_table('product_types')
    op.drop_table('users')
