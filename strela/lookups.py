from selectable.base import ModelLookup
from selectable.registry import registry

from .models import Skola

class SkolaLookup(ModelLookup):
    model = Skola
    search_fields = ('nazev__icontains',)

    def get_query(self, request, term):
        result = super().get_query(request, term)
        return result.order_by('nazev')

registry.register(SkolaLookup)