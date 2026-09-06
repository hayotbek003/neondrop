from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


class CaseInsensitiveModelBackend(ModelBackend):
    """
    Case-insensitive authentication backend for NEONDROP.
    Allows users and administrators to log in using their username or email
    regardless of letter casing (e.g. 'Smoke', 'smoke', 'SMOKE', 'smoke@neondrop.gg').
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('email') or kwargs.get('username_or_email')
        if not username or not password:
            return None

        identifier = str(username).strip()
        user = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        ).first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
