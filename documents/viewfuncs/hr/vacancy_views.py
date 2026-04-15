from django.utils import timezone
import logging
from django.contrib.auth.decorators import login_required, user_passes_test
from documents.forms import VacancyForm
from documents.models import Vacancy, VacancySkill, VacancyTag
from ..rba_decorators import is_hr
from ..helper_funcs.staff_tenant_or_user import get_tenant_or_staff
from ..helper_funcs.permissions import can_manage_vacancies
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from tenants.models import Tenant

logger = logging.getLogger(__name__)

def handle_additional_tags_skills(vacancy, post_data):    
    # Handle tags
    tags_input = post_data.get('tags_input', '')
    if tags_input:
        tag_names = [name.strip() for name in tags_input.split(',') if name.strip()]
        for tag_name in tag_names:
            tag, created = VacancyTag.objects.get_or_create(
                name=tag_name.lower(),
                defaults={'name': tag_name.lower()}
            )
            vacancy.tags.add(tag)
    
    # Handle skills
    skills_input = post_data.get('skills_input', '')
    if skills_input:
        skill_names = [name.strip() for name in skills_input.split(',') if name.strip()]
        for skill_name in skill_names:
            # Check for similar skills (case-insensitive, close matches)
            existing_skill = VacancySkill.objects.filter(
                name__iexact=skill_name.lower()
            ).first()
            
            if existing_skill:
                vacancy.skills.add(existing_skill)
            else:
                # Create new skill only if no similar one exists
                skill, created = VacancySkill.objects.get_or_create(
                    name=skill_name.lower(),
                    defaults={'name': skill_name.lower()}
                )
                vacancy.skills.add(skill)

@login_required
# @user_passes_test(is_hr)  # ← keeps HR check — but we allow staff/superuser bypass via logic below
def vacancy_list(request):
    """
    Lists vacancies visible to the current effective context.
    
    Access rules (in priority order):
    - Superuser                → sees everything (no tenant filter)
    - Global staff (is_staff + tenant=None) → sees everything or selected tenant (via effective_tenant)
    - Normal company HR/user   → only sees vacancies of their effective tenant
    - Personal/individual user → only sees their own vacancies (tenant=None, created_by=effective_user)
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to view or manage vacancies.'
        })
    
    # Determine which tenant context we're operating in
    effective_tenant = getattr(request, 'effective_tenant', None)
    
    # Base queryset — we'll apply filters progressively
    vacancies_qs = Vacancy.objects.select_related(
        'created_by', 'updated_by', 'shared_by'
    ).prefetch_related('skills', 'tags')   # optional: add if you display them in list
    
    # ── 1. Superuser ────────────────────────────────────────────────────────
    if request.user.is_superuser:
        # No tenant filtering — full access
        pass  # qs remains unfiltered by tenant

    # ── 2. Global staff or impersonating staff ──────────────────────────────
    elif request.user.is_staff:
        if effective_tenant:
            # Staff switched to / impersonating a specific tenant
            vacancies_qs = vacancies_qs.filter(tenant=effective_tenant)
        else:
            # Global view — see everything (including personal + all tenants)
            # If you want to restrict global staff → add extra condition here
            pass

    # ── 3. Personal / individual user ───────────────────────────────────────
    elif getattr(request.user, 'is_personal', False):
        # Only their own vacancies (tenant must be None)
        vacancies_qs = vacancies_qs.filter(
            tenant__isnull=True,
            created_by=request.effective_user   # usually == request.user unless impersonated (rare)
        )

    # ── 4. Normal company user (HR inside tenant) ───────────────────────────
    else:
        if effective_tenant is None:
            # Should not happen thanks to middleware — but safety net
            return render(request, 'tenant_error.html', {
                'error_code': '403',
                'message': 'No company context available. Please access via your company subdomain.'
            })
        
        vacancies_qs = vacancies_qs.filter(tenant=effective_tenant)

    # ── Common filtering / search ───────────────────────────────────────────
    search = request.GET.get("search", "").strip()
    if search:
        vacancies_qs = vacancies_qs.filter(
            Q(title__icontains=search) |
            Q(work_mode__icontains=search) |
            Q(description__icontains=search) |
            Q(skills__name__icontains=search) |
            Q(tags__name__icontains=search) |
            Q(city__icontains=search) |
            Q(status__icontains=search)
        ).distinct()   # important when searching across m2m fields

    # ── Annotate shareable link logic (only for display) ─────────────────────
    now = timezone.now()
    for vacancy in vacancies_qs:  # iterator → lower memory if many records
        if vacancy.is_shared and vacancy.share_time and vacancy.share_time <= now:
            if vacancy.share_time_end:
                if now <= vacancy.share_time_end:
                    vacancy.shareable_link = request.build_absolute_uri(vacancy.get_shareable_link())
                else:
                    vacancy.shareable_link = None
                    vacancy.status = "withdrawn"  # in-memory only — not saved
            else:
                vacancy.shareable_link = request.build_absolute_uri(vacancy.get_shareable_link())
        else:
            vacancy.shareable_link = None

    # ── Pagination ──────────────────────────────────────────────────────────
    paginator = Paginator(vacancies_qs, 10)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    context = {
        'vacancies': page_obj,
        'is_impersonating': getattr(request, 'is_impersonating', False),
        'effective_tenant': effective_tenant,
        # optional: add tenant name / user name when impersonating
    }

    return render(request, 'hr/vacancy_list.html', context)

@login_required
def create_vacancy(request):
    """
    Create a new vacancy in the current effective context.

    - Personal users → tenant = None, created_by = effective_user
    - Company users → tenant = effective_tenant (from subdomain or ?tenant_id=)
    - Staff / superusers → can create in any tenant via ?tenant_id=
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to create vacancies.'
        })

    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user
    print(f"Effective tenant: {effective_tenant}, Effective user: {effective_user}")

    # Optional: block personal users from creating in a company context
    # (uncomment if you want to enforce this separation)
    if getattr(request.user, 'is_personal', False) and effective_tenant is not None:
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'Personal accounts cannot create vacancies for companies.'
        })

    if request.method == 'POST':
        form = VacancyForm(request.POST)
        if form.is_valid():
            vacancy = form.save(commit=False)

            # ── Set tenant correctly ────────────────────────────────────────
            vacancy.tenant = effective_tenant   # None for personal users

            vacancy.created_by = effective_user
            vacancy.created_at = timezone.now()   # optional, if not auto_now_add
            vacancy.save()

            form.save_m2m()                       # for ManyToMany fields in form
            handle_additional_tags_skills(vacancy, request.POST)

            # Optional: success message / redirect with message
            return redirect('vacancy_list')       # or 'vacancy_detail', vacancy.pk

        else:
            # form invalid → fall through to re-render with errors
            pass

    else:
        form = VacancyForm()

    context = {
        'form': form,
        'effective_tenant': effective_tenant,
        'is_impersonating': getattr(request, 'is_impersonating', False),
        # optional extras
        # 'tenant_name': effective_tenant.name if effective_tenant else "Personal Account"
    }

    return render(request, 'hr/create_vacancy.html', context) 

@login_required
def edit_vacancy(request, vacancy_id):
    """
    Edit an existing vacancy in the current effective context.

    Rules:
    - Personal users → can only edit their own vacancies (tenant=None, created_by=effective_user)
    - Company users → can edit vacancies belonging to effective_tenant
    - Staff / superusers → can edit in any tenant (via ?tenant_id= if needed)
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to edit vacancies.'
        })

    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user

    # ── Determine queryset filters based on context ─────────────────────────
    filters = {'id': vacancy_id}

    if getattr(request.user, 'is_personal', False) and not request.user.is_staff:
        # Personal users — strict ownership + no tenant
        filters['tenant__isnull'] = True
        filters['created_by'] = effective_user
    else:
        # Company context, staff, superuser
        if effective_tenant is not None:
            filters['tenant'] = effective_tenant
        # else: superuser/global staff with no tenant selected → can edit any

    vacancy = get_object_or_404(Vacancy, **filters)

    # Optional extra safety: even if queryset allowed it, block editing
    # of vacancies from other tenants unless you're staff/superuser
    if effective_tenant is not None and vacancy.tenant != effective_tenant:
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("You cannot edit vacancies from other companies.")

    if request.method == 'POST':
        form = VacancyForm(request.POST, instance=vacancy)
        if form.is_valid():
            vacancy = form.save(commit=False)
            vacancy.updated_by = effective_user
            vacancy.updated_at = timezone.now()
            vacancy.save()
            form.save_m2m()

            handle_additional_tags_skills(vacancy, request.POST)

            next_url = request.GET.get("next") or 'vacancy_list'
            return redirect(next_url)
        # else: invalid form → fall through to re-render
    else:
        form = VacancyForm(instance=vacancy)

    context = {
        'form': form,
        'vacancy': vacancy,
        'effective_tenant': effective_tenant,
        'is_impersonating': getattr(request, 'is_impersonating', False),
        # optional: 'tenant_name': effective_tenant.name if effective_tenant else "Personal"
    }

    return render(request, 'hr/edit_vacancy.html', context)

@login_required
def vacancy_detail(request, vacancy_id):
    """
    Display a single vacancy, respecting the effective context.

    Access rules:
    - Personal users → only their own vacancies (tenant=None, created_by=effective_user)
    - Company users → vacancies belonging to effective_tenant
    - Staff / superusers → any vacancy (can use ?tenant_id= to switch context)
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to view this vacancy.'
        })

    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user

    # ── Build queryset filters based on who is viewing ──────────────────────
    filters = {'id': vacancy_id}

    if getattr(request.user, 'is_personal', False) and not request.user.is_staff:
        # Personal users — strict ownership
        filters['tenant__isnull'] = True
        filters['created_by'] = effective_user
    else:
        # Company users, staff, superusers
        if effective_tenant is not None:
            filters['tenant'] = effective_tenant
        # else → superuser/global staff with no tenant → can see any vacancy

    vacancy = get_object_or_404(Vacancy, **filters)

    # Optional defense-in-depth: prevent viewing cross-tenant unless privileged
    if effective_tenant is not None and vacancy.tenant != effective_tenant:
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("You cannot view vacancies from other companies.")

    # ── Shareable link / expiration logic (unchanged) ───────────────────────
    now = timezone.now()
    if vacancy.is_shared and vacancy.share_time and vacancy.share_time <= now:
        if vacancy.share_time_end:
            if now <= vacancy.share_time_end:
                vacancy.shareable_link = request.build_absolute_uri(vacancy.get_shareable_link())
            else:
                vacancy.shareable_link = None
                vacancy.status = "withdrawn"  # in-memory only
        else:
            vacancy.shareable_link = request.build_absolute_uri(vacancy.get_shareable_link())
    else:
        vacancy.shareable_link = None

    # Determine if current viewer has HR rights in this context
    # (useful for showing edit/share buttons, etc.)
    viewer_is_hr = is_hr(request.user) if effective_tenant else False

    context = {
        'vacancy': vacancy,
        'is_hr': viewer_is_hr,
        'is_impersonating': getattr(request, 'is_impersonating', False),
        'effective_tenant': effective_tenant,
        # optional extras you might use in template:
        # 'effective_tenant_name': effective_tenant.name if effective_tenant else "Personal Account",
        # 'can_edit': can_edit_vacancy(request, vacancy),  # if you add such helper
    }

    return render(request, 'hr/vacancy_detail.html', context)

@login_required
# @require_POST
def delete_vacancy(request, vacancy_id):
    """
    Delete a vacancy, respecting the effective context.

    Rules:
    - Personal users → only delete own vacancies (tenant=None, created_by=effective_user)
    - Company users → delete vacancies in effective_tenant
    - Staff / superusers → delete in any tenant (via ?tenant_id= if needed)
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete vacancies.'
        })

    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user

    # ── Build queryset filters based on context ─────────────────────────────
    filters = {'id': vacancy_id}

    if getattr(request.user, 'is_personal', False) and not request.user.is_staff:
        # Personal users — strict ownership + no tenant
        filters['tenant__isnull'] = True
        filters['created_by'] = effective_user
    else:
        # Company context, staff, superusers
        if effective_tenant is not None:
            filters['tenant'] = effective_tenant
        # else: superuser/global staff with no tenant → can delete any

    vacancy = get_object_or_404(Vacancy, **filters)

    # Optional defense-in-depth (non-privileged users cannot cross tenants)
    if effective_tenant is not None and vacancy.tenant != effective_tenant:
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("You cannot delete vacancies from other companies.")

    # Optional: extra business rule check
    # e.g. prevent deletion of active/shared vacancies unless staff
    # if vacancy.is_shared and not request.user.is_staff:
    #     raise PermissionDenied("Cannot delete shared/active vacancies.")

    vacancy.delete()

    next_url = request.GET.get("next") or 'vacancy_list'
    return redirect(next_url)

@login_required
# @require_POST
def share_vacancy(request, vacancy_id):
    """
    Share (publish publicly) a vacancy.

    Allowed:
    - Personal users → only their own vacancies (tenant=None)
    - Company HR users → vacancies in their effective_tenant
    - Staff / superusers → any vacancy (via ?tenant_id= if needed)
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete vacancies.'
        })

    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user

    filters = {'id': vacancy_id}

    is_personal_context = getattr(request.user, 'is_personal', False) and not request.user.is_staff

    if is_personal_context:
        # Personal users — only own vacancies
        filters['tenant__isnull'] = True
        filters['created_by'] = effective_user
    else:
        # Company context or staff/superuser
        if effective_tenant is not None:
            filters['tenant'] = effective_tenant
        # else: full access (superuser / global staff with no tenant selected)

    vacancy = get_object_or_404(Vacancy, **filters)

    # Safety: prevent cross-tenant action unless privileged
    if effective_tenant is not None and vacancy.tenant != effective_tenant:
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"success": False, "error": "Wrong company"}, status=403)

    # ── Business rule: maybe block sharing already withdrawn/closed ───────
    # if vacancy.status in ['closed', 'withdrawn']:
    #     return JsonResponse({"success": False, "error": "Vacancy cannot be shared"}, status=400)

    end_date = request.POST.get('end_date')
    share_time_end = None

    if end_date:
        try:
            share_time_end = timezone.datetime.strptime(end_date, '%Y-%m-%d')
            share_time_end = timezone.make_aware(share_time_end)
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

    vacancy.is_shared     = True
    vacancy.status        = 'active'
    vacancy.shared_by     = effective_user
    vacancy.share_time    = timezone.now()
    vacancy.share_time_end = share_time_end
    vacancy.save()

    shareable_link = request.build_absolute_uri(vacancy.get_shareable_link())

    return JsonResponse({
        "success": True,
        "vacancy": vacancy.id,
        "shareable_link": shareable_link
    })

@login_required
# @require_POST
def withdraw_vacancy(request, vacancy_id):
    """
    Withdraw (unshare / hide publicly) a previously shared vacancy.

    Allowed:
    - Personal users → only their own vacancies (tenant=None)
    - Company HR users → vacancies in effective_tenant
    - Staff / superusers → any vacancy (via ?tenant_id= if needed)
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete vacancies.'
        })

    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user

    # ── Build queryset filters based on who is acting ───────────────────────
    filters = {'id': vacancy_id}

    is_personal_context = getattr(request.user, 'is_personal', False) and not request.user.is_staff

    if is_personal_context:
        # Personal users — only their own vacancies
        filters['tenant__isnull'] = True
        filters['created_by'] = effective_user
    else:
        # Company context or staff/superuser
        if effective_tenant is not None:
            filters['tenant'] = effective_tenant
        # else: superuser / global staff with no tenant selected → full access

    vacancy = get_object_or_404(Vacancy, **filters)

    # Safety: prevent cross-tenant action unless privileged
    if effective_tenant is not None and vacancy.tenant != effective_tenant:
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse(
                {"success": False, "error": "You cannot withdraw vacancies from other companies."},
                status=403
            )

    # Optional: extra business rule (e.g. already withdrawn → no-op or error)
    if not vacancy.is_shared:
        return JsonResponse(
            {"success": False, "error": "This vacancy is not currently shared."},
            status=400
        )

    # ── Perform withdrawal ──────────────────────────────────────────────────
    vacancy.is_shared     = False
    vacancy.shared_by     = None
    vacancy.share_time    = None
    vacancy.share_time_end = None
    vacancy.status        = 'withdrawn'
    vacancy.save()

    return JsonResponse({"success": True})

def vacancy_post(request, token):
    vacancy = get_object_or_404(Vacancy, share_token=token)
    if not vacancy.is_shared or (vacancy.share_time_end and timezone.now() > vacancy.share_time_end) or vacancy.status in ['closed', 'withdrawn']:
        message = "This vacancy is no longer available."
        if vacancy.status == 'closed':
            message = "This vacancy is closed."
        elif vacancy.status == 'withdrawn':
            message = "This vacancy is withdrawn."
        return render(request, 'hr/vacancy_expired.html', {'message': message})
    
    return render(request, 'hr/vacancy_post.html', {'vacancy': vacancy})