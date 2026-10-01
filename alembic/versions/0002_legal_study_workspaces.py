"""Legal Study Workspace: workspaces table + documents.workspace_id

Idempotent on purpose, so it is safe whether the database was created by
`alembic upgrade head` or by database_setup.sql.
"""
from alembic import op

revision = '0002_legal_study_workspaces'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS workspaces (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(150) NOT NULL,
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspaces_owner_id ON workspaces(owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspaces_owner_updated ON workspaces(owner_id, updated_at)")
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_workspace_id ON documents(workspace_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_documents_workspace_id")
    op.execute("DELETE FROM documents WHERE workspace_id IS NOT NULL")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS workspace_id")
    op.execute("DROP TABLE IF EXISTS workspaces")
