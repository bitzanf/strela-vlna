from django import template
register = template.Library()

@register.filter
def list_index(l, i):
    try:
        return l[i]
    except:
        return None