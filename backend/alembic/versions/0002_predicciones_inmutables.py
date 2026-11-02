"""Trigger en PostgreSQL que impide modificar el contenido de una predicción.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

FN = """
CREATE OR REPLACE FUNCTION predictions_immutable() RETURNS trigger AS $$
BEGIN
  IF NEW.probabilities::text IS DISTINCT FROM OLD.probabilities::text
     OR NEW.predicted_outcome IS DISTINCT FROM OLD.predicted_outcome
     OR NEW.confidence IS DISTINCT FROM OLD.confidence
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
     OR NEW.kickoff_at IS DISTINCT FROM OLD.kickoff_at
     OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
     OR NEW.market IS DISTINCT FROM OLD.market
     OR NEW.match_id IS DISTINCT FROM OLD.match_id
     OR NEW.is_backtest IS DISTINCT FROM OLD.is_backtest THEN
    RAISE EXCEPTION 'Las predicciones son inmutables (id=%)', OLD.id;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(FN)
    op.execute("CREATE TRIGGER trg_predictions_immutable BEFORE UPDATE ON predictions "
               "FOR EACH ROW EXECUTE FUNCTION predictions_immutable();")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_predictions_immutable ON predictions;")
    op.execute("DROP FUNCTION IF EXISTS predictions_immutable();")
