import pytest

from apps.accounts.models import User


@pytest.mark.django_db
def test_user_identity_is_email_first():
    user = User.objects.create_user(email="OWNER@EXAMPLE.COM", password="not-a-real-secret", display_name="Owner")

    assert user.email == "owner@example.com"
    assert user.username is None
    assert user.check_password("not-a-real-secret")
