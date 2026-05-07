"""merge heads

Revision ID: 1b3d17642dc2
Revises: ('0003_advanced_risk_fields', '0002_persistence')
Create Date: 2026-04-01 13:04:06.770337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b3d17642dc2'
down_revision: Union[str, None] = ('0003_advanced_risk_fields', '0002_persistence')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
