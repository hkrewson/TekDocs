from allauth.account.adapter import DefaultAccountAdapter


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    """Registration remains closed until the bootstrap/invite flow lands in 0.1.0."""

    def is_open_for_signup(self, request):  # type: ignore[no-untyped-def]
        return False
