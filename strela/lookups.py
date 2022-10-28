from selectable.base import ModelLookup
from selectable.registry import registry

from .models import Skola

class SkolaLookup(ModelLookup):
    model = Skola
    search_fields = ('nazev__icontains',)

    def get_query(self, request, term):
        result = super().get_query(request, term)
        uzemi = request.GET.get('uzemi', '')
        if not uzemi:
            return self.model.objects.none()
        else:
            result = result.filter(region=uzemi[3], kraj=uzemi[4], okres=uzemi[5])

        return result.order_by('nazev')

registry.register(SkolaLookup)