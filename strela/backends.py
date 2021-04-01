from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User

from .models import Tym 

class TymBackend(ModelBackend):
    def authenticate(self, request, **kwargs):
        login = kwargs['username']
        password = kwargs['password']

        try:
            user = Tym.objects.get(login=login)
            if user.check_password(password) is True:
                return user
        except Tym.DoesNotExist:
            pass
            
        return None

    def get_user(self, user_id):
        try:
            return Tym.objects.get(pk=user_id)
        except Tym.DoesNotExist:
            return None