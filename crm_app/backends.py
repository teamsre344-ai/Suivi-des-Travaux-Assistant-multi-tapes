import requests
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.models import Q

User = get_user_model()

class EmailBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using their email address
    instead of a username.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.filter(Q(email__iexact=username) | Q(username__iexact=username)).first()
            if user and user.check_password(password):
                return user
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

class MicrosoftAuthenticationBackend(ModelBackend):
    """
    Custom authentication backend for Microsoft Azure AD.
    It handles the token exchange and user lookup/creation based on the email.
    """
    def authenticate(self, request, code=None, **kwargs):
        if not code:
            return None

        token_url = f"{settings.MICROSOFT_AUTHORITY}/oauth2/v2.0/token"
        token_data = {
            "client_id": settings.MICROSOFT_APP_ID,
            "scope": " ".join(settings.MICROSOFT_SCOPE + ["openid", "profile", "email"]),
            "code": code,
            "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
            "grant_type": "authorization_code",
            "client_secret": settings.MICROSOFT_APP_SECRET,
        }

        try:
            token_response = requests.post(token_url, data=token_data)
            token_response.raise_for_status()
            token_json = token_response.json()
            access_token = token_json.get("access_token")

            if not access_token:
                return None

            # Get user info from Microsoft Graph
            graph_url = "https://graph.microsoft.com/v1.0/me"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info_response = requests.get(graph_url, headers=headers)
            user_info_response.raise_for_status()
            user_info = user_info_response.json()
            
            email = user_info.get("mail") or user_info.get("userPrincipalName")
            if not email:
                return None

            # Check if user exists in your system
            try:
                user = User.objects.get(email__iexact=email)
                return user
            except User.DoesNotExist:
                # If user does not exist, deny access as per requirement
                return None

        except requests.exceptions.RequestException as e:
            print(f"Microsoft authentication error: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during Microsoft authentication: {e}")
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
