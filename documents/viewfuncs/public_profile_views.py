import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from documents.models import StaffProfile, UserProfile, CompanyProfile, CustomUser, Department, Team

logger = logging.getLogger(__name__)


# ─── Public (unauthenticated) profile views ────────────────────────────────

def public_profile_view(request, slug):
    """
    Single entry‑point for /p/<slug>/.
    Tries StaffProfile → UserProfile → CompanyProfile in order.
    """
    # 1. Staff profile
    profile = StaffProfile.objects.filter(public_slug=slug, is_public=True).select_related('user', 'tenant').first()
    if profile:
        return _render_staff_public(request, profile)

    # 2. User (personal) profile
    profile = UserProfile.objects.filter(public_slug=slug, is_public=True).select_related('user').first()
    if profile:
        return _render_user_public(request, profile)

    # 3. Company profile
    profile = CompanyProfile.objects.filter(public_slug=slug, is_public=True).select_related('tenant').first()
    if profile:
        return _render_company_public(request, profile)

    raise Http404("Profile not found or not public.")


def _render_staff_public(request, profile):
    sections = profile.get_public_sections
    context = {
        'profile': profile,
        'profile_type': 'staff',
        'sections': sections,
        'recommendations': (
            profile.recommendations_received.filter(is_visible=True)
            if sections.get('recommendations') and hasattr(profile, 'recommendations_received')
            else []
        ),
    }
    return render(request, 'public/public_profile.html', context)


def _render_user_public(request, profile):
    sections = profile.get_public_sections
    context = {
        'profile': profile,
        'profile_type': 'user',
        'sections': sections,
        'recommendations': (
            profile.recommendations_received.filter(is_visible=True)
            if sections.get('recommendations') and hasattr(profile, 'recommendations_received')
            else []
        ),
    }
    return render(request, 'public/public_profile.html', context)


def _render_company_public(request, profile):
    sections = profile.get_public_sections
    depts = Department.objects.filter(tenant=profile.tenant) if sections.get('departments_teams') else []
    teams = Team.objects.filter(tenant=profile.tenant) if sections.get('departments_teams') else []
    context = {
        'profile': profile,
        'profile_type': 'company',
        'sections': sections,
        'depts': depts,
        'teams': teams,
    }
    return render(request, 'public/public_company_profile.html', context)


# ─── Authenticated owner toggle APIs ───────────────────────────────────────

@login_required
@require_POST
def toggle_profile_public(request):
    """Toggle is_public on/off for the requesting user's profile."""
    user = request.effective_user
    profile = _get_own_profile(user)
    if not profile:
        return JsonResponse({'error': 'Profile not found'}, status=404)

    profile.is_public = not profile.is_public
    profile.save()

    return JsonResponse({
        'success': True,
        'is_public': profile.is_public,
        'public_slug': profile.public_slug or '',
    })


@login_required
@require_POST
def toggle_section_visibility(request):
    """Toggle a single section's public visibility."""
    user = request.effective_user
    profile = _get_own_profile(user)
    if not profile:
        return JsonResponse({'error': 'Profile not found'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    section_key = data.get('section')
    visible = data.get('visible')

    if section_key is None or visible is None:
        return JsonResponse({'error': 'section and visible are required'}, status=400)

    # Validate key exists in defaults
    defaults = profile.get_public_sections
    if section_key not in defaults:
        return JsonResponse({'error': f'Unknown section: {section_key}'}, status=400)

    sections = dict(profile.public_sections or {})
    sections[section_key] = bool(visible)
    profile.public_sections = sections
    profile.save(update_fields=['public_sections'])

    return JsonResponse({
        'success': True,
        'section': section_key,
        'visible': bool(visible),
    })


@login_required
@require_POST
def toggle_company_public(request):
    """Toggle is_public on/off for the company profile (admin only)."""
    user = request.effective_user
    tenant = request.effective_tenant
    if not tenant:
        return JsonResponse({'error': 'No tenant context'}, status=400)

    try:
        profile = CompanyProfile.objects.get(tenant=tenant)
    except CompanyProfile.DoesNotExist:
        return JsonResponse({'error': 'Company profile not found'}, status=404)

    profile.is_public = not profile.is_public
    profile.save()

    return JsonResponse({
        'success': True,
        'is_public': profile.is_public,
        'public_slug': profile.public_slug or '',
    })


@login_required
@require_POST
def toggle_company_section(request):
    """Toggle a single section's public visibility on the company profile."""
    user = request.effective_user
    tenant = request.effective_tenant
    if not tenant:
        return JsonResponse({'error': 'No tenant context'}, status=400)

    try:
        profile = CompanyProfile.objects.get(tenant=tenant)
    except CompanyProfile.DoesNotExist:
        return JsonResponse({'error': 'Company profile not found'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    section_key = data.get('section')
    visible = data.get('visible')

    if section_key is None or visible is None:
        return JsonResponse({'error': 'section and visible are required'}, status=400)

    defaults = profile.get_public_sections
    if section_key not in defaults:
        return JsonResponse({'error': f'Unknown section: {section_key}'}, status=400)

    sections = dict(profile.public_sections or {})
    sections[section_key] = bool(visible)
    profile.public_sections = sections
    profile.save(update_fields=['public_sections'])

    return JsonResponse({
        'success': True,
        'section': section_key,
        'visible': bool(visible),
    })


# ─── Helper ────────────────────────────────────────────────────────────────

def _get_own_profile(user):
    """Return the user's own StaffProfile or UserProfile."""
    profile = getattr(user, 'staff_profile', None)
    if profile:
        return profile
    profile = getattr(user, 'user_profile', None)
    return profile
