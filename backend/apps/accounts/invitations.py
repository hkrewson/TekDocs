from __future__ import annotations

import re
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.core.email import send_invitation_email
from apps.core.models import AuditEvent, Tenant

from .models import EMPTY_DIGEST, Invitation, InvitationState, TenantMembership, User


class InvitationConflict(APIException):
    status_code = 409
    default_detail = "The invitation cannot be changed in its current state."
    default_code = "invitation_conflict"


class InvitationDeliveryUnavailable(APIException):
    status_code = 503
    default_detail = "The invitation was retained, but email delivery failed. It can be resent."
    default_code = "invitation_delivery_unavailable"


class InvitationDeliveryRejected(Exception):
    pass


class InvitationUnavailable(APIException):
    status_code = 410
    default_detail = "This invitation is no longer available. Ask the TekDocs owner for a new invitation."
    default_code = "invitation_unavailable"


@dataclass(frozen=True)
class IssuedInvitation:
    invitation: Invitation
    token: str


@dataclass(frozen=True)
class AcceptedInvitation:
    invitation: Invitation
    user: User


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _expires_at() -> datetime:
    return timezone.now() + timedelta(hours=settings.INVITATION_TTL_HOURS)


def _acceptance_url(token: str) -> str:
    return f"{settings.TEKDOCS_PUBLIC_URL.rstrip('/')}/auth/invitations/accept#token={token}"


def _audit(*, invitation: Invitation, actor: User | None, action: str) -> None:
    AuditEvent.objects.create(
        tenant=invitation.tenant,
        actor=actor,
        action=action,
        entity_id=invitation.id,
        metadata={},
    )


def _mark_expired(invitation: Invitation, actor: User | None) -> None:
    invitation.state = InvitationState.EXPIRED
    invitation.token_digest = EMPTY_DIGEST
    invitation.save(update_fields=("state", "token_digest", "updated_at"))
    _audit(invitation=invitation, actor=actor, action="invitation.expired")


def _deliver(issued: IssuedInvitation, actor: User) -> Invitation:
    invitation = issued.invitation
    try:
        delivered = send_invitation_email(
            recipient=invitation.email,
            acceptance_url=_acceptance_url(issued.token),
            tenant_name=invitation.tenant.name,
            expires_at=invitation.expires_at,
        )
        if delivered != 1:
            raise InvitationDeliveryRejected
    except (InvitationDeliveryRejected, OSError, smtplib.SMTPException):
        with transaction.atomic():
            current = Invitation.scoped.for_tenant(invitation.tenant).select_for_update().get(pk=invitation.pk)
            current.last_delivery_failed_at = timezone.now()
            current.save(update_fields=("last_delivery_failed_at", "updated_at"))
            _audit(invitation=current, actor=actor, action="invitation.delivery_failed")
        raise InvitationDeliveryUnavailable() from None

    with transaction.atomic():
        current = Invitation.scoped.for_tenant(invitation.tenant).select_for_update().get(pk=invitation.pk)
        current.last_sent_at = timezone.now()
        current.last_delivery_failed_at = None
        current.send_count += 1
        current.save(update_fields=("last_sent_at", "last_delivery_failed_at", "send_count", "updated_at"))
        _audit(invitation=current, actor=actor, action="invitation.delivered")
    return current


def issue_invitation(*, tenant: Tenant, actor: User, email: str) -> Invitation:
    normalized_email = User.objects.normalize_email(email).strip().lower()
    token = _new_token()
    try:
        with transaction.atomic():
            if User.objects.filter(email__iexact=normalized_email).exists():
                raise InvitationConflict("An account already uses this email address.")
            existing = (
                Invitation.scoped.for_tenant(tenant)
                .select_for_update()
                .filter(email=normalized_email, state=InvitationState.PENDING)
                .first()
            )
            if existing is not None:
                if existing.expires_at > timezone.now():
                    raise InvitationConflict("An active invitation already exists for this email address.")
                _mark_expired(existing, actor)
            invitation = Invitation.objects.create(
                tenant=tenant,
                email=normalized_email,
                token_digest=Invitation.digest_token(token),
                invited_by=actor,
                expires_at=_expires_at(),
                delivery_attempts=1,
            )
            _audit(invitation=invitation, actor=actor, action="invitation.issued")
    except IntegrityError as exc:
        raise InvitationConflict("An active invitation already exists for this email address.") from exc
    return _deliver(IssuedInvitation(invitation, token), actor)


def resend_invitation(*, invitation: Invitation, actor: User) -> Invitation:
    token = _new_token()
    with transaction.atomic():
        current = (
            Invitation.scoped.for_tenant(invitation.tenant)
            .select_for_update()
            .select_related("tenant")
            .get(pk=invitation.pk)
        )
        if current.state == InvitationState.PENDING and current.expires_at <= timezone.now():
            _mark_expired(current, actor)
        if current.state != InvitationState.PENDING:
            raise InvitationConflict()
        current.token_digest = Invitation.digest_token(token)
        current.expires_at = _expires_at()
        current.delivery_attempts += 1
        current.save(update_fields=("token_digest", "expires_at", "delivery_attempts", "updated_at"))
        _audit(invitation=current, actor=actor, action="invitation.resend_requested")
    return _deliver(IssuedInvitation(current, token), actor)


def revoke_invitation(*, invitation: Invitation, actor: User) -> Invitation:
    with transaction.atomic():
        current = Invitation.scoped.for_tenant(invitation.tenant).select_for_update().get(pk=invitation.pk)
        if current.state == InvitationState.PENDING and current.expires_at <= timezone.now():
            _mark_expired(current, actor)
        if current.state != InvitationState.PENDING:
            raise InvitationConflict()
        current.state = InvitationState.REVOKED
        current.revoked_at = timezone.now()
        current.token_digest = EMPTY_DIGEST
        current.save(update_fields=("state", "revoked_at", "token_digest", "updated_at"))
        _audit(invitation=current, actor=actor, action="invitation.revoked")
    return current


def accept_invitation(*, token: str, display_name: str, password: str) -> AcceptedInvitation:
    if re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token) is None:
        raise InvitationUnavailable()

    digest = Invitation.digest_token(token)
    accepted: AcceptedInvitation | None = None
    try:
        with transaction.atomic():
            # Token redemption is the deliberately narrow pre-authentication lookup boundary:
            # the tenant cannot be known until the digest resolves, and lifecycle checks remain
            # generic and transactional below. Ordinary domain reads must use ``scoped``.
            invitation = (
                Invitation.objects.select_for_update().select_related("tenant").filter(token_digest=digest).first()
            )
            if invitation is None or invitation.state != InvitationState.PENDING:
                pass
            elif invitation.expires_at <= timezone.now():
                _mark_expired(invitation, actor=None)
            elif not invitation.matches_active_token(token):
                pass
            elif User.objects.filter(email__iexact=invitation.email).exists():
                pass
            else:
                candidate = User(email=invitation.email, display_name=display_name.strip())
                try:
                    password_validation.validate_password(password, candidate)
                except DjangoValidationError as exc:
                    raise ValidationError({"password": list(exc.messages)}) from exc
                user = User.objects.create_user(
                    email=invitation.email,
                    password=password,
                    display_name=display_name.strip(),
                )
                EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
                TenantMembership.objects.create(tenant=invitation.tenant, user=user)
                invitation.state = InvitationState.ACCEPTED
                invitation.accepted_by = user
                invitation.accepted_at = timezone.now()
                invitation.token_digest = EMPTY_DIGEST
                invitation.save(update_fields=("state", "accepted_by", "accepted_at", "token_digest", "updated_at"))
                _audit(invitation=invitation, actor=user, action="invitation.accepted")
                accepted = AcceptedInvitation(invitation=invitation, user=user)
    except IntegrityError as exc:
        raise InvitationUnavailable() from exc

    if accepted is None:
        raise InvitationUnavailable()
    return accepted
