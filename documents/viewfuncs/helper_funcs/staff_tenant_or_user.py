from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseForbidden, Http404
from tenants.models import Tenant
from documents.models import CustomUser

import logging

logger = logging.getLogger(__name__)

def get_tenant_or_staff(request):
    if request.user.is_staff:
        # Staff can switch tenants
        tenant_id = request.GET.get("tenant_id")

        if tenant_id:
            tenant = get_object_or_404(Tenant, id=tenant_id)
        else:
            tenant = request.user.tenant

        logger.info(f"Staff access by {request.user.username} to tenant")

    else:
        # Non-staff users: strict tenant enforcement
        if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
            logger.error(
                f"Unauthorized access by user {request.user.username}: tenant mismatch"
            )
            return HttpResponseForbidden("You are not authorized for this company.")

        tenant = request.tenant

    return tenant

def get_user_or_staff(request):
    if request.user.is_staff:
        # Staff can switch tenants
        user_id = request.GET.get("user_id")

        if user_id:
            user = get_object_or_404(CustomUser, id=user_id)
        else:
            user = request.user

        logger.info(f"Staff access by {request.user.username} to user {user.username}")

    else:
        # Non-staff users: strict tenant enforcement
        if not hasattr(request, 'user'):
            logger.error(
                f"Unauthorized access by user {request.user.username}: tenant mismatch"
            )
            return HttpResponseForbidden("You are not authorized for this company.")

        user = request.user

    return user

def enforce_tenant_or_personal_access(request):
    """
    Returns None if access is allowed, otherwise returns a response (403 page).
    Call it like: response = enforce_...; if response: return response
    """
    tenant = getattr(request, 'tenant', None)

    if tenant is not None:
        # Multi-tenant mode
        if not hasattr(request.user, 'tenant') or request.user.tenant != tenant:
            return render(request, 'error.html', {
                'message': 'You are not a member of this company.'
            }, status=403)
    else:
        # Personal mode
        if not getattr(request.user, 'is_personal', False):
            return render(request, 'error.html', {
                'message': 'This area is for personal accounts only. Use your company subdomain.'
            }, status=403)

    return None  # access ok


def get_context_filter_kwargs(request):
    """
    Returns Q-ready kwargs for filtering the base queryset.
    Example return: {'tenant': <tenant_obj>} or {'tenant__isnull': True, 'created_by': <user>}
    """
    tenant = getattr(request, 'tenant', None)
    if tenant is not None:
        return {'tenant': tenant, 'user': request.user}
    else:
        if not request.user.is_personal:
            raise ValueError("Personal mode but user.is_personal=False")
        return {'tenant': None, 'user': request.user}