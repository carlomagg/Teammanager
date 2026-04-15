from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import Http404

from .models import FundRequest, FundRequestStep, FundRequestAttachment, FundRequestComment, FundRequestCategory, FundRequestType, FundRequestSetting
from .forms import (
    FundRequestCreateForm, FundRequestForwardForm, FundRequestCommentForm,
    FundRequestExternalSubmissionForm, FundRequestCategoryForm, FundRequestTypeForm, FundRequestSettingForm,
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


def _handle_attachments(request, fundrequest, step=None):
    """Save uploaded attachments for a fundrequest."""
    files = request.FILES.getlist('attachments')
    user = getattr(request, 'effective_user', None)
    for f in files:
        FundRequestAttachment.objects.create(
            fund_request=fundrequest,
            step=step,
            file=f,
            original_name=f.name,
            uploaded_by=user,
        )


def _get_next_step_number(fundrequest):
    """Get the next step number for a fundrequest."""
    last = fundrequest.steps.order_by('-step_number').first()
    return (last.step_number + 1) if last else 1


def _require_note(request, error_message):
    """Get trimmed note from POST; enforce non-empty."""
    note = (request.POST.get('note', '') or '').strip()
    if not note:
        messages.error(request, error_message, extra_tags='fund_request')
        return None
    return note


# ─── Super Admin Dashboard ──────────────────────────────────────────────────

@login_required
def superadmin_fund_request_dashboard(request):
    """
    Super Admin dashboard showing all fundrequests across all tenants.
    Only accessible to superusers and staff.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'You do not have permission to access this page.', extra_tags='fund_request')
        return redirect('fund_request:dashboard')

    # All fundrequests across all tenants
    all_memos = FundRequest.objects.all().select_related('tenant', 'created_by', 'current_holder', 'category')
    all_steps = FundRequestStep.objects.all()
    
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
    
    # Action statistics - Track all actions taken on fundrequests
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
    
    # Personal fundrequests (no tenant)
    personal_memos = all_memos.filter(tenant=None)
    if personal_memos.exists():
        tenant_stats.insert(0, {
            'tenant': {'name': 'Personal', 'slug': 'personal'},
            'total': personal_memos.count(),
            'pending': personal_memos.filter(status='pending').count(),
            'completed': personal_memos.filter(status='completed').count(),
            'escalated': personal_memos.filter(status='escalated').count(),
        })
    
    # Top 10 most active tenants by fundrequest count
    top_tenants = sorted(tenant_stats, key=lambda x: x['total'], reverse=True)[:10]
    
    # Daily trend (last 30 days)
    daily_trend = []
    for i in range(29, -1, -1):
        date = today.date() - timedelta(days=i)
        count = all_memos.filter(created_at__date=date).count()
        daily_trend.append({'date': date.strftime('%Y-%m-%d'), 'count': count})
    
    # Recent fundrequests with tenant info
    recent_memos = all_memos.order_by('-created_at')[:20]
    
    # Most active users (by fundrequest creation)
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
    categories = FundRequestCategory.objects.all()
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
    
    # Overdue fundrequests (urgent/high priority pending for more than 3 days, or escalated)
    from django.utils.timezone import now
    three_days_ago = now() - timedelta(days=3)
    overdue_memos = all_memos.filter(
        Q(priority__in=['urgent', 'high'], status__in=['pending', 'in_progress'], created_at__lt=three_days_ago) |
        Q(status='escalated')
    ).order_by('-created_at')[:10]
    
    # Average processing time (for completed fundrequests)
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
    return render(request, 'fund_request/superadmin_analytics.html', context)

@login_required
def fund_request_dashboard(request):
    """FundRequest dashboard showing inbox, outbox, and summary stats."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Check if user is admin or superuser
    is_admin = user.roles.filter(name='Admin').exists() or user.is_superuser

    # Inbox: fundrequests where user has a step assigned to them OR is current holder
    if tenant:
        inbox = FundRequest.objects.filter(
            Q(tenant=tenant) & 
            (Q(current_holder=user) | Q(steps__to_user=user))
        ).exclude(status__in=['completed', 'closed']).distinct()
        # Outbox: prioritize active fundrequests, show completed only if no active ones
        outbox_active = FundRequest.objects.filter(tenant=tenant, created_by=user).exclude(status__in=['completed', 'closed'])
        outbox_completed = FundRequest.objects.filter(tenant=tenant, created_by=user, status__in=['completed', 'closed'])
        all_memos = FundRequest.objects.filter(tenant=tenant)
    else:
        inbox = FundRequest.objects.filter(
            Q(tenant=None) & 
            (Q(current_holder=user) | Q(steps__to_user=user))
        ).exclude(status__in=['completed', 'closed']).distinct()
        # Outbox: prioritize active fundrequests, show completed only if no active ones
        outbox_active = FundRequest.objects.filter(tenant=None, created_by=user).exclude(status__in=['completed', 'closed'])
        outbox_completed = FundRequest.objects.filter(tenant=None, created_by=user, status__in=['completed', 'closed'])
        all_memos = FundRequest.objects.filter(tenant=None, created_by=user)

    # If there are active fundrequests, show only active ones; otherwise show completed ones
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
    return render(request, 'fund_request/dashboard.html', context)


# ─── FundRequest List ──────────────────────────────────────────────────────────────

@login_required
def fund_request_list(request):
    """List all fundrequests with search and filter."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequests = FundRequest.objects.filter(tenant=tenant)
    else:
        fundrequests = FundRequest.objects.filter(tenant=None, created_by=user)

    # Filters
    status = request.GET.get('status', '')
    priority = request.GET.get('priority', '')
    category = request.GET.get('category', '')
    search = request.GET.get('search', '')
    view_type = request.GET.get('view', '')  # inbox / outbox / all

    if status:
        fundrequests = fundrequests.filter(status=status)
    if priority:
        fundrequests = fundrequests.filter(priority=priority)
    if category:
        fundrequests = fundrequests.filter(category_id=category)
    if search:
        fundrequests = fundrequests.filter(
            Q(title__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(description__icontains=search) |
            Q(external_name__icontains=search)
        )
    if view_type == 'inbox':
        fundrequests = fundrequests.filter(Q(current_holder=user) | Q(steps__to_user=user)).distinct()
    elif view_type == 'outbox':
        fundrequests = fundrequests.filter(created_by=user)

    fundrequests = fundrequests.order_by('-updated_at')

    paginator = Paginator(fundrequests, 12)
    page = request.GET.get('page')
    fundrequests = paginator.get_page(page)

    categories = FundRequestCategory.objects.filter(tenant=tenant) if tenant else FundRequestCategory.objects.filter(tenant=None)

    context = {
        'fundrequests': fundrequests,
        'status': status,
        'priority': priority,
        'category': category,
        'search': search,
        'view_type': view_type,
        'categories': categories,
    }
    return render(request, 'fund_request/fund_request_list.html', context)


# ─── Create ─────────────────────────────────────────────────────────────────

@login_required
def fund_request_create(request):
    """Create a new internal fundrequest."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = FundRequestCreateForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            action = request.POST.get('action')
            is_draft = action == 'draft'

            fundrequest = form.save(commit=False)
            fundrequest.tenant = tenant
            fundrequest.created_by = user
            fundrequest.status = 'draft' if is_draft else 'pending'

            forward_to = form.cleaned_data.get('forward_to')
            if is_draft:
                fundrequest.current_holder = user
            elif forward_to and forward_to.exists():
                fundrequest.current_holder = forward_to.first()
            else:
                # Assign to receptionist pool or self
                receptionists = _get_receptionist_users(tenant) if tenant else CustomUser.objects.none()
                if receptionists.exists():
                    fundrequest.current_holder = receptionists.first()
                else:
                    fundrequest.current_holder = user

            fundrequest.save()

            if is_draft:
                step = FundRequestStep.objects.create(
                    fund_request=fundrequest,
                    step_number=1,
                    from_user=user,
                    to_user=user,
                    action='drafted',
                    note=form.cleaned_data.get('note', ''),
                )
                _handle_attachments(request, fundrequest, step=step)
                # Assign to_users for draft as well
                fundrequest.to_users.set(forward_to)
                messages.success(request, f'FundRequest {fundrequest.reference_number} saved as draft.', extra_tags='fund_request')
                return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

            # Assign to_users with all forward_to recipients
            fundrequest.to_users.set(forward_to)

            # Persist CC/BCC users on the fundrequest
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])
            fundrequest.cc_users.set(cc_users)
            fundrequest.bcc_users.set(bcc_users)

            # Handle attachments - create them first before steps
            note_text = form.cleaned_data.get('note', '')

            # Create steps for ALL forward_to recipients
            forwarded_users = list(forward_to) if forward_to else []
            step_number = 1
            for forward_user in forwarded_users:
                step = FundRequestStep.objects.create(
                    fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=forward_user,
                    action='created',
                    note=note_text,
                )
                step_number += 1

            # Create a temporary step for attachments (linked to first recipient)
            first_step = fundrequest.steps.first()
            _handle_attachments(request, fundrequest, step=first_step)

            # Create notifications for all forward_to recipients
            for forward_user in forwarded_users:
                _create_fund_request_notification(
                    tenant=tenant,
                    user=forward_user,
                    title=f"New FundRequest: {fundrequest.title}",
                    message=f"A new fundrequest has been created and assigned to you by {fundrequest.submitter_display}.",
                    fundrequest=fundrequest
                )

            # Create steps and notify CC users
            for cc_user in cc_users:
                # Create step for CC user
                FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action='created',
                    note=f"CC: {note_text}",
                )
                step_number += 1
                
                # Notify CC user
                _create_fund_request_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"New FundRequest (CC): {fundrequest.title}",
                    message=f"You have been CC'd on a new fundrequest by {fundrequest.submitter_display}.",
                    fundrequest=fundrequest
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                # Create step for BCC user
                FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action='created',
                    note=f"BCC: {note_text}",
                )
                step_number += 1
                
                # Notify BCC user
                _create_fund_request_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"New FundRequest: {fundrequest.title}",
                    message=f"A new fundrequest has been shared with you by {fundrequest.submitter_display}.",
                    fundrequest=fundrequest
                )

            messages.success(request, f'FundRequest {fundrequest.reference_number} created successfully.', extra_tags='fund_request')
            return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)
    else:
        form = FundRequestCreateForm(request=request)

    return render(request, 'fund_request/fund_request_create.html', {'form': form})


@login_required
def fund_request_edit(request, pk):
    """Edit a draft fundrequest."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant, created_by=user, status='draft')
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user, status='draft')

    if request.method == 'POST':
        form = FundRequestCreateForm(request.POST, request.FILES, request=request, instance=fundrequest)
        if form.is_valid():
            action = request.POST.get('action')
            is_draft = action == 'draft'

            fundrequest = form.save(commit=False)
            fundrequest.status = 'draft' if is_draft else 'pending'

            forward_to = form.cleaned_data.get('forward_to')
            if is_draft:
                fundrequest.current_holder = user
            elif forward_to and forward_to.exists():
                fundrequest.current_holder = forward_to.first()
            else:
                receptionists = _get_receptionist_users(tenant) if tenant else CustomUser.objects.none()
                if receptionists.exists():
                    fundrequest.current_holder = receptionists.first()
                else:
                    fundrequest.current_holder = user

            fundrequest.save()

            if is_draft:
                step = FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=_get_next_step_number(fundrequest),
                    from_user=user,
                    to_user=user,
                    action='drafted',
                    note=form.cleaned_data.get('note', ''),
                )
                _handle_attachments(request, fundrequest, step=step)
                # Assign to_users for draft as well
                fundrequest.to_users.set(forward_to)
                messages.success(request, f'Draft fundrequest {fundrequest.reference_number} updated.', extra_tags='fund_request')
                return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

            # Assign to_users with all forward_to recipients
            fundrequest.to_users.set(forward_to)

            # Persist CC/BCC users on the fundrequest
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])
            fundrequest.cc_users.set(cc_users)
            fundrequest.bcc_users.set(bcc_users)

            # FundRequest is being sent - create steps for ALL recipients
            note_text = form.cleaned_data.get('note', '')
            step_number = _get_next_step_number(fundrequest)
            
            # Create steps for all forward_to recipients
            forwarded_users = list(forward_to) if forward_to else []
            for forward_user in forwarded_users:
                step = FundRequestStep.objects.create(
                    fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=forward_user,
                    action='created',
                    note=note_text,
                )
                step_number += 1
            
            # Handle attachments with first step
            first_step = fundrequest.steps.first()
            _handle_attachments(request, fundrequest, step=first_step)

            # Create notifications for all forward_to recipients
            for forward_user in forwarded_users:
                _create_fund_request_notification(
                    tenant=tenant,
                    user=forward_user,
                    title=f"New FundRequest: {fundrequest.title}",
                    message=f"A new fundrequest has been sent to you by {fundrequest.submitter_display}.",
                    fundrequest=fundrequest
                )
            
            # Create steps and notify CC users
            for cc_user in cc_users:
                FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action='created',
                    note=f"CC: {note_text}",
                )
                step_number += 1
                
                _create_fund_request_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"New FundRequest (CC): {fundrequest.title}",
                    message=f"You have been CC'd on a new fundrequest by {fundrequest.submitter_display}.",
                    fundrequest=fundrequest
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action='created',
                    note=f"BCC: {note_text}",
                )
                step_number += 1
                
                _create_fund_request_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"New FundRequest: {fundrequest.title}",
                    message=f"A new fundrequest has been shared with you by {fundrequest.submitter_display}.",
                    fundrequest=fundrequest
                )
                    

            messages.success(request, f'FundRequest {fundrequest.reference_number} sent successfully.', extra_tags='fund_request')
            return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)
    else:
        form = FundRequestCreateForm(request=request, instance=fundrequest)

    return render(request, 'fund_request/fund_request_edit.html', {'form': form, 'fund_request': fundrequest})



# ─── Detail ─────────────────────────────────────────────────────────────────

@login_required
def fund_request_detail(request, pk):
    """View full fundrequest trail with steps, comments, and attachments."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    # Most recent first so the earliest (step 1) sits at the bottom.
    steps = fundrequest.steps.select_related('from_user', 'to_user').order_by('-step_number')
    attachments = fundrequest.attachments.select_related('uploaded_by', 'step').order_by('uploaded_at')

    # Filter comments based on privacy
    all_comments = fundrequest.comments.select_related('author', 'step').order_by('created_at')
    visible_comments = []
    for comment in all_comments:
        if not comment.is_private:
            visible_comments.append(comment)
        elif comment.author == user or fundrequest.current_holder == user:
            visible_comments.append(comment)

    # Determine available actions
    is_holder = (fundrequest.current_holder == user)
    is_creator = (fundrequest.created_by == user)
    # Check if user is a recipient (has a step assigned to them)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    # Recipients can act on the fundrequest (forward, approve, reject, etc.)
    can_act = (is_holder or is_recipient) and fundrequest.can_be_acted_on
    
    can_forward = can_act
    can_approve = can_act
    can_reject = can_act
    can_request_info = can_act and not is_creator
    can_escalate = (is_holder or is_creator or is_recipient) and fundrequest.can_be_acted_on
    can_complete = is_creator and fundrequest.status == 'approved'
    can_close = is_creator and fundrequest.status == 'rejected'
    can_reopen = is_creator and fundrequest.status in ('closed', 'completed')
    can_mark_in_progress = (is_holder or is_creator or is_recipient) and fundrequest.status in ['pending', 'in_view', 'escalated']
    can_keep_in_view = (is_holder or is_creator or is_recipient) and fundrequest.status == 'pending'
    can_record_response = can_act and not (is_creator and fundrequest.status == 'pending')
    # Withdraw: creator can withdraw a fundrequest while it's still pending
    can_withdraw = is_creator and fundrequest.status == 'pending'

    comment_form = FundRequestCommentForm()
    forward_form = FundRequestForwardForm(request=request, fund_request=fundrequest)

    context = {
        'fund_request': fundrequest,
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
    return render(request, 'fund_request/fund_request_detail.html', context)


# ─── Forward / Route ────────────────────────────────────────────────────────

@login_required
def fund_request_forward(request, pk):
    """Forward/route a fundrequest to the next person with an action."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if not fundrequest.can_be_acted_on:
        messages.error(request, 'This fundrequest cannot be acted on in its current state.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if request.method == 'POST':
        form = FundRequestForwardForm(request.POST, request.FILES, request=request, fund_request=fundrequest)
        if form.is_valid():
            to_users = form.cleaned_data['to_users']
            action = form.cleaned_data['action']
            note = form.cleaned_data.get('note', '')
            is_private = form.cleaned_data.get('is_private_note', False)

            # Get CC and BCC users
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])

            # Persist CC/BCC users on the fundrequest
            fundrequest.cc_users.set(cc_users)
            fundrequest.bcc_users.set(bcc_users)

            # Create steps for ALL to_users recipients
            step_number = _get_next_step_number(fundrequest)
            routed_users = list(to_users)
            
            for to_user in routed_users:
                step = FundRequestStep.objects.create(
                    fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=to_user,
                    action=action,
                    note=note,
                    is_private_note=is_private,
                )
                step_number += 1

            # Handle attachments with first step
            first_step = fundrequest.steps.order_by('-step_number').first()
            _handle_attachments(request, fundrequest, step=first_step)

            # Update fundrequest state
            # The person who is acting becomes the current holder (tracks who last acted)
            # Then based on the action, we may route it to someone else
            primary_to_user = routed_users[0] if routed_users else user
            
            if action == 'approved':
                fundrequest.status = 'approved'
                # For approval, if routing to someone specific, they become holder
                # Otherwise, the person who approved becomes the holder
                fundrequest.current_holder = primary_to_user
            elif action == 'rejected':
                fundrequest.status = 'rejected'
                # For rejection, send back to creator
                fundrequest.current_holder = fundrequest.created_by
            elif action == 'escalated':
                fundrequest.status = 'escalated'
                # For escalation, send to the escalation recipient
                fundrequest.current_holder = primary_to_user
            elif action == 'returned':
                fundrequest.status = 'in_view'
                # For return, send back to creator
                fundrequest.current_holder = fundrequest.created_by
            else:
                # For forward/minute, send to the first new recipient
                fundrequest.status = 'pending'
                fundrequest.current_holder = primary_to_user
            fundrequest.save()

            # Create notifications for all to_users recipients
            for routed_user in routed_users:
                _create_fund_request_notification(
                    tenant=tenant,
                    user=routed_user,
                    title="FundRequest Routed To You",
                    message=f"FundRequest '{fundrequest.title}' was routed to you by {user.get_full_name()} ({action}).",
                    fundrequest=fundrequest
                )
            
            # Create steps and notify CC users
            for cc_user in cc_users:
                # Create step for CC user
                FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action=action,
                    note=f"CC: {note}",
                    is_private_note=is_private,
                )
                step_number += 1
                
                # Notify CC user
                _create_fund_request_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"FundRequest Routed (CC): {fundrequest.title}",
                    message=f"You have been CC'd on a fundrequest routed by {user.get_full_name()} ({action}).",
                    fundrequest=fundrequest
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                # Create step for BCC user
                FundRequestStep.objects.create(fund_request=fundrequest,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action=action,
                    note=f"BCC: {note}",
                    is_private_note=is_private,
                )
                step_number += 1
                
                # Notify BCC user
                _create_fund_request_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"FundRequest Routed: {fundrequest.title}",
                    message=f"A fundrequest has been shared with you by {user.get_full_name()} ({action}).",
                    fundrequest=fundrequest
                )

            # Create success message
            recipient_names = ', '.join([u.get_full_name() or u.username for u in routed_users[:3]])
            if len(routed_users) > 3:
                recipient_names += f' and {len(routed_users) - 3} others'
            
            messages.success(request, f'FundRequest {action} to {recipient_names}.', extra_tags='fund_request')
            return redirect('fund_request:fund_request_detail', pk=pk)
    else:
        form = FundRequestForwardForm(request=request, fund_request=fundrequest)

    return render(request, 'fund_request/fund_request_forward.html', {'form': form, 'fund_request': fundrequest})


# ─── Quick Actions (approve / reject / escalate) ───────────────────────────

@login_required
def fund_request_approve(request, pk):
    """Quick approve and return to creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if request.method == 'POST' and fundrequest.can_be_acted_on:
        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = fundrequest.created_by

        step = FundRequestStep.objects.create(
            fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=to_user,
            action='approved',
            note=request.POST.get('note', ''),
        )
        fundrequest.status = 'approved'
        fundrequest.current_holder = to_user
        fundrequest.save()
        
        # Notify the recipient (send_to user or creator)
        if to_user:
            _create_fund_request_notification(
                tenant=tenant,
                user=to_user,
                title="FundRequest Approved",
                message=f"FundRequest '{fundrequest.title}' was approved by {user.get_full_name()}.",
                fundrequest=fundrequest
            )
        # Also notify the creator if the fundrequest was sent to someone else
        if send_to_id and fundrequest.created_by and to_user != fundrequest.created_by:
            _create_fund_request_notification(
                tenant=tenant,
                user=fundrequest.created_by,
                title="FundRequest Approved",
                message=f"Your fundrequest '{fundrequest.title}' was approved by {user.get_full_name()} and sent to {to_user.get_full_name()}.",
                fundrequest=fundrequest
            )
        
        messages.success(request, 'FundRequest approved successfully.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


@login_required
def fund_request_reject(request, pk):
    """Quick reject and return to creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if request.method == 'POST' and fundrequest.can_be_acted_on:
        note = (request.POST.get('note', '') or '').strip()
        if not note:
            messages.error(request, 'Please provide a reason for rejection.', extra_tags='fund_request')
            return redirect('fund_request:fund_request_detail', pk=pk)

        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = fundrequest.created_by

        step = FundRequestStep.objects.create(fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=to_user,
            action='rejected',
            note=note,
        )
        fundrequest.status = 'rejected'
        fundrequest.current_holder = to_user
        fundrequest.save()
        
        # Notify the recipient (send_to user or creator)
        if to_user:
            _create_fund_request_notification(
                tenant=tenant,
                user=to_user,
                title="FundRequest Rejected",
                message=f"FundRequest '{fundrequest.title}' was rejected by {user.get_full_name()}.",
                fundrequest=fundrequest
            )
        # Also notify the creator if the fundrequest was sent to someone else
        if send_to_id and fundrequest.created_by and to_user != fundrequest.created_by:
            _create_fund_request_notification(
                tenant=tenant,
                user=fundrequest.created_by,
                title="FundRequest Rejected",
                message=f"Your fundrequest '{fundrequest.title}' was rejected by {user.get_full_name()} and sent to {to_user.get_full_name()}.",
                fundrequest=fundrequest
            )
        
        messages.success(request, 'FundRequest rejected.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


@login_required
def fund_request_escalate(request, pk):
    """Escalate a fundrequest."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    # Both holder and creator can escalate
    if user != fundrequest.current_holder and user != fundrequest.created_by:
        messages.error(request, 'You do not have permission to escalate this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if request.method == 'POST' and fundrequest.can_be_acted_on:
        to_user_id = request.POST.get('escalate_to')
        to_user = get_object_or_404(CustomUser, pk=to_user_id)

        step = FundRequestStep.objects.create(fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=to_user,
            action='escalated',
            note=request.POST.get('note', ''),
        )
        fundrequest.status = 'escalated'
        fundrequest.current_holder = to_user
        fundrequest.save()
        
        # Create notification for recipient
        _create_fund_request_notification(
            tenant=tenant,
            user=to_user,
            title="FundRequest Escalated To You",
            message=f"FundRequest '{fundrequest.title}' was escalated to you by {user.get_full_name()}.",
            fundrequest=fundrequest
        )
        
        messages.success(request, f'FundRequest escalated to {to_user.username}.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


@login_required
def fund_request_request_info(request, pk):
    """Request more information from the fundrequest creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if not fundrequest.can_be_acted_on:
        messages.error(request, 'This fundrequest cannot be acted on in its current state.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if request.method == 'POST':
        note = _require_note(request, 'Please specify what information you need.')
        if note is None:
            return redirect('fund_request:fund_request_detail', pk=pk)

        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = fundrequest.created_by

        # Return fundrequest to creator with request for info
        step = FundRequestStep.objects.create(fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=to_user,
            action='request_info',
            note=note,
        )
        
        fundrequest.status = 'in_view'
        fundrequest.current_holder = to_user
        fundrequest.save()
        
        # Notify the recipient
        if to_user:
            _create_fund_request_notification(
                tenant=tenant,
                user=to_user,
                title="More Information Requested",
                message=f"More information has been requested for fundrequest '{fundrequest.title}' by {user.get_full_name()}.",
                fundrequest=fundrequest
            )
        
        
        messages.success(request, 'Request for more information sent to creator.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


# ─── Complete / Close / Reopen ──────────────────────────────────────────────

@login_required
def fund_request_complete(request, pk):
    """Mark fundrequest as completed (by creator after approval)."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Try to get fundrequest for authenticated users
    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None)

    # Check permissions: either the creator or external user with token
    is_creator = fundrequest.created_by == user
    is_external_with_permission = False
    
    if fundrequest.is_external and not is_creator:
        # Check if this is an external user accessing via their fundrequest
        # External users should use the external_status view with token
        # But if they somehow got here, check fundrequest settings
        memo_setting = FundRequestSetting.objects.filter(tenant=tenant).first()
        is_external_with_permission = memo_setting and memo_setting.allow_external_completion
    
    if not (is_creator or is_external_with_permission):
        messages.error(request, 'You do not have permission to complete this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=pk)

    if request.method == 'POST' and fundrequest.status == 'approved':
        fundrequest.status = 'completed'
        fundrequest.completed_at = timezone.now()
        fundrequest.save()
        messages.success(request, 'FundRequest marked as completed.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


@login_required
def fund_request_close(request, pk):
    """Mark fundrequest as closed (by creator after rejection)."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant, created_by=user)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and fundrequest.status == 'rejected':
        fundrequest.status = 'closed'
        fundrequest.closed_at = timezone.now()
        fundrequest.save()
        messages.success(request, 'FundRequest closed.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


@login_required
def fund_request_reopen(request, pk):
    """Reopen a closed or completed fundrequest."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant, created_by=user)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and fundrequest.status in ('closed', 'completed'):
        fundrequest.status = 'in_progress'
        fundrequest.closed_at = None
        fundrequest.completed_at = None
        fundrequest.current_holder = user
        fundrequest.save()

        FundRequestStep.objects.create(fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=user,
            action='forwarded',
            note='FundRequest reopened by creator.',
        )
        messages.success(request, 'FundRequest reopened.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


# ─── Comments ───────────────────────────────────────────────────────────────

@login_required
def fund_request_add_comment(request, pk):
    """Add a comment to a fundrequest."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST':
        form = FundRequestCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.fundrequest = fundrequest
            comment.author = user
            comment.save()
            messages.success(request, 'Comment added.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


# ─── External Submission ────────────────────────────────────────────────────

def fund_request_external_submit(request, slug):
    """Public fundrequest submission form (no auth required)."""
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

            fundrequest = FundRequest.objects.create(
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
            FundRequestStep.objects.create(
                fund_request=fundrequest,
                step_number=1,
                from_user=None,
                to_user=current_holder,
                action='received',
                note=f"External submission from {form.cleaned_data['submitter_name']}",
            )

            # Handle attachments
            files = request.FILES.getlist('attachments')
            for f in files:
                FundRequestAttachment.objects.create(
                    fund_request=fundrequest,
                    file=f,
                    original_name=f.name,
                )

            # Notify the assigned staff member in the bell icon notifications
            if current_holder:
                _create_fund_request_notification(
                    tenant=tenant,
                    user=current_holder,
                    title=f"New External FundRequest: {fundrequest.title}",
                    message=f"You received a new external fundrequest from {fundrequest.external_name or fundrequest.external_email or 'External'} ({fundrequest.reference_number}).",
                    fundrequest=fundrequest
                )

            messages.success(request, 'Your request has been submitted successfully.', extra_tags='fund_request')
            return render(request, 'fund_request/external_submit_success.html', {
                'fund_request': fundrequest,
                'tenant': tenant,
            })
    else:
        form = MemoExternalSubmissionForm(tenant=tenant)

    return render(request, 'fund_request/external_submit.html', {
        'form': form,
        'tenant': tenant,
    })


def fund_request_external_submit_personal(request, token):
    """Public fundrequest submission form for a specific user (no auth required)."""
    from documents.models import CustomUser
    target_user = get_object_or_404(CustomUser, personal_external_token=token, is_active=True)
    tenant = target_user.tenant

    if not tenant:
        return render(request, 'fund_request/external_submit.html', {
            'form': None,
            'tenant': None,
            'error': 'This user is not associated with an organization.',
        })

    if request.method == 'POST':
        form = MemoExternalSubmissionForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            # Create fundrequest assigned directly to the target user
            fundrequest = FundRequest.objects.create(
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
            FundRequestStep.objects.create(fund_request=fundrequest,
                step_number=1,
                from_user=None,
                to_user=target_user,
                action='received',
                note=f"External submission from {form.cleaned_data['submitter_name']} (sent directly to {target_user.get_full_name() or target_user.username})",
            )

            # Handle attachments
            files = request.FILES.getlist('attachments')
            for f in files:
                FundRequestAttachment.objects.create(
                    fund_request=fundrequest,
                    file=f,
                    original_name=f.name,
                )

            # Notify the target user
            _create_fund_request_notification(
                tenant=tenant,
                user=target_user,
                title=f"New External FundRequest: {fundrequest.title}",
                message=f"You received a new external fundrequest from {fundrequest.external_name or fundrequest.external_email or 'External'} ({fundrequest.reference_number}).",
                fundrequest=fundrequest
            )

            messages.success(request, 'Your request has been submitted successfully.', extra_tags='fund_request')
            return render(request, 'fund_request/external_submit_success.html', {
                'fund_request': fundrequest,
                'tenant': tenant,
            })
    else:
        form = MemoExternalSubmissionForm(tenant=tenant)

    return render(request, 'fund_request/external_submit.html', {
        'form': form,
        'tenant': tenant,
        'target_user': target_user,
    })


def fund_request_external_status(request, token):
    """External user: view fundrequest status (no auth required)."""
    fundrequest = get_object_or_404(FundRequest, external_token=token)
    tenant = fundrequest.tenant

    # Check tenant settings
    memo_setting = FundRequestSetting.objects.filter(tenant=tenant).first()

    # Most recent first for external tracking view as well.
    steps = fundrequest.steps.order_by('-step_number')
    # External users see all steps, but private notes are hidden
    visible_steps = steps

    # Public comments only
    comments = fundrequest.comments.filter(is_private=False).order_by('created_at')

    can_escalate = memo_setting.allow_external_escalation if memo_setting else False
    can_complete = memo_setting.allow_external_completion if memo_setting else False

    context = {
        'fund_request': fundrequest,
        'steps': visible_steps,
        'comments': comments,
        'can_escalate': can_escalate and fundrequest.can_be_acted_on,
        'can_complete': can_complete and fundrequest.status == 'approved',
    }
    return render(request, 'fund_request/external_status.html', context)


def fund_request_external_complete(request, token):
    """External user: mark fundrequest as completed (no auth required)."""
    fundrequest = get_object_or_404(FundRequest, external_token=token)
    tenant = fundrequest.tenant

    # Check tenant settings
    memo_setting = FundRequestSetting.objects.filter(tenant=tenant).first()
    can_complete = memo_setting.allow_external_completion if memo_setting else False

    if not can_complete:
        messages.error(request, 'You do not have permission to complete this fundrequest.', extra_tags='fund_request')
        return redirect('fund_request:external_status', token=token)

    if request.method == 'POST' and fundrequest.status == 'approved':
        fundrequest.status = 'completed'
        fundrequest.completed_at = timezone.now()
        fundrequest.save()
        
        # Create a step for the completion
        FundRequestStep.objects.create(fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            action='completed',
            from_user=None,
            to_user=None,
            note='Marked as completed by external user',
            is_private_note=False
        )
        
        messages.success(request, 'FundRequest marked as completed.', extra_tags='fund_request')

    return redirect('fund_request:external_status', token=token)


# ─── Categories ─────────────────────────────────────────────────────────────

@login_required
def fund_request_categories(request):
    """List fundrequest categories."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        categories = FundRequestCategory.objects.filter(tenant=tenant)
    else:
        categories = FundRequestCategory.objects.filter(tenant=None, created_by=user)

    return render(request, 'fund_request/categories.html', {'categories': categories})


@login_required
def fund_request_category_create(request):
    """Create a fundrequest category."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = FundRequestCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.tenant = tenant
            cat.created_by = user
            cat.save()
            messages.success(request, 'Category created.', extra_tags='fund_request')
            return redirect('fund_request:categories')
    else:
        form = FundRequestCategoryForm()

    return render(request, 'fund_request/category_form.html', {'form': form, 'action': 'Create'})


@login_required
def fund_request_category_edit(request, pk):
    """Edit a fundrequest category."""
    tenant = request.effective_tenant

    if tenant:
        cat = get_object_or_404(FundRequestCategory, pk=pk, tenant=tenant)
    else:
        cat = get_object_or_404(FundRequestCategory, pk=pk, tenant=None)

    if request.method == 'POST':
        form = FundRequestCategoryForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.', extra_tags='fund_request')
            return redirect('fund_request:categories')
    else:
        form = FundRequestCategoryForm(instance=cat)

    return render(request, 'fund_request/category_form.html', {'form': form, 'action': 'Edit', 'category': cat})


@login_required
def fund_request_category_delete(request, pk):
    """Delete a fundrequest category."""
    tenant = request.effective_tenant

    if tenant:
        cat = get_object_or_404(FundRequestCategory, pk=pk, tenant=tenant)
    else:
        cat = get_object_or_404(FundRequestCategory, pk=pk, tenant=None)

    if request.method == 'POST':
        cat.delete()
        messages.success(request, 'Category deleted.', extra_tags='fund_request')
        return redirect('fund_request:categories')

    return render(request, 'fund_request/category_confirm_delete.html', {'category': cat})


# ─── Request Types ──────────────────────────────────────────────────────────

@login_required
def fund_request_types(request):
    """List fundrequest request types."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        request_types = FundRequestType.objects.filter(tenant=tenant)
    else:
        request_types = FundRequestType.objects.filter(tenant=None, created_by=user)

    return render(request, 'fund_request/request_types.html', {'request_types': request_types})


@login_required
def fund_request_type_create(request):
    """Create a fundrequest request type."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = FundRequestTypeForm(request.POST)
        if form.is_valid():
            req_type = form.save(commit=False)
            req_type.tenant = tenant
            req_type.created_by = user
            req_type.save()
            messages.success(request, 'Request type created.', extra_tags='fund_request')
            return redirect('fund_request:request_types')
    else:
        form = FundRequestTypeForm()

    return render(request, 'fund_request/request_type_form.html', {'form': form, 'action': 'Create'})


@login_required
def fund_request_type_edit(request, pk):
    """Edit a fundrequest request type."""
    tenant = request.effective_tenant

    if tenant:
        req_type = get_object_or_404(FundRequestType, pk=pk, tenant=tenant)
    else:
        req_type = get_object_or_404(FundRequestType, pk=pk, tenant=None)

    if request.method == 'POST':
        form = FundRequestTypeForm(request.POST, instance=req_type)
        if form.is_valid():
            form.save()
            messages.success(request, 'Request type updated.', extra_tags='fund_request')
            return redirect('fund_request:request_types')
    else:
        form = FundRequestTypeForm(instance=req_type)

    return render(request, 'fund_request/request_type_form.html', {'form': form, 'action': 'Edit', 'request_type': req_type})


@login_required
def fund_request_type_delete(request, pk):
    """Delete a fundrequest request type."""
    tenant = request.effective_tenant

    if tenant:
        req_type = get_object_or_404(FundRequestType, pk=pk, tenant=tenant)
    else:
        req_type = get_object_or_404(FundRequestType, pk=pk, tenant=None)

    if request.method == 'POST':
        req_type.delete()
        messages.success(request, 'Request type deleted.', extra_tags='fund_request')
        return redirect('fund_request:request_types')

    return render(request, 'fund_request/request_type_confirm_delete.html', {'request_type': req_type})


# ─── Settings ───────────────────────────────────────────────────────────────

@login_required
def fund_request_settings(request):
    """Tenant fundrequest settings."""
    tenant = request.effective_tenant
    if not tenant:
        messages.error(request, 'Settings are only available for organization accounts.', extra_tags='fund_request')
        return redirect('fund_request:dashboard')

    # Check if user is tenant admin or superuser
    is_admin = request.user.is_superuser or request.user.roles.filter(name='Admin').exists()

    setting, created = FundRequestSetting.objects.get_or_create(tenant=tenant)

    if request.method == 'POST':
        # Only allow admins to update external submission settings
        if not is_admin:
            messages.error(request, 'You do not have permission to update these settings.', extra_tags='fund_request')
            return redirect('fund_request:settings')
            
        form = FundRequestSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, 'FundRequest settings updated.', extra_tags='fund_request')
            return redirect('fund_request:settings')
    else:
        form = FundRequestSettingForm(instance=setting)

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
    categories = FundRequestCategory.objects.filter(tenant=tenant).order_by('name')

    return render(request, 'fund_request/settings.html', {
        'form': form,
        'staff_members': staff_members,
        'categories': categories,
        'is_admin': is_admin,
    })


# ─── Receptionist Management ───────────────────────────────────────────────

@login_required
def fund_request_manage_receptionist(request):
    """Assign/revoke Receptionist role (Admin only)."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Only admins can manage this
    is_admin = user.roles.filter(name='Admin').exists() or user.is_superuser
    if not is_admin:
        messages.error(request, 'Only admins can manage the Receptionist role.', extra_tags='fund_request')
        return redirect('fund_request:dashboard')

    # Ensure the Receptionist role exists
    receptionist_role, _ = Role.objects.get_or_create(name='Receptionist', defaults={'description': 'Handles incoming fundrequests with no specific recipient'})

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
            messages.success(request, f'{target_user.username} assigned as Receptionist.', extra_tags='fund_request')
        elif action == 'revoke':
            target_user.roles.remove(receptionist_role)
            messages.success(request, f'Receptionist role removed from {target_user.username}.', extra_tags='fund_request')

        return redirect('fund_request:manage_receptionist')

    # Annotate who has the role
    receptionist_ids = set(
        _get_receptionist_users(tenant).values_list('id', flat=True)
    ) if tenant else set()

    context = {
        'staff': staff,
        'receptionist_ids': receptionist_ids,
    }
    return render(request, 'fund_request/manage_receptionist.html', context)


# ==========================================
# MISSING FEATURES: IN PROGRESS, NOTIFS
# ==========================================

@login_required
def fund_request_mark_in_progress(request, pk):
    """Mark a fundrequest as 'In Progress'."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_creator = (fundrequest.created_by == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this fundrequest.", extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

    if request.method == 'POST':
        if fundrequest.status in ['pending', 'in_view', 'escalated']:
            fundrequest.status = 'in_progress'
            fundrequest.current_holder = user  # The person marking it in progress becomes the current holder
            fundrequest.save()
            
            
            messages.success(request, "FundRequest marked as In Progress.", extra_tags='fund_request')
        else:
            messages.error(request, f"Cannot mark as In Progress from state '{fundrequest.get_status_display()}'.", extra_tags='fund_request')
    
    return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

@login_required
def fund_request_keep_in_view(request, pk):
    """Mark a fundrequest as 'In View' manually."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_creator = (fundrequest.created_by == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this fundrequest.", extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

    if request.method == 'POST':
        if fundrequest.can_be_acted_on:
            # Determine recipient: optional send_to user, or fall back to self
            send_to_id = (request.POST.get('to_user') or '').strip()
            if send_to_id:
                to_user = get_object_or_404(CustomUser, pk=send_to_id)
            else:
                to_user = user

            fundrequest.status = 'in_view'
            fundrequest.current_holder = to_user
            fundrequest.save()

            note = (request.POST.get('note', '') or '').strip() or 'FundRequest kept in view.'

            FundRequestStep.objects.create(
                fund_request=fundrequest,
                step_number=_get_next_step_number(fundrequest),
                from_user=user,
                to_user=to_user,
                action='kept_in_view',
                note=note,
            )

            # Notify the recipient if different from sender
            if to_user != user:
                _create_fund_request_notification(
                    tenant=tenant,
                    user=to_user,
                    title="FundRequest Kept In View",
                    message=f"FundRequest '{fundrequest.title}' has been kept in view by {user.get_full_name()} and sent to you.",
                    fundrequest=fundrequest
                )

            messages.success(request, "FundRequest marked as In-View.", extra_tags='fund_request')
        else:
            messages.error(request, f"Cannot keep In-View from state '{fundrequest.get_status_display()}'.", extra_tags='fund_request')
    
    return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)


@login_required
def fund_request_positive_response(request, pk):
    """Record a positive response with a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_creator = (fundrequest.created_by == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this fundrequest.", extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

    if request.method == 'POST' and fundrequest.can_be_acted_on:
        note = _require_note(request, 'Please add a note for the positive response.')
        if note is None:
            return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        FundRequestStep.objects.create(
            fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=to_user,
            action='positive_response',
            note=note,
        )

        fundrequest.status = 'positive_response'
        fundrequest.current_holder = to_user
        fundrequest.save()

        # Notify the recipient if different from sender
        if to_user != user:
            _create_fund_request_notification(
                tenant=tenant,
                user=to_user,
                title="Positive Recommendation",
                message=f"FundRequest '{fundrequest.title}' received a positive recommendation from {user.get_full_name()}.",
                fundrequest=fundrequest
            )

        messages.success(request, 'Positive response recorded.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)


@login_required
def fund_request_negative_response(request, pk):
    """Record a negative response with a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (fundrequest.current_holder == user)
    is_creator = (fundrequest.created_by == user)
    is_recipient = fundrequest.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this fundrequest.", extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

    if request.method == 'POST' and fundrequest.can_be_acted_on:
        note = _require_note(request, 'Please add a note for the negative response.')
        if note is None:
            return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        FundRequestStep.objects.create(
            fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=to_user,
            action='negative_response',
            note=note,
        )

        fundrequest.status = 'negative_response'
        fundrequest.current_holder = to_user
        fundrequest.save()

        # Notify the recipient if different from sender
        if to_user != user:
            _create_fund_request_notification(
                tenant=tenant,
                user=to_user,
                title="Negative Recommendation",
                message=f"FundRequest '{fundrequest.title}' received a negative recommendation from {user.get_full_name()}.",
                fundrequest=fundrequest
            )

        messages.success(request, 'Negative response recorded.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)


@login_required
def fund_request_keep_in_view_with_note(request, pk):
    """Keep a fundrequest in view and record a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    if fundrequest.current_holder != user and fundrequest.created_by != user:
        messages.error(request, "You don't have permission to update this fundrequest.", extra_tags='fund_request')
        return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

    if request.method == 'POST' and fundrequest.can_be_acted_on:
        note = _require_note(request, 'Please add a note for keeping this fundrequest in view.')
        if note is None:
            return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)

        # Always move the fundrequest into the "In View" state while it can still be acted on,
        # so the main status and filters reflect this action.
        fundrequest.status = 'in_view'
        fundrequest.save(update_fields=['status'])

        FundRequestStep.objects.create(
            fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=fundrequest.current_holder,
            action='kept_in_view',
            note=note,
        )
        messages.success(request, 'FundRequest kept in view with note.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=fundrequest.pk)


@login_required
def fund_request_withdraw(request, pk):
    """Withdraw a fundrequest (by creator). Sets status to closed."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=tenant, created_by=user)
    else:
        fundrequest = get_object_or_404(FundRequest, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and fundrequest.status == 'pending':
        note = (request.POST.get('note', '') or '').strip()
        if not note:
            note = 'FundRequest withdrawn by creator.'

        FundRequestStep.objects.create(
            fund_request=fundrequest,
            step_number=_get_next_step_number(fundrequest),
            from_user=user,
            to_user=user,
            action='withdrawn',
            note=note,
        )
        fundrequest.status = 'closed'
        fundrequest.closed_at = timezone.now()
        fundrequest.save()

        # Notify the current holder if it's not the creator
        if fundrequest.current_holder and fundrequest.current_holder != user:
            _create_fund_request_notification(
                tenant=tenant,
                user=fundrequest.current_holder,
                title="FundRequest Withdrawn",
                message=f"FundRequest '{fundrequest.title}' was withdrawn by {user.get_full_name()}.",
                fundrequest=fundrequest
            )

        messages.success(request, 'FundRequest withdrawn successfully.', extra_tags='fund_request')
    else:
        messages.error(request, 'This fundrequest cannot be withdrawn.', extra_tags='fund_request')

    return redirect('fund_request:fund_request_detail', pk=pk)


def _create_fund_request_notification(tenant, user, title, message, url=None, fundrequest=None):
    """Helper to create a bell icon notification for fundrequest events."""
    from django.contrib.contenttypes.models import ContentType
    try:
        # Build the link URL from the fundrequest if not provided
        if not url and fundrequest:
            url = f"/fund-request/{fundrequest.pk}/"

        kwargs = {
            'tenant': tenant,
            'title': title,
            'message': message,
            'type': Notification.NotificationType.MEMO,
            'is_active': True,
            'link': url,
        }

        # Also set generic relation so get_absolute_url() has multiple fallback paths
        if fundrequest:
            kwargs['content_type'] = ContentType.objects.get_for_model(fundrequest)
            kwargs['object_id'] = fundrequest.pk

        notif = Notification.objects.create(**kwargs)
        UserNotification.objects.create(
            tenant=tenant,
            user=user,
            notification=notif
        )
    except Exception as e:
        print(f"Failed to create notification: {e}")


    """Send email to external submitter if tenant settings allow it."""
    if not fundrequest.is_external or not fundrequest.external_email:
        return
        
    try:
        settings = FundRequestSetting.objects.get(tenant=fundrequest.tenant)
        if not settings.notify_external_on_move:
            return
            
        subject = f"FundRequest Update: {fundrequest.title} [{fundrequest.reference_number}]"
        
        base_domain = "127.0.0.1:8000" if django_settings.DEBUG else "teammanager.ng"
        protocol = "http" if django_settings.DEBUG else "https"
        status_url = f"{protocol}://{base_domain}/fundrequest/external/status/{fundrequest.external_token}/"
        
        html_message = f"""
        <html><body>
        <h2>Your FundRequest has been updated</h2>
        <p><strong>Reference:</strong> {fundrequest.reference_number}</p>
        <p><strong>Title:</strong> {fundrequest.title}</p>
        <p><strong>New Action/Status:</strong> {action_taken} ({fundrequest.get_status_display()})</p>
        <br>
        <p>You can track the full progress of your fundrequest here:</p>
        <p><a href="{status_url}">{status_url}</a></p>
        </body></html>
        """

        send_mail(
            subject=subject,
            message=f"Your fundrequest has been updated. New status: {action_taken}. Track here: {status_url}",
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[fundrequest.external_email],
            fail_silently=True,
            html_message=html_message
        )
    except FundRequestSetting.DoesNotExist:
        pass
    except Exception as e:
        print(f"Failed to send external email notification: {e}")

