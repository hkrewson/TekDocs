from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class StaffInvitationMutationThrottle(UserRateThrottle):
    """Bound owner-driven invitation mutations without throttling read-only status views."""

    scope = "staff_invitations"

    def get_cache_key(self, request, view):  # type: ignore[no-untyped-def]
        if request.method in SAFE_METHODS or not request.user.is_authenticated:
            return None
        return super().get_cache_key(request, view)
