# helper_funcs/permissions.py  (or wherever makes sense)

from ..rba_decorators import is_hr, is_conference_organizer
from ...models import BookingType
def can_manage_vacancies(request):
    """
    Decides if current effective context is allowed to list/create/edit vacancies.
    """
    if not request.user.is_authenticated:
        return False

    # Superuser → always yes
    if request.user.is_superuser:
        return True

    # Global staff → yes (they can see everything or impersonate)
    if request.user.is_staff:
        return True

    # Personal user → yes, they manage their own
    if getattr(request.user, 'is_personal', False):
        return True

    # Company user → only if they are HR in their tenant
    if request.effective_tenant:
        if is_hr(request.effective_user) or request.effective_tenant.admin == request.effective_user:
            return True

    return False


def can_create_conferences(request):
    """
    Returns True if the current user (or effective user) is allowed to
    create a conference in the given tenant context (or personal).
    """
    if not request.effective_user.is_authenticated:
        return False

    # Superuser → always yes
    if request.effective_user.is_superuser:
        return True

    # Global staff → yes (they can see everything or impersonate)
    if request.effective_user.is_staff:
        return True

    # Personal user → yes, they manage their own
    if getattr(request.effective_user, 'is_personal', False):
        return True

    # Tenant-level check — only admins (customize as needed)
    if request.effective_tenant.admin == request.effective_user:
        return True
    
    if is_conference_organizer(request.effective_user):
        return True

    # Optional: future role-based check
    # if effective_user.has_perm('documents.can_create_conference', effective_tenant):
    #     return True

    return False

def can_edit_conferences(request, conference):
    if not request.effective_user.is_authenticated:
        return False
    
    if request.effective_user.is_superuser:
        return True

    elif request.effective_user.is_staff:
        # Global staff policy — usually allowed to edit anything they can see
        return True

    elif getattr(request.effective_user, 'is_personal', False) and request.effective_user == conference.organizer:
        return True

    elif request.effective_tenant and request.effective_tenant.admin == request.effective_user:
        return True

    elif is_conference_organizer(request.effective_user):
        return True
    
    return False


def can_manage_conference_participant(request, conference):
    user = request.effective_user
    return (
        user == conference.organizer or
        user == conference.tenant.admin or
        user.is_superuser or
        user.roles.filter(name='Conference Organizer').exists() or
        (user.is_staff and getattr(user, 'tenant', None) is None)
    )


# def can_manage_participant(request, participant):
#     user = request.effective_user
#     return (
#         user == participant.organizer or
#         user == participant.tenant.admin or
#         user.is_superuser or
#         (user.is_staff and getattr(user, 'tenant', None) is None)
#     )

def user_can_manage_booking_type(user, booking_type: BookingType) -> bool:
    """Central permission check"""
    if booking_type.tenant:
        # Organization context → must be a manager
        return user in booking_type.managers.all()
    else:
        # Personal context → must be the creator
        return booking_type.created_by == user