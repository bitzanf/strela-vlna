from django.conf import settings
from django import __version__ as django_version

def add_verze_context(request):
    return {
        'strela_verze': getattr(settings, "STRELA_VERZE", "1.0"),
        'django_verze': django_version
    }