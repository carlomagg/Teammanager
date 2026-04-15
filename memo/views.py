from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import Http404

from .models import Memo, MemoStep, MemoAttachment, MemoComment, MemoCategory, MemoSetting
from .forms import (
    MemoCreateForm, MemoForwardForm, MemoCommentForm,
    MemoExternalSubmissionForm, MemoCategoryForm, MemoSettingForm,
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


def _handle_attachments(request, memo, step=None):
    """Save uploaded attachments for a memo."""
    files = request.FILES.getlist('attachments')
    user = getattr(request, 'effective_user', None)
    for f in files:
        MemoAttachment.objects.create(
            memo=memo,
            step=step,
            file=f,
            original_name=f.name,
            uploaded_by=user,
        )


def _get_next_step_number(memo):
    """Get the next step number for a memo."""
    last = memo.steps.order_by('-step_number').first()
    return (last.step_number + 1) if last else 1


def _require_note(request, error_message):
    """Get trimmed note from POST; enforce non-empty."""
    note = (request.POST.get('note', '') or '').strip()
    if not note:
        messages.error(request, error_message, extra_tags='memo')
        return None
    return note


# ─── Super Admin Dashboard ──────────────────────────────────────────────────

@login_required
def superadmin_memo_dashboard(request):
    """
    Super Admin dashboard showing all memos across all tenants.
    Only accessible to superusers and staff.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, 'You do not have permission to access this page.', extra_tags='memo')
        return redirect('memo:dashboard')

    # All memos across all tenants
    all_memos = Memo.objects.all().select_related('tenant', 'created_by', 'current_holder', 'category')
    all_steps = MemoStep.objects.all()
    
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
    
    # Action statistics - Track all actions taken on memos
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
    
    # Personal memos (no tenant)
    personal_memos = all_memos.filter(tenant=None)
    if personal_memos.exists():
        tenant_stats.insert(0, {
            'tenant': {'name': 'Personal', 'slug': 'personal'},
            'total': personal_memos.count(),
            'pending': personal_memos.filter(status='pending').count(),
            'completed': personal_memos.filter(status='completed').count(),
            'escalated': personal_memos.filter(status='escalated').count(),
        })
    
    # Top 10 most active tenants by memo count
    top_tenants = sorted(tenant_stats, key=lambda x: x['total'], reverse=True)[:10]
    
    # Daily trend (last 30 days)
    daily_trend = []
    for i in range(29, -1, -1):
        date = today.date() - timedelta(days=i)
        count = all_memos.filter(created_at__date=date).count()
        daily_trend.append({'date': date.strftime('%Y-%m-%d'), 'count': count})
    
    # Recent memos with tenant info
    recent_memos = all_memos.order_by('-created_at')[:20]
    
    # Most active users (by memo creation)
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
    categories = MemoCategory.objects.all()
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
    
    # Overdue memos (urgent/high priority pending for more than 3 days, or escalated)
    from django.utils.timezone import now
    three_days_ago = now() - timedelta(days=3)
    overdue_memos = all_memos.filter(
        Q(priority__in=['urgent', 'high'], status__in=['pending', 'in_progress'], created_at__lt=three_days_ago) |
        Q(status='escalated')
    ).order_by('-created_at')[:10]
    
    # Average processing time (for completed memos)
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
    return render(request, 'memo/superadmin_analytics.html', context)

@login_required
def memo_dashboard(request):
    """Memo dashboard showing inbox, outbox, and summary stats."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Check if user is admin or superuser
    is_admin = user.roles.filter(name='Admin').exists() or user.is_superuser

    # Inbox: memos where user has a step assigned to them OR is current holder
    if tenant:
        inbox = Memo.objects.filter(
            Q(tenant=tenant) & 
            (Q(current_holder=user) | Q(steps__to_user=user))
        ).exclude(status__in=['completed', 'closed']).distinct()
        # Outbox: prioritize active memos, show completed only if no active ones
        outbox_active = Memo.objects.filter(tenant=tenant, created_by=user).exclude(status__in=['completed', 'closed'])
        outbox_completed = Memo.objects.filter(tenant=tenant, created_by=user, status__in=['completed', 'closed'])
        all_memos = Memo.objects.filter(tenant=tenant)
    else:
        inbox = Memo.objects.filter(
            Q(tenant=None) & 
            (Q(current_holder=user) | Q(steps__to_user=user))
        ).exclude(status__in=['completed', 'closed']).distinct()
        # Outbox: prioritize active memos, show completed only if no active ones
        outbox_active = Memo.objects.filter(tenant=None, created_by=user).exclude(status__in=['completed', 'closed'])
        outbox_completed = Memo.objects.filter(tenant=None, created_by=user, status__in=['completed', 'closed'])
        all_memos = Memo.objects.filter(tenant=None, created_by=user)

    # If there are active memos, show only active ones; otherwise show completed ones
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
    return render(request, 'memo/dashboard.html', context)


# ─── Memo List ──────────────────────────────────────────────────────────────

@login_required
def memo_list(request):
    """List all memos with search and filter."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memos = Memo.objects.filter(tenant=tenant)
    else:
        memos = Memo.objects.filter(tenant=None, created_by=user)

    # Filters
    status = request.GET.get('status', '')
    priority = request.GET.get('priority', '')
    category = request.GET.get('category', '')
    search = request.GET.get('search', '')
    view_type = request.GET.get('view', '')  # inbox / outbox / all

    if status:
        memos = memos.filter(status=status)
    if priority:
        memos = memos.filter(priority=priority)
    if category:
        memos = memos.filter(category_id=category)
    if search:
        memos = memos.filter(
            Q(title__icontains=search) |
            Q(reference_number__icontains=search) |
            Q(description__icontains=search) |
            Q(external_name__icontains=search)
        )
    if view_type == 'inbox':
        memos = memos.filter(Q(current_holder=user) | Q(steps__to_user=user)).distinct()
    elif view_type == 'outbox':
        memos = memos.filter(created_by=user)

    memos = memos.order_by('-updated_at')

    paginator = Paginator(memos, 12)
    page = request.GET.get('page')
    memos = paginator.get_page(page)

    categories = MemoCategory.objects.filter(tenant=tenant) if tenant else MemoCategory.objects.filter(tenant=None)

    context = {
        'memos': memos,
        'status': status,
        'priority': priority,
        'category': category,
        'search': search,
        'view_type': view_type,
        'categories': categories,
    }
    return render(request, 'memo/memo_list.html', context)


# ─── Create ─────────────────────────────────────────────────────────────────

@login_required
def memo_create(request):
    """Create a new internal memo."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = MemoCreateForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            action = request.POST.get('action')
            is_draft = action == 'draft'

            memo = form.save(commit=False)
            memo.tenant = tenant
            memo.created_by = user
            memo.status = 'draft' if is_draft else 'pending'

            forward_to = form.cleaned_data.get('forward_to')
            if is_draft:
                memo.current_holder = user
            elif forward_to and forward_to.exists():
                memo.current_holder = forward_to.first()
            else:
                # Assign to receptionist pool or self
                receptionists = _get_receptionist_users(tenant) if tenant else CustomUser.objects.none()
                if receptionists.exists():
                    memo.current_holder = receptionists.first()
                else:
                    memo.current_holder = user

            memo.save()

            if is_draft:
                step = MemoStep.objects.create(
                    memo=memo,
                    step_number=1,
                    from_user=user,
                    to_user=user,
                    action='drafted',
                    note=form.cleaned_data.get('note', ''),
                )
                _handle_attachments(request, memo, step=step)
                # Assign to_users for draft as well
                memo.to_users.set(forward_to)
                messages.success(request, f'Memo {memo.reference_number} saved as draft.', extra_tags='memo')
                return redirect('memo:memo_detail', pk=memo.pk)

            # Assign to_users with all forward_to recipients
            memo.to_users.set(forward_to)

            # Persist CC/BCC users on the memo
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])
            memo.cc_users.set(cc_users)
            memo.bcc_users.set(bcc_users)

            # Handle attachments - create them first before steps
            note_text = form.cleaned_data.get('note', '')

            # Create steps for ALL forward_to recipients
            forwarded_users = list(forward_to) if forward_to else []
            step_number = 1
            for forward_user in forwarded_users:
                step = MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=forward_user,
                    action='created',
                    note=note_text,
                )
                step_number += 1

            # Create a temporary step for attachments (linked to first recipient)
            first_step = memo.steps.first()
            _handle_attachments(request, memo, step=first_step)

            # Create notifications for all forward_to recipients
            for forward_user in forwarded_users:
                _create_memo_notification(
                    tenant=tenant,
                    user=forward_user,
                    title=f"New Memo: {memo.title}",
                    message=f"A new memo has been created and assigned to you by {memo.submitter_display}.",
                    memo=memo
                )

            # Create steps and notify CC users
            for cc_user in cc_users:
                # Create step for CC user
                MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action='created',
                    note=f"CC: {note_text}",
                )
                step_number += 1
                
                # Notify CC user
                _create_memo_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"New Memo (CC): {memo.title}",
                    message=f"You have been CC'd on a new memo by {memo.submitter_display}.",
                    memo=memo
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                # Create step for BCC user
                MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action='created',
                    note=f"BCC: {note_text}",
                )
                step_number += 1
                
                # Notify BCC user
                _create_memo_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"New Memo: {memo.title}",
                    message=f"A new memo has been shared with you by {memo.submitter_display}.",
                    memo=memo
                )
            # Send external notification if applicable
            _notify_external_if_needed(request, memo, "Created")

            messages.success(request, f'Memo {memo.reference_number} created successfully.', extra_tags='memo')
            return redirect('memo:memo_detail', pk=memo.pk)
    else:
        form = MemoCreateForm(request=request)

    return render(request, 'memo/memo_create.html', {'form': form})


@login_required
def memo_edit(request, pk):
    """Edit a draft memo."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant, created_by=user, status='draft')
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user, status='draft')

    if request.method == 'POST':
        form = MemoCreateForm(request.POST, request.FILES, request=request, instance=memo)
        if form.is_valid():
            action = request.POST.get('action')
            is_draft = action == 'draft'

            memo = form.save(commit=False)
            memo.status = 'draft' if is_draft else 'pending'

            forward_to = form.cleaned_data.get('forward_to')
            if is_draft:
                memo.current_holder = user
            elif forward_to and forward_to.exists():
                memo.current_holder = forward_to.first()
            else:
                receptionists = _get_receptionist_users(tenant) if tenant else CustomUser.objects.none()
                if receptionists.exists():
                    memo.current_holder = receptionists.first()
                else:
                    memo.current_holder = user

            memo.save()

            if is_draft:
                step = MemoStep.objects.create(
                    memo=memo,
                    step_number=_get_next_step_number(memo),
                    from_user=user,
                    to_user=user,
                    action='drafted',
                    note=form.cleaned_data.get('note', ''),
                )
                _handle_attachments(request, memo, step=step)
                # Assign to_users for draft as well
                memo.to_users.set(forward_to)
                messages.success(request, f'Draft memo {memo.reference_number} updated.', extra_tags='memo')
                return redirect('memo:memo_detail', pk=memo.pk)

            # Assign to_users with all forward_to recipients
            memo.to_users.set(forward_to)

            # Persist CC/BCC users on the memo
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])
            memo.cc_users.set(cc_users)
            memo.bcc_users.set(bcc_users)

            # Memo is being sent - create steps for ALL recipients
            note_text = form.cleaned_data.get('note', '')
            step_number = _get_next_step_number(memo)
            
            # Create steps for all forward_to recipients
            forwarded_users = list(forward_to) if forward_to else []
            for forward_user in forwarded_users:
                step = MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=forward_user,
                    action='created',
                    note=note_text,
                )
                step_number += 1
            
            # Handle attachments with first step
            first_step = memo.steps.first()
            _handle_attachments(request, memo, step=first_step)

            # Create notifications for all forward_to recipients
            for forward_user in forwarded_users:
                _create_memo_notification(
                    tenant=tenant,
                    user=forward_user,
                    title=f"New Memo: {memo.title}",
                    message=f"A new memo has been sent to you by {memo.submitter_display}.",
                    memo=memo
                )
            
            # Create steps and notify CC users
            for cc_user in cc_users:
                MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action='created',
                    note=f"CC: {note_text}",
                )
                step_number += 1
                
                _create_memo_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"New Memo (CC): {memo.title}",
                    message=f"You have been CC'd on a new memo by {memo.submitter_display}.",
                    memo=memo
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action='created',
                    note=f"BCC: {note_text}",
                )
                step_number += 1
                
                _create_memo_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"New Memo: {memo.title}",
                    message=f"A new memo has been shared with you by {memo.submitter_display}.",
                    memo=memo
                )
                    
            _notify_external_if_needed(request, memo, "Created")

            messages.success(request, f'Memo {memo.reference_number} sent successfully.', extra_tags='memo')
            return redirect('memo:memo_detail', pk=memo.pk)
    else:
        form = MemoCreateForm(request=request, instance=memo)

    return render(request, 'memo/memo_edit.html', {'form': form, 'memo': memo})



# ─── Detail ─────────────────────────────────────────────────────────────────

@login_required
def memo_detail(request, pk):
    """View full memo trail with steps, comments, and attachments."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    # Most recent first so the earliest (step 1) sits at the bottom.
    steps = memo.steps.select_related('from_user', 'to_user').order_by('-step_number')
    attachments = memo.attachments.select_related('uploaded_by', 'step').order_by('uploaded_at')

    # Filter comments based on privacy
    all_comments = memo.comments.select_related('author', 'step').order_by('created_at')
    visible_comments = []
    for comment in all_comments:
        if not comment.is_private:
            visible_comments.append(comment)
        elif comment.author == user or memo.current_holder == user:
            visible_comments.append(comment)

    # Determine available actions
    is_holder = (memo.current_holder == user)
    is_creator = (memo.created_by == user)
    # Check if user is a recipient (has a step assigned to them)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    # Recipients can act on the memo (forward, approve, reject, etc.)
    can_act = (is_holder or is_recipient) and memo.can_be_acted_on
    
    can_forward = can_act
    can_approve = can_act
    can_reject = can_act
    can_request_info = can_act and not is_creator
    can_escalate = (is_holder or is_creator or is_recipient) and memo.can_be_acted_on
    can_complete = is_creator and memo.status == 'approved'
    can_close = is_creator and memo.status == 'rejected'
    can_reopen = is_creator and memo.status in ('closed', 'completed')
    can_mark_in_progress = (is_holder or is_creator or is_recipient) and memo.status in ['pending', 'in_view', 'escalated']
    can_keep_in_view = (is_holder or is_creator or is_recipient) and memo.status == 'pending'
    can_record_response = can_act and not (is_creator and memo.status == 'pending')
    # Withdraw: creator can withdraw a memo while it's still pending
    can_withdraw = is_creator and memo.status == 'pending'

    comment_form = MemoCommentForm()
    forward_form = MemoForwardForm(request=request, memo=memo)

    context = {
        'memo': memo,
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
    return render(request, 'memo/memo_detail.html', context)


# ─── Forward / Route ────────────────────────────────────────────────────────

@login_required
def memo_forward(request, pk):
    """Forward/route a memo to the next person with an action."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (memo.current_holder == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this memo.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if not memo.can_be_acted_on:
        messages.error(request, 'This memo cannot be acted on in its current state.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if request.method == 'POST':
        form = MemoForwardForm(request.POST, request.FILES, request=request, memo=memo)
        if form.is_valid():
            to_users = form.cleaned_data['to_users']
            action = form.cleaned_data['action']
            note = form.cleaned_data.get('note', '')
            is_private = form.cleaned_data.get('is_private_note', False)

            # Get CC and BCC users
            cc_users = form.cleaned_data.get('cc_users', [])
            bcc_users = form.cleaned_data.get('bcc_users', [])

            # Persist CC/BCC users on the memo
            memo.cc_users.set(cc_users)
            memo.bcc_users.set(bcc_users)

            # Create steps for ALL to_users recipients
            step_number = _get_next_step_number(memo)
            routed_users = list(to_users)
            
            for to_user in routed_users:
                step = MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=to_user,
                    action=action,
                    note=note,
                    is_private_note=is_private,
                )
                step_number += 1

            # Handle attachments with first step
            first_step = memo.steps.order_by('-step_number').first()
            _handle_attachments(request, memo, step=first_step)

            # Update memo state
            # The person who is acting becomes the current holder (tracks who last acted)
            # Then based on the action, we may route it to someone else
            primary_to_user = routed_users[0] if routed_users else user
            
            if action == 'approved':
                memo.status = 'approved'
                # For approval, if routing to someone specific, they become holder
                # Otherwise, the person who approved becomes the holder
                memo.current_holder = primary_to_user
            elif action == 'rejected':
                memo.status = 'rejected'
                # For rejection, send back to creator
                memo.current_holder = memo.created_by
            elif action == 'escalated':
                memo.status = 'escalated'
                # For escalation, send to the escalation recipient
                memo.current_holder = primary_to_user
            elif action == 'returned':
                memo.status = 'in_view'
                # For return, send back to creator
                memo.current_holder = memo.created_by
            else:
                # For forward/minute, send to the first new recipient
                memo.status = 'pending'
                memo.current_holder = primary_to_user
            memo.save()

            # Create notifications for all to_users recipients
            for routed_user in routed_users:
                _create_memo_notification(
                    tenant=tenant,
                    user=routed_user,
                    title="Memo Routed To You",
                    message=f"Memo '{memo.title}' was routed to you by {user.get_full_name()} ({action}).",
                    memo=memo
                )
            
            # Create steps and notify CC users
            for cc_user in cc_users:
                # Create step for CC user
                MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=cc_user,
                    action=action,
                    note=f"CC: {note}",
                    is_private_note=is_private,
                )
                step_number += 1
                
                # Notify CC user
                _create_memo_notification(
                    tenant=tenant,
                    user=cc_user,
                    title=f"Memo Routed (CC): {memo.title}",
                    message=f"You have been CC'd on a memo routed by {user.get_full_name()} ({action}).",
                    memo=memo
                )
            
            # Create steps and notify BCC users
            for bcc_user in bcc_users:
                # Create step for BCC user
                MemoStep.objects.create(
                    memo=memo,
                    step_number=step_number,
                    from_user=user,
                    to_user=bcc_user,
                    action=action,
                    note=f"BCC: {note}",
                    is_private_note=is_private,
                )
                step_number += 1
                
                # Notify BCC user
                _create_memo_notification(
                    tenant=tenant,
                    user=bcc_user,
                    title=f"Memo Routed: {memo.title}",
                    message=f"A memo has been shared with you by {user.get_full_name()} ({action}).",
                    memo=memo
                )
            # Send external notification if applicable
            _notify_external_if_needed(request, memo, action.capitalize())

            # Create success message
            recipient_names = ', '.join([u.get_full_name() or u.username for u in routed_users[:3]])
            if len(routed_users) > 3:
                recipient_names += f' and {len(routed_users) - 3} others'
            
            messages.success(request, f'Memo {action} to {recipient_names}.', extra_tags='memo')
            return redirect('memo:memo_detail', pk=pk)
    else:
        form = MemoForwardForm(request=request, memo=memo)

    return render(request, 'memo/memo_forward.html', {'form': form, 'memo': memo})


# ─── Quick Actions (approve / reject / escalate) ───────────────────────────

@login_required
def memo_approve(request, pk):
    """Quick approve and return to creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (memo.current_holder == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this memo.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if request.method == 'POST' and memo.can_be_acted_on:
        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = memo.created_by

        step = MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='approved',
            note=request.POST.get('note', ''),
        )
        memo.status = 'approved'
        memo.current_holder = to_user
        memo.save()
        
        # Notify the recipient (send_to user or creator)
        if to_user:
            _create_memo_notification(
                tenant=tenant,
                user=to_user,
                title="Memo Approved",
                message=f"Memo '{memo.title}' was approved by {user.get_full_name()}.",
                memo=memo
            )
        # Also notify the creator if the memo was sent to someone else
        if send_to_id and memo.created_by and to_user != memo.created_by:
            _create_memo_notification(
                tenant=tenant,
                user=memo.created_by,
                title="Memo Approved",
                message=f"Your memo '{memo.title}' was approved by {user.get_full_name()} and sent to {to_user.get_full_name()}.",
                memo=memo
            )
        # Send external notification if applicable
        _notify_external_if_needed(request, memo, "Approved")
        
        messages.success(request, 'Memo approved successfully.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


@login_required
@login_required
def memo_reject(request, pk):
    """Quick reject and return to creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (memo.current_holder == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this memo.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if request.method == 'POST' and memo.can_be_acted_on:
        note = (request.POST.get('note', '') or '').strip()
        if not note:
            messages.error(request, 'Please provide a reason for rejection.', extra_tags='memo')
            return redirect('memo:memo_detail', pk=pk)

        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = memo.created_by

        step = MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='rejected',
            note=note,
        )
        memo.status = 'rejected'
        memo.current_holder = to_user
        memo.save()
        
        # Notify the recipient (send_to user or creator)
        if to_user:
            _create_memo_notification(
                tenant=tenant,
                user=to_user,
                title="Memo Rejected",
                message=f"Memo '{memo.title}' was rejected by {user.get_full_name()}.",
                memo=memo
            )
        # Also notify the creator if the memo was sent to someone else
        if send_to_id and memo.created_by and to_user != memo.created_by:
            _create_memo_notification(
                tenant=tenant,
                user=memo.created_by,
                title="Memo Rejected",
                message=f"Your memo '{memo.title}' was rejected by {user.get_full_name()} and sent to {to_user.get_full_name()}.",
                memo=memo
            )
        # Send external notification if applicable
        _notify_external_if_needed(request, memo, "Rejected")
        
        messages.success(request, 'Memo rejected.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


@login_required
def memo_escalate(request, pk):
    """Escalate a memo."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    # Both holder and creator can escalate
    if user != memo.current_holder and user != memo.created_by:
        messages.error(request, 'You do not have permission to escalate this memo.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if request.method == 'POST' and memo.can_be_acted_on:
        to_user_id = request.POST.get('escalate_to')
        to_user = get_object_or_404(CustomUser, pk=to_user_id)

        step = MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='escalated',
            note=request.POST.get('note', ''),
        )
        memo.status = 'escalated'
        memo.current_holder = to_user
        memo.save()
        
        # Create notification for recipient
        _create_memo_notification(
            tenant=tenant,
            user=to_user,
            title="Memo Escalated To You",
            message=f"Memo '{memo.title}' was escalated to you by {user.get_full_name()}.",
            memo=memo
        )
        # Send external notification if applicable
        _notify_external_if_needed(request, memo, "Escalated")
        
        messages.success(request, f'Memo escalated to {to_user.username}.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


@login_required
def memo_request_info(request, pk):
    """Request more information from the memo creator."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None)

    # Check if user is current holder OR a recipient
    is_holder = (memo.current_holder == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_recipient):
        messages.error(request, 'You do not have permission to act on this memo.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if not memo.can_be_acted_on:
        messages.error(request, 'This memo cannot be acted on in its current state.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if request.method == 'POST':
        note = _require_note(request, 'Please specify what information you need.')
        if note is None:
            return redirect('memo:memo_detail', pk=pk)

        # Determine recipient: optional send_to user, or fall back to creator
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = memo.created_by

        # Return memo to creator with request for info
        step = MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='request_info',
            note=note,
        )
        
        memo.status = 'in_view'
        memo.current_holder = to_user
        memo.save()
        
        # Notify the recipient
        if to_user:
            _create_memo_notification(
                tenant=tenant,
                user=to_user,
                title="More Information Requested",
                message=f"More information has been requested for memo '{memo.title}' by {user.get_full_name()}.",
                memo=memo
            )
        
        # Send external notification if applicable
        _notify_external_if_needed(request, memo, "More Information Requested")
        
        messages.success(request, 'Request for more information sent.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


# ─── Complete / Close / Reopen ──────────────────────────────────────────────

@login_required
def memo_complete(request, pk):
    """Mark memo as completed (by creator after approval)."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Try to get memo for authenticated users
    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None)

    # Check permissions: either the creator or external user with token
    is_creator = memo.created_by == user
    is_external_with_permission = False
    
    if memo.is_external and not is_creator:
        # Check if this is an external user accessing via their memo
        # External users should use the external_status view with token
        # But if they somehow got here, check memo settings
        memo_setting = MemoSetting.objects.filter(tenant=tenant).first()
        is_external_with_permission = memo_setting and memo_setting.allow_external_completion
    
    if not (is_creator or is_external_with_permission):
        messages.error(request, 'You do not have permission to complete this memo.', extra_tags='memo')
        return redirect('memo:memo_detail', pk=pk)

    if request.method == 'POST' and memo.status == 'approved':
        memo.status = 'completed'
        memo.completed_at = timezone.now()
        memo.save()
        messages.success(request, 'Memo marked as completed.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


@login_required
def memo_close(request, pk):
    """Mark memo as closed (by creator after rejection)."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant, created_by=user)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and memo.status == 'rejected':
        memo.status = 'closed'
        memo.closed_at = timezone.now()
        memo.save()
        messages.success(request, 'Memo closed.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


@login_required
def memo_reopen(request, pk):
    """Reopen a closed or completed memo."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant, created_by=user)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and memo.status in ('closed', 'completed'):
        memo.status = 'in_progress'
        memo.closed_at = None
        memo.completed_at = None
        memo.current_holder = user
        memo.save()

        MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=user,
            action='forwarded',
            note='Memo reopened by creator.',
        )
        messages.success(request, 'Memo reopened.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


# ─── Comments ───────────────────────────────────────────────────────────────

@login_required
def memo_add_comment(request, pk):
    """Add a comment to a memo."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST':
        form = MemoCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.memo = memo
            comment.author = user
            comment.save()
            messages.success(request, 'Comment added.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


# ─── External Submission ────────────────────────────────────────────────────

def memo_external_submit(request, slug):
    """Public memo submission form (no auth required)."""
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

            memo = Memo.objects.create(
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
            MemoStep.objects.create(
                memo=memo,
                step_number=1,
                from_user=None,
                to_user=current_holder,
                action='received',
                note=f"External submission from {form.cleaned_data['submitter_name']}",
            )

            # Handle attachments
            files = request.FILES.getlist('attachments')
            for f in files:
                MemoAttachment.objects.create(
                    memo=memo,
                    file=f,
                    original_name=f.name,
                )

            # Notify the assigned staff member in the bell icon notifications
            if current_holder:
                _create_memo_notification(
                    tenant=tenant,
                    user=current_holder,
                    title=f"New External Memo: {memo.title}",
                    message=f"You received a new external memo from {memo.external_name or memo.external_email or 'External'} ({memo.reference_number}).",
                    memo=memo
                )

            messages.success(request, 'Your request has been submitted successfully.', extra_tags='memo')
            return render(request, 'memo/external_submit_success.html', {
                'memo': memo,
                'tenant': tenant,
            })
    else:
        form = MemoExternalSubmissionForm(tenant=tenant)

    return render(request, 'memo/external_submit.html', {
        'form': form,
        'tenant': tenant,
    })


def memo_external_submit_personal(request, token):
    """Public memo submission form for a specific user (no auth required)."""
    from documents.models import CustomUser
    target_user = get_object_or_404(CustomUser, personal_external_token=token, is_active=True)
    tenant = target_user.tenant

    if not tenant:
        return render(request, 'memo/external_submit.html', {
            'form': None,
            'tenant': None,
            'error': 'This user is not associated with an organization.',
        })

    if request.method == 'POST':
        form = MemoExternalSubmissionForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            # Create memo assigned directly to the target user
            memo = Memo.objects.create(
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
            MemoStep.objects.create(
                memo=memo,
                step_number=1,
                from_user=None,
                to_user=target_user,
                action='received',
                note=f"External submission from {form.cleaned_data['submitter_name']} (sent directly to {target_user.get_full_name() or target_user.username})",
            )

            # Handle attachments
            files = request.FILES.getlist('attachments')
            for f in files:
                MemoAttachment.objects.create(
                    memo=memo,
                    file=f,
                    original_name=f.name,
                )

            # Notify the target user
            _create_memo_notification(
                tenant=tenant,
                user=target_user,
                title=f"New External Memo: {memo.title}",
                message=f"You received a new external memo from {memo.external_name or memo.external_email or 'External'} ({memo.reference_number}).",
                memo=memo
            )

            messages.success(request, 'Your request has been submitted successfully.', extra_tags='memo')
            return render(request, 'memo/external_submit_success.html', {
                'memo': memo,
                'tenant': tenant,
            })
    else:
        form = MemoExternalSubmissionForm(tenant=tenant)

    return render(request, 'memo/external_submit.html', {
        'form': form,
        'tenant': tenant,
        'target_user': target_user,
    })


def memo_external_status(request, token):
    """External user: view memo status (no auth required)."""
    memo = get_object_or_404(Memo, external_token=token)
    tenant = memo.tenant

    # Check tenant settings
    memo_setting = MemoSetting.objects.filter(tenant=tenant).first()

    # Most recent first for external tracking view as well.
    steps = memo.steps.order_by('-step_number')
    # External users see all steps, but private notes are hidden
    visible_steps = steps

    # Public comments only
    comments = memo.comments.filter(is_private=False).order_by('created_at')

    can_escalate = memo_setting.allow_external_escalation if memo_setting else False
    can_complete = memo_setting.allow_external_completion if memo_setting else False

    context = {
        'memo': memo,
        'steps': visible_steps,
        'comments': comments,
        'can_escalate': can_escalate and memo.can_be_acted_on,
        'can_complete': can_complete and memo.status == 'approved',
    }
    return render(request, 'memo/external_status.html', context)


def memo_external_complete(request, token):
    """External user: mark memo as completed (no auth required)."""
    memo = get_object_or_404(Memo, external_token=token)
    tenant = memo.tenant

    # Check tenant settings
    memo_setting = MemoSetting.objects.filter(tenant=tenant).first()
    can_complete = memo_setting.allow_external_completion if memo_setting else False

    if not can_complete:
        messages.error(request, 'You do not have permission to complete this memo.', extra_tags='memo')
        return redirect('memo:external_status', token=token)

    if request.method == 'POST' and memo.status == 'approved':
        memo.status = 'completed'
        memo.completed_at = timezone.now()
        memo.save()
        
        # Create a step for the completion
        MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            action='completed',
            from_user=None,
            to_user=None,
            note='Marked as completed by external user',
            is_private_note=False
        )
        
        messages.success(request, 'Memo marked as completed.', extra_tags='memo')

    return redirect('memo:external_status', token=token)


# ─── Categories ─────────────────────────────────────────────────────────────

@login_required
def memo_categories(request):
    """List memo categories."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        categories = MemoCategory.objects.filter(tenant=tenant)
    else:
        categories = MemoCategory.objects.filter(tenant=None, created_by=user)

    return render(request, 'memo/categories.html', {'categories': categories})


@login_required
def memo_category_create(request):
    """Create a memo category."""
    tenant = request.effective_tenant
    user = request.effective_user

    if request.method == 'POST':
        form = MemoCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.tenant = tenant
            cat.created_by = user
            cat.save()
            messages.success(request, 'Category created.', extra_tags='memo')
            return redirect('memo:categories')
    else:
        form = MemoCategoryForm()

    return render(request, 'memo/category_form.html', {'form': form, 'action': 'Create'})


@login_required
def memo_category_edit(request, pk):
    """Edit a memo category."""
    tenant = request.effective_tenant

    if tenant:
        cat = get_object_or_404(MemoCategory, pk=pk, tenant=tenant)
    else:
        cat = get_object_or_404(MemoCategory, pk=pk, tenant=None)

    if request.method == 'POST':
        form = MemoCategoryForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated.', extra_tags='memo')
            return redirect('memo:categories')
    else:
        form = MemoCategoryForm(instance=cat)

    return render(request, 'memo/category_form.html', {'form': form, 'action': 'Edit', 'category': cat})


@login_required
def memo_category_delete(request, pk):
    """Delete a memo category."""
    tenant = request.effective_tenant

    if tenant:
        cat = get_object_or_404(MemoCategory, pk=pk, tenant=tenant)
    else:
        cat = get_object_or_404(MemoCategory, pk=pk, tenant=None)

    if request.method == 'POST':
        cat.delete()
        messages.success(request, 'Category deleted.', extra_tags='memo')
        return redirect('memo:categories')

    return render(request, 'memo/category_confirm_delete.html', {'category': cat})


# ─── Settings ───────────────────────────────────────────────────────────────

@login_required
def memo_settings(request):
    """Tenant memo settings."""
    tenant = request.effective_tenant
    if not tenant:
        messages.error(request, 'Settings are only available for organization accounts.', extra_tags='memo')
        return redirect('memo:dashboard')

    # Check if user is tenant admin or superuser
    is_admin = request.user.is_superuser or request.user.roles.filter(name='Admin').exists()

    setting, created = MemoSetting.objects.get_or_create(tenant=tenant)

    if request.method == 'POST':
        # Only allow admins to update external submission settings
        if not is_admin:
            messages.error(request, 'You do not have permission to update these settings.', extra_tags='memo')
            return redirect('memo:settings')
            
        form = MemoSettingForm(request.POST, instance=setting)
        if form.is_valid():
            form.save()
            messages.success(request, 'Memo settings updated.', extra_tags='memo')
            return redirect('memo:settings')
    else:
        form = MemoSettingForm(instance=setting)

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
    categories = MemoCategory.objects.filter(tenant=tenant).order_by('name')

    return render(request, 'memo/settings.html', {
        'form': form,
        'staff_members': staff_members,
        'categories': categories,
        'is_admin': is_admin,
    })


# ─── Receptionist Management ───────────────────────────────────────────────

@login_required
def memo_manage_receptionist(request):
    """Assign/revoke Receptionist role (Admin only)."""
    tenant = request.effective_tenant
    user = request.effective_user

    # Only admins can manage this
    is_admin = user.roles.filter(name='Admin').exists() or user.is_superuser
    if not is_admin:
        messages.error(request, 'Only admins can manage the Receptionist role.', extra_tags='memo')
        return redirect('memo:dashboard')

    # Ensure the Receptionist role exists
    receptionist_role, _ = Role.objects.get_or_create(name='Receptionist', defaults={'description': 'Handles incoming memos with no specific recipient'})

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
            messages.success(request, f'{target_user.username} assigned as Receptionist.', extra_tags='memo')
        elif action == 'revoke':
            target_user.roles.remove(receptionist_role)
            messages.success(request, f'Receptionist role removed from {target_user.username}.', extra_tags='memo')

        return redirect('memo:manage_receptionist')

    # Annotate who has the role
    receptionist_ids = set(
        _get_receptionist_users(tenant).values_list('id', flat=True)
    ) if tenant else set()

    context = {
        'staff': staff,
        'receptionist_ids': receptionist_ids,
    }
    return render(request, 'memo/manage_receptionist.html', context)


# ==========================================
# MISSING FEATURES: IN PROGRESS, NOTIFS
# ==========================================

@login_required
def memo_mark_in_progress(request, pk):
    """Mark a memo as 'In Progress'."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (memo.current_holder == user)
    is_creator = (memo.created_by == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this memo.", extra_tags='memo')
        return redirect('memo:memo_detail', pk=memo.pk)

    if request.method == 'POST':
        if memo.status in ['pending', 'in_view', 'escalated']:
            memo.status = 'in_progress'
            memo.current_holder = user  # The person marking it in progress becomes the current holder
            memo.save()
            
            # Send external notification if applicable
            _notify_external_if_needed(request, memo, "In Progress")
            
            messages.success(request, "Memo marked as In Progress.", extra_tags='memo')
        else:
            messages.error(request, f"Cannot mark as In Progress from state '{memo.get_status_display()}'.", extra_tags='memo')
    
    return redirect('memo:memo_detail', pk=memo.pk)

@login_required
def memo_keep_in_view(request, pk):
    """Mark a memo as 'In View' manually."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (memo.current_holder == user)
    is_creator = (memo.created_by == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this memo.", extra_tags='memo')
        return redirect('memo:memo_detail', pk=memo.pk)

    if request.method == 'POST':
        if memo.can_be_acted_on:
            # Determine recipient: optional send_to user, or fall back to self
            send_to_id = (request.POST.get('to_user') or '').strip()
            if send_to_id:
                to_user = get_object_or_404(CustomUser, pk=send_to_id)
            else:
                to_user = user

            memo.status = 'in_view'
            memo.current_holder = to_user
            memo.save()

            note = (request.POST.get('note', '') or '').strip() or 'Memo kept in view.'

            MemoStep.objects.create(
                memo=memo,
                step_number=_get_next_step_number(memo),
                from_user=user,
                to_user=to_user,
                action='kept_in_view',
                note=note,
            )

            # Notify the recipient if different from sender
            if to_user != user:
                _create_memo_notification(
                    tenant=tenant,
                    user=to_user,
                    title="Memo Kept In View",
                    message=f"Memo '{memo.title}' has been kept in view by {user.get_full_name()} and sent to you.",
                    memo=memo
                )

            # Send external notification if applicable
            _notify_external_if_needed(request, memo, "In View")

            messages.success(request, "Memo marked as In-View.", extra_tags='memo')
        else:
            messages.error(request, f"Cannot keep In-View from state '{memo.get_status_display()}'.", extra_tags='memo')
    
    return redirect('memo:memo_detail', pk=memo.pk)


@login_required
def memo_positive_response(request, pk):
    """Record a positive response with a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (memo.current_holder == user)
    is_creator = (memo.created_by == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this memo.", extra_tags='memo')
        return redirect('memo:memo_detail', pk=memo.pk)

    if request.method == 'POST' and memo.can_be_acted_on:
        note = _require_note(request, 'Please add a note for the positive response.')
        if note is None:
            return redirect('memo:memo_detail', pk=memo.pk)

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='positive_response',
            note=note,
        )

        memo.status = 'positive_response'
        memo.current_holder = to_user
        memo.save()

        # Notify the recipient if different from sender
        if to_user != user:
            _create_memo_notification(
                tenant=tenant,
                user=to_user,
                title="Positive Recommendation",
                message=f"Memo '{memo.title}' received a positive recommendation from {user.get_full_name()}.",
                memo=memo
            )

        messages.success(request, 'Positive response recorded.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=memo.pk)


@login_required
def memo_negative_response(request, pk):
    """Record a negative response with a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    # Check if user is current holder, creator, OR a recipient
    is_holder = (memo.current_holder == user)
    is_creator = (memo.created_by == user)
    is_recipient = memo.steps.filter(to_user=user).exists()
    
    if not (is_holder or is_creator or is_recipient):
        messages.error(request, "You don't have permission to update this memo.", extra_tags='memo')
        return redirect('memo:memo_detail', pk=memo.pk)

    if request.method == 'POST' and memo.can_be_acted_on:
        note = _require_note(request, 'Please add a note for the negative response.')
        if note is None:
            return redirect('memo:memo_detail', pk=memo.pk)

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='negative_response',
            note=note,
        )

        memo.status = 'negative_response'
        memo.current_holder = to_user
        memo.save()

        # Notify the recipient if different from sender
        if to_user != user:
            _create_memo_notification(
                tenant=tenant,
                user=to_user,
                title="Negative Recommendation",
                message=f"Memo '{memo.title}' received a negative recommendation from {user.get_full_name()}.",
                memo=memo
            )

        messages.success(request, 'Negative response recorded.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=memo.pk)


@login_required
def memo_keep_in_view_with_note(request, pk):
    """Keep a memo in view and record a required note."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    if memo.current_holder != user and memo.created_by != user:
        messages.error(request, "You don't have permission to update this memo.", extra_tags='memo')
        return redirect('memo:memo_detail', pk=memo.pk)

    if request.method == 'POST' and memo.can_be_acted_on:
        note = _require_note(request, 'Please add a note for keeping this memo in view.')
        if note is None:
            return redirect('memo:memo_detail', pk=memo.pk)

        # Always move the memo into the "In View" state while it can still be acted on,
        # so the main status and filters reflect this action.
        memo.status = 'in_view'
        memo.save(update_fields=['status'])

        MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=memo.current_holder,
            action='kept_in_view',
            note=note,
        )
        messages.success(request, 'Memo kept in view with note.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=memo.pk)


@login_required
def memo_withdraw(request, pk):
    """Withdraw a memo (by creator). Sets status to closed."""
    tenant = request.effective_tenant
    user = request.effective_user

    if tenant:
        memo = get_object_or_404(Memo, pk=pk, tenant=tenant, created_by=user)
    else:
        memo = get_object_or_404(Memo, pk=pk, tenant=None, created_by=user)

    if request.method == 'POST' and memo.status == 'pending':
        note = (request.POST.get('note', '') or '').strip()
        if not note:
            note = 'Memo withdrawn by creator.'

        # Determine recipient: optional send_to user, or fall back to self
        send_to_id = (request.POST.get('to_user') or '').strip()
        if send_to_id:
            to_user = get_object_or_404(CustomUser, pk=send_to_id)
        else:
            to_user = user

        MemoStep.objects.create(
            memo=memo,
            step_number=_get_next_step_number(memo),
            from_user=user,
            to_user=to_user,
            action='withdrawn',
            note=note,
        )
        memo.status = 'closed'
        memo.closed_at = timezone.now()
        memo.current_holder = to_user
        memo.save()

        # Notify the recipient if different from creator
        if to_user != user:
            _create_memo_notification(
                tenant=tenant,
                user=to_user,
                title="Memo Withdrawn",
                message=f"Memo '{memo.title}' was withdrawn by {user.get_full_name()}.",
                memo=memo
            )
        # Also notify the current holder if it's not the creator or recipient
        elif memo.current_holder and memo.current_holder != user and memo.current_holder != to_user:
            _create_memo_notification(
                tenant=tenant,
                user=memo.current_holder,
                title="Memo Withdrawn",
                message=f"Memo '{memo.title}' was withdrawn by {user.get_full_name()}.",
                memo=memo
            )
        # Send external notification if applicable
        _notify_external_if_needed(request, memo, "Withdrawn")

        messages.success(request, 'Memo withdrawn successfully.', extra_tags='memo')
    else:
        messages.error(request, 'This memo cannot be withdrawn.', extra_tags='memo')

    return redirect('memo:memo_detail', pk=pk)


def _create_memo_notification(tenant, user, title, message, url=None, memo=None):
    """Helper to create a bell icon notification for memo events."""
    from django.contrib.contenttypes.models import ContentType
    try:
        # Build the link URL from the memo if not provided
        if not url and memo:
            url = f"/memo/{memo.pk}/"

        kwargs = {
            'tenant': tenant,
            'title': title,
            'message': message,
            'type': Notification.NotificationType.MEMO,
            'is_active': True,
            'link': url,
        }

        # Also set generic relation so get_absolute_url() has multiple fallback paths
        if memo:
            kwargs['content_type'] = ContentType.objects.get_for_model(memo)
            kwargs['object_id'] = memo.pk

        notif = Notification.objects.create(**kwargs)
        UserNotification.objects.create(
            tenant=tenant,
            user=user,
            notification=notif
        )
    except Exception as e:
        print(f"Failed to create notification: {e}")


def _notify_external_if_needed(request, memo, action_taken):
    """Send email to external submitter if tenant settings allow it."""
    if not memo.is_external or not memo.external_email:
        return
        
    try:
        settings = MemoSetting.objects.get(tenant=memo.tenant)
        if not settings.notify_external_on_move:
            return
            
        subject = f"Memo Update: {memo.title} [{memo.reference_number}]"
        
        base_domain = "127.0.0.1:8000" if django_settings.DEBUG else "teammanager.ng"
        protocol = "http" if django_settings.DEBUG else "https"
        status_url = f"{protocol}://{base_domain}/memo/external/status/{memo.external_token}/"
        
        html_message = f"""
        <html><body>
        <h2>Your Memo has been updated</h2>
        <p><strong>Reference:</strong> {memo.reference_number}</p>
        <p><strong>Title:</strong> {memo.title}</p>
        <p><strong>New Action/Status:</strong> {action_taken} ({memo.get_status_display()})</p>
        <br>
        <p>You can track the full progress of your memo here:</p>
        <p><a href="{status_url}">{status_url}</a></p>
        </body></html>
        """

        send_mail(
            subject=subject,
            message=f"Your memo has been updated. New status: {action_taken}. Track here: {status_url}",
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[memo.external_email],
            fail_silently=True,
            html_message=html_message
        )
    except MemoSetting.DoesNotExist:
        pass
    except Exception as e:
        print(f"Failed to send external email notification: {e}")
