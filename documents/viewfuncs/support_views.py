"""
Customer Support Dashboard Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from documents.models import CustomerSupport, CustomUser, Vacancy, Conference, GuestUser, StaffProfile, UserProfile
from tenants.models import Tenant
from documents.decorators import support_dashboard_permission_required, support_update_permission_required


@support_dashboard_permission_required
def support_dashboard(request):
    """
    Main Customer Support Dashboard view.
    Displays recent activity with tabs for different entity types.
    Supports filtering by date range, search, and pagination.
    Includes "Past Records" tab for records older than 30 days.
    """
    # Get filter parameters from request
    entity_filter = request.GET.get('entity', 'all')  # all, tenant, vacancy, conference, user, guest
    date_filter = request.GET.get('days', '30')  # 7, 30, 90, 'all', or 'past'
    status_filter = request.GET.get('status', 'all')  # all, new, contacted, follow_up, converted, inactive
    search_query = request.GET.get('search', '').strip()
    page_number = request.GET.get('page', 1)
    
    # Base queryset
    support_records = CustomerSupport.objects.all()
    
    # Apply entity type filter
    if entity_filter != 'all':
        support_records = support_records.filter(entity_type=entity_filter)
    
    # Apply status filter
    if status_filter != 'all':
        support_records = support_records.filter(status=status_filter)
    
    # Apply date range filter
    if date_filter == 'past':
        # Past Records: older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        support_records = support_records.filter(created_at__lt=cutoff_date)
    elif date_filter != 'all':
        try:
            days = int(date_filter)
            cutoff_date = timezone.now() - timedelta(days=days)
            support_records = support_records.filter(created_at__gte=cutoff_date)
        except ValueError:
            pass  # Invalid days value, show all
    
    # Apply search filter
    if search_query:
        matching_ids = []
        
        # Search tenants
        tenant_ids = Tenant.objects.filter(
            Q(name__icontains=search_query) | Q(slug__icontains=search_query)
        ).values_list('id', flat=True)
        matching_ids.extend([('tenant', tid) for tid in tenant_ids])
        
        # Search vacancies
        vacancy_ids = Vacancy.objects.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        ).values_list('id', flat=True)
        matching_ids.extend([('vacancy', vid) for vid in vacancy_ids])
        
        # Search conferences
        conference_ids = Conference.objects.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        ).values_list('id', flat=True)
        matching_ids.extend([('conference', cid) for cid in conference_ids])
        
        # Search users
        user_ids = CustomUser.objects.filter(
            Q(username__icontains=search_query) | 
            Q(first_name__icontains=search_query) | 
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        ).values_list('id', flat=True)
        matching_ids.extend([('user', uid) for uid in user_ids])
        
        # Search guest users
        guest_ids = GuestUser.objects.filter(
            email__icontains=search_query
        ).values_list('id', flat=True)
        matching_ids.extend([('guest', gid) for gid in guest_ids])
        
        # Filter support records by matching entities
        if matching_ids:
            query_filter = Q()
            for entity_type, entity_id in matching_ids:
                query_filter |= Q(entity_type=entity_type, entity_id=entity_id)
            support_records = support_records.filter(query_filter)
        else:
            # No matches found
            support_records = support_records.none()
    
    # Order by most recent first
    support_records = support_records.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(support_records, 25)  # 25 records per page
    try:
        support_records_page = paginator.page(page_number)
    except PageNotAnInteger:
        support_records_page = paginator.page(1)
    except EmptyPage:
        support_records_page = paginator.page(paginator.num_pages)
    
    # Get counts for each entity type (for tab badges)
    entity_counts = {
        'all': CustomerSupport.objects.count(),
        'tenant': CustomerSupport.objects.filter(entity_type='tenant').count(),
        'vacancy': CustomerSupport.objects.filter(entity_type='vacancy').count(),
        'conference': CustomerSupport.objects.filter(entity_type='conference').count(),
        'user': CustomerSupport.objects.filter(entity_type='user').count(),
        'guest': CustomerSupport.objects.filter(entity_type='guest').count(),
    }
    
    # Get status counts
    status_counts = {
        'all': CustomerSupport.objects.count(),
        'new': CustomerSupport.objects.filter(status='new').count(),
        'contacted': CustomerSupport.objects.filter(status='contacted').count(),
        'follow_up': CustomerSupport.objects.filter(status='follow_up').count(),
        'converted': CustomerSupport.objects.filter(status='converted').count(),
        'inactive': CustomerSupport.objects.filter(status='inactive').count(),
    }
    
    # Get count for past records (older than 30 days)
    past_cutoff = timezone.now() - timedelta(days=30)
    past_records_count = CustomerSupport.objects.filter(created_at__lt=past_cutoff).count()
    
    # Build query string for pagination links (preserve filters)
    query_params = request.GET.copy()
    if 'page' in query_params:
        query_params.pop('page')
    query_string = query_params.urlencode()
    
    context = {
        'support_records': support_records_page,
        'entity_counts': entity_counts,
        'status_counts': status_counts,
        'past_records_count': past_records_count,
        'current_entity_filter': entity_filter,
        'current_date_filter': date_filter,
        'current_status_filter': status_filter,
        'search_query': search_query,
        'query_string': query_string,
        'paginator': paginator,
    }
    
    return render(request, 'support/dashboard.html', context)


@support_update_permission_required
@require_POST
def mark_as_contacted(request, support_id):
    """
    Mark a CustomerSupport record as contacted.
    Allows adding notes about the contact.
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)
    
    # Get notes from POST data
    notes_text = request.POST.get('notes', '').strip()
    
    # Mark as contacted
    support_record.mark_contacted(request.user, notes_text)
    
    messages.success(request, f"Marked {support_record.get_entity_name()} as contacted.")
    
    # Return JSON response for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Marked as contacted',
            'status': support_record.get_status_display(),
            'contacted_by': support_record.contacted_by.username if support_record.contacted_by else None,
            'contacted_at': support_record.contacted_at.strftime('%Y-%m-%d %H:%M') if support_record.contacted_at else None,
        })
    
    # Redirect back to dashboard
    return redirect('support_dashboard')


@support_update_permission_required
@require_POST
def update_support_status(request, support_id):
    """
    Update the status of a CustomerSupport record.
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)
    
    new_status = request.POST.get('status')
    notes_text = request.POST.get('notes', '').strip()
    
    # Validate status
    valid_statuses = [choice[0] for choice in CustomerSupport.STATUS_CHOICES]
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status selected.")
        return redirect('support_dashboard')
    
    # Update status
    support_record.status = new_status
    
    # Add notes if provided
    if notes_text:
        if support_record.notes:
            support_record.notes += f"\n\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {request.user.username}: {notes_text}"
        else:
            support_record.notes = f"[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {request.user.username}: {notes_text}"
    
    support_record.save()
    
    messages.success(request, f"Updated status for {support_record.get_entity_name()} to {support_record.get_status_display()}.")
    
    # Return JSON response for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Status updated',
            'status': support_record.get_status_display(),
        })
    
    return redirect('support_dashboard')


@support_update_permission_required
@require_POST
def add_support_notes(request, support_id):
    """
    Add notes to a CustomerSupport record without changing status.
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)
    
    notes_text = request.POST.get('notes', '').strip()
    
    if not notes_text:
        messages.warning(request, "No notes provided.")
        return redirect('support_dashboard')
    
    # Append notes with timestamp and username
    timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
    new_note = f"[{timestamp}] {request.user.username}: {notes_text}"
    
    if support_record.notes:
        support_record.notes += f"\n\n{new_note}"
    else:
        support_record.notes = new_note
    
    support_record.save()
    
    messages.success(request, "Notes added successfully.")
    
    # Return JSON response for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Notes added',
            'notes': support_record.notes,
        })
    
    return redirect('support_dashboard')


@support_update_permission_required
@require_POST
def delete_support_record(request, support_id):
    """
    Delete a CustomerSupport record AND its underlying entity (Tenant, User, etc.).
    Requires explicit confirmation via POST param 'confirm_delete'='yes'.
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)
    entity_name = support_record.get_entity_name()
    entity_type = support_record.entity_type

    confirm = request.POST.get('confirm_delete', '').strip()
    if confirm != 'yes':
        messages.error(request, "Deletion not confirmed.")
        return redirect('support_record_detail', support_id=support_id)

    # Delete the underlying entity first
    entity = support_record.get_entity()
    if entity:
        try:
            entity.delete()
        except Exception as e:
            messages.error(request, f"Could not delete underlying {entity_type}: {e}")
            return redirect('support_record_detail', support_id=support_id)

    # Then delete the support record itself
    support_record.delete()

    messages.success(request, f"Deleted {entity_type} '{entity_name}' and its support record.")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f"Deleted {entity_name}"})

    return redirect('support_dashboard')


@support_update_permission_required
@require_POST
def convert_user_to_staff(request, support_id):
    """
    Convert a personal user (tenant=None, is_personal=True) to a tenant staff account.
    - Sets user.tenant = chosen tenant, user.is_personal = False
    - Creates StaffProfile from UserProfile data, then deletes UserProfile
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)

    if support_record.entity_type != 'user':
        messages.error(request, "This record is not a user.")
        return redirect('support_record_detail', support_id=support_id)

    user = support_record.get_entity()
    if not user:
        messages.error(request, "User not found.")
        return redirect('support_record_detail', support_id=support_id)

    if user.tenant is not None or not getattr(user, 'is_personal', True):
        messages.error(request, "This user is already associated with a tenant.")
        return redirect('support_record_detail', support_id=support_id)

    tenant_id = request.POST.get('tenant_id', '').strip()
    if not tenant_id:
        messages.error(request, "No tenant selected.")
        return redirect('support_record_detail', support_id=support_id)

    tenant = get_object_or_404(Tenant, id=tenant_id)

    try:
        # Grab existing user profile data (if any)
        user_profile = getattr(user, 'user_profile', None)

        # Build StaffProfile kwargs from UserProfile
        staff_kwargs = {
            'tenant': tenant,
            'user': user,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
        }
        if user_profile:
            for field in [
                'photo', 'middle_name', 'phone_number', 'email', 'date_of_birth',
                'home_address', 'sex', 'religion', 'marital_status',
                'designation', 'location',
            ]:
                val = getattr(user_profile, field, None)
                if val is not None:
                    staff_kwargs[field] = val
            # Use UserProfile first/last if richer
            if user_profile.first_name:
                staff_kwargs['first_name'] = user_profile.first_name
            if user_profile.last_name:
                staff_kwargs['last_name'] = user_profile.last_name

        StaffProfile.objects.create(**staff_kwargs)

        # Delete old UserProfile
        if user_profile:
            user_profile.delete()

        # Update user account
        user.tenant = tenant
        user.is_personal = False
        user.save()

        # Update support record status
        support_record.status = 'converted'
        support_record.save()

        messages.success(
            request,
            f"Converted {user.get_full_name() or user.username} to staff account under '{tenant.name}'."
        )

    except Exception as e:
        messages.error(request, f"Conversion failed: {e}")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Converted to staff account'})

    return redirect('support_record_detail', support_id=support_id)


@support_update_permission_required
@require_POST
def convert_user_to_tenant(request, support_id):
    """
    Convert a personal user to a tenant account holder (on request).
    Creates a new Tenant + CompanyProfile using provided details.
    - tenant.name = org_name
    - tenant.slug = slug
    - tenant.admin = user
    - company_profile.email = provided email or user email
    - company_profile.contact_details = provided phone or user phone
    Also sets user.tenant = new_tenant and user.is_personal = False.
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)

    if support_record.entity_type != 'user':
        messages.error(request, "This record is not a user.")
        return redirect('support_record_detail', support_id=support_id)

    user = support_record.get_entity()
    if not user:
        messages.error(request, "User not found.")
        return redirect('support_record_detail', support_id=support_id)

    if user.tenant is not None or not getattr(user, 'is_personal', True):
        messages.error(request, "This user is already associated with a tenant.")
        return redirect('support_record_detail', support_id=support_id)

    org_name = request.POST.get('org_name', '').strip()
    slug = request.POST.get('slug', '').strip()
    company_email = request.POST.get('company_email', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()

    if not org_name or not slug:
        messages.error(request, "Organisation name and slug are required.")
        return redirect('support_record_detail', support_id=support_id)

    # Check uniqueness
    if Tenant.objects.filter(name=org_name).exists():
        messages.error(request, f"A tenant with the name '{org_name}' already exists.")
        return redirect('support_record_detail', support_id=support_id)
    if Tenant.objects.filter(slug=slug).exists():
        messages.error(request, f"A tenant with the slug '{slug}' already exists.")
        return redirect('support_record_detail', support_id=support_id)

    try:
        from documents.models import CompanyProfile

        # Create tenant
        tenant = Tenant.objects.create(
            name=org_name,
            slug=slug,
            admin=user,
            created_by=request.user,
        )

        # Resolve email & phone fallbacks
        final_email = company_email or user.email or ''
        user_profile = getattr(user, 'user_profile', None)
        final_phone = phone_number or (
            getattr(user_profile, 'phone_number', '') if user_profile else ''
        ) or ''

        # Create company profile
        CompanyProfile.objects.create(
            tenant=tenant,
            company_name=org_name,
            email=final_email or None,
            contact_details=final_phone or None,
        )

        # Update user account
        user.tenant = tenant
        user.is_personal = False
        user.save()

        # Grab existing user profile data (if any)
        user_profile = getattr(user, 'user_profile', None)

        # Build StaffProfile kwargs from UserProfile
        staff_kwargs = {
            'tenant': tenant,
            'user': user,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
        }
        if user_profile:
            for field in [
                'photo', 'middle_name', 'phone_number', 'email', 'date_of_birth',
                'home_address', 'sex', 'religion', 'marital_status',
                'designation', 'location',
            ]:
                val = getattr(user_profile, field, None)
                if val is not None:
                    staff_kwargs[field] = val
            # Use UserProfile first/last if richer
            if user_profile.first_name:
                staff_kwargs['first_name'] = user_profile.first_name
            if user_profile.last_name:
                staff_kwargs['last_name'] = user_profile.last_name

        StaffProfile.objects.create(**staff_kwargs)

        # Delete old UserProfile
        if user_profile:
            user_profile.delete()

        # Update support record
        support_record.status = 'converted'
        support_record.save()

        messages.success(
            request,
            f"Created tenant '{org_name}' and assigned {user.get_full_name() or user.username} as admin."
        )

    except Exception as e:
        messages.error(request, f"Conversion failed: {e}")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Converted to tenant account'})

    return redirect('support_record_detail', support_id=support_id)


@support_dashboard_permission_required
def support_record_detail(request, support_id):
    """
    View detailed information about a specific CustomerSupport record.
    Shows full notes history and entity details.
    """
    support_record = get_object_or_404(CustomerSupport, id=support_id)
    entity = support_record.get_entity()
    
    # Get entity-specific details
    entity_details = {}
    if support_record.entity_type == 'tenant' and entity:
        entity_details = {
            'name': entity.name,
            'slug': entity.slug,
            'admin': entity.admin,
            'created_by': entity.created_by,
            'is_verified': entity.is_verified,
            'subscription_status': entity.subscription_status,
        }
    elif support_record.entity_type == 'vacancy' and entity:
        entity_details = {
            'title': entity.title,
            'tenant': entity.tenant,
            'created_by': entity.created_by,
            'status': entity.status,
            'work_mode': entity.work_mode,
        }
    elif support_record.entity_type == 'conference' and entity:
        entity_details = {
            'title': entity.title,
            'tenant': entity.tenant,
            'organizer': entity.organizer,
            'start_date': entity.start_date,
            'conference_type': entity.conference_type,
        }
    elif support_record.entity_type == 'user' and entity:
        entity_details = {
            'username': entity.username,
            'email': entity.email,
            'full_name': entity.get_full_name(),
            'tenant': entity.tenant,
            'date_joined': entity.date_joined,
        }
    elif support_record.entity_type == 'guest' and entity:
        entity_details = {
            'email': entity.email,
            'created_at': entity.created_at,
            'last_accessed_at': entity.last_accessed_at,
        }
    
    # Provide tenant list for convert-to-staff modal (only relevant for personal users)
    all_tenants = []
    if support_record.entity_type == 'user' and entity and entity.tenant is None:
        all_tenants = Tenant.objects.order_by('name')

    context = {
        'support_record': support_record,
        'entity': entity,
        'entity_details': entity_details,
        'all_tenants': all_tenants,
    }
    
    return render(request, 'support/record_detail.html', context)