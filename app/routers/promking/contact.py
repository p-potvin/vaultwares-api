"""Public Contact & DMCA inquiry endpoint forwarding mail to admin@sexyprn.lol."""
from __future__ import annotations

import asyncio
from collections import deque
from email.message import EmailMessage
import logging
import os
import re
import shutil
import time
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ._models import Site

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["promking:contact"])

CONTACT_RECIPIENT = os.getenv("PROMKING_CONTACT_TO", "admin@sexyprn.lol")
CONTACT_SENDER_DOMAIN = os.getenv("PROMKING_CONTACT_SENDER_DOMAIN", "sexyprn.lol")
_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_HEADER_CR_LF = re.compile(r"[\r\n]+")

_RATE_WINDOW_SECONDS = 3600
_RATE_MAX_REQUESTS = 5
_ip_hits: dict[str, deque[float]] = {}


class ContactSubmission(BaseModel):
    site: Site = "sexyprn"
    form_type: Literal["contact", "dmca"] = "contact"
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200)
    subject: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=10, max_length=5000)
    infringing_url: Optional[str] = Field(default=None, max_length=1000)
    original_work: Optional[str] = Field(default=None, max_length=1000)
    signature: Optional[str] = Field(default=None, max_length=160)
    website: Optional[str] = Field(default=None, max_length=200)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    q = _ip_hits.setdefault(ip, deque())
    while q and now - q[0] > _RATE_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= _RATE_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Too many submissions from your IP. Please try again later.",
        )
    q.append(now)


def _clean_header(value: str) -> str:
    return _HEADER_CR_LF.sub(" ", value).strip()


async def _deliver_sendmail(msg: EmailMessage) -> bool:
    sendmail_bin = shutil.which("sendmail") or "/usr/sbin/sendmail"
    if not os.path.exists(sendmail_bin):
        return False
    proc = await asyncio.create_subprocess_exec(
        sendmail_bin,
        "-t",
        "-i",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(msg.as_bytes()), timeout=15)
    if proc.returncode != 0:
        err_txt = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"sendmail exited {proc.returncode}: {err_txt}")
    return True


@router.post("", response_model=dict)
async def submit_contact_form(payload: ContactSubmission, request: Request) -> dict:
    # Honeypot field filled by automated bots — accept silently without delivering mail.
    if payload.website and payload.website.strip():
        return {"ok": True, "message": "Thank you. Your inquiry has been received."}

    clean_email = _clean_header(payload.email)
    if not _EMAIL_RE.match(clean_email):
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")

    if payload.form_type == "dmca" and not (payload.infringing_url and payload.infringing_url.strip()):
        raise HTTPException(status_code=422, detail="Please provide the infringing URL(s).")

    ip = _client_ip(request)
    _check_rate_limit(ip)

    clean_name = _clean_header(payload.name)
    clean_subject = _clean_header(payload.subject)
    tag = "DMCA" if payload.form_type == "dmca" else "Contact"

    body_lines = [
        f"Form Type: {tag}",
        f"Site: {payload.site}",
        f"From Name: {clean_name}",
        f"From Email: {clean_email}",
        f"Client IP: {ip}",
    ]
    if payload.infringing_url:
        body_lines.append(f"Infringing URL(s): {payload.infringing_url.strip()}")
    if payload.original_work:
        body_lines.append(f"Original Work: {payload.original_work.strip()}")
    if payload.signature:
        body_lines.append(f"Electronic Signature: {_clean_header(payload.signature)}")
    body_lines.extend(["", "Message:", payload.message.strip()])

    msg = EmailMessage()
    msg["From"] = f"{payload.site} {tag} <noreply@{CONTACT_SENDER_DOMAIN}>"
    msg["To"] = CONTACT_RECIPIENT
    msg["Reply-To"] = f"{clean_name} <{clean_email}>" if "@" not in clean_name else clean_email
    msg["Subject"] = f"[{payload.site} {tag}] {clean_subject}"
    msg.set_content("\n".join(body_lines))

    try:
        delivered = await _deliver_sendmail(msg)
    except Exception as exc:
        logger.exception("Failed delivering %s inquiry from %s (%s)", tag, clean_email, payload.site)
        raise HTTPException(status_code=502, detail=f"Unable to send message right now: {exc}") from exc

    if not delivered:
        logger.warning("sendmail binary unavailable; logged %s submission from %s (%s)", tag, clean_email, payload.site)
        raise HTTPException(status_code=503, detail="Mail transport is not configured on this server.")

    logger.info("Delivered %s message to %s from %s (site=%s)", tag, CONTACT_RECIPIENT, clean_email, payload.site)
    return {"ok": True, "message": f"Your {tag.lower()} notice has been sent to {CONTACT_RECIPIENT}."}
