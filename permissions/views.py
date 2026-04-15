from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import Http404

from .models import Permission, PermissionStep, PermissionAttachment, PermissionComment, PermissionCategory, PermissionSetting
from .forms import (
    PermissionCreateForm, PermissionForwardForm, PermissionCommentForm,
    PermissionExternalSubmissionForm, PermissionCategoryForm, PermissionSettingForm,
)
from documents.models import CustomUser, Role, Notification, UserNotification
from tenants.models import Tenant
from django.core.mail import send_mail
from django.template.loader import render_to_string
from raadaa import settings as django_settings


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_receptionist_users(tenant):
    """Get users with the Receptionist role for a tenant."""
    try:
        role = Role.objects.get(name='Receptionist')
        return CustomUser.objects.filter(tenant=tenant, roles=role, is_active=True)
    except Role.DoesNotExist:
        return CustomUser.objects.none()


def _handle_attachments(request, permission, step=None):
    """Save uploaded attachments for a permission."""
    files = request.FILES.getlist('attachments')
    user = getattr(request, 'effective_user', None)
    for f in files:
        PermissionAttachment.objects.create(
            permissions=permission,
            step=step,
            file=f,
            original_name=f.name,
            uploaded_by=user,
        )


def _get_next_step_number(permission):
    """Get the next step number for a permission."""
    last = permission.steps.order_by('-step_number').first()
    return (last.step_number + 1) if last else 1


def _require_note(request, error_message):
    """Get trimmed note from POST; enforce non-empty."""
    note = (request.POST.get('note', '') or '').strip()
    if not note:
        messages.error(request, error_message, extra_tags='permissions')
        return None
    return note


# ─── Super Admin Dashboard ──────────────────────────────────────────────────

@login_required
def superadmin_permissions_dashboard(request):
    """
    Super Admin dashboard showing all permissions across all tenants.
    Only accessible to superusers and staff.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'You do not have permission to access this page.', extra_tags='permissions')
        return redirect('permissions:dashboard')

    # All permissions across all tenants
    all_memos = Permission.objects.all().select_related('tenant', 'created_by', 'current_holder', 'category')
    all_steps = PermissionStep.objects.all()
    
    # Date filtering
    from django.utils.timezone import now, timedelta
    today = now()
    last_7_days = today - timedelta(days=7)
    last_30_days = today - timedelta(days=30)
    
    # Core statistics - Status
    stats = {
        'total': all_memos.count(),
        'today': all_memos.filter(created_at__date=today.date()).count(),
        'last_7_days': all_memos.filter(created_at__gte=last_7_days).count(),
        'last_30_days': all_memos.filter(created_at__gte=last_30_days).count(),
        'pending': all_memos.filter(status='pending').count(),
        'in_progress': all_memos.filter(status='in_progress').count(),
        'in_view': all_memos.filter(status='in_view').count(),
        'escalated': all_memos.filter(status='escalated').count(),
        'approved': all_memos.filter(status='approved').count(),
        'rejected': all_memos.filter(status='rejected').count(),
        'positive_response': all_memos.filter(status='positive_response').count(),
        'negative_response': all_memos.filter(status='negative_response').count(),
        'completed': all_memos.filter(status='completed').count(),
        'closed': all_memos.filter(status='closed').count(),
        'external': all_memos.filter(is_external=True).count(),
        'internal': all_memos.filter(is_external=False).count(),
    }
    
    # Action statistics - Track all actions taken on permissions
    action_stats = {
        'created': all_steps.filter(action='created').count(),
        'forwarded': all_steps.filter(action='forwarded').count(),
        'approved': all_steps.filter(action='approved').count(),
        'rejected': all_steps.filter(action='rejected').count(),
        'escalated': all_steps.filter(action='escalated').count(),
        'returned': all_steps.filter(action='returned').count(),
        'received': all_steps.filter(action='received').count(),
        'positive_response': all_steps.filter(action='positive_response').count(),
        'negative_response': all_steps.filter(action='negative_response').count(),
        'kept_in_view': all_steps.filter(action='kept_in_view').count(),
        'request_info': all_steps.filter(action='request_info').count(),
    }
    
    # Combine for total activity
    stats['total_actions'] = sum(action_stats.values())
    
    # Status breakdown for chart
    status_data = {
        'labels': ['Pending', 'In Progress', 'In View', 'Escalated', 'Approved', 'Rejected', 'Positive Response', 'Negative Response', 'Completed', 'Closed'],
        'data': [
            stats['pending'], stats['in_progress'], stats['in_view'], stats['escalated'],
            stats['approved'], stats['rejected'], stats['positive_response'], stats['negative_response'], stats['completed'], stats['closed']
        ],
        'colors': ['#f59e0b', '#0ea5e9', '#6366f1', '#dc2626', '#16a34a', '#b91c1c', '#8b5cf6', '#ec4899', '#111827', '#6b7280']
    }
    
    # Priority breakdown
    priority_stats = {
        'low': all_memos.filter(priority='low').count(),
        'medium': all_memos.filter(priority='medium').count(),
        'high': all_memos.filter(priority='high').count(),
        'urgent': all_memos.filter(priority='urgent').count(),
    }
    
    # Tenant-wise breakdown
    tenant_stats = []
    for tenant in Tenant.objects.all().order_by('name'):
        tenant_memos = all_memos.filter(tenant=tenant)
        tenant_stats.append({
            'tenant': tenant,
            'total': tenant_memos.count(),
            'pending': tenant_memos.filter(status='pending').count(),
            'completed': tenant_memos.filter(status='completed').count(),
            'escalated': tenant_memos.filter(status='escalated').count(),
        })
    
    # Personal permissions (no tenant)
    personal_memos = all_memos.filter(tenant=None)
    if personal_memos.exists():
        tenant_stats.insert(0, {
            'tenant': {'name': 'Personal', 'slug': 'personal'},
            'total': personal_memos.count(),
            'pending': personal_memos.filter(status='pending').count(),
            'completed': personal_memos.filter(status='completed').count(),
            'escalated': personal_memos.filter(status='escalated').count(),
        })
    
    # Top 10 most active tenants by permission count
    top_tenants = sorted(tenant_stats, key=lambda x: x['total'], reverse=True)[:10]
    
    # Daily trend (last 30 days)
    daily_trend = []
    for i in range(29, -1, -1):
        date = today.date() - timedelta(days=i)
        count = all_memos.filter(created_at__date=date).count()
        daily_trend.append({'date': date.strftime('%Y-%m-%d'), 'count': count})
    
    # Recent permissions with tenant info
    recent_memos = all_memos.order_by('-created_at')[:20]
    
    # Most active users (by permission creation)
    from django.db.models import Count as DjangoCount
    active_creators = CustomUser.objects.filter(
        created_memos__isnull=False
    ).annotate(
        memo_count=DjangoCount('created_memos')
    ).order_by('-memo_count')[:10]
    
    # Most active current holders
    active_holders = CustomUser.objects.filter(
        held_memos__isnull=False
    ).annotate(
        holding_count=DjangoCount('held_memos')
    ).order_by('-holding_count')[:10]
    
    # External vs Internal over time (last 30 days)
    external_trend = []
    for i in range(29, -1, -1):
        date = today.date() - timedelta(days=i)
        external_count = all_memos.filter(created_at__date=date, is_external=True).count()
        internal_count = all_memos.filter(created_at__date=date, is_external=False).count()
        external_trend.append({
            'date': date.strftime('%Y-%m-%d'),
            'external': external_count,
            'internal': internal_count
        })
    
    # Category distribution
    categories = PermissionCategory.objects.all()
    category_stats = []
    for cat in categories:
        cat_count = all_memos.filter(category=cat).count()
        if cat_count > 0:
            category_stats.append({
                'name': cat.name,
                'count': cat_count,
                'color': cat.color if hasattr(cat, 'color') and cat.color else '#667eea'
            })
    category_stats = sorted(category_stats, key=lambda x: x['count'], reverse=True)[:8]
    
    # Overdue permissions (urgent/high priority pending for more than 3 days, or escalated)
    from django.utils.timezone import now
    three_days_ago = now() - timedelta(days=3)
    overdue_memos = all_memos.filter(
        Q(priority__in=['urgent', 'high'], status__in=['pending', 'in_progress'], created_at__lt=three_days_ago) |
        Q(status='escalated')
    ).order_by('-created_at')[:10]
    
    # Average processing time (for completed permissions)
    from django.db.models import Avg, F, ExpressionWrapper, DurationField
    completed_memos = all_memos.filter(status='completed', completed_at__isnull=False)
    avg_processing_time = completed_memos.annotate(
        duration=ExpressionWrapper(
            F('completed_at') - F('created_at'),
            output_field=DurationField()
        )
    ).aggregate(avg_duration=Avg('duration'))['avg_duration']
    
    # Convert to hours for display
    avg_hours = None
    if avg_processing_time:
        avg_hours = round(avg_processing_time.total_seconds() / 3600, 1)
    
    context = {
        'stats': stats,
        'action_stats': action_stats,
        'status_data': status_data,
        'priority_stats': priority_stats,
        'tenant_stats': tenant_stats,
        'top_tenants': top_tenants,
        'daily_trend': daily_trend,
        'recent_memos': recent_memos,
        'active_creators': active_creators,
        'active_holders': active_holders,
        'external_trend': external_trend,
        'category_stats': category_stats,
        'overdue_memos': overdue_memos,
        'avg_processing_hours': avg_hours,
        'overdue_count': overdue_memos.count(),
    }
    return render(request, 'permissions/superadmin_analytics.html', context)

@login_required
def permissions_dashboard(request):
    """Permission dashboard showing inbox, outbox, and summary stats."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Check if user is admin or superuser
    is_admin = user.roles.filter(name='Admin').exists() or user.is_superuser

    # Inbox: permissions where user has a step assigned to them OR is current holder
    if tenant:
        inbox = Permission.objects.filter(
            Q(tenant=tenant) & 
            (Q(current_holder=user) | Q(steps__to_user=user))
        ).exclude(status__in=['completed', 'closed']).distinct()
        # Outbox: prioritize active permissions, show completed only if no active ones
        outbox_active = Permission.objects.filter(tenant=tenant, created_by=user).exclude(status__in=['completed', 'closed'])
        outbox_completed = Permission.objects.filter(tenant=tenant, created_by=user, status__in=['completed', 'closed'])
        all_memos = Permission.objects.filter(tenant=tenant)
    else:
        inbox = Permission.objects.filter(
            Q(tenant=None) & 
            (Q(current_holder=user) | Q(steps__to_user=user))
        ).exclude(status__in=['completed', 'closed']).distinct()
        # Outbox: prioritize active permissions, show completed only if no active ones
        outbox_active = Permission.objects.filter(tenant=None, created_by=user).exclude(status__in=['completed', 'closed'])
        outbox_completed = Permission.objects.filter(tenant=None, created_by=user, status__in=['completed', 'closed'])
        all_memos = Permission.objects.filter(tenant=None, created_by=user)

    # If there are active permissions, show only active ones; otherwise show completed ones
    if outbox_active.exists():
        outbox = outbox_active
    else:
        outbox = outbox_completed

    # Pagination for inbox
    inbox_page = request.GET.get('inbox_page', 1)
    inbox_paginator = Paginator(inbox.order_by('-updated_at'), 7)
    inbox_memos = inbox_paginator.get_page(inbox_page)

    # Pagination for outbox
    outbox_page = request.GET.get('outbox_page', 1)
    outbox_paginator = Paginator(outbox.order_by('-created_at'), 7)
    outbox_memos = outbox_paginator.get_page(outbox_page)

    stats = {
        'total': all_memos.exclude(status__in=['completed', 'closed']).count(),
        'pending': all_memos.filter(status='pending').count(),
        'in_progress': all_memos.filter(status='in_progress').count(),
        'approved': all_memos.filter(steps__action='approved').exclude(status__in=['completed', 'closed']).distinct().count(),
        'rejected': all_memos.filter(steps__action='rejected').exclude(status__in=['completed', 'closed']).distinct().count(),
        'escalated': all_memos.filter(steps__action='escalated').exclude(status__in=['completed', 'closed']).distinct().count(),
        'created': all_memos.filter(steps__action='created').exclude(status__in=['completed', 'closed']).distinct().count(),
        'positive_response': all_memos.filter(steps__action='positive_response').exclude(status__in=['completed', 'closed']).distinct().count(),
        'negative_response': all_memos.filter(steps__action='negative_response').exclude(status__in=['completed', 'closed']).distinct().count(),
        'kept_in_view': all_memos.filter(steps__action='kept_in_view').exclude(status__in=['completed', 'closed']).distinct().count(),
        'external': all_memos.filter(is_external=True).exclude(status__in=['completed', 'closed']).count(),
    }

    context = {
        'inbox': inbox_memos,
        'outbox': outbox_memos,
        'inbox_count': inbox.count(),
        'outbox_count': outbox.count(),
        'stats': stats,
        'is_admin': is_admin,
    }
    return render(request, 'permissions/dashboard.html', context)


# ─── Permission List ──────────────────────────────────────────────────────────────

@login_required
def permissions_list(request):
    """List all permissions with search and filter."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permissions = Permission.objects.filter(tenant=tenant)
    else:
        permissions = Permission.objects.filter(tenant=None, created_by=user)

    # Filters
    status = request.GET.get('status', '')
    priority = request.GET.get('priority', '')
    category = request.GET.get('category', '')
    search = request.GET.get('search', '')
    view_type = request.GET.get('view', '')  # inbox / outbox / all

    if status:
        permissions = permissions.filter(status=status)
    if priority:
        permissions = permissions.filter(priority=priority)
    if category:
        permissions = permissions.filter(category_id=category)
    if search:
        permissions = permissions.filter(
            Q(title__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(description__icontains=search) |
            Q(external_name__icontains=search)
        )
    if view_type == 'inbox':
        permissions = permissions.filter(Q(current_holder=user) | Q(steps__to_user=user)).distinct()
    elif view_type == 'outbox':
        permissions = permissions.filter(created_by=user)

    permissions = permissions.order_by('-updated_at')

    paginator = Paginator(permissions, 12)
    page = request.GET.get('page')
    permissions = paginator.get_page(page)

    categories = PermissionCategory.objects.filter(tenant=tenant) if tenant else PermissionCategory.objects.filter(tenant=None)

    context = {
        'permissions': permissions,
        'status': status,
        'priority': priority,
        'category': category,
        'search': search,
        'view_type': view_type,
        'categories': categories,
    }
    return render(request, 'permissions/permissions_list.html', context)


# ─── Create ─────────────────────────────────────────────────────────────────

@login_required
def permissions_create(request):
    """Create a new internal permission."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = PermissionCreateForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            action = request.POST.get('action')
            is_draft = action == 'draft'

            permission = form.save(commit=False)
            permission.tenant = tenant
            permission.created_by = user
            permission.status = 'draft' if is_draft else 'pending'

            forward_to = form.cleaned_data.get('forward_to')
            if is_draft:
                permission.current_holder = user
            elif forward_to and forward_to.exists():
                permission.current_holder = forward_to.first()
            else:
                # Assign to receptionist pool or self
                receptionists = _get_receptionist_users(tenant) if tenant else CustomUser.objects.none()
                if receptionists.exists():
                    permission.current_holder = receptionists.first()
                else:
                    permission.current_holder = user

            permission.save()

            if is_draft:
                step = PermissionStep.objects.create(
                    permissions=permission,
                    step_number=1,
                    from_user=user,
                    to_user=user,
                    action='drafted',
                    note=form.cleaned_data.get('note', ''),
                )
                _handle_attachments(request, permission, step=step)
                # Assign to_users for draft as well
                permission.to_users.set(forward_to)
                messages.success(request, f'Permission {permission.reference_number} saved as draft.', extra_tags='permissions')
                return redirect('permissions:permissions_detail', pk=permission.pk)

            # Assign to_users with all forward_to recipients
            permission.to_users.set(forward_to)

            # Persist CC/BCC users on the permission
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])
            permission.cc_users.set(cc_users)
            permission.bcc_users.set(bcc_users)

            # Handle attachments - create them first before steps
            note_text = form.cleaned_data.get('note', '')

            # Create steps for ALL forward_to recipients
            forwarded_users = list(forward_to) if forward_to else []
            step_number = 1
            for forward_user in forwarded_users:
                step = PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=forward_user,
                    action='created',
                    note=note_text,
                )
                step_number += 1

            # Create a temporary step for attachments (linked to first recipient)
            first_step = permission.steps.first()
            _handle_attachments(request, permission, step=first_step)

            # Create notifications for all forward_to recipients
            for forward_user in forwarded_users:
                _create_permissions_notification(
                    tenant=tenant,
                    user=forward_user,
                    title=f"New Permission: {permission.title}",
                    message=f"A new permission has been created and assigned to you by {permission.submitter_display}.",
                    permission=permission
                )

            # Create steps and notify CC users
            for cc_user in cc_users:
                # Create step for CC user
                PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action='created',
                    note=f"CC: {note_text}",
                )
                step_number += 1
                
                # Notify CC user
                _create_permissions_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"New Permission (CC): {permission.title}",
                    message=f"You have been CC'd on a new permission by {permission.submitter_display}.",
                    permission=permission
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                # Create step for BCC user
                PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action='created',
                    note=f"BCC: {note_text}",
                )
                step_number += 1
                
                # Notify BCC user
                _create_permissions_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"New Permission: {permission.title}",
                    message=f"A new permission has been shared with you by {permission.submitter_display}.",
                    permission=permission
                )

            messages.success(request, f'Permission {permission.reference_number} created successfully.', extra_tags='permissions')
            return redirect('permissions:permissions_detail', pk=permission.pk)
    else:
        form = PermissionCreateForm(request=request)

    return render(request, 'permissions/permissions_create.html', {'form': form})


@login_required
def permissions_edit(request, pk):
    """Edit a draft permission."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant, created_by=user, status='draft')
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user, status='draft')

    if request.method == 'POST':
        form = PermissionCreateForm(request.POST, request.FILES, request=request, instance=permission)
        if form.is_valid():
            action = request.POST.get('action')
            is_draft = action == 'draft'

            permission = form.save(commit=False)
            permission.status = 'draft' if is_draft else 'pending'

            forward_to = form.cleaned_data.get('forward_to')
            if is_draft:
                permission.current_holder = user
            elif forward_to and forward_to.exists():
                permission.current_holder = forward_to.first()
            else:
                receptionists = _get_receptionist_users(tenant) if tenant else CustomUser.objects.none()
                if receptionists.exists():
                    permission.current_holder = receptionists.first()
                else:
                    permission.current_holder = user

            permission.save()

            if is_draft:
                step = PermissionStep.objects.create(
                    permissions=permission,
                    step_number=_get_next_step_number(permission),
                    from_user=user,
                    to_user=user,
                    action='drafted',
                    note=form.cleaned_data.get('note', ''),
                )
                _handle_attachments(request, permission, step=step)
                # Assign to_users for draft as well
                permission.to_users.set(forward_to)
                messages.success(request, f'Draft permission {permission.reference_number} updated.', extra_tags='permissions')
                return redirect('permissions:permissions_detail', pk=permission.pk)

            # Assign to_users with all forward_to recipients
            permission.to_users.set(forward_to)

            # Persist CC/BCC users on the permission
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])
            permission.cc_users.set(cc_users)
            permission.bcc_users.set(bcc_users)

            # Permission is being sent - create steps for ALL recipients
            note_text = form.cleaned_data.get('note', '')
            step_number = _get_next_step_number(permission)
            
            # Create steps for all forward_to recipients
            forwarded_users = list(forward_to) if forward_to else []
            for forward_user in forwarded_users:
                step = PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=forward_user,
                    action='created',
                    note=note_text,
                )
                step_number += 1
            
            # Handle attachments with first step
            first_step = permission.steps.first()
            _handle_attachments(request, permission, step=first_step)

            # Create notifications for all forward_to recipients
            for forward_user in forwarded_users:
                _create_permissions_notification(
                    tenant=tenant,
                    user=forward_user,
                    title=f"New Permission: {permission.title}",
                    message=f"A new permission has been sent to you by {permission.submitter_display}.",
                    permission=permission
                )
            
            # Create steps and notify CC users
            for cc_user in cc_users:
                PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action='created',
                    note=f"CC: {note_text}",
                )
                step_number += 1
                
                _create_permissions_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"New Permission (CC): {permission.title}",
                    message=f"You have been CC'd on a new permission by {permission.submitter_display}.",
                    permission=permission
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action='created',
                    note=f"BCC: {note_text}",
                )
                step_number += 1
                
                _create_permissions_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"New Permission: {permission.title}",
                    message=f"A new permission has been shared with you by {permission.submitter_display}.",
                    permission=permission
                )
                    

            messages.success(request, f'Permission {permission.reference_number} sent successfully.', extra_tags='permissions')
            return redirect('permissions:permissions_detail', pk=permission.pk)
    else:
        form = PermissionCreateForm(request=request, instance=permission)

    return render(request, 'permissions/permissions_edit.html', {'form': form, 'permission': permission})



# ─── Detail ─────────────────────────────────────────────────────────────────

@login_required
def permissions_detail(request, pk):
    """View full permission trail with steps, comments, and attachments."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    # Most recent first so the earliest (step 1) sits at the bottom.
    steps = permission.steps.select_related('from_user', 'to_user').order_by('-step_number')
    attachments = permission.attachments.select_related('uploaded_by', 'step').order_by('uploaded_at')

    # Filter comments based on privacy
    all_comments = permission.comments.select_related('author', 'step').order_by('created_at')
    visible_comments = []
    for comment in all_comments:
        if not comment.is_private:
            visible_comments.append(comment)
        elif comment.author == user or permission.current_holder == user:
            visible_comments.append(comment)

    # Determine available actions
    is_holder = (permission.current_holder == user)
    is_creator = (permission.created_by == user)
    # Check if user is a recipient (has a step assigned to them)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    # Recipients can act on the permission (forward, approve, reject, etc.)
    can_act = (is_holder or is_recipient) and permission.can_be_acted_on
    
    can_forward = can_act
    can_approve = can_act
    can_reject = can_act
    can_request_info = can_act and not is_creator
    can_escalate = (is_holder or is_creator or is_recipient) and permission.can_be_acted_on
    can_complete = is_creator and permission.status == 'approved'
    can_close = is_creator and permission.status == 'rejected'
    can_reopen = is_creator and permission.status in ('closed', 'completed')
    can_mark_in_progress = (is_holder or is_creator or is_recipient) and permission.status in ['pending', 'in_view', 'escalated']
    can_keep_in_view = (is_holder or is_creator or is_recipient) and permission.status == 'pending'
    can_record_response = can_act and not (is_creator and permission.status == 'pending')
    # Withdraw: creator can withdraw a permission while it's still pending
    can_withdraw = is_creator and permission.status == 'pending'

    comment_form = PermissionCommentForm()
    forward_form = PermissionForwardForm(request=request, permissions=permission)

    context = {
        'permission': permission,
        'steps': steps,
        'attachments': attachments,
        'comments': visible_comments,
        'comment_form': comment_form,
        'forward_form': forward_form,
        'is_holder': is_holder,
        'is_creator': is_creator,
        'is_recipient': is_recipient,
        'can_forward': can_forward,
        'can_approve': can_approve,
        'can_reject': can_reject,
        'can_request_info': can_request_info,
        'can_escalate': can_escalate,
        'can_complete': can_complete,
        'can_close': can_close,
        'can_reopen': can_reopen,
        'can_mark_in_progress': can_mark_in_progress,
        'can_keep_in_view': can_keep_in_view,
        'can_record_response': can_record_response,
        'can_withdraw': can_withdraw,
    }
    return render(request, 'permissions/permissions_detail.html', context)


# ─── Forward / Route ────────────────────────────────────────────────────────

@login_required
def permissions_forward(request, pk):
    """Forward/route a permission to the next person with an action."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (permission.current_holder == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this permission.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if not permission.can_be_acted_on:
        messages.error(request, 'This permission cannot be acted on in its current state.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if request.method == 'POST':
        form = PermissionForwardForm(request.POST, request.FILES, request=request, permissions=permission)
        if form.is_valid():
            to_users = form.cleaned_data['to_users']
            action = form.cleaned_data['action']
            note = form.cleaned_data.get('note', '')
            is_private = form.cleaned_data.get('is_private_note', False)

            # Get CC and BCC users
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])

            # Persist CC/BCC users on the permission
            permission.cc_users.set(cc_users)
            permission.bcc_users.set(bcc_users)

            # Create steps for ALL to_users recipients
            step_number = _get_next_step_number(permission)
            routed_users = list(to_users)
            
            for to_user in routed_users:
                step = PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=to_user,
                    action=action,
                    note=note,
                    is_private_note=is_private,
                )
                step_number += 1

            # Handle attachments with first step
            first_step = permission.steps.order_by('-step_number').first()
            _handle_attachments(request, permission, step=first_step)

            # Update permission state
            # The person who is acting becomes the current holder (tracks who last acted)
            # Then based on the action, we may route it to someone else
            primary_to_user = routed_users[0] if routed_users else user
            
            if action == 'approved':
                permission.status = 'approved'
                # For approval, if routing to someone specific, they become holder
                # Otherwise, the person who approved becomes the holder
                permission.current_holder = primary_to_user
            elif action == 'rejected':
                permission.status = 'rejected'
                # For rejection, send back to creator
                permission.current_holder = permission.created_by
            elif action == 'escalated':
                permission.status = 'escalated'
                # For escalation, send to the escalation recipient
                permission.current_holder = primary_to_user
            elif action == 'returned':
                permission.status = 'in_view'
                # For return, send back to creator
                permission.current_holder = permission.created_by
            else:
                # For forward/minute, send to the first new recipient
                permission.status = 'pending'
                permission.current_holder = primary_to_user
            permission.save()

            # Create notifications for all to_users recipients
            for routed_user in routed_users:
                _create_permissions_notification(
                    tenant=tenant,
                    user=routed_user,
                    title="Permission Routed To You",
                    message=f"Permission '{permission.title}' was routed to you by {user.get_full_name()} ({action}).",
                    permission=permission
                )
            
            # Create steps and notify CC users
            for cc_user in cc_users:
                # Create step for CC user
                PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action=action,
                    note=f"CC: {note}",
                    is_private_note=is_private,
                )
                step_number += 1
                
                # Notify CC user
                _create_permissions_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"Permission Routed (CC): {permission.title}",
                    message=f"You have been CC'd on a permission routed by {user.get_full_name()} ({action}).",
                    permission=permission
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                # Create step for BCC user
                PermissionStep.objects.create(
                    permissions=permission,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action=action,
                    note=f"BCC: {note}",
                    is_private_note=is_private,
                )
                step_number += 1
                
                # Notify BCC user
                _create_permissions_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"Permission Routed: {permission.title}",
                    message=f"A permission has been shared with you by {user.get_full_name()} ({action}).",
                    permission=permission
                )

            # Create success message
            recipient_names = ', '.join([u.get_full_name() or u.username for u in routed_users[:3]])
            if len(routed_users) > 3:
                recipient_names += f' and {len(routed_users) - 3} others'
            
            messages.success(request, f'Permission {action} to {recipient_names}.', extra_tags='permissions')
            return redirect('permissions:permissions_detail', pk=pk)
    else:
        form = PermissionForwardForm(request=request, permissions=permission)

    return render(request, 'permissions/permissions_forward.html', {'form': form, 'permission': permission})


# ─── Quick Actions (approve / reject / escalate) ───────────────────────────

@login_required
def permissions_approve(request, pk):
    """Quick approve and return to creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (permission.current_holder == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this permission.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if request.method == 'POST' and permission.can_be_acted_on:
        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = permission.created_by

        step = PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=to_user,
            action='approved',
            note=request.POST.get('note', ''),
        )
        permission.status = 'approved'
        permission.current_holder = to_user
        permission.save()
        
        # Notify the recipient (send_to user or creator)
        if to_user:
            _create_permissions_notification(
                tenant=tenant,
                user=to_user,
                title="Permission Approved",
                message=f"Permission '{permission.title}' was approved by {user.get_full_name()}.",
                permission=permission
            )
        # Also notify the creator if the permission was sent to someone else
        if send_to_id and permission.created_by and to_user != permission.created_by:
            _create_permissions_notification(
                tenant=tenant,
                user=permission.created_by,
                title="Permission Approved",
                message=f"Your permission '{permission.title}' was approved by {user.get_full_name()} and sent to {to_user.get_full_name()}.",
                permission=permission
            )
        
        messages.success(request, 'Permission approved successfully.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


@login_required
def permissions_reject(request, pk):
    """Quick reject and return to creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (permission.current_holder == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this permission.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if request.method == 'POST' and permission.can_be_acted_on:
        note = (request.POST.get('note', '') or '').strip()
        if not note:
            messages.error(request, 'Please provide a reason for rejection.', extra_tags='permissions')
            return redirect('permissions:permissions_detail', pk=pk)

        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = permission.created_by

        step = PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=to_user,
            action='rejected',
            note=note,
        )
        permission.status = 'rejected'
        permission.current_holder = to_user
        permission.save()
        
        # Notify the recipient (send_to user or creator)
        if to_user:
            _create_permissions_notification(
                tenant=tenant,
                user=to_user,
                title="Permission Rejected",
                message=f"Your permission '{permission.title}' was rejected by {user.get_full_name()}.",
                permission=permission
            )
        
        messages.success(request, 'Permission rejected.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


@login_required
def permissions_escalate(request, pk):
    """Escalate a permission."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    # Both holder and creator can escalate
    if user != permission.current_holder and user != permission.created_by:
        messages.error(request, 'You do not have permission to escalate this permission.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if request.method == 'POST' and permission.can_be_acted_on:
        to_user_id = request.POST.get('escalate_to')
        to_user = get_object_or_404(CustomUser, pk=to_user_id)

        step = PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=to_user,
            action='escalated',
            note=request.POST.get('note', ''),
        )
        permission.status = 'escalated'
        permission.current_holder = to_user
        permission.save()
        
        # Create notification for recipient
        _create_permissions_notification(
            tenant=tenant,
            user=to_user,
            title="Permission Escalated To You",
            message=f"Permission '{permission.title}' was escalated to you by {user.get_full_name()}.",
            permission=permission
        )
        
        messages.success(request, f'Permission escalated to {to_user.username}.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


@login_required
def permissions_request_info(request, pk):
    """Request more information from the permission creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (permission.current_holder == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this permission.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if not permission.can_be_acted_on:
        messages.error(request, 'This permission cannot be acted on in its current state.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if request.method == 'POST':
        note = _require_note(request, 'Please specify what information you need.')
        if note is None:
            return redirect('permissions:permissions_detail', pk=pk)

        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = permission.created_by

        # Return permission to selected user with request for info
        step = PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=to_user,
            action='request_info',
            note=note,
        )
        
        permission.status = 'in_view'
        permission.current_holder = to_user
        permission.save()
        
        # Notify the recipient
        if to_user:
            _create_permissions_notification(
                tenant=tenant,
                user=to_user,
                title="More Information Requested",
                message=f"More information has been requested for your permission '{permission.title}' by {user.get_full_name()}.",
                permission=permission
            )
        
        
        messages.success(request, 'Request for more information sent to creator.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


# ─── Complete / Close / Reopen ──────────────────────────────────────────────

@login_required
def permissions_complete(request, pk):
    """Mark permission as completed (by creator after approval)."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Try to get permission for authenticated users
    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None)

    # Check permissions: either the creator or external user with token
    is_creator = permission.created_by == user
    is_external_with_permission = False
    
    if permission.is_external and not is_creator:
        # Check if this is an external user accessing via their permission
        # External users should use the external_status view with token
        # But if they somehow got here, check permission settings
        memo_setting = PermissionSetting.objects.filter(tenant=tenant).first()
        is_external_with_permission = memo_setting and memo_setting.allow_external_completion
    
    if not (is_creator or is_external_with_permission):
        messages.error(request, 'You do not have permission to complete this permission.', extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=pk)

    if request.method == 'POST' and permission.status == 'approved':
        permission.status = 'completed'
        permission.completed_at = timezone.now()
        permission.save()
        messages.success(request, 'Permission marked as completed.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


@login_required
def permissions_close(request, pk):
    """Mark permission as closed (by creator after rejection)."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant, created_by=user)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and permission.status == 'rejected':
        permission.status = 'closed'
        permission.closed_at = timezone.now()
        permission.save()
        messages.success(request, 'Permission closed.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


@login_required
def permissions_reopen(request, pk):
    """Reopen a closed or completed permission."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant, created_by=user)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and permission.status in ('closed', 'completed'):
        permission.status = 'in_progress'
        permission.closed_at = None
        permission.completed_at = None
        permission.current_holder = user
        permission.save()

        PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=user,
            action='forwarded',
            note='Permission reopened by creator.',
        )
        messages.success(request, 'Permission reopened.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


# ─── Comments ───────────────────────────────────────────────────────────────

@login_required
def permissions_add_comment(request, pk):
    """Add a comment to a permission."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST':
        form = PermissionCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.permission = permission
            comment.author = user
            comment.save()
            messages.success(request, 'Comment added.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


# ─── External Submission ────────────────────────────────────────────────────

def permissions_external_submit(request, slug):
    """Public permission submission form (no auth required)."""
    tenant = get_object_or_404(Tenant, slug=slug)

    if request.method == 'POST':
        form = MemoExternalSubmissionForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            # Find recipient
            staff_suggestion = form.cleaned_data.get('staff_suggestion')
            if staff_suggestion:
                current_holder = staff_suggestion
            else:
                receptionists = _get_receptionist_users(tenant)
                current_holder = receptionists.first() if receptionists.exists() else None

            if not current_holder:
                # Fallback: assign to tenant admin
                current_holder = tenant.admin

            permission = Permission.objects.create(
                tenant=tenant,
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                category=form.cleaned_data.get('category'),
                status='pending',
                priority='medium',
                is_external=True,
                external_name=form.cleaned_data['submitter_name'],
                external_email=form.cleaned_data['submitter_email'],
                external_phone=form.cleaned_data.get('submitter_phone', ''),
                current_holder=current_holder,
                created_by=None,
            )

            # Create initial step
            PermissionStep.objects.create(
                permissions=permission,
                step_number=1,
                from_user=None,
                to_user=current_holder,
                action='received',
                note=f"External submission from {form.cleaned_data['submitter_name']}",
            )

            # Handle attachments
            files = request.FILES.getlist('attachments')
            for f in files:
                PermissionAttachment.objects.create(
                    permissions=permission,
                    file=f,
                    original_name=f.name,
                )

            # Notify the assigned staff member in the bell icon notifications
            if current_holder:
                _create_permissions_notification(
                    tenant=tenant,
                    user=current_holder,
                    title=f"New External Permission: {permission.title}",
                    message=f"You received a new external permission from {permission.external_name or permission.external_email or 'External'} ({permission.reference_number}).",
                    permission=permission
                )

            messages.success(request, 'Your request has been submitted successfully.', extra_tags='permissions')
            return render(request, 'permissions/external_submit_success.html', {
                'permission': permission,
                'tenant': tenant,
            })
    else:
        form = MemoExternalSubmissionForm(tenant=tenant)

    return render(request, 'permissions/external_submit.html', {
        'form': form,
        'tenant': tenant,
    })


def permissions_external_submit_personal(request, token):
    """Public permission submission form for a specific user (no auth required)."""
    from documents.models import CustomUser
    target_user = get_object_or_404(CustomUser, personal_external_token=token, is_active=True)
    tenant = target_user.tenant

    if not tenant:
        return render(request, 'permissions/external_submit.html', {
            'form': None,
            'tenant': None,
            'error': 'This user is not associated with an organization.',
        })

    if request.method == 'POST':
        form = MemoExternalSubmissionForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            # Create permission assigned directly to the target user
            permission = Permission.objects.create(
                tenant=tenant,
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                category=form.cleaned_data.get('category'),
                status='pending',
                priority='medium',
                is_external=True,
                external_name=form.cleaned_data['submitter_name'],
                external_email=form.cleaned_data['submitter_email'],
                external_phone=form.cleaned_data.get('submitter_phone', ''),
                current_holder=target_user,  # Directly assigned to target user
                created_by=None,
            )

            # Create initial step
            PermissionStep.objects.create(
                permissions=permission,
                step_number=1,
                from_user=None,
                to_user=target_user,
                action='received',
                note=f"External submission from {form.cleaned_data['submitter_name']} (sent directly to {target_user.get_full_name() or target_user.username})",
            )

            # Handle attachments
            files = request.FILES.getlist('attachments')
            for f in files:
                PermissionAttachment.objects.create(
                    permissions=permission,
                    file=f,
                    original_name=f.name,
                )

            # Notify the target user
            _create_permissions_notification(
                tenant=tenant,
                user=target_user,
                title=f"New External Permission: {permission.title}",
                message=f"You received a new external permission from {permission.external_name or permission.external_email or 'External'} ({permission.reference_number}).",
                permission=permission
            )

            messages.success(request, 'Your request has been submitted successfully.', extra_tags='permissions')
            return render(request, 'permissions/external_submit_success.html', {
                'permission': permission,
                'tenant': tenant,
            })
    else:
        form = MemoExternalSubmissionForm(tenant=tenant)

    return render(request, 'permissions/external_submit.html', {
        'form': form,
        'tenant': tenant,
        'target_user': target_user,
    })


def permissions_external_status(request, token):
    """External user: view permission status (no auth required)."""
    permission = get_object_or_404(Permission, external_token=token)
    tenant = permission.tenant

    # Check tenant settings
    memo_setting = PermissionSetting.objects.filter(tenant=tenant).first()

    # Most recent first for external tracking view as well.
    steps = permission.steps.order_by('-step_number')
    # External users see all steps, but private notes are hidden
    visible_steps = steps

    # Public comments only
    comments = permission.comments.filter(is_private=False).order_by('created_at')

    can_escalate = memo_setting.allow_external_escalation if memo_setting else False
    can_complete = memo_setting.allow_external_completion if memo_setting else False

    context = {
        'permission': permission,
        'steps': visible_steps,
        'comments': comments,
        'can_escalate': can_escalate and permission.can_be_acted_on,
        'can_complete': can_complete and permission.status == 'approved',
    }
    return render(request, 'permissions/external_status.html', context)


def permissions_external_complete(request, token):
    """External user: mark permission as completed (no auth required)."""
    permission = get_object_or_404(Permission, external_token=token)
    tenant = permission.tenant

    # Check tenant settings
    memo_setting = PermissionSetting.objects.filter(tenant=tenant).first()
    can_complete = memo_setting.allow_external_completion if memo_setting else False

    if not can_complete:
        messages.error(request, 'You do not have permission to complete this permission.', extra_tags='permissions')
        return redirect('permissions:external_status', token=token)

    if request.method == 'POST' and permission.status == 'approved':
        permission.status = 'completed'
        permission.completed_at = timezone.now()
        permission.save()
        
        # Create a step for the completion
        PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            action='completed',
            from_user=None,
            to_user=None,
            note='Marked as completed by external user',
            is_private_note=False
        )
        
        messages.success(request, 'Permission marked as completed.', extra_tags='permissions')

    return redirect('permissions:external_status', token=token)


# ─── Categories ─────────────────────────────────────────────────────────────

@login_required
def permissions_categories(request):
    """List permission categories."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        categories = PermissionCategory.objects.filter(tenant=tenant)
    else:
        categories = PermissionCategory.objects.filter(tenant=None, created_by=user)

    return render(request, 'permissions/categories.html', {'categories': categories})


@login_required
def permissions_category_create(request):
    """Create a permission category."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = PermissionCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.tenant = tenant
            cat.created_by = user
            cat.save()
            messages.success(request, 'Category created.', extra_tags='permissions')
            return redirect('permissions:categories')
    else:
        form = PermissionCategoryForm()

    return render(request, 'permissions/category_form.html', {'form': form, 'action': 'Create'})


@login_required
def permissions_category_edit(request, pk):
    """Edit a permission category."""
    tenant = request.effective_tenant

    if tenant:
        cat = get_object_or_404(PermissionCategory, pk=pk, tenant=tenant)
    else:
        cat = get_object_or_404(PermissionCategory, pk=pk, tenant=None)

    if request.method == 'POST':
        form = PermissionCategoryForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.', extra_tags='permissions')
            return redirect('permissions:categories')
    else:
        form = PermissionCategoryForm(instance=cat)

    return render(request, 'permissions/category_form.html', {'form': form, 'action': 'Edit', 'category': cat})


@login_required
def permissions_category_delete(request, pk):
    """Delete a permission category."""
    tenant = request.effective_tenant

    if tenant:
        cat = get_object_or_404(PermissionCategory, pk=pk, tenant=tenant)
    else:
        cat = get_object_or_404(PermissionCategory, pk=pk, tenant=None)

    if request.method == 'POST':
        cat.delete()
        messages.success(request, 'Category deleted.', extra_tags='permissions')
        return redirect('permissions:categories')

    return render(request, 'permissions/category_confirm_delete.html', {'category': cat})


# ─── Settings ───────────────────────────────────────────────────────────────

@login_required
def permissions_settings(request):
    """Tenant permission settings."""
    tenant = request.effective_tenant
    if not tenant:
        messages.error(request, 'Settings are only available for organization accounts.', extra_tags='permissions')
        return redirect('permissions:dashboard')

    # Check if user is tenant admin or superuser
    is_admin = request.user.is_superuser or request.user.roles.filter(name='Admin').exists()

    setting, created = PermissionSetting.objects.get_or_create(tenant=tenant)

    if request.method == 'POST':
        # Only allow admins to update external submission settings
        if not is_admin:
            messages.error(request, 'You do not have permission to update these settings.', extra_tags='permissions')
            return redirect('permissions:settings')
            
        form = PermissionSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, 'Permission settings updated.', extra_tags='permissions')
            return redirect('permissions:settings')
    else:
        form = PermissionSettingForm(instance=setting)

    # Get staff members for personal links
    # Admins see all staff, regular users only see themselves
    if is_admin:
        staff_members = CustomUser.objects.filter(
            tenant=tenant, 
            is_active=True, 
            is_superuser=False
        ).exclude(
            personal_external_token__isnull=True
        )
    else:
        # Regular users only see their own link if they have one
        if request.user.personal_external_token:
            staff_members = CustomUser.objects.filter(id=request.user.id)
        else:
            staff_members = None

    # Get categories for the tenant
    categories = PermissionCategory.objects.filter(tenant=tenant).order_by('name')

    return render(request, 'permissions/settings.html', {
        'form': form,
        'staff_members': staff_members,
        'categories': categories,
        'is_admin': is_admin,
    })


# ─── Receptionist Management ───────────────────────────────────────────────

@login_required
def permissions_manage_receptionist(request):
    """Assign/revoke Receptionist role (Admin only)."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Only admins can manage this
    is_admin = user.roles.filter(name='Admin').exists() or user.is_superuser
    if not is_admin:
        messages.error(request, 'Only admins can manage the Receptionist role.', extra_tags='permissions')
        return redirect('permissions:dashboard')

    # Ensure the Receptionist role exists
    receptionist_role, _ = Role.objects.get_or_create(name='Receptionist', defaults={'description': 'Handles incoming permissions with no specific recipient'})

    if tenant:
        staff = CustomUser.objects.filter(tenant=tenant, is_active=True)
    else:
        staff = CustomUser.objects.filter(id=user.id)

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        target_user = get_object_or_404(CustomUser, pk=user_id)

        if action == 'assign':
            target_user.roles.add(receptionist_role)
            messages.success(request, f'{target_user.username} assigned as Receptionist.', extra_tags='permissions')
        elif action == 'revoke':
            target_user.roles.remove(receptionist_role)
            messages.success(request, f'Receptionist role removed from {target_user.username}.', extra_tags='permissions')

        return redirect('permissions:manage_receptionist')

    # Annotate who has the role
    receptionist_ids = set(
        _get_receptionist_users(tenant).values_list('id', flat=True)
    ) if tenant else set()

    context = {
        'staff': staff,
        'receptionist_ids': receptionist_ids,
    }
    return render(request, 'permissions/manage_receptionist.html', context)


# ==========================================
# MISSING FEATURES: IN PROGRESS, NOTIFS
# ==========================================

@login_required
def permissions_mark_in_progress(request, pk):
    """Mark a permission as 'In Progress'."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (permission.current_holder == user)
    is_creator = (permission.created_by == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this permission.", extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=permission.pk)

    if request.method == 'POST':
        if permission.status in ['pending', 'in_view', 'escalated']:
            permission.status = 'in_progress'
            permission.current_holder = user  # The person marking it in progress becomes the current holder
            permission.save()
            
            
            messages.success(request, "Permission marked as In Progress.", extra_tags='permissions')
        else:
            messages.error(request, f"Cannot mark as In Progress from state '{permission.get_status_display()}'.", extra_tags='permissions')
    
    return redirect('permissions:permissions_detail', pk=permission.pk)

@login_required
def permissions_keep_in_view(request, pk):
    """Mark a permission as 'In View' manually."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (permission.current_holder == user)
    is_creator = (permission.created_by == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this permission.", extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=permission.pk)

    if request.method == 'POST':
        if permission.can_be_acted_on:
            note = (request.POST.get('note', '') or '').strip()
            if not note:
                note = 'Permission kept in view.'

            # Determine recipient: optional send_to user, or fall back to self
            send_to_id = (request.POST.get('to_user') or '').strip()
            if send_to_id:
                to_user = get_object_or_404(CustomUser, pk=send_to_id)
            else:
                to_user = user

            permission.status = 'in_view'
            permission.current_holder = to_user
            permission.save()

            PermissionStep.objects.create(
                permissions=permission,
                step_number=_get_next_step_number(permission),
                from_user=user,
                to_user=to_user,
                action='kept_in_view',
                note=note,
            )

            # Notify the recipient if different from sender
            if to_user != user:
                _create_permissions_notification(
                    tenant=tenant,
                    user=to_user,
                    title="Permission Kept In-View",
                    message=f"Permission '{permission.title}' was kept in-view and sent to you by {user.get_full_name()}.",
                    permission=permission
                )

            messages.success(request, "Permission marked as In-View.", extra_tags='permissions')
        else:
            messages.error(request, f"Cannot keep In-View from state '{permission.get_status_display()}'.", extra_tags='permissions')
    
    return redirect('permissions:permissions_detail', pk=permission.pk)


@login_required
def permissions_positive_response(request, pk):
    """Record a positive response with a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (permission.current_holder == user)
    is_creator = (permission.created_by == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this permission.", extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=permission.pk)

    if request.method == 'POST' and permission.can_be_acted_on:
        note = _require_note(request, 'Please add a note for the positive response.')
        if note is None:
            return redirect('permissions:permissions_detail', pk=permission.pk)

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=to_user,
            action='positive_response',
            note=note,
        )

        permission.status = 'positive_response'
        permission.current_holder = to_user
        permission.save()

        # Notify the recipient if different from sender
        if to_user != user:
            _create_permissions_notification(
                tenant=tenant,
                user=to_user,
                title="Positive Response",
                message=f"Permission '{permission.title}' received a positive response from {user.get_full_name()}.",
                permission=permission
            )

        messages.success(request, 'Positive response recorded.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=permission.pk)


@login_required
def permissions_negative_response(request, pk):
    """Record a negative response with a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (permission.current_holder == user)
    is_creator = (permission.created_by == user)
    is_recipient = permission.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this permission.", extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=permission.pk)

    if request.method == 'POST' and permission.can_be_acted_on:
        note = _require_note(request, 'Please add a note for the negative response.')
        if note is None:
            return redirect('permissions:permissions_detail', pk=permission.pk)

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=to_user,
            action='negative_response',
            note=note,
        )

        permission.status = 'negative_response'
        permission.current_holder = to_user
        permission.save()

        # Notify the recipient if different from sender
        if to_user != user:
            _create_permissions_notification(
                tenant=tenant,
                user=to_user,
                title="Negative Response",
                message=f"Permission '{permission.title}' received a negative response from {user.get_full_name()}.",
                permission=permission
            )

        messages.success(request, 'Negative response recorded.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=permission.pk)


@login_required
def permissions_keep_in_view_with_note(request, pk):
    """Keep a permission in view and record a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    if permission.current_holder != user and permission.created_by != user:
        messages.error(request, "You don't have permission to update this permission.", extra_tags='permissions')
        return redirect('permissions:permissions_detail', pk=permission.pk)

    if request.method == 'POST' and permission.can_be_acted_on:
        note = _require_note(request, 'Please add a note for keeping this permission in view.')
        if note is None:
            return redirect('permissions:permissions_detail', pk=permission.pk)

        # Always move the permission into the "In View" state while it can still be acted on,
        # so the main status and filters reflect this action.
        permission.status = 'in_view'
        permission.save(update_fields=['status'])

        PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=permission.current_holder,
            action='kept_in_view',
            note=note,
        )
        messages.success(request, 'Permission kept in view with note.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=permission.pk)


@login_required
def permissions_withdraw(request, pk):
    """Withdraw a permission (by creator). Sets status to closed."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        permission = get_object_or_404(Permission, pk=pk, tenant=tenant, created_by=user)
    else:
        permission = get_object_or_404(Permission, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and permission.status == 'pending':
        note = (request.POST.get('note', '') or '').strip()
        if not note:
            note = 'Permission withdrawn by creator.'

        PermissionStep.objects.create(
            permissions=permission,
            step_number=_get_next_step_number(permission),
            from_user=user,
            to_user=user,
            action='withdrawn',
            note=note,
        )
        permission.status = 'closed'
        permission.closed_at = timezone.now()
        permission.save()

        # Notify the current holder if it's not the creator
        if permission.current_holder and permission.current_holder != user:
            _create_permissions_notification(
                tenant=tenant,
                user=permission.current_holder,
                title="Permission Withdrawn",
                message=f"Permission '{permission.title}' was withdrawn by {user.get_full_name()}.",
                permission=permission
            )

        messages.success(request, 'Permission withdrawn successfully.', extra_tags='permissions')
    else:
        messages.error(request, 'This permission cannot be withdrawn.', extra_tags='permissions')

    return redirect('permissions:permissions_detail', pk=pk)


def _create_permissions_notification(tenant, user, title, message, url=None, permission=None):
    """Helper to create a bell icon notification for permission events."""
    from django.contrib.contenttypes.models import ContentType
    try:
        # Build the link URL from the permission if not provided
        if not url and permission:
            url = f"/permissions/{permission.pk}/"

        kwargs = {
            'tenant': tenant,
            'title': title,
            'message': message,
            'type': Notification.NotificationType.MEMO,
            'is_active': True,
            'link': url,
        }

        # Also set generic relation so get_absolute_url() has multiple fallback paths
        if permission:
            kwargs['content_type'] = ContentType.objects.get_for_model(permission)
            kwargs['object_id'] = permission.pk

        notif = Notification.objects.create(**kwargs)
        UserNotification.objects.create(
            tenant=tenant,
            user=user,
            notification=notif
        )
    except Exception as e:
        print(f"Failed to create notification: {e}")


    """Send email to external submitter if tenant settings allow it."""
    if not permission.is_external or not permission.external_email:
        return
        
    try:
        settings = PermissionSetting.objects.get(tenant=permission.tenant)
        if not settings.notify_external_on_move:
            return
            
        subject = f"Permission Update: {permission.title} [{permission.reference_number}]"
        
        base_domain = "127.0.0.1:8000" if django_settings.DEBUG else "teammanager.ng"
        protocol = "http" if django_settings.DEBUG else "https"
        status_url = f"{protocol}://{base_domain}/permission/external/status/{permission.external_token}/"
        
        html_message = f"""
        <html><body>
        <h2>Your Permission has been updated</h2>
        <p><strong>Reference:</strong> {permission.reference_number}</p>
        <p><strong>Title:</strong> {permission.title}</p>
        <p><strong>New Action/Status:</strong> {action_taken} ({permission.get_status_display()})</p>
        <br>
        <p>You can track the full progress of your permission here:</p>
        <p><a href="{status_url}">{status_url}</a></p>
        </body></html>
        """

        send_mail(
            subject=subject,
            message=f"Your permission has been updated. New status: {action_taken}. Track here: {status_url}",
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[permission.external_email],
            fail_silently=True,
            html_message=html_message
        )
    except PermissionSetting.DoesNotExist:
        pass
    except Exception as e:
        print(f"Failed to send external email notification: {e}")
