# tickets/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from documents.models import (
    Ticket, TicketComment, TicketCategory, TicketPriority,
    QueueEntry, TicketStatusHistory,
)
from documents.forms import (
    TicketCreatePublicForm, TicketCreateStaffForm,
    TicketStatusForm, TicketAssignForm,
    TicketCommentForm, QueueIssueForm, TicketLookupForm,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_tenant(request):
    return request.user.tenant if request.user.is_authenticated else None


def _is_ticket_staff(user):
    """Returns True if the user can manage tickets (HR, Admin, Receptionist, staff)."""
    if user.is_staff or user.is_superuser:
        return True
    role_names = set(user.roles.values_list('name', flat=True))
    return bool(role_names & {'HR', 'Admin', 'Receptionist', 'Support'})


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC / CUSTOMER-FACING VIEWS
# ══════════════════════════════════════════════════════════════════════════════

def ticket_submit_public(request, tenant_slug=None):
    """
    Public ticket submission form — accessible without login.
    tenant_slug allows multi-tenant routing from a public URL.
    """
    from tenants.models import Tenant
    from documents.models import Notification, UserNotification
    from django.contrib.contenttypes.models import ContentType
    
    if tenant_slug:
        tenant = get_object_or_404(Tenant, slug=tenant_slug)
    elif request.user.is_authenticated:
        tenant = request.user.tenant
    else:
        tenant = None

    if request.method == 'POST':
        form = TicketCreatePublicForm(request.POST, tenant=tenant)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.tenant = tenant
            ticket.source = 'online'
            if request.user.is_authenticated:
                ticket.created_by = request.user
            ticket.save()
            
            # Create bell notification for staff
            submitter_name = ticket.submitter_display
            notification = Notification.objects.create(
                tenant=tenant,
                title=f"New Support Ticket from {submitter_name}",
                message=f"Ticket {ticket.ticket_number}: {ticket.title}",
                type=Notification.NotificationType.ALERT,
                content_type=ContentType.objects.get_for_model(Ticket),
                object_id=ticket.id,
                link=f'/support/tickets/{ticket.ticket_number}/'
            )
            
            # Notify all staff members
            staff_users = tenant.users.filter(is_staff=True, is_active=True)
            for staff_user in staff_users:
                UserNotification.objects.create(
                    tenant=tenant,
                    user=staff_user,
                    notification=notification
                )
            
            messages.success(request,
                f"Ticket {ticket.ticket_number} submitted successfully. "
                f"Use your ticket number to check status.")
            return redirect('ticket_submitted', token=ticket.access_token)
    else:
        form = TicketCreatePublicForm(tenant=tenant)

    return render(request, 'tickets/public/submit.html', {
        'form':   form,
        'tenant': tenant,
    })


def ticket_submitted(request, token):
    """Confirmation page after public submission. Shows ticket number + status link."""
    ticket = get_object_or_404(Ticket, access_token=token)
    return render(request, 'tickets/public/submitted.html', {'ticket': ticket})


def ticket_status_lookup(request):
    """
    Guest/public ticket status check — ticket number + email or phone.
    """
    ticket = None
    form   = TicketLookupForm(request.GET or None)

    if form.is_valid():
        number  = form.cleaned_data['ticket_number'].strip()
        contact = form.cleaned_data['email_or_phone'].strip()
        ticket  = Ticket.objects.filter(
            ticket_number__iexact=number
        ).filter(
            Q(guest_email__iexact=contact) | Q(guest_phone=contact)
        ).first()

        if not ticket:
            messages.error(request, "No ticket found matching those details.")

    # Public comments only
    comments = ticket.comments.filter(is_internal=False) if ticket else []
    return render(request, 'tickets/public/status.html', {
        'form': form, 'ticket': ticket, 'comments': comments,
    })


# ══════════════════════════════════════════════════════════════════════════════
# STAFF TICKET VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def ticket_list(request):
    """
    Staff ticket list with filters: status, category, priority, assigned_to, search.
    """
    tenant = request.user.tenant
    qs     = Ticket.objects.filter(tenant=tenant).select_related(
        'category', 'priority', 'assigned_to', 'created_by'
    )

    # Filters
    status   = request.GET.get('status', '')
    category = request.GET.get('category', '')
    priority = request.GET.get('priority', '')
    assigned = request.GET.get('assigned', '')
    q        = request.GET.get('q', '')

    if status:   qs = qs.filter(status=status)
    if category: qs = qs.filter(category_id=category)
    if priority: qs = qs.filter(priority_id=priority)
    if assigned == 'me':
        qs = qs.filter(assigned_to=request.user)
    elif assigned == 'unassigned':
        qs = qs.filter(assigned_to__isnull=True)
    if q:
        qs = qs.filter(
            Q(ticket_number__icontains=q) | Q(title__icontains=q) |
            Q(guest_name__icontains=q)    | Q(guest_email__icontains=q)
        )

    paginator = Paginator(qs.order_by('-created_at'), 25)
    page      = paginator.get_page(request.GET.get('page'))

    return render(request, 'tickets/staff/ticket_list.html', {
        'tickets':    page,
        'categories': TicketCategory.objects.filter(tenant=tenant, is_active=True),
        'priorities': TicketPriority.objects.order_by('level'),
        'status_choices': Ticket.STATUS_CHOICES,
        'filters': {
            'status': status, 'category': category,
            'priority': priority, 'assigned': assigned, 'q': q,
        },
        # Summary counts
        'count_open':       Ticket.objects.filter(tenant=tenant).exclude(
                                status__in=('closed','resolved')).count(),
        'count_escalated':  Ticket.objects.filter(tenant=tenant, status='escalated').count(),
        'count_unassigned': Ticket.objects.filter(tenant=tenant,
                                assigned_to__isnull=True).exclude(
                                status__in=('closed','resolved')).count(),
    })


@login_required
def ticket_detail(request, ticket_number):
    """
    Full ticket detail — shows comments (internal hidden from non-staff),
    status history, and action forms.
    """
    tenant = request.user.tenant
    ticket = get_object_or_404(Ticket, tenant=tenant, ticket_number=ticket_number)
    is_staff_user = _is_ticket_staff(request.user)

    comments = ticket.comments.all() if is_staff_user else \
               ticket.comments.filter(is_internal=False)

    comment_form = TicketCommentForm(is_staff=is_staff_user)
    status_form  = TicketStatusForm(instance=ticket)
    assign_form  = TicketAssignForm(instance=ticket, tenant=tenant)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'comment':
            comment_form = TicketCommentForm(request.POST, is_staff=is_staff_user)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.ticket = ticket
                comment.author = request.user
                comment.save()
                messages.success(request, "Comment added.")
                return redirect('ticket_detail', ticket_number=ticket_number)

        elif action == 'status' and is_staff_user:
            old_status  = ticket.status
            status_form = TicketStatusForm(request.POST, instance=ticket)
            if status_form.is_valid():
                note = status_form.cleaned_data.get('note', '')
                ticket = status_form.save()
                TicketStatusHistory.objects.create(
                    ticket=ticket, from_status=old_status,
                    to_status=ticket.status,
                    changed_by=request.user, note=note,
                )
                messages.success(request,
                    f"Status updated to {ticket.get_status_display()}.")
                return redirect('ticket_detail', ticket_number=ticket_number)

        elif action == 'assign' and is_staff_user:
            assign_form = TicketAssignForm(request.POST, instance=ticket, tenant=tenant)
            if assign_form.is_valid():
                t = assign_form.save(commit=False)
                if t.assigned_to and not ticket.assigned_at:
                    t.assigned_at = timezone.now()
                    if t.status == 'new':
                        t.status = 'assigned'
                t.save()
                messages.success(request, "Ticket assigned.")
                return redirect('ticket_detail', ticket_number=ticket_number)

    return render(request, 'tickets/staff/ticket_detail.html', {
        'ticket':        ticket,
        'comments':      comments,
        'history':       ticket.status_history.order_by('changed_at'),
        'comment_form':  comment_form,
        'status_form':   status_form,
        'assign_form':   assign_form,
        'is_staff_user': is_staff_user,
        'queue_entries': ticket.queue_entries.order_by('-issued_at'),
    })


@login_required
def ticket_create_staff(request):
    """Front-desk staff creates a ticket for a walk-in customer."""
    tenant = request.user.tenant
    form   = TicketCreateStaffForm(request.POST or None, tenant=tenant)

    if request.method == 'POST' and form.is_valid():
        ticket = form.save(commit=False)
        ticket.tenant = tenant
        if not ticket.created_by:
            ticket.guest_name  = form.cleaned_data.get('guest_name') or 'Walk-in'
        ticket.save()
        messages.success(request, f"Ticket {ticket.ticket_number} created.")
        return redirect('ticket_detail', ticket_number=ticket.ticket_number)

    return render(request, 'tickets/staff/ticket_create.html', {
        'form': form,
    })

# documents/viewfuncs/ticket_views.py — replace queue_dashboard view

@login_required
def queue_dashboard(request):
    """
    Queue dashboard with role-based filtering:
    - Admin / Receptionist / Superuser → see ALL queues
    - HOD / Department member         → see only their department's queues
    Queues sorted by priority (High → Medium → Low) then by issued_at.
    """
    tenant = request.user.tenant
    today  = timezone.localdate()

    # ── Determine access scope ────────────────────────────────────────────────
    user_role_names = set(request.user.roles.values_list('name', flat=True))
    is_full_access  = (
        request.user.is_staff or
        request.user.is_superuser or
        bool(user_role_names & {'Admin', 'Receptionist'})
    )

    # Resolve the user's department (adjust field name to match your CustomUser model)
    user_department = getattr(request.user, 'department', None)

    # ── Build base queryset ────────────────────────────────────────────────────
    base_qs = QueueEntry.objects.filter(
        tenant=tenant,
        issued_at__date=today,
    ).select_related(
        'category',
        'category__department',
        'ticket',
        'ticket__priority',
        'served_by',
    )

    if not is_full_access and user_department:
        # Department-scoped: only show queues whose category belongs to this dept
        base_qs = base_qs.filter(
            category__department=user_department
        )

    # ── Priority ordering ─────────────────────────────────────────────────────
    # Queue entries are ordered by linked ticket priority (High=3 first),
    # then by issued_at so earlier arrivals are served first within the same priority.
    # Entries without a ticket (no priority) are treated as lowest priority.
    from django.db.models import Case, When, IntegerField, Value
    priority_order = Case(
        When(ticket__priority__level=3, then=Value(1)),   # High   → first
        When(ticket__priority__level=2, then=Value(2)),   # Medium → second
        When(ticket__priority__level=1, then=Value(3)),   # Low    → third
        default=Value(4),                                  # No ticket → last
        output_field=IntegerField(),
    )

    waiting   = base_qs.filter(status='waiting').annotate(
        priority_rank=priority_order
    ).order_by('priority_rank', 'issued_at')

    serving   = base_qs.filter(status='serving').order_by('called_at')
    completed = base_qs.filter(status='completed').order_by('-completed_at')[:20]
    no_show   = base_qs.filter(status='no_show').order_by('-issued_at')[:10]

    # ── Per-category stats ─────────────────────────────────────────────────────
    if is_full_access:
        categories = TicketCategory.objects.filter(tenant=tenant, is_active=True)
    else:
        categories = TicketCategory.objects.filter(
            tenant=tenant,
            is_active=True,
            department=user_department,
        ) if user_department else TicketCategory.objects.none()

    queue_stats = []
    for cat in categories.select_related('department'):
        cat_qs = base_qs.filter(category=cat)
        # Count by priority within this category
        high_count   = cat_qs.filter(status='waiting', ticket__priority__level=3).count()
        medium_count = cat_qs.filter(status='waiting', ticket__priority__level=2).count()
        low_count    = cat_qs.filter(status='waiting', ticket__priority__level=1).count()
        no_prio      = cat_qs.filter(status='waiting', ticket__isnull=True).count()

        queue_stats.append({
            'category':     cat,
            'department':   cat.department,
            'waiting':      cat_qs.filter(status='waiting').count(),
            'serving':      cat_qs.filter(status='serving').count(),
            'completed':    cat_qs.filter(status='completed').count(),
            'no_show':      cat_qs.filter(status='no_show').count(),
            'total':        cat_qs.count(),
            'high_count':   high_count,
            'medium_count': medium_count,
            'low_count':    low_count,
            'no_prio':      no_prio,
        })

    # Sort stats: departments with highest-priority waiting first
    queue_stats.sort(key=lambda s: (-(s['high_count'] * 3 +
                                      s['medium_count'] * 2 +
                                      s['low_count'])))

    issue_form = QueueIssueForm(tenant=tenant)

    return render(request, 'tickets/staff/queue_dashboard.html', {
        'today':          today,
        'waiting':        waiting,
        'serving':        serving,
        'completed':      completed,
        'no_show':        no_show,
        'queue_stats':    queue_stats,
        'issue_form':     issue_form,
        'is_full_access': is_full_access,
        'user_department': user_department,
    })

















@login_required
@require_POST
def queue_call_next(request, category_id):
    """Call the next waiting entry in a category."""
    tenant   = request.user.tenant
    today    = timezone.localdate()
    category = get_object_or_404(TicketCategory, pk=category_id, tenant=tenant)

    next_entry = QueueEntry.objects.filter(
        tenant=tenant, category=category,
        status='waiting', issued_at__date=today,
    ).order_by('issued_at').first()

    if next_entry:
        next_entry.mark_called(staff_user=request.user)
        return JsonResponse({
            'ok':           True,
            'queue_number': next_entry.queue_number,
            'customer':     next_entry.customer_display,
            'entry_id':     next_entry.pk,
        })
    return JsonResponse({'ok': False, 'message': 'No one waiting in this queue.'})


@login_required
@require_POST
def queue_mark_served(request, entry_id):
    """Mark an entry as completed / served."""
    tenant = request.user.tenant
    entry  = get_object_or_404(QueueEntry, pk=entry_id, tenant=tenant)
    entry.mark_completed()
    return JsonResponse({'ok': True, 'queue_number': entry.queue_number})


@login_required
@require_POST
def queue_mark_no_show(request, entry_id):
    """Mark an entry as no-show."""
    tenant = request.user.tenant
    entry  = get_object_or_404(QueueEntry, pk=entry_id, tenant=tenant)
    entry.mark_no_show()
    return JsonResponse({'ok': True, 'queue_number': entry.queue_number})


# ─── AJAX: live queue status ───────────────────────────────────────────────────

@login_required
def queue_status_json(request):
    """Returns today's queue status as JSON for live dashboard refresh."""
    tenant  = request.user.tenant
    today   = timezone.localdate()
    entries = QueueEntry.objects.filter(
        tenant=tenant, issued_at__date=today
    ).select_related('category').values(
        'id', 'queue_number', 'category__name',
        'status', 'customer_name', 'issued_at'
    )
    return JsonResponse({'entries': list(entries)}, json_dumps_params={'default': str})





# documents/viewfuncs/ticket_views.py — replace queue_issue view

@login_required
def queue_issue(request):
    """
    Issue a new queue number.
    Supports three ticket modes:
      none     — queue token only, no ticket
      existing — attach to an existing verified ticket
      new      — create a fresh ticket and link it
    """
    tenant = request.user.tenant

    if request.method == 'POST':
        form = QueueIssueForm(request.POST, tenant=tenant)
        if form.is_valid():
            d        = form.cleaned_data
            category = d['category']
            mode     = d['ticket_mode']

            # Handle Other category — record the specified text
            other_text = d.get('other_category', '').strip()
            if category.slug == 'OTHER' and other_text:
                # Use Other category but annotate the notes field
                pass

            # ── Generate queue number ──────────────────────────────────────────
            queue_number = QueueEntry.generate_queue_number(tenant, category)

            # ── Resolve ticket ─────────────────────────────────────────────────
            ticket = None

            if mode == 'existing':
                # Already verified in form.clean() — just retrieve it
                ticket = d.get('_verified_ticket')

            elif mode == 'new':
                # Create a new ticket and link it
                desc = d.get('ticket_description', '') or ''
                if category.slug == 'OTHER' and other_text:
                    desc = f"[Category: {other_text}]\n" + desc

                ticket = Ticket.objects.create(
                    tenant=tenant,
                    category=category,
                    priority=d.get('ticket_priority'),
                    title=d['ticket_title'],
                    description=desc,
                    guest_name=d.get('customer_name') or 'Walk-in',
                    guest_phone=d.get('customer_phone') or '',
                    guest_email=d.get('customer_email') or '',
                    source='walkin',
                    status='new',
                )

            # ── Create queue entry ─────────────────────────────────────────────
            notes = f"[Other: {other_text}]" if (
                category.slug == 'OTHER' and other_text) else ''

            entry = QueueEntry.objects.create(
                tenant=tenant,
                queue_number=queue_number,
                category=category,
                customer_name=d.get('customer_name') or '',
                customer_phone=d.get('customer_phone') or '',
                customer_email=d.get('customer_email') or '',
                source=d.get('source', 'walkin'),
                ticket=ticket,
                notes=notes,
            )

            # ── Build success message ──────────────────────────────────────────
            msg = f"Queue number <strong>{queue_number}</strong> issued."
            if ticket and mode == 'new':
                msg += f" New ticket <strong>{ticket.ticket_number}</strong> created."
            elif ticket and mode == 'existing':
                msg += f" Attached to ticket <strong>{ticket.ticket_number}</strong>."
            messages.success(request, msg)

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'ok':            True,
                    'queue_number':  queue_number,
                    'ticket_number': ticket.ticket_number if ticket else None,
                    'entry_id':      entry.pk,
                })
            return redirect('queue_dashboard')
    else:
        form = QueueIssueForm(tenant=tenant)

    return render(request, 'tickets/staff/queue_issue.html', {'form': form})


# ── AJAX: verify existing ticket (called live before form submit) ──────────────

# @login_required
# def ajax_verify_ticket(request):
#     """
#     AJAX endpoint — verify a ticket number + email/phone before queue issuance.
#     Returns: {found, ticket_number, title, status, guest_name}
#     """
#     tenant     = request.user.tenant
#     ticket_num = request.GET.get('ticket_number', '').strip()
#     verify     = request.GET.get('verify', '').strip()

#     if not ticket_num or not verify:
#         return JsonResponse({'found': False, 'error': 'Missing fields.'})

#     try:
#         ticket = Ticket.objects.get(tenant=tenant,
#                                     ticket_number__iexact=ticket_num)
#     except Ticket.DoesNotExist:
#         return JsonResponse({'found': False, 'error': 'Ticket not found.'})

#     # Verify customer identity
#     match = (
#         (ticket.guest_email  and ticket.guest_email.lower()  == verify.lower()) or
#         (ticket.guest_phone  and ticket.guest_phone           == verify) or
#         (ticket.created_by   and ticket.created_by.email.lower() == verify.lower())
#     )
#     if not match:
#         return JsonResponse({'found': False,
#                              'error': 'Details do not match this ticket.'})

#     return JsonResponse({
#         'found':         True,
#         'ticket_number': ticket.ticket_number,
#         'title':         ticket.title,
#         'status':        ticket.get_status_display(),
#         'guest_name':    ticket.submitter_display,
#         'category':      ticket.category.slug if ticket.category else '—',
#     })






# documents/viewfuncs/ticket_views.py — replace ajax_verify_ticket with this

@login_required
def ajax_verify_ticket(request):
    """
    AJAX — verify a ticket by number + any of: email, phone, first name, last name.
    Returns: {found, ticket_number, title, status, guest_name, category}
    """
    tenant     = request.user.tenant
    ticket_num = request.GET.get('ticket_number', '').strip()
    verify     = request.GET.get('verify', '').strip().lower()

    if not ticket_num or not verify:
        return JsonResponse({'found': False, 'error': 'Missing fields.'})

    try:
        ticket = Ticket.objects.get(
            tenant=tenant,
            ticket_number__iexact=ticket_num,
        )
    except Ticket.DoesNotExist:
        return JsonResponse({'found': False, 'error': 'Ticket not found.'})

    # ── Verify identity against multiple fields ────────────────────────────────
    matched = any([
        ticket.guest_email  and ticket.guest_email.lower()  == verify,
        ticket.guest_phone  and ticket.guest_phone           == verify,
        ticket.guest_phone  and ticket.guest_phone.replace(' ', '') == verify.replace(' ', ''),
        # First name / last name match against guest_name
        ticket.guest_name   and verify in ticket.guest_name.lower().split(),
        # Registered user fields
        ticket.created_by   and ticket.created_by.email.lower()      == verify,
        ticket.created_by   and ticket.created_by.first_name.lower() == verify,
        ticket.created_by   and ticket.created_by.last_name.lower()  == verify,
    ])

    if not matched:
        return JsonResponse({
            'found': False,
            'error': 'Details do not match this ticket. '
                     'Try the email, phone, or first/last name used when submitting.',
        })

    return JsonResponse({
        'found':         True,
        'ticket_number': ticket.ticket_number,
        'title':         ticket.title,
        'status':        ticket.get_status_display(),
        'guest_name':    ticket.submitter_display,
        'category':      ticket.category.slug if ticket.category else '—',
    })