from documents.forms import PromotionHistoryForm
from documents.models import PromotionHistory
import csv
import logging
from django.contrib.auth.decorators import user_passes_test, login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from documents.models import Department, StaffDocument, StaffProfile, CustomUser
from documents.forms import StaffDocumentForm, EducationHistoryForm, WorkHistoryForm, AchievementForm, IdentityDocumentForm, PromotionHistoryForm
from .rba_decorators import is_admin 
from django.db.models import Q
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST


logger = logging.getLogger(__name__)


@login_required
def add_staff_document(request):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    if request.method == 'POST':
        form = StaffDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.tenant = request.user.tenant
            document.staff_profile = get_object_or_404(StaffProfile, user=request.user, tenant=request.tenant)
            document.save()
            return JsonResponse({
                'success': True,
                'document': {
                    'id': document.id,
                    'description': document.description or document.document_type,
                    'file_url': document.file.url,
                    'document_type': document.get_document_type_display(),
                    'uploaded_at': document.uploaded_at.strftime('%B %d, %Y')
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
def delete_staff_document(request, document_id):
    if hasattr(request, 'tenant') and request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    try:
        # Get the user's StaffProfile (assuming one profile per user)
        staff_profile = StaffProfile.objects.get(user=request.user, tenant=request.tenant)
        document = get_object_or_404(StaffDocument, id=document_id, staff_profile=staff_profile)
        if request.user != document.staff_profile.user:
            return JsonResponse({'success': False, 'error': 'You are not authorized to delete this document.'}, status=403)
        if request.method == 'POST':
            document.delete()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)
    except StaffProfile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Staff profile not found'}, status=404)
    except StaffDocument.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Document not found or not owned by user'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
@login_required    
@user_passes_test(is_admin)
def staff_directory(request):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        # return HttpResponseForbidden("You are not authorized for this company.")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    
    # Filter staff profiles by tenant
    profiles = StaffProfile.objects.select_related(
        "user", "department"
    ).prefetch_related("team").filter(user__tenant=request.user.tenant)

    # Restrict to department for HODs (optional)
    if request.user.is_hod() and not is_admin(request.user):
        profiles = profiles.filter(department=request.user.department)

    logger.debug(f"Profiles found: {profiles.count()}")

    # Grouping by Department → Team (Tenant is already scoped)
    grouped = {}
    for profile in profiles:
        dept = profile.current_department.name if profile.current_department else "No Department"
        team = profile.current_team
        team_name = team.name if team else "No Team"
        grouped.setdefault(dept, {}).setdefault(team_name, []).append(profile)

    logger.debug(f"Grouped dictionary: {grouped}")
    return render(request, "staff/staff_directory.html", {"grouped": grouped})

@login_required
def view_staff_profile(request, user_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        # return HttpResponseForbidden("You are not authorized for this company.")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    
    # profile = get_object_or_404(StaffProfile, user_id=user_id, tenant=request.tenant)

    # Ensure the profile belongs to the same tenant as the requesting user
    # if profile.user.tenant != request.user.tenant:
    #     return render(request, "403.html", status=403)

    visible_fields = [
        "photo",
        "first_name", "last_name", "middle_name", "email", "phone_number", "sex", "date_of_birth", "home_address",
        "state_of_origin", "lga", "religion",
        "account_number", "bank_name", "account_name",
        "location", "employment_date",
        "department", "team", "designation", "official_email",
        "emergency_name", "emergency_relationship", "emergency_phone",
        "emergency_address", "emergency_email",
    ]

    if request.user.is_staff:
        viewer = request.user
        user = get_object_or_404(CustomUser, id=user_id)
        profile, created = StaffProfile.objects.get_or_create(user=user, tenant=user.tenant)
    else:
        viewer = StaffProfile.objects.filter(user=request.user, tenant=request.tenant).first()
        profile = get_object_or_404(StaffProfile, user_id=user_id, tenant=request.tenant)

    is_owner = profile.user == request.user

    # Visibility logic based on shared department/team (within same tenant already)
    # if viewer:
        # if profile.department == viewer.department:
        #     visible_fields += ["department"]
        #     shared_teams = set(profile.team.values_list("id", flat=True)) & set(viewer.team.values_list("id", flat=True))
        #     if shared_teams:
        #         visible_fields += ["team"]

    context = {
        "profile": profile,
        "viewer": viewer,
        "visible_fields": visible_fields,
        "is_owner": is_owner,
    }

    if is_owner:
        context.update({
            "education_form": EducationHistoryForm(),
            "experience_form": WorkHistoryForm(),
            "achievement_form": AchievementForm(),
            "identity_form": IdentityDocumentForm(),
            "promotion_form": PromotionHistoryForm()
        })

    return render(request, "staff/view_staff_profile.html", context)

def staff_list(request):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        # return HttpResponseForbidden("You are not authorized for this company.")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    
    # Get query parameters
    sort_by = request.GET.get('sort_by', 'name')
    sort_order = request.GET.get('sort_order', 'asc')
    search_query = request.GET.get('search', '')
    filter_dept = request.GET.get('dept', '')
    page = request.GET.get('page', 1)

    # Base queryset: only staff from the same tenant
    profiles = StaffProfile.objects.select_related(
        'user', 'department'
    ).prefetch_related('team', 'user__roles').filter(user__tenant=request.user.tenant)

    # Search by name
    if search_query:
        profiles = profiles.filter(
            Q(first_name__icontains=search_query) |
            Q(middle_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    # Filter by department
    if filter_dept:
        profiles = profiles.filter(department__name__iexact=filter_dept)

    # Sorting
    sort_field = sort_by
    if sort_by == 'name':
        sort_field = 'first_name'
    elif sort_by == 'department':
        sort_field = 'department__name'
    elif sort_by == 'team':
        sort_field = 'team__name'
    elif sort_by == 'photo':
        sort_field = 'photo'
    elif sort_by == 'employment_date':
        sort_field = 'employment_date'
    elif sort_by == 'location':
        sort_field = 'location'

    if sort_order == 'desc':
        sort_field = f'-{sort_field}'
    profiles = profiles.order_by(sort_field)

    # Pagination
    paginator = Paginator(profiles, 10)  # 10 profiles per page
    page_obj = paginator.get_page(page)

    # Filter dropdown: restrict departments to the tenant only
    departments = Department.objects.filter(
        staff__user__tenant=request.user.tenant
    ).distinct()

    context = {
        'profiles': page_obj,
        'departments': departments,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'search_query': search_query,
        'filter_dept': filter_dept,
    }
    return render(request, 'staff/staff_list.html', context)

@require_POST
def export_staff_csv(request):
    profile_ids = request.POST.getlist('profile_ids')
    if not profile_ids:
        return HttpResponse(
            status=400,
            content_type='application/json',
            content='{"error": "No profiles selected"}'
        )

    # Only export profiles that belong to the same tenant as the requester
    profiles = StaffProfile.objects.filter(
        user__id__in=profile_ids,
        user__tenant=request.user.tenant
    ).select_related('user', 'department').prefetch_related('team')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="staff_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'Phone Number', 'Email', 'Sex', 'Designation', 'Department', 'Team'])

    for profile in profiles:
        writer.writerow([
            f"{profile.first_name} {profile.middle_name or ''} {profile.last_name}".strip(),
            profile.phone_number or 'N/A',
            profile.email or 'N/A',
            profile.sex or 'N/A',
            profile.current_designation or 'N/A',
            profile.current_department.name if profile.current_department else 'N/A',
            profile.current_team.name if profile.current_team else 'N/A',
        ])

    return response
