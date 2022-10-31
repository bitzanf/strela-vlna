from django import template
from ..utils import vokalizace_z_ze
register = template.Library()

@register.filter
def list_index(l, i):
    try:
        return l[i]
    except:
        return None

@register.filter
def z_ze_vokalizace(s, k=True):
    try:
        return vokalizace_z_ze(s, k)
    except:
        return None