"""Send ops mail via Microsoft Graph (application / client-credentials).

Follows:
  https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow
  https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0

App-only tokens have no signed-in user, so /me/sendMail is invalid.
Send as GRAPH_SENDER with POST /users/{userPrincipalName}/sendMail.
Requires application permission Mail.Send + admin consent.
"""

from __future__ import annotations

import html
import logging
import threading
import time
from typing import Optional
from urllib.parse import quote

import requests

import config as app_config

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/users/{user}/sendMail"
_TOKEN_SKEW_SEC = 60

_token_lock = threading.Lock()
_cached_token: Optional[str] = None
_cached_token_expires_at = 0.0


def graph_send_configured() -> bool:
    """Can send mail as GRAPH_SENDER. Ops notify list is not required."""
    return bool(
        app_config.GRAPH_TENANT_ID
        and app_config.GRAPH_CLIENT_ID
        and app_config.GRAPH_CLIENT_SECRET
        and app_config.GRAPH_SENDER
    )


def graph_mail_configured() -> bool:
    return graph_send_configured() and bool(app_config.ACCESS_NOTIFY_TO)


def _access_token() -> str:
    """Client credentials token. Scope must be {resource}/.default (Entra docs)."""
    global _cached_token, _cached_token_expires_at
    now = time.time()
    with _token_lock:
        if _cached_token and now < _cached_token_expires_at:
            return _cached_token

        url = _TOKEN_URL.format(tenant=app_config.GRAPH_TENANT_ID)
        response = requests.post(
            url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_id": app_config.GRAPH_CLIENT_ID,
                "client_secret": app_config.GRAPH_CLIENT_SECRET,
                "grant_type": "client_credentials",
                "scope": _GRAPH_SCOPE,
            },
            timeout=20,
        )
        if not response.ok:
            logger.error(
                "[graph-mail] token failed status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()
        payload = response.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in") or 3600)
        _cached_token = token
        _cached_token_expires_at = now + max(30, expires_in - _TOKEN_SKEW_SEC)
        return token


def send_mail(*, subject: str, body: str, to: list[str], content_type: str = "HTML") -> None:
    """POST /users/{UPN}/sendMail. Success is HTTP 202 with an empty body."""
    if not to:
        raise ValueError("to is required")
    kind = "HTML" if content_type.upper() == "HTML" else "Text"
    token = _access_token()
    sender = app_config.GRAPH_SENDER
    url = _SEND_MAIL_URL.format(user=quote(sender, safe=""))
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": kind, "content": body},
            "toRecipients": [
                {"emailAddress": {"address": address}} for address in to
            ],
        },
        "saveToSentItems": True,
    }
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    if response.status_code != 202:
        logger.error(
            "[graph-mail] sendMail failed status=%s body=%s",
            response.status_code,
            response.text[:800],
        )
        response.raise_for_status()
        raise RuntimeError(f"Graph sendMail returned {response.status_code}")


def _esc(value: str | None) -> str:
    return html.escape((value or "").strip() or "—", quote=True)


def _access_request_html(
    *,
    company_name: str,
    contact_name: str,
    email: str,
    phone: str | None,
    message: str | None,
    review_url: str,
) -> str:
    """Outlook-safe table layout. Colors match Prabhat light UI."""
    rows = [
        ("Company", company_name),
        ("Name", contact_name),
        ("Phone", phone or "—"),
        ("Email", email),
    ]
    row_html = "".join(
        f"""
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #ececec;width:120px;font-size:12px;color:#737373;letter-spacing:0.06em;text-transform:uppercase;">{_esc(label)}</td>
          <td style="padding:10px 0;border-bottom:1px solid #ececec;font-size:14px;color:#0a0a0a;">{_esc(value)}</td>
        </tr>
        """
        for label, value in rows
    )
    note_html = ""
    if (message or "").strip():
        note_html = f"""
        <tr>
          <td style="padding:10px 0;width:120px;font-size:12px;color:#737373;letter-spacing:0.06em;text-transform:uppercase;vertical-align:top;">Note</td>
          <td style="padding:10px 0;font-size:14px;color:#0a0a0a;white-space:pre-wrap;">{_esc(message)}</td>
        </tr>
        """
    button_html = ""
    if review_url:
        button_html = f"""
        <tr>
          <td colspan="2" style="padding-top:24px;">
            <a href="{_esc(review_url)}" style="display:inline-block;background:#0a0a0a;color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;padding:10px 16px;border-radius:8px;">Review request</a>
          </td>
        </tr>
        """
    return f"""
    <div style="margin:0;padding:24px;background:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">
      <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e5e5;border-radius:8px;">
        <tr>
          <td style="padding:20px 24px 16px;border-bottom:1px solid #ececec;">
            <div style="font-size:13px;font-weight:700;letter-spacing:0.12em;color:#0a0a0a;">PRABHAT<span style="color:#7c3aed;">.</span></div>
            <div style="margin-top:10px;font-size:18px;font-weight:600;color:#0a0a0a;">Demo access request</div>
            <div style="margin-top:4px;font-size:13px;color:#737373;">A company asked for a Prabhat login. Grant from the admin panel.</div>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 24px 24px;">
            <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
              {row_html}
              {note_html}
              {button_html}
            </table>
          </td>
        </tr>
      </table>
    </div>
    """


def notify_access_request(
    *,
    company_name: str,
    contact_name: str,
    email: str,
    phone: str | None,
    message: str | None,
) -> None:
    """Best-effort ops ping. Never raises — callers must not fail the public form."""
    if not graph_mail_configured():
        logger.info("[graph-mail] skipped — GRAPH_* / ACCESS_NOTIFY_TO not fully set")
        return
    base = (app_config.FRONTEND_BASE_URL or "").rstrip("/")
    review_url = f"{base}/admin/requests" if base else ""
    try:
        send_mail(
            subject=f"Prabhat Demo access request — {company_name}",
            body=_access_request_html(
                company_name=company_name,
                contact_name=contact_name,
                email=email,
                phone=phone,
                message=message,
                review_url=review_url,
            ),
            to=list(app_config.ACCESS_NOTIFY_TO),
            content_type="HTML",
        )
        logger.info(
            "[graph-mail] access request mailed to=%s company=%s",
            ",".join(app_config.ACCESS_NOTIFY_TO),
            company_name,
        )
    except Exception:
        logger.exception("[graph-mail] failed to notify ops company=%s", company_name)


def _invite_html(
    *,
    contact_name: str,
    setup_url: str,
    hours: int,
) -> str:
    return f"""
    <div style="margin:0;padding:24px;background:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">
      <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e5e5;border-radius:8px;">
        <tr>
          <td style="padding:20px 24px 16px;border-bottom:1px solid #ececec;">
            <div style="font-size:13px;font-weight:700;letter-spacing:0.12em;color:#0a0a0a;">PRABHAT<span style="color:#7c3aed;">.</span></div>
            <div style="margin-top:10px;font-size:18px;font-weight:600;color:#0a0a0a;">Your access is ready</div>
            <div style="margin-top:4px;font-size:13px;color:#737373;">Hi {_esc(contact_name)}. Set a password to sign in. This link expires in {hours} hours and can be used once.</div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px;">
            <a href="{_esc(setup_url)}" style="display:inline-block;background:#0a0a0a;color:#ffffff;text-decoration:none;font-size:13px;font-weight:600;padding:10px 16px;border-radius:8px;">Set password</a>
            <p style="margin:20px 0 0;font-size:12px;line-height:1.5;color:#737373;">If you did not request Prabhat access, ignore this email. We never send your password by email.</p>
          </td>
        </tr>
      </table>
    </div>
    """


def notify_access_granted(
    *,
    contact_name: str,
    email: str,
    setup_url: str,
) -> bool:
    """Email the applicant a set-password link. Never includes a password. Returns sent?"""
    if not graph_send_configured():
        logger.info("[graph-mail] invite skipped — Graph sender not configured")
        return False
    try:
        send_mail(
            subject="Your Prabhat access is ready",
            body=_invite_html(
                contact_name=contact_name,
                setup_url=setup_url,
                hours=app_config.PASSWORD_SETUP_HOURS,
            ),
            to=[email],
            content_type="HTML",
        )
        logger.info("[graph-mail] invite mailed to applicant")
        return True
    except Exception:
        logger.exception("[graph-mail] failed to mail invite")
        return False
