# helpers.py
from urllib.parse import urlparse
from django.conf import settings

# helpers.py
def get_tenant_origin(request) -> str:
    host   = request.get_host()           # "raadaa.localhost:8000"
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{host}"           # "http://raadaa.localhost:8000"

def get_rp_id(request) -> str:
    """
    In dev: use the exact hostname (e.g. raadaa.localhost).
    In prod: use the apex domain (e.g. teammanager.ng).
    """
    from django.conf import settings
    if settings.DEBUG:
        return request.get_host().split(":")[0]  # strip port → "raadaa.localhost"
    return settings.WEBAUTHN_RP_ID               # "teammanager.ng"