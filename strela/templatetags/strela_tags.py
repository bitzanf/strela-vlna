from django import template
register = template.Library()

@register.filter
def list_index(l, i):
    try:
        return l[i]
    except:
        return None

@register.filter
def is_shop_available(shop, obtiznost):
    if obtiznost == 'A':
        return True
    for s in shop:
        if s['otazka__obtiznost'] == obtiznost:
            return True
    return False