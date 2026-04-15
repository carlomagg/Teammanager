# yourapp/templatetags/feature_utils.py
from django import template

register = template.Library()

@register.inclusion_tag('partials/feature_badge.html')
def feature_badge(key, badges):
    """
    Usage: {% feature_badge 'job_board' feature_badges %}
    Returns the rendered badge if it should be shown, else empty string.
    """
    label = badges.get(key)
    if label:
        return {'label': label}
    return {'label': None}