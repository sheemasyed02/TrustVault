"""Controlled verification of password-reset flow against the live local API.

Never prints secrets, raw tokens, password hashes, or complete reset URLs.
Uses DEMO_* env passwords when present; creates a disposable VIEWER otherwise.

Optional real Brevo send:
  Set PASSWORD_RESET_VERIFY_INBOX to a mailbox you can check. A temporary
  active VIEWER is created for that address (or reused), forgot-password is
  called with the real Brevo client, and the script reports whether Brevo
  accepted the request. Inbox receipt must still be confirmed manually.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.database_url import redact_database_url
from app.core.security import hash_password, verify_password
from app.db.models import PasswordResetToken, User
from app.services.auth_service import normalize_email
from app.services.brevo_email import build_password_reset_url, load_brevo_email_config
from app.services.password_reset_rate_limit import reset_password_reset_rate_limiter
from app.services.password_reset_tokens import create_password_reset_token, hash_reset_token

API = os.getenv("PASSWORD_RESET_VERIFY_API", "http://127.0.0.1:8000").rstrip("/")
GENERIC_FORGOT = (
    "If an eligible account exists for that email, a password reset link will be sent."
)


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str]] = []

    def ok(self, name: str, detail: str = "") -> None:
        self.rows.append((name, "PASS" + (f" — {detail}" if detail else "")))
        print(f"[PASS] {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        self.rows.append((name, "FAIL — " + detail))
        print(f"[FAIL] {name} — {detail}")

    def skip(self, name: str, detail: str) -> None:
        self.rows.append((name, "SKIP — " + detail))
        print(f"[SKIP] {name} — {detail}")

    @property
    def failed(self) -> bool:
        return any(v.startswith("FAIL") for _, v in self.rows)


def _ensure_schema(engine) -> None:
    import time

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with engine.connect() as conn:
                ver = conn.execute(text("select version_num from alembic_version")).scalar()
                has = conn.execute(
                    text(
                        "select 1 from information_schema.tables "
                        "where table_schema='public' and table_name='password_reset_tokens'"
                    )
                ).scalar()
                if ver != "d4e5f6a7b8c9" or not has:
                    raise RuntimeError(
                        f"Schema not ready (alembic={ver!r}, "
                        f"password_reset_tokens={bool(has)}). "
                        "Run: alembic upgrade head"
                    )
                return
        except Exception as exc:  # noqa: BLE001 — retry transient Neon drops
            last_error = exc
            time.sleep(2 * attempt)
    assert last_error is not None
    raise last_error


def _get_or_create_viewer(session: Session, email: str, password: str) -> User:
    normalized = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None:
        user = User(
            name="Reset Verify Viewer",
            email=normalized,
            password_hash=hash_password(password),
            role="VIEWER",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    user.password_hash = hash_password(password)
    user.is_active = True
    if user.role == "ADMIN":
        # Never alter admin accounts in this verifier.
        raise RuntimeError("Refusing to overwrite an ADMIN account for verification")
    session.commit()
    session.refresh(user)
    return user


def main() -> int:
    report = Report()
    settings = get_settings()
    print("database:", redact_database_url(settings.database_url))
    print("api:", API)
    print(
        "brevo_configured:",
        bool((settings.brevo_api_key or "").strip())
        and bool((settings.brevo_sender_email or "").strip()),
    )
    print(
        "frontend_base_url_ok:",
        bool((settings.frontend_base_url or "").strip())
        and (settings.frontend_base_url or "").startswith(("http://", "https://")),
    )

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 60},
    )
    try:
        _ensure_schema(engine)
        report.ok("schema", "password_reset_tokens present at head")
    except Exception as exc:  # noqa: BLE001
        report.fail("schema", type(exc).__name__)
        return 1

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    reset_password_reset_rate_limiter()

    password_a = f"verify-old-{uuid.uuid4().hex[:10]}-xx"
    password_b = f"verify-new-{uuid.uuid4().hex[:10]}-yy"
    local_email = f"reset-verify-{uuid.uuid4().hex[:10]}@example.com"

    with SessionLocal() as session:
        user = _get_or_create_viewer(session, local_email, password_a)
        report.ok("fixture_user", f"role={user.role} active={user.is_active}")

    # Health
    try:
        with httpx.Client(timeout=30.0) as client:
            health = client.get(f"{API}/health")
        if health.status_code == 200:
            report.ok("api_health")
        else:
            report.fail("api_health", f"status={health.status_code}")
            return 1
    except Exception as exc:  # noqa: BLE001
        report.fail("api_health", f"unreachable ({type(exc).__name__})")
        return 1

    with httpx.Client(timeout=60.0) as client:
        # Malformed email
        bad = client.post(f"{API}/auth/forgot-password", json={"email": "not-an-email"})
        if bad.status_code == 422:
            report.ok("forgot_rejects_malformed_email")
        else:
            report.fail("forgot_rejects_malformed_email", f"status={bad.status_code}")

        # Unregistered — same public message; no token row for that email
        ghost = f"ghost-{uuid.uuid4().hex[:10]}@example.com"
        with SessionLocal() as session:
            before = session.execute(text("select count(*) from password_reset_tokens")).scalar()
        unk = client.post(f"{API}/auth/forgot-password", json={"email": ghost})
        with SessionLocal() as session:
            after = session.execute(text("select count(*) from password_reset_tokens")).scalar()
        if (
            unk.status_code == 200
            and unk.json().get("message") == GENERIC_FORGOT
            and after == before
        ):
            report.ok("forgot_unregistered_generic_no_token")
        else:
            report.fail(
                "forgot_unregistered_generic_no_token",
                f"status={unk.status_code} token_delta={after - before}",
            )

        # Registered path with mocked Brevo would need process patch; instead
        # issue token via service and exercise reset endpoints for local logic,
        # then optionally call real Brevo for PASSWORD_RESET_VERIFY_INBOX.
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == normalize_email(local_email)))
            assert user is not None
            issued = create_password_reset_token(session, user=user, settings=settings)
            session.commit()
            raw_token = issued.raw_token
            token_id = str(issued.record.id)
            token_hash = issued.record.token_hash

        if token_hash == hash_reset_token(raw_token) and raw_token not in token_hash:
            report.ok("token_stored_as_hash_only")
        else:
            report.fail("token_stored_as_hash_only", "hash mismatch")

        # URL shape without printing token
        try:
            cfg = load_brevo_email_config(settings)
            url = build_password_reset_url(
                frontend_base_url=cfg.frontend_base_url,
                raw_token=raw_token,
            )
            path_ok = "/reset-password?token=" in url
            host_ok = url.startswith(cfg.frontend_base_url.rstrip("/"))
            if path_ok and host_ok and raw_token not in url.split("?", 1)[0]:
                report.ok(
                    "reset_link_shape",
                    f"https={url.startswith('https://')} local_http={url.startswith('http://localhost') or url.startswith('http://127.0.0.1')}",
                )
            else:
                report.fail("reset_link_shape", "unexpected URL shape")
        except Exception as exc:  # noqa: BLE001
            report.fail("reset_link_shape", type(exc).__name__)

        # Wrong confirmation
        mismatch = client.post(
            f"{API}/auth/reset-password",
            json={
                "token": raw_token,
                "new_password": password_b,
                "confirm_password": password_b + "x",
            },
        )
        if mismatch.status_code == 422:
            report.ok("reset_rejects_password_mismatch")
        else:
            report.fail("reset_rejects_password_mismatch", f"status={mismatch.status_code}")

        # Short password (schema)
        short = client.post(
            f"{API}/auth/reset-password",
            json={
                "token": raw_token,
                "new_password": "short",
                "confirm_password": "short",
            },
        )
        if short.status_code == 422:
            report.ok("reset_rejects_short_password")
        else:
            report.fail("reset_rejects_short_password", f"status={short.status_code}")

        # Successful reset
        ok_reset = client.post(
            f"{API}/auth/reset-password",
            json={
                "token": raw_token,
                "new_password": password_b,
                "confirm_password": password_b,
            },
        )
        if ok_reset.status_code == 200:
            report.ok("reset_success")
        else:
            report.fail("reset_success", f"status={ok_reset.status_code}")

        # Replay
        replay = client.post(
            f"{API}/auth/reset-password",
            json={
                "token": raw_token,
                "new_password": password_b + "z",
                "confirm_password": password_b + "z",
            },
        )
        if replay.status_code == 400:
            report.ok("reset_rejects_consumed_token")
        else:
            report.fail("reset_rejects_consumed_token", f"status={replay.status_code}")

        with SessionLocal() as session:
            row = session.get(PasswordResetToken, uuid.UUID(token_id))
            user = session.scalar(select(User).where(User.email == normalize_email(local_email)))
            assert user is not None and row is not None
            if row.used_at is not None and verify_password(password_b, user.password_hash):
                report.ok("password_hash_updated_and_token_consumed")
            else:
                report.fail("password_hash_updated_and_token_consumed", "state mismatch")

        # Login new vs old
        login_new = client.post(
            f"{API}/auth/login",
            json={"email": local_email, "password": password_b},
        )
        login_old = client.post(
            f"{API}/auth/login",
            json={"email": local_email, "password": password_a},
        )
        if login_new.status_code == 200 and "access_token" in login_new.json():
            report.ok("login_with_new_password")
        else:
            report.fail("login_with_new_password", f"status={login_new.status_code}")
        if login_old.status_code == 401:
            report.ok("old_password_rejected")
        else:
            report.fail("old_password_rejected", f"status={login_old.status_code}")

        # Expired token
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == normalize_email(local_email)))
            assert user is not None
            issued2 = create_password_reset_token(session, user=user, settings=settings)
            issued2.record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            session.commit()
            expired_raw = issued2.raw_token
        expired = client.post(
            f"{API}/auth/reset-password",
            json={
                "token": expired_raw,
                "new_password": password_b,
                "confirm_password": password_b,
            },
        )
        if expired.status_code == 400:
            report.ok("reset_rejects_expired_token")
        else:
            report.fail("reset_rejects_expired_token", f"status={expired.status_code}")

        # Invalid token
        invalid = client.post(
            f"{API}/auth/reset-password",
            json={
                "token": "definitely-not-a-valid-reset-token",
                "new_password": password_b,
                "confirm_password": password_b,
            },
        )
        if invalid.status_code == 400:
            report.ok("reset_rejects_invalid_token")
        else:
            report.fail("reset_rejects_invalid_token", f"status={invalid.status_code}")

        # Admin policy: existing ADMIN accounts must not be mutated by this script.
        # Confirm admin can still login with DEMO_ADMIN_PASSWORD when set, and
        # forgot-password remains available (no exclusion implemented).
        admin_pw = (os.getenv("DEMO_ADMIN_PASSWORD") or "").strip()
        with SessionLocal() as session:
            admin = session.scalar(select(User).where(User.role == "ADMIN").limit(1))
        if admin is None:
            report.skip("admin_policy", "no ADMIN user in database")
        elif not admin_pw:
            report.skip("admin_policy", "DEMO_ADMIN_PASSWORD unset; not probing admin login")
        else:
            admin_login = client.post(
                f"{API}/auth/login",
                json={"email": admin.email, "password": admin_pw},
            )
            if admin_login.status_code == 200:
                report.ok("admin_login_unchanged")
            else:
                report.fail("admin_login_unchanged", f"status={admin_login.status_code}")

        # Real Brevo acceptance (optional inbox)
        inbox = (os.getenv("PASSWORD_RESET_VERIFY_INBOX") or "").strip()
        if not inbox:
            report.skip(
                "brevo_real_send",
                "Set PASSWORD_RESET_VERIFY_INBOX to a mailbox you can open to verify delivery",
            )
        else:
            inbox_password = f"inbox-verify-{uuid.uuid4().hex[:10]}-zz"
            with SessionLocal() as session:
                inbox_user = _get_or_create_viewer(session, inbox, inbox_password)
            # Clear rate limit so the real call is not blocked by earlier probes.
            reset_password_reset_rate_limiter()
            before_tokens = 0
            with SessionLocal() as session:
                before_tokens = session.execute(
                    text(
                        "select count(*) from password_reset_tokens where user_id = :uid"
                    ),
                    {"uid": str(inbox_user.id)},
                ).scalar()
            sent = client.post(f"{API}/auth/forgot-password", json={"email": inbox})
            with SessionLocal() as session:
                after_tokens = session.execute(
                    text(
                        "select count(*) from password_reset_tokens where user_id = :uid"
                    ),
                    {"uid": str(inbox_user.id)},
                ).scalar()
            if sent.status_code == 200 and after_tokens == before_tokens + 1:
                report.ok(
                    "brevo_real_send_accepted",
                    "API 200 and token persisted; confirm inbox manually (spam too)",
                )
            elif sent.status_code == 503:
                report.fail(
                    "brevo_real_send_accepted",
                    "API returned 503 (provider/config failure; account existence not leaked)",
                )
            else:
                report.fail(
                    "brevo_real_send_accepted",
                    f"status={sent.status_code} token_delta={after_tokens - before_tokens}",
                )

            # Unregistered still generic while Brevo is live
            ghost2 = f"ghost2-{uuid.uuid4().hex[:8]}@example.com"
            g = client.post(f"{API}/auth/forgot-password", json={"email": ghost2})
            if g.status_code == 200 and g.json().get("message") == GENERIC_FORGOT:
                report.ok("forgot_unregistered_with_live_brevo_still_generic")
            else:
                report.fail(
                    "forgot_unregistered_with_live_brevo_still_generic",
                    f"status={g.status_code}",
                )

    # Cleanup disposable example.com user (keep inbox user if created)
    with SessionLocal() as session:
        disposable = session.scalar(
            select(User).where(User.email == normalize_email(local_email))
        )
        if disposable is not None and disposable.role != "ADMIN":
            session.execute(
                text("delete from password_reset_tokens where user_id = :uid"),
                {"uid": str(disposable.id)},
            )
            session.delete(disposable)
            session.commit()
            report.ok("cleanup_disposable_user")

    print("---")
    print(f"total={len(report.rows)} failed={sum(1 for _, v in report.rows if v.startswith('FAIL'))}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
