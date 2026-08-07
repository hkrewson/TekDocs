import hashlib
import secrets
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .managers import UserManager

EMPTY_DIGEST = ""


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None  # type: ignore[assignment]
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=160)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []  # type: ignore[misc]

    objects = UserManager()  # type: ignore[misc,assignment]

    def __str__(self) -> str:
        return self.email


class InvitationState(models.TextChoices):
    PENDING = "pending", "Pending"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"
    ACCEPTED = "accepted", "Accepted"


class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="invitations")
    email = models.EmailField(max_length=254)
    token_digest = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=16, choices=InvitationState, default=InvitationState.PENDING)
    invited_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="issued_invitations")
    accepted_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="accepted_invitations",
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_delivery_failed_at = models.DateTimeField(null=True, blank=True)
    delivery_attempts = models.PositiveIntegerField(default=0)
    send_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "email"),
                condition=models.Q(state=InvitationState.PENDING),
                name="unique_pending_invitation_per_tenant_email",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("created_at")),
                name="invitation_expires_after_creation",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state=InvitationState.PENDING) & ~models.Q(token_digest=EMPTY_DIGEST)
                    | ~models.Q(state=InvitationState.PENDING) & models.Q(token_digest=EMPTY_DIGEST)
                ),
                name="invitation_token_presence_matches_pending_state",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state=InvitationState.ACCEPTED,
                        accepted_at__isnull=False,
                        accepted_by__isnull=False,
                    )
                    | ~models.Q(state=InvitationState.ACCEPTED)
                    & models.Q(accepted_at__isnull=True, accepted_by__isnull=True)
                ),
                name="invitation_acceptance_fields_match_state",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state=InvitationState.REVOKED, revoked_at__isnull=False)
                    | ~models.Q(state=InvitationState.REVOKED) & models.Q(revoked_at__isnull=True)
                ),
                name="invitation_revocation_time_matches_state",
            ),
        ]
        indexes = [models.Index(fields=("tenant", "state", "expires_at"))]

    def __str__(self) -> str:
        return f"Invitation {self.id} ({self.state})"

    @staticmethod
    def digest_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def matches_active_token(self, token: str) -> bool:
        return (
            self.state == InvitationState.PENDING
            and self.expires_at > timezone.now()
            and bool(self.token_digest)
            and secrets.compare_digest(self.token_digest, self.digest_token(token))
        )


class TenantMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Tenant", on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="tenant_memberships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("tenant", "user"), name="unique_tenant_membership"),
        ]

    def __str__(self) -> str:
        return f"Membership {self.id}"
