import hashlib

from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class StaffInvitationMutationThrottle(UserRateThrottle):
    """Bound owner-driven invitation mutations without throttling read-only status views."""

    scope = "staff_invitations"

    def get_cache_key(self, request, view):  # type: ignore[no-untyped-def]
        if request.method in SAFE_METHODS or not request.user.is_authenticated:
            return None
        return super().get_cache_key(request, view)


class InboundWebhookSourceThrottle(SimpleRateThrottle):
    """Bound aggregate anonymous work even when callers rotate endpoint identifiers."""

    scope = "inbound_webhook_sources"

    def get_cache_key(self, request, view):  # type: ignore[no-untyped-def]
        del view
        identity = str(request.META.get("REMOTE_ADDR", "unknown"))
        digest = hashlib.sha256(identity.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class InboundWebhookEndpointThrottle(SimpleRateThrottle):
    """Bound work directed at one opaque inbound endpoint."""

    scope = "inbound_webhooks"

    def get_cache_key(self, request, view):  # type: ignore[no-untyped-def]
        endpoint_id = str(view.kwargs.get("endpoint_id", ""))
        digest = hashlib.sha256(endpoint_id.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
