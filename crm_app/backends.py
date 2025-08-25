from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # Fallback to default ModelBackend authentication
            return super().authenticate(request, username=username, password=password, **kwargs)
        else:
            if user.check_password(password):
                return user
        return None
