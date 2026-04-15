from django import template

register = template.Library()

@register.simple_tag
def url_replace(request, field, value):
    """
    Replaces a GET parameter in the current URL while preserving all other parameters.
    Usage: {% url_replace request 'page' 2 %}
    Returns: Updated query string (e.g., '?search=foo&city=bar&page=2')
    """
    updated_params = request.GET.copy()
    updated_params[field] = str(value)
    
    # Remove empty parameters to clean up the URL
    for key in list(updated_params.keys()):
        if not updated_params[key]:
            del updated_params[key]
    
    return updated_params.urlencode()