from allauth.account.adapter import DefaultAccountAdapter


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    """Public registration remains closed; users enter through controlled invitations."""

    def is_open_for_signup(self, request):  # type: ignore[no-untyped-def]
        return False
