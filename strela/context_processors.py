from django.conf import settings

def add_verze_context(request):
    return {'strela_verze': getattr(settings, "STRELA_VERZE", "1.0")}