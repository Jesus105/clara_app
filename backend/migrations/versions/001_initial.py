"""Initial v1 schema. Future schema changes require a new migration."""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("leads", sa.Column("id", sa.String(36), primary_key=True), sa.Column("identity", sa.String(300), nullable=False, unique=True),
        sa.Column("company", sa.String(200), nullable=False), sa.Column("domain", sa.String(200), nullable=False),
        sa.Column("contact", sa.String(200), nullable=False), sa.Column("email", sa.String(300), nullable=False),
        sa.Column("country", sa.String(60), nullable=False), sa.Column("employees", sa.Integer), sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("owner", sa.String(100), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("score", sa.Integer, nullable=False),
        sa.Column("summary", sa.Text, nullable=False), sa.Column("angle", sa.Text, nullable=False), sa.Column("destination", sa.String(100), nullable=False),
        sa.Column("is_demo", sa.Boolean, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_score", "leads", ["score"])
    op.create_table("sources", sa.Column("id", sa.String(36), primary_key=True), sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False), sa.Column("title", sa.String(200), nullable=False), sa.Column("content", sa.Text, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("signals", sa.Column("id", sa.String(36), primary_key=True), sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False), sa.Column("type", sa.String(30), nullable=False), sa.Column("evidence", sa.Text, nullable=False), sa.Column("points", sa.Integer, nullable=False))
    op.create_table("drafts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False, unique=True),
        sa.Column("subject", sa.String(300), nullable=False), sa.Column("body", sa.Text, nullable=False), sa.Column("revision", sa.Integer, nullable=False), sa.Column("edited", sa.Boolean, nullable=False))
    op.create_table("jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("attempts", sa.Integer, nullable=False), sa.Column("error", sa.Text, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False), sa.Column("locked_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("trace", sa.JSON, nullable=False))
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table("audit_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id")),
        sa.Column("action", sa.String(50), nullable=False), sa.Column("actor", sa.String(100), nullable=False), sa.Column("detail", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_table("deliveries", sa.Column("id", sa.String(36), primary_key=True), sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("sequence", sa.String(100), nullable=False), sa.Column("snapshot", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("configuration", sa.Column("key", sa.String(50), primary_key=True), sa.Column("value", sa.JSON, nullable=False))
    for table in ["sources", "signals", "jobs"]:
        op.create_index("ix_" + table + "_lead_id", table, ["lead_id"])


def downgrade():
    for table in ["configuration", "deliveries", "audit_events", "jobs", "drafts", "signals", "sources", "leads"]:
        op.drop_table(table)

