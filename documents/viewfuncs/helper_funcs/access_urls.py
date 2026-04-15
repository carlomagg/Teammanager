from django.conf import settings
from django.urls import reverse
from documents.models import Conference, ConferenceParticipant, CustomUser
from urllib.parse import urlencode


def build_conference_access_url(conference: Conference, participant: ConferenceParticipant) -> str:
    path = reverse(
        'conference_access',
        kwargs={'conference_id': conference.id, 'token': participant.unique_token}
    )

    # Fallback: always use main domain for access links
    protocol = "https" if not settings.DEBUG else "http"
    base = "localhost:8000" if settings.DEBUG else "teammanager.ng"

    # → Always main domain for participant access
    return f"{protocol}://{base}{path}"

def build_guest_dashboard_url(token: str) -> str:
    path = reverse('guest_dashboard')
    query = urlencode({'token': token})
    protocol = "https" if not settings.DEBUG else "http"
    base = "localhost:8000" if settings.DEBUG else "teammanager.ng"
    return f"{protocol}://{base}{path}?{query}"

def build_user_activity_dashboard_url(user: CustomUser) -> str:
    path = reverse('user_activity_dashboard')
    protocol = "https" if not settings.DEBUG else "http"
    base = "localhost:8000" if settings.DEBUG else "teammanager.ng"
    if user.tenant is not None:
        subdomain = user.tenant.slug
        return f"{protocol}://{subdomain}.{base}{path}"
    else:
        return f"{protocol}://{base}{path}"

def build_conference_feedback_url(request, conference: Conference) -> str:
    path = reverse(
        'conference_feedback',
        kwargs={'conference_id': conference.id,}
    )

    # Fallback: always use main domain for access links
    protocol = "https" if not settings.DEBUG else "http"
    base = "localhost:8000" if settings.DEBUG else "teammanager.ng"

    if request.user.is_authenticated:
        if request.user.tenant is not None:
            subdomain = request.user.tenant.slug
            return f"{protocol}://{subdomain}.{base}{path}"
        else:
            return f"{protocol}://{base}{path}"

    # → Always main domain for participant access
    return f"{protocol}://{base}{path}"