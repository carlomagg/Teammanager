from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary"""
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def filter_by_status(payrolls, status):
    """Filter payrolls by status"""
    return payrolls.filter(status=status) if hasattr(payrolls, 'filter') else [p for p in payrolls if p.status == status]
