from datetime import datetime, timedelta, date, time
from decimal import Decimal
from django.middleware.csrf import get_token
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db.models import Q, Exists, OuterRef
from documents.models import Event, BookingType, CustomUser, Booking, Payment, Payer, BookingTypeSchedule
from django.db import transaction
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_safe
from django.http import Http404, JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from raadaa import settings
from .helper_funcs.paystack import initialize_paystack_payment
from .send_mails import (
    send_booking_request_email,
    send_booking_received_email,
    send_booking_confirmed_email,
    send_booking_declined_email,
    send_external_event_invite_email,   # NEW – add this to send_mails.py
)
from tenants.models import Tenant
import pytz

def get_effective_timezone(booking_type=None, user=None, tenant=None):
    """
    Returns the IANA timezone string to use for a given context.
 
    Priority:
      1. First active schedule of the given booking_type  (most specific)
      2. First active schedule of any public BookingType owned by the user
      3. 'Africa/Lagos' fallback
    """
    if booking_type:
        schedule = booking_type.schedules.filter(is_active=True).first()
        if schedule:
            return schedule.timezone
 
    if user:
        from documents.models import BookingType as BT
        schedule = (
            BT.objects
            .filter(
                Q(created_by=user) | Q(host_user=user),
                *([Q(tenant=tenant)] if tenant else [Q(tenant__isnull=True)])
            )
            .values_list('schedules__timezone', flat=True)
            .filter(schedules__is_active=True)
            .first()
        )
        if schedule:
            return schedule
 
    return 'Africa/Lagos'
 
 
@login_required
def booking_dashboard(request):
    user      = request.effective_user
    is_personal = user.is_personal
    tenant    = request.effective_tenant
 
    if is_personal:
        booking_types = BookingType.objects.filter(created_by=user, tenant__isnull=True)
    else:
        booking_types = (
            BookingType.objects
            .filter(tenant=tenant)
            .filter(Q(created_by=user) | Q(managers=user))
            .distinct()
        )
 
    from documents.models import Booking
    bookings = Booking.objects.filter(
        Q(event__created_by=user) if is_personal else Q(event__tenant=tenant)
    ).order_by('-event__start_time')[:10]
 
    is_shareable = booking_types.filter(is_public=True).exists()
    from raadaa import settings
    base_url = "http://localhost:8000" if settings.DEBUG else "https://teammanager.ng"
    shareable_link = f"{base_url}/bookings/book/{user.id}/" if is_shareable else None
    org_shareable_link = (
        f"{base_url}/bookings/book/org/{tenant.slug}/"
        if (is_shareable and not is_personal) else None
    )
 
    from django.middleware.csrf import get_token
    from documents.models import CustomUser
    users = CustomUser.objects.filter(tenant=user.tenant) if user.tenant else CustomUser.objects.none()
 
    # Timezone: derive from the user's first booking service schedule
    first_bt = booking_types.prefetch_related('schedules').first()
    effective_timezone = get_effective_timezone(booking_type=first_bt, user=user, tenant=tenant)
 
    # Schedule count (replaces availability_rules_count)
    schedules_count = (
        BookingTypeSchedule.objects
        .filter(booking_type__in=booking_types, is_active=True)
        .count()
    )
 
    context = {
        'is_personal':           is_personal,
        'booking_types_count':   booking_types.count(),
        'schedules_count':       schedules_count,   # replaces availability_rules_count
        'recent_bookings':       bookings,
        'is_shareable':          is_shareable,
        'shareable_link':        shareable_link,
        'org_shareable_link':    org_shareable_link,
        'effective_timezone':    effective_timezone,
        'user':                  user,
        'tenant':                tenant,
        'csrf_token':            get_token(request),
        'notification_bar_items': [],
        'birthday_others':       [],
        'birthday_self':         False,
        'users':                 users,
    }
    return render(request, 'booking/booking_dashboard.html', context)
 
 
@login_required
def bookings_list(request):
    from documents.models import Booking
    user        = request.effective_user
    is_personal = user.is_personal
    tenant      = request.effective_tenant
 
    bookings = (
        Booking.objects
        .filter(booking_type__managers=user)
        .select_related('event', 'booking_type', 'event__booking_type', 'user')
        .prefetch_related('event__external_participants')
        .order_by('-event__start_time')
    )
 
    status_filter  = request.GET.get('status', '').strip()
    payment_filter = request.GET.get('payment_status', '').strip()
    search_query   = request.GET.get('q', '').strip()
    date_from      = request.GET.get('date_from', '').strip()
    date_to        = request.GET.get('date_to', '').strip()
 
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    if payment_filter:
        bookings = bookings.filter(payment_status=payment_filter)
    if search_query:
        bookings = bookings.filter(
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )
    if date_from:
        try:
            bookings = bookings.filter(
                event__start_time__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date()
            )
        except ValueError:
            pass
    if date_to:
        try:
            bookings = bookings.filter(
                event__start_time__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date()
            )
        except ValueError:
            pass
 
    # Timezone: derive from user's booking services, no AvailabilityRule needed
    effective_tz       = get_effective_timezone(user=user, tenant=tenant)
    effective_tz_abbrev = datetime.now(pytz.timezone(effective_tz)).strftime('%Z')
 
    active_filters = {
        'status':         status_filter,
        'payment_status': payment_filter,
        'q':              search_query,
        'date_from':      date_from,
        'date_to':        date_to,
    }
 
    context = {
        'effective_timezone':  effective_tz,
        'effective_tz_abbrev': effective_tz_abbrev,
        'bookings':            bookings,
        'is_personal':         is_personal,
        'active_filters':      active_filters,
        'has_active_filters':  any(active_filters.values()),
        'total_count':         bookings.count(),
    }
    return render(request, 'booking/bookings_list.html', context)


@login_required
def booking_action(request, uuid, action):
    booking = get_object_or_404(Booking, uuid=uuid)
    user = request.user

    if user not in booking.booking_type.managers.all():
        messages.error(request, "You do not have permission to perform this action.")
        return redirect('bookings_list')

    if action == 'accept':
        booking.status = 'confirmed'
        booking.event.status = 'confirmed'
        send_booking_confirmed_email(booking)
    elif action == 'decline':
        booking.status = 'cancelled'
        booking.event.status = 'cancelled'
        send_booking_declined_email(booking)
    else:
        messages.error(request, "Invalid action.")
        return redirect('bookings_list')

    booking.save()
    booking.event.save()
    messages.success(request, f"Booking {action}ed successfully.")
    return redirect('bookings_list')


def get_available_slots(
    owner,
    start_date: date,
    end_date: date,
    timezone: str,
    booking_type: 'BookingType' = None,
    duration_minutes: int = None,
) -> list:
    """
    Returns a list of slot dicts for the given BookingType over the date range.
    Now reads schedules directly from booking_type.schedules instead of AvailabilityRule.
    """
    from documents.models import Event, Booking
 
    if not booking_type:
        return []
 
    tz  = pytz.timezone(timezone or 'Africa/Lagos')
    now = dj_timezone.now()
 
    # Respect active window
    today = now.date()
    if booking_type.start_date and booking_type.start_date > end_date:
        return []
    if booking_type.end_date and booking_type.end_date < start_date:
        return []
 
    effective_start = max(start_date, booking_type.start_date or start_date, today)
    effective_end   = min(end_date,   booking_type.end_date   or end_date)
 
    if effective_start > effective_end:
        return []
 
    slot_minutes = duration_minutes or booking_type.duration_minutes
    slot_delta   = timedelta(minutes=slot_minutes)
 
    # ── Fetch active schedules ──────────────────────────────────────────────
    schedules_qs = booking_type.schedules.filter(is_active=True)
    if not schedules_qs.exists():
        return []
 
    # Group by weekday so we only do one dict lookup per day
    schedules_by_weekday: dict[int, list] = {}
    for sched in schedules_qs:
        schedules_by_weekday.setdefault(sched.weekday, []).append(sched)
 
    slots        = []
    current_date = effective_start
 
    while current_date <= effective_end:
        weekday    = current_date.weekday()
        day_scheds = schedules_by_weekday.get(weekday, [])
        if not day_scheds:
            current_date += timedelta(days=1)
            continue
 
        # Daily cap check
        if booking_type.max_bookings_per_day:
            daily_count = Event.objects.filter(
                booking_type=booking_type,
                start_time__date=current_date,
                tenant=booking_type.tenant,
            ).count()
            if daily_count >= booking_type.max_bookings_per_day:
                current_date += timedelta(days=1)
                continue
 
        for sched in day_scheds:
            sched_tz     = pytz.timezone(sched.timezone or 'Africa/Lagos')
            window_start = sched_tz.localize(datetime.combine(current_date, sched.start_time))
            window_end   = sched_tz.localize(datetime.combine(current_date, sched.end_time))
 
            # Apply buffers to shrink the bookable window
            bookable_start = window_start + timedelta(minutes=sched.buffer_before_minutes)
            bookable_end   = window_end   - timedelta(minutes=sched.buffer_after_minutes)
 
            if bookable_start >= bookable_end:
                continue
 
            candidate = bookable_start
            while candidate + slot_delta <= bookable_end:
                slot_start = candidate
                slot_end   = candidate + slot_delta
 
                # Skip past slots
                if slot_end <= now:
                    candidate += slot_delta
                    continue
 
                # Booking deadline
                if booking_type.booking_deadline_hours:
                    deadline = now + timedelta(hours=booking_type.booking_deadline_hours)
                    if slot_start < deadline:
                        candidate += slot_delta
                        continue
 
                available, booked, cap = is_slot_available(
                    slot_start, slot_end, booking_type, owner=None
                )
 
                slots.append({
                    "start":             slot_start.isoformat(),
                    "end":               slot_end.isoformat(),
                    "available":         available,
                    "current_bookings":  booked,
                    "capacity":          cap,
                    "booking_type_uuid": str(booking_type.uuid),
                    "booking_type_name": booking_type.name,
                    "price":             float(booking_type.price) if booking_type.price else 0,
                    "duration_minutes":  booking_type.duration_minutes,
                    "color":             booking_type.color or '#28a745',
                    "is_hybrid":         booking_type.is_hybrid,
                    "location":          booking_type.location or '',
                    "virtual_link":      bool(booking_type.virtual_link),
                })
 
                candidate += slot_delta
 
        current_date += timedelta(days=1)
 
    return slots
 
 
def is_slot_available(start_dt, end_dt, booking_type, owner=None):
    """Unchanged logic — checks for conflicts and capacity."""
    from documents.models import Event, Booking
 
    if not booking_type:
        return False, 0, 1
 
    base_filter = {'tenant': booking_type.tenant}
 
    blocked = Event.objects.filter(
        is_booking=False,
        start_time__lt=end_dt,
        end_time__gt=start_dt,
        **base_filter,
    ).exists()
 
    if blocked:
        return False, 0, booking_type.effective_max_capacity
 
    overlapping = Event.objects.filter(
        is_booking=True,
        booking_type=booking_type,
        start_time__lt=end_dt,
        end_time__gt=start_dt,
        **base_filter,
    )
 
    active_count = Booking.objects.filter(
        event__in=overlapping,
        status__in=['pending', 'confirmed'],
    ).count()
 
    max_cap = booking_type.effective_max_capacity
 
    return (
        max_cap is None or active_count < max_cap,
        active_count,
        max_cap,
    )


@require_safe
def public_booking_page(request, booking_type_uuid):
    booking_type = get_object_or_404(
        BookingType,
        uuid=booking_type_uuid,
        is_public=True
    )

    owner = booking_type.host_user
    user_tz = request.GET.get('tz', 'Africa/Lagos')

    today = dj_timezone.now().date()
    start_date = today
    end_date = today + timedelta(days=28)

    available_slots = get_available_slots(
        owner=owner,
        start_date=start_date,
        end_date=end_date,
        timezone=user_tz,
        booking_type=booking_type,
    )

    context = {
        'booking_type': booking_type,
        'owner': owner,
        'available_slots_json': available_slots,
        'user_timezone': user_tz,
        'page_title': f"Book {booking_type.name}",
        'is_organization': bool(booking_type.tenant),
        'today': today,
    }

    return render(request, 'booking/public_booking.html', context)


class ToggleBookingTypePublicAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, uuid):
        bt = get_object_or_404(BookingType, uuid=uuid)

        if bt.tenant:
            if request.effective_tenant != bt.tenant:
                return Response({"detail": "Not authorized"}, status=403)
        else:
            if bt.created_by != request.user:
                return Response({"detail": "Not authorized"}, status=403)

        is_public = request.data.get('is_public', False)
        bt.is_public = bool(is_public)
        bt.shareable_link = bt.get_shareable_link()
        bt.save(update_fields=['is_public', 'shareable_link'])

        return Response({
            "success": True,
            "is_public": bt.is_public,
            "public_url": bt.public_url if bt.is_public else None
        })


@require_safe
def unified_calendar_public_view(request, user_id):
    owner = get_object_or_404(CustomUser, id=user_id)
    tenant = request.effective_tenant
    user = request.effective_user

    public_types = BookingType.objects.filter(
        Q(tenant__isnull=True) | Q(tenant=owner.tenant),
        created_by=owner,
        is_public=True,
    )

    if not public_types.exists():
        raise Http404("No public booking services available")

    user_tz_str = request.GET.get('tz')
    if not user_tz_str:
        # Derive timezone from first schedule of any public type
        first_sched_tz = (
            public_types
            .values_list('schedules__timezone', flat=True)
            .filter(schedules__is_active=True)
            .first()
        )
        user_tz_str = first_sched_tz or 'Africa/Lagos'

    today = dj_timezone.now().date()
    start_date = today
    end_date = today + timedelta(days=35)

    all_slots = []
    booking_types_data = []

    for bt in public_types:
        slots = get_available_slots(
            owner=owner,
            start_date=start_date,
            end_date=end_date,
            timezone=user_tz_str,
            booking_type=bt,
            duration_minutes=bt.duration_minutes,
        )

        for slot in slots:
            slot['booking_type_uuid'] = str(bt.uuid)
            slot['booking_type_name'] = bt.name
            slot['price'] = float(bt.price) if bt.price else 0
            slot['currency'] = bt.currency or "NGN"
            slot['duration_minutes'] = bt.duration_minutes
            slot['color'] = bt.color or '#28a745'

        all_slots.extend(slots)

        booking_types_data.append({
            'uuid': str(bt.uuid),
            'name': bt.name,
            'price': float(bt.price) if bt.price else 0,
            'currency': bt.currency or "NGN",
            'duration': bt.duration_minutes,
            'description': bt.description or "",
            'is_multiple': bt.is_multiple,
            'is_hybrid': bt.is_hybrid,
            'location': bt.location or '',
            'has_virtual': bool(bt.virtual_link),
            'color': bt.color or '#28a745',
            # Expose active window so JS can grey-out out-of-range months
            'start_date': bt.start_date.isoformat() if bt.start_date else None,
            'end_date': bt.end_date.isoformat() if bt.end_date else None,
        })

    context = {
        'owner': owner,
        'owner_name': owner.get_full_name() or owner.username,
        'available_slots_json': all_slots,
        'booking_types_json': booking_types_data,
        'user_timezone': user_tz_str,
        'today': today,
        'page_title': f"Book time with {owner.get_full_name() or owner.username}",
        'is_organization': False,
    }

    return render(request, 'booking/unified_calendar_public.html', context)


def unified_organization_public_view(request, tenant_slug):
    from documents.models import BookingType as BT
 
    tenant = get_object_or_404(Tenant, slug=tenant_slug)
 
    public_types = (
        BT.objects
        .filter(tenant=tenant, booking_for='organization', is_public=True)
        .select_related('tenant')
        .prefetch_related('schedules')
    )
 
    if not public_types.exists():
        # Show a general booking request form instead
        if request.method == 'POST':
            # Handle booking request submission
            from django.core.mail import send_mail
            from django.conf import settings
            from django.contrib.contenttypes.models import ContentType
            from documents.models import Ticket, Notification, UserNotification
            
            try:
                # Get form data
                full_name = request.POST.get('full_name')
                email = request.POST.get('email')
                phone = request.POST.get('phone')
                company = request.POST.get('company', '')
                preferred_date = request.POST.get('preferred_date')
                preferred_time = request.POST.get('preferred_time')
                meeting_type = request.POST.get('meeting_type')
                purpose = request.POST.get('purpose')
                duration = request.POST.get('duration', '60')
                format_type = request.POST.get('format')
                
                # Create a support ticket for the booking request
                ticket_description = f"""
Booking Request Details:
------------------------
Name: {full_name}
Email: {email}
Phone: {phone}
Company: {company or 'N/A'}

Preferred Date: {preferred_date}
Preferred Time: {preferred_time}
Duration: {duration} minutes
Meeting Type: {meeting_type}
Format: {format_type}

Purpose:
{purpose}
"""
                
                ticket = Ticket.objects.create(
                    tenant=tenant,
                    title=f"Booking Request - {full_name}",
                    description=ticket_description,
                    guest_name=full_name,
                    guest_email=email,
                    guest_phone=phone,
                    status='new',
                    source='online'
                )
                
                # Create notification for staff members
                from documents.models import CustomUser
                notification = Notification.objects.create(
                    tenant=tenant,
                    title=f"New Booking Request from {full_name}",
                    message=f"{full_name} requested an appointment for {preferred_date} at {preferred_time}",
                    type=Notification.NotificationType.ALERT,
                    content_type=ContentType.objects.get_for_model(Ticket),
                    object_id=ticket.id,
                    link=f'/support/tickets/{ticket.ticket_number}/'
                )
                
                # Notify all staff members
                staff_users = CustomUser.objects.filter(
                    tenant=tenant,
                    is_staff=True, 
                    is_active=True
                )
                for staff_user in staff_users:
                    UserNotification.objects.create(
                        tenant=tenant,
                        user=staff_user,
                        notification=notification
                    )
                
                # Send email notification to tenant admins
                try:
                    admin_emails = staff_users.values_list('email', flat=True)
                    if admin_emails:
                        send_mail(
                            subject=f'New Booking Request from {full_name}',
                            message=ticket_description,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=list(admin_emails),
                            fail_silently=True,
                        )
                except Exception as e:
                    print(f"Email notification failed: {e}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'ticket_id': ticket.id})
                else:
                    messages.success(request, 'Your booking request has been submitted successfully!')
                    return redirect('quick_services')
                    
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': str(e)})
                else:
                    messages.error(request, 'An error occurred. Please try again.')
        
        return render(request, 'booking/public_booking_request.html', {
            'tenant': tenant,
        })
 
    user_tz_str = request.GET.get('tz')
    if not user_tz_str:
        # Derive timezone from first schedule of any public type
        first_sched_tz = (
            public_types
            .values_list('schedules__timezone', flat=True)
            .filter(schedules__is_active=True)
            .first()
        )
        user_tz_str = first_sched_tz or 'Africa/Lagos'
 
    today      = dj_timezone.now().date()
    start_date = today
    end_date   = today + timedelta(days=35)
 
    all_slots          = []
    booking_types_data = []
 
    for bt in public_types:
        slots = get_available_slots(
            owner=None,
            start_date=start_date,
            end_date=end_date,
            timezone=user_tz_str,
            booking_type=bt,
            duration_minutes=bt.duration_minutes,
        )
        for slot in slots:
            slot.update({
                'booking_type_uuid': str(bt.uuid),
                'booking_type_name': bt.name,
                'price':             float(bt.price) if bt.price else 0,
                'currency':          bt.currency or 'NGN',
                'duration_minutes':  bt.duration_minutes,
                'color':             bt.color or '#319795',
            })
        all_slots.extend(slots)
 
        booking_types_data.append({
            'uuid':             str(bt.uuid),
            'name':             bt.name,
            'price':            float(bt.price) if bt.price else 0,
            'currency':         bt.currency or 'NGN',
            'duration':         bt.duration_minutes,
            'description':      bt.description or '',
            'is_hybrid':        bt.is_hybrid,
            'location':         bt.location or '',
            'has_virtual':      bool(bt.virtual_link),
            'color':            bt.color or '#319795',
            'start_date':       bt.start_date.isoformat() if bt.start_date else None,
            'end_date':         bt.end_date.isoformat() if bt.end_date else None,
        })
 
    context = {
        'is_organization':      True,
        'tenant':               tenant,
        'organization_name':    tenant.name or tenant.slug,
        'available_slots_json': all_slots,
        'booking_types_json':   booking_types_data,
        'user_timezone':        user_tz_str,
        'today':                today,
        'page_title':           f"Book time with {tenant.name or tenant.slug}",
    }
    return render(request, 'booking/unified_calendar_public.html', context)
 


def calculate_platform_fee(amount: Decimal) -> tuple[Decimal, Decimal]:
    if amount <= 0:
        return Decimal('0.00'), Decimal('0.00')

    percent_fee = amount * Decimal('0.10')
    fixed_fee = Decimal('100.00')
    total_fee = percent_fee + fixed_fee

    return total_fee.quantize(Decimal('0.01'))


class PublicBookingCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):
        data = request.data

        required = ['start', 'booking_type_uuid', 'first_name', 'email']
        for f in required:
            if not data.get(f):
                return Response({"error": f"{f} is required"}, status=400)

        start_iso = data['start']
        bt_uuid = data['booking_type_uuid']
        first_name = data['first_name'].strip()
        last_name = data.get('last_name', '').strip()
        email = data['email'].strip()
        phone = data.get('phone', '').strip()
        attendance_mode = data.get('attendance_mode', '')
        if attendance_mode:
            attendance_mode = attendance_mode.strip()
        else:
            attendance_mode = None
        notes = data.get('notes', '').strip()
        full_name = f"{first_name} {last_name}"

        try:
            start_dt = dj_timezone.datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
        except Exception:
            return Response({"error": "Invalid start time"}, status=400)

        booking_type = get_object_or_404(BookingType, uuid=bt_uuid, is_public=True)

        owner = booking_type.host_user
        tenant = booking_type.tenant if booking_type.tenant else None

        duration = booking_type.duration_minutes
        end_dt = start_dt + timedelta(minutes=duration)

        is_avail, curr_count, max_cap = is_slot_available(
            start_dt, end_dt, booking_type=booking_type, owner=owner
        )

        if not is_avail:
            return Response(
                {"error": "This time is no longer available. Please choose another slot."},
                status=409
            )

        event_title = f"Booking: {booking_type.name} - {first_name} {last_name}".strip()
        event, created = Event.objects.get_or_create(
            start_time=start_dt,
            end_time=end_dt,
            booking_type=booking_type,
            created_by=owner,
            tenant=tenant,
            defaults={
                'title': event_title,
                'description': notes,
                'is_booking': True,
                'status': 'pending',
                'payment_status': 'not_required' if booking_type.price <= 0 else 'pending',
                'attendee_name': f"{first_name} {last_name}".strip(),
                'attendee_email': email,
                'attendee_phone': phone,
            }
        )

        booking = Booking.objects.create(
            event=event,
            booking_type=booking_type,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            attendance_mode=attendance_mode or 'online',
            status='pending',
            payment_status=event.payment_status,
        )

        if booking_type.price <= 0:
            send_booking_request_email(booking)
            send_booking_received_email(booking)
            return Response({
                "success": True,
                "message": "Booking request sent! Awaiting confirmation.",
                "booking_uuid": str(booking.uuid),
                "status": "pending",
                "redirect": reverse('booking_success', kwargs={'uuid': str(booking.uuid)})
            }, status=201)

        # ── Paid path ──────────────────────────────────────────────────────────────
        booking_fee = Decimal(str(booking_type.price))
        platform_fee = calculate_platform_fee(booking_fee)
        gross_amount = platform_fee + booking_fee

        payer, _ = Payer.objects.get_or_create(
            tenant=tenant,
            email=email,
            defaults={"name": full_name, "phone": phone}
        )
        payer.name = full_name
        payer.phone = phone
        payer.save()

        payment = Payment.objects.create(
            tenant=tenant,
            amount=gross_amount,
            net_amount=booking_fee,
            payment_type='booking_fee',
            direction='incoming',
            status='pending',
            content_type=ContentType.objects.get_for_model(Booking),
            object_id=booking.id,
            payer=payer,
            created_by=owner,
            content_object=booking,
            return_url=reverse('booking_success', kwargs={'uuid': str(booking.uuid)}),
        )

        metadata = {
            "source": "booking",
            "source_id": str(booking.id),
            "source_url": request.build_absolute_uri(reverse('booking_success', kwargs={'uuid': str(booking.uuid)})),
            "participant_id": str(booking.id),
            "participant_name": f"{first_name} {last_name}",
            "participant_email": booking.email,
            'booking_uuid': str(booking.uuid),
            'booking_type_uuid': str(booking_type.uuid),
            'tenant_slug': tenant.slug if tenant else None,
            "base_price": str(booking_type.price),
            "payable_amount": str(gross_amount),
        }

        auth_url, reference = initialize_paystack_payment(
            email=email,
            amount_ngn=float(gross_amount),
            metadata=metadata
        )

        if not auth_url:
            booking.delete()
            event.delete()
            return Response({"error": "Could not initialize payment"}, status=500)

        payment.transaction_id = reference
        payment.save()

        return Response({
            "success": True,
            "status": "redirect_to_payment",
            "payment_url": auth_url,
            "booking_uuid": str(booking.uuid),
            "redirect": auth_url,
        }, status=200)


def booking_success(request, uuid):
    booking = get_object_or_404(Booking, uuid=uuid)

    if booking.payment_status == 'not_required':
        context = {
            'title': 'Request Received',
            'message': 'Your booking request has been sent.',
            'submessage': 'The host will confirm soon.',
            'class': 'text-primary',
            'icon': 'fas fa-paper-plane'
        }
    elif booking.payment_status == 'paid':
        context = {
            'title': 'Booking Confirmed!',
            'message': 'Your payment was successful.',
            'submessage': 'See you at the appointment!',
            'class': 'text-success',
            'icon': 'fas fa-check-circle'
        }
    else:
        context = {
            'title': 'Payment in Progress',
            'message': 'We are confirming your booking...',
            'submessage': 'Refresh in a moment if needed.',
            'class': 'text-info',
            'icon': 'fas fa-spinner fa-spin'
        }

    return render(request, 'booking/booking_success.html', context)