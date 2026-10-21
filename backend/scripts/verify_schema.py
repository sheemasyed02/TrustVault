"""Read-only schema verification. Does not print secrets."""

from pathlib import Path
import sys

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import get_engine, reset_engine

EXPECTED_TABLES = {
    "users",
    "documents",
    "document_permissions",
    "audit_events",
    "alembic_version",
}


def main() -> None:
    reset_engine()
    with get_engine().connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(:names)
                    """
                ),
                {"names": list(EXPECTED_TABLES)},
            )
        }
        index_exists = connection.execute(
            text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'uq_document_permissions_active_document_user'
                """
            )
        ).scalar()
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()

    print("tables:", sorted(tables))
    print("missing:", sorted(EXPECTED_TABLES - tables))
    print("partial_unique_index_present:", bool(index_exists))
    print("alembic_version:", version)


if __name__ == "__main__":
    main()
