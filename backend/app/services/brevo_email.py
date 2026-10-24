"""Brevo (Sendinblue) transactional email for TrustVault password resets.

Uses httpx against POST https://api.brevo.com/v3/smtp/email.
Never logs API keys, raw tokens, or complete reset URLs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from urllib.parse import quote, urljoin

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

BREVO_SMTP_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"
_HTTP_TIMEOUT_SECONDS = 15.0


class EmailConfigurationError(Exception):
    """Raised when Brevo / frontend settings required for email are missing."""

    def __init__(self, message: str, *, missing: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.missing = missing or []


class EmailDeliveryError(Exception):
    """Raised when Brevo rejects the request or the network call fails."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class BrevoEmailConfig:
    api_key: str
    sender_email: str
    sender_name: str
    frontend_base_url: str


def _missing_brevo_fields(settings: Settings) -> list[str]:
    mapping = {
        "BREVO_API_KEY": settings.brevo_api_key,
        "BREVO_SENDER_EMAIL": settings.brevo_sender_email,
        "BREVO_SENDER_NAME": settings.brevo_sender_name,
        "FRONTEND_BASE_URL": settings.frontend_base_url,
    }
    missing: list[str] = []
    for name, value in mapping.items():
        if value is None or not str(value).strip():
            missing.append(name)
    return missing


def load_brevo_email_config(settings: Settings) -> BrevoEmailConfig:
    """Validate required env when the password-reset email feature is invoked."""
    missing = _missing_brevo_fields(settings)
    if missing:
        raise EmailConfigurationError(
            "Password reset email is not configured. Missing: " + ", ".join(missing),
            missing=missing,
        )

    frontend = settings.frontend_base_url.strip().rstrip("/")
    if not (
        frontend.startswith("https://") or frontend.startswith("http://")
    ):
        raise EmailConfigurationError(
            "FRONTEND_BASE_URL must be an absolute http(s) URL",
            missing=["FRONTEND_BASE_URL"],
        )

    sender_email = settings.brevo_sender_email.strip()
    if "@" not in sender_email:
        raise EmailConfigurationError(
            "BREVO_SENDER_EMAIL must be a valid email address",
            missing=["BREVO_SENDER_EMAIL"],
        )

    return BrevoEmailConfig(
        api_key=settings.brevo_api_key.strip(),
        sender_email=sender_email,
        sender_name=settings.brevo_sender_name.strip(),
        frontend_base_url=frontend,
    )


def build_password_reset_url(*, frontend_base_url: str, raw_token: str) -> str:
    """Build the frontend reset-password link. Token is only the ``token`` query param."""
    base = frontend_base_url.rstrip("/") + "/"
    # Existing frontend convention for the reset form route.
    path = "reset-password"
    return urljoin(base, path) + "?token=" + quote(raw_token, safe="")


def build_password_reset_email_content(
    *,
    recipient_name: str,
    reset_url: str,
    expire_minutes: int,
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body). ``reset_url`` must not be logged.

    Presentation uses the TrustVault product palette only (Warm Ivory card shell,
    Deep Lavender CTA). No remote logo is embedded: ``frontend/public/logo.png``
    is app-local and no verified absolute HTTPS logo URL is configured.
    """
    display_name = (recipient_name or "there").strip() or "there"
    safe_name = escape(display_name)
    safe_url = escape(reset_url, quote=True)
    subject = "Reset your TrustVault password"

    text_body = (
        f"Hello {display_name},\n\n"
        "We received a request to reset your TrustVault password.\n\n"
        f"This single-use link expires in {expire_minutes} minutes.\n\n"
        "Open this link to choose a new password:\n"
        f"{reset_url}\n\n"
        "If you did not request a password reset, you can ignore this email. "
        "Your password will stay the same.\n\n"
        "— The TrustVault team\n"
    )

    # Palette (inline only — email clients ignore external CSS):
    # Warm Ivory #FAF8F5 · White #FFFFFF · Deep Lavender #8B78A6 ·
    # Dark Plum hover/accent #6F5A88 · Deep Aubergine #30283B · Soft White #F8F5FA ·
    # Dark Plum heading #342B3D · Muted Grey #817986 · Pale Lavender #E8E0EF ·
    # Champagne Gold #C5A568 · Misty Lavender #F1ECF6
    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light" />
  <title>{escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#FAF8F5;font-family:Arial,Helvetica,sans-serif;color:#342B3D;-webkit-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#FAF8F5;padding:28px 14px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background-color:#FFFFFF;border-radius:14px;overflow:hidden;border:1px solid #E8E0EF;">
          <tr>
            <td style="background-color:#30283B;padding:22px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="vertical-align:middle;">
                    <p style="margin:0;font-size:20px;font-weight:700;line-height:1.25;color:#F8F5FA;letter-spacing:0.02em;">TrustVault</p>
                    <p style="margin:6px 0 0;font-size:13px;line-height:1.4;color:#F8F5FA;opacity:0.85;">Secure Documents. Trusted Access.</p>
                  </td>
                  <td align="right" style="vertical-align:middle;width:48px;">
                    <span style="display:inline-block;width:36px;height:3px;background-color:#C5A568;border-radius:2px;" aria-hidden="true"></span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 28px 8px;">
              <h1 style="margin:0 0 14px;font-size:22px;line-height:1.3;font-weight:700;color:#342B3D;">Reset your password</h1>
              <p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:#817986;">
                Hello {safe_name},
              </p>
              <p style="margin:0 0 18px;font-size:15px;line-height:1.6;color:#817986;">
                We received a request to reset your TrustVault password. Use the button below to choose a new one. The link can be used only once.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 22px;background-color:#F1ECF6;border:1px solid #E8E0EF;border-radius:10px;">
                <tr>
                  <td style="padding:14px 16px;">
                    <p style="margin:0;font-size:13px;line-height:1.55;color:#342B3D;">
                      <strong style="color:#6F5A88;">Link expiry:</strong>
                      <span style="color:#817986;"> This reset link expires in <strong style="color:#342B3D;">{expire_minutes} minutes</strong>.</span>
                    </p>
                  </td>
                </tr>
              </table>
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:0 auto 24px;">
                <tr>
                  <td align="center" bgcolor="#8B78A6" style="border-radius:10px;background-color:#8B78A6;">
                    <a href="{safe_url}" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:700;line-height:1.25;color:#FFFFFF;text-decoration:none;border-radius:10px;background-color:#8B78A6;">
                      Reset Password
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px;font-size:13px;line-height:1.55;color:#817986;">
                If the button does not work, copy and paste this link into your browser:
              </p>
              <p style="margin:0 0 20px;font-size:12px;line-height:1.55;word-break:break-all;">
                <a href="{safe_url}" style="color:#6F5A88;text-decoration:underline;">{safe_url}</a>
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 8px;">
                <tr>
                  <td style="border-top:1px solid #E8E0EF;font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table>
              <p style="margin:16px 0 0;font-size:13px;line-height:1.55;color:#817986;">
                If you did not request a password reset, you can ignore this email. Your password will remain unchanged.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background-color:#30283B;padding:18px 28px;">
              <p style="margin:0;font-size:12px;line-height:1.5;color:#F8F5FA;">
                This message was sent by TrustVault. Do not reply with passwords or secrets.
              </p>
              <p style="margin:8px 0 0;font-size:11px;line-height:1.45;color:#F8F5FA;opacity:0.75;">
                Secure document sharing with server-side access control.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return subject, text_body, html_body


def send_password_reset_email(
    settings: Settings,
    *,
    to_email: str,
    to_name: str,
    raw_token: str,
    client: httpx.Client | None = None,
) -> None:
    """Send a TrustVault password-reset email via Brevo.

    Raises ``EmailConfigurationError`` or ``EmailDeliveryError``. Never reports
    success when Brevo rejects the request. Does not log secrets or reset URLs.
    """
    config = load_brevo_email_config(settings)
    reset_url = build_password_reset_url(
        frontend_base_url=config.frontend_base_url,
        raw_token=raw_token,
    )
    subject, text_body, html_body = build_password_reset_email_content(
        recipient_name=to_name,
        reset_url=reset_url,
        expire_minutes=settings.password_reset_token_expire_minutes,
    )

    payload = {
        "sender": {
            "name": config.sender_name,
            "email": config.sender_email,
        },
        "to": [
            {
                "email": to_email.strip().lower(),
                "name": (to_name or "").strip() or to_email.strip(),
            }
        ],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    headers = {
        "api-key": config.api_key,
        "accept": "application/json",
        "content-type": "application/json",
    }

    owns_client = client is None
    http_client = client or httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS)
    try:
        response = http_client.post(
            BREVO_SMTP_EMAIL_URL,
            headers=headers,
            json=payload,
        )
    except httpx.TimeoutException as exc:
        logger.error(
            "Brevo password-reset email timed out",
            extra={"brevo_event": "timeout"},
        )
        raise EmailDeliveryError(
            "Unable to send password reset email",
            reason_code="BREVO_TIMEOUT",
        ) from exc
    except httpx.HTTPError as exc:
        logger.error(
            "Brevo password-reset email network error",
            extra={
                "brevo_event": "network_error",
                "error_type": type(exc).__name__,
            },
        )
        raise EmailDeliveryError(
            "Unable to send password reset email",
            reason_code="BREVO_NETWORK_ERROR",
        ) from exc
    finally:
        if owns_client:
            http_client.close()

    if response.status_code >= 400:
        # Log only non-sensitive diagnostics — never API key, token, or URL.
        body_snippet = (response.text or "")[:200].replace("\n", " ")
        logger.error(
            "Brevo rejected password-reset email",
            extra={
                "brevo_event": "rejected",
                "http_status": response.status_code,
                "response_snippet_len": len(response.text or ""),
                "response_snippet": body_snippet,
            },
        )
        raise EmailDeliveryError(
            "Unable to send password reset email",
            reason_code="BREVO_REJECTED",
            status_code=response.status_code,
        )

    logger.info(
        "Brevo password-reset email accepted",
        extra={
            "brevo_event": "accepted",
            "http_status": response.status_code,
        },
    )
