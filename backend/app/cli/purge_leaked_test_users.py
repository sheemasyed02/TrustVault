"""Remove users left behind by a misconfigured test run (dev/demo DB only).

Pytest historically shared the application DATABASE_URL. Endpoint
``session.commit()`` calls could leak fixture users (``*@example.com``,
``* Security`` names) into the live users table. Test isolation is fixed;
this command cleans residual rows.

Never deletes ``@trustvault.demo`` seed accounts.

Usage (from backend directory):

  python -m app.cli.purge_leaked_test_users
  python -m app.cli.purge_leaked_test_users --dry-run
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
from sqlalchemy import delete, or_, select

from app.core.config import get_settings
from app.db.models import AuditEvent, Document, DocumentPermission, User
from app.db.session import get_session_factory, reset_engine


def _leaked_user_filter():
    return or_(
        User.email.ilike("%@example.com"),
        User.email.ilike("commit-persist@%"),
        User.email.ilike("commit-rollback@%"),
        User.name.like("% Security"),
        User.name.in_(
            (
                "Auth Test User",
                "Commit Persist",
                "Commit Rollback",
            )
        ),
    )


def purge_leaked_test_users(*, dry_run: bool) -> tuple[int, list[str]]:
    """Delete leaked test users and dependent rows. Returns (count, emails)."""
    session = get_session_factory()()
    try:
        users = list(session.scalars(select(User).where(_leaked_user_filter())).all())
        emails = [u.email for u in users]
        if not users:
            return 0, []
        if dry_run:
            return len(users), emails

        ids = [u.id for u in users]
        doc_ids = list(
            session.scalars(select(Document.id).where(Document.owner_id.in_(ids))).all()
        )
        if doc_ids:
            session.execute(
                delete(DocumentPermission).where(
                    DocumentPermission.document_id.in_(doc_ids)
                )
            )
        session.execute(
            delete(DocumentPermission).where(
                DocumentPermission.user_id.in_(ids)
                | DocumentPermission.granted_by.in_(ids)
            )
        )
        audit_clause = or_(
            AuditEvent.actor_id.in_(ids),
            AuditEvent.target_user_id.in_(ids),
        )
        if doc_ids:
            audit_clause = or_(audit_clause, AuditEvent.document_id.in_(doc_ids))
        session.execute(delete(AuditEvent).where(audit_clause))
        if doc_ids:
            session.execute(delete(Document).where(Document.id.in_(doc_ids)))
        session.execute(delete(User).where(User.id.in_(ids)))
        session.commit()
        return len(users), emails
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Purge leaked pytest users from the development database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching users without deleting.",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    get_settings.cache_clear()
    reset_engine()
    try:
        get_settings()
    except Exception as exc:
        print(f"Configuration error: {exc.__class__.__name__}")
        return 1

    try:
        count, emails = purge_leaked_test_users(dry_run=args.dry_run)
    except Exception:
        print("Purge failed unexpectedly")
        reset_engine()
        get_settings.cache_clear()
        return 1
    finally:
        reset_engine()
        get_settings.cache_clear()

    if count == 0:
        print("No leaked test users found.")
        return 0

    mode = "Would delete" if args.dry_run else "Deleted"
    print(f"{mode} {count} leaked test user(s):")
    for email in sorted(emails):
        print(f"  {email}")
    if args.dry_run:
        print("Re-run without --dry-run to apply.")
    else:
        print("Demo @trustvault.demo accounts were not touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
