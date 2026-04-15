
# Create your views here.
import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
     StaffPINSetupForm,StaffManualCheckInForm,
    VisitorCheckInForm, VisitorCheckOutForm, WorkScheduleForm,ManualCheckInForm,VisitorCheckoutForm
)
from .models import (
    BiometricCredential, StaffCheckIn, StaffPIN, StaffQRToken,
    Visitor, VisitorLog, VisitorTagCounter, WorkSchedule,
)
from documents.models import CustomUser

from django.db.models import Count
from django.contrib.auth import get_user_model

User = get_user_model()



# Role Based Access Control helpers

CHECKIN_ROLES = ('Admin', 'HR', 'Receptionist')


def can_process_checkin(user) -> bool:
    return (
        user.is_superuser or
        user.is_staff or
        user.roles.filter(name__in=CHECKIN_ROLES).exists()
    )


def checkin_required(view_func):
    """Decorator: login + Receptionist / HR / Admin / staff check."""
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not can_process_checkin(request.user):
            messages.error(request, "You don't have permission to access Check-in.")
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapped


def admin_only(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_superuser or
                request.user.roles.filter(name='Admin').exists()):
            messages.error(request, "Only admins can perform this action.")
            return redirect('checkin_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapped



# Shared helper

def _process_staff_checkin(request, staff: CustomUser, method: str):
    """
    Create today's StaffCheckIn record.
    Returns the record or None if already processed.
    """
    today = timezone.now().date()
    now   = timezone.now()

    record, created = StaffCheckIn.objects.get_or_create(
        tenant=request.user.tenant,
        staff=staff,
        date=today,
        defaults={
            'check_in_time': now,
            'method': method,
            'checked_in_by': request.user,
        },
    )

    if not created:
        messages.warning(request, f"{staff.get_full_name() or staff.username} already recorded today.")
        return None

    # Determine late status against work schedule
    try:
        schedule = WorkSchedule.objects.get(tenant=request.user.tenant)
        if now.time() > schedule.late_after:
            record.is_late = True
            record.status  = 'late'
        else:
            record.status = 'present'
    except WorkSchedule.DoesNotExist:
        record.status = 'present'

    record.save(update_fields=['is_late', 'status'])

    label = record.get_status_display()
    messages.success(request, f"{staff.get_full_name() or staff.username} checked in — {label}.")
    return record


# Main Dashboard


@checkin_required
def checkin_dashboard(request):
    today  = timezone.now().date()
    tenant = request.user.tenant

    staff_today = (
        StaffCheckIn.objects
        .filter(tenant=tenant, date=today)
        .select_related('staff', 'checked_in_by')
    )
    visitors_today = (
        VisitorLog.objects
        .filter(tenant=tenant, date=today)
        .select_related('visitor', 'visitee')
    )

    try:
        schedule = WorkSchedule.objects.get(tenant=tenant)
    except WorkSchedule.DoesNotExist:
        schedule = None

    manual_form = StaffManualCheckInForm(tenant=tenant)
    checkout_form = VisitorCheckOutForm()

    context = {
        'today':             today,
        'schedule':          schedule,
        'staff_today':       staff_today,
        'checked_in_count':  staff_today.filter(check_in_time__isnull=False).count(),
        'checked_out_count': staff_today.filter(check_out_time__isnull=False).count(),
        'late_count':        staff_today.filter(is_late=True).count(),
        'visitors_inside':   visitors_today.filter(time_out__isnull=True),
        'visitors_out':      visitors_today.filter(time_out__isnull=False),
        'visitors_count':    visitors_today.count(),
        'manual_form':       manual_form,
        'checkout_form':     checkout_form,
    }
    return render(request, 'checkin/dashboard.html', context)



# Work Schedule



@admin_only
def work_schedule_setup(request):
    tenant   = request.user.tenant
    instance = WorkSchedule.objects.filter(tenant=tenant).first()

    if request.method == 'POST':
        form = WorkScheduleForm(request.POST, instance=instance)
        if form.is_valid():
            ws = form.save(commit=False)
            ws.tenant     = tenant
            ws.created_by = request.user
            ws.save()
            messages.success(request, "Work schedule saved.")
            return redirect('checkin:checkin_dashboard')   # ← fixed
    else:
        form = WorkScheduleForm(instance=instance)

    return render(request, 'checkin/work_schedule.html', {'form': form, 'schedule': instance})


# Staff Check-in: QR Code






@checkin_required
@require_POST
def staff_checkin_qr(request):
    token = request.POST.get('token', '').strip()
    try:
        qr_obj = StaffQRToken.objects.select_related('user').get(token=token)
        staff  = qr_obj.user
        if staff.tenant != request.user.tenant:
            raise ValueError("Wrong tenant")
    except (StaffQRToken.DoesNotExist, ValueError):
        messages.error(request, "Invalid QR code.")
        return redirect('checkin:checkin_dashboard')   # ← fixed

    _process_staff_checkin(request, staff, 'qrcode')
    return redirect('checkin:checkin_dashboard')   # ← fixed


# Staff Check-in: PIN





@checkin_required
@require_POST
def staff_checkin_pin(request):
    username = request.POST.get('username', '').strip()
    raw_pin  = request.POST.get('pin', '').strip()

    try:
        staff = CustomUser.objects.get(username=username, tenant=request.user.tenant)
    except CustomUser.DoesNotExist:
        messages.error(request, "Staff member not found.")
        return redirect('checkin:checkin_dashboard')   # ← fixed

    try:
        if not staff.checkin_pin.verify_pin(raw_pin):
            messages.error(request, "Incorrect PIN.")
            return redirect('checkin:checkin_dashboard')   # ← fixed
    except StaffPIN.DoesNotExist:
        messages.error(request, f"No PIN set for {username}. Ask them to set one first.")
        return redirect('checkin:checkin_dashboard')   # ← fixed

    _process_staff_checkin(request, staff, 'pin')
    return redirect('checkin:checkin_dashboard')   # ← fixed




# Staff Check-in: Manual



@checkin_required
@require_POST
def staff_checkin_manual(request):
    form = StaffManualCheckInForm(request.POST, tenant=request.user.tenant)
    if form.is_valid():
        staff = form.cleaned_data['staff']
        record = _process_staff_checkin(request, staff, 'manual')
        if record and form.cleaned_data.get('notes'):
            record.notes = form.cleaned_data['notes']
            record.save(update_fields=['notes'])
    else:
        messages.error(request, "Please select a staff member.")
    return redirect('checkin:checkin_dashboard')   # ← fixed




# Staff Check-in: Biometric (WebAuthn stub)

@checkin_required
def biometric_checkin_begin(request):
    """
    Returns a WebAuthn PublicKeyCredentialRequestOptions JSON for the browser.
    Full implementation requires:  pip install py_webauthn
    """
    # TODO: generate challenge with webauthn.generate_authentication_options()
    # and store challenge in session for verification step.
    return JsonResponse({
        'status': 'stub',
        'message': 'WebAuthn challenge generation goes here (py_webauthn).',
    })


@checkin_required
@require_POST
def biometric_checkin_complete(request):
    """Verify WebAuthn assertion and record check-in."""
    # TODO: verify with webauthn.verify_authentication_response(),
    # look up BiometricCredential by credential_id, update sign_count,
    # then call _process_staff_checkin().
    return JsonResponse({'status': 'stub', 'message': 'WebAuthn verification goes here.'})



# Staff Check-out









@checkin_required
def staff_checkout(request, checkin_id):
    record = get_object_or_404(StaffCheckIn, id=checkin_id, tenant=request.user.tenant)
    if record.check_out_time:
        messages.warning(request, f"{record.staff.get_full_name() or record.staff.username} already checked out.")
    else:
        record.check_out_time = timezone.now()
        record.save(update_fields=['check_out_time'])
        messages.success(request, f"{record.staff.get_full_name() or record.staff.username} checked out.")
    return redirect('checkin:checkin_dashboard')   # ← fixed







# PIN Setup (self-service for each staff member)



@login_required
def set_staff_pin(request):
    if request.method == 'POST':
        form = StaffPINSetupForm(request.POST)
        if form.is_valid():
            pin_obj, _ = StaffPIN.objects.get_or_create(user=request.user)
            pin_obj.set_pin(form.cleaned_data['pin'])
            pin_obj.save()
            messages.success(request, "PIN set successfully.")
            return redirect('checkin:my_qr_code')   # ← fixed
    else:
        form = StaffPINSetupForm()
    has_pin = StaffPIN.objects.filter(user=request.user).exists()
    return render(request, 'checkin/set_pin.html', {'form': form, 'has_pin': has_pin})



# QR Code (self-service)

@login_required
def my_qr_code(request):
    qr_obj, _ = StaffQRToken.objects.get_or_create(user=request.user)
    return render(request, 'checkin/my_qr.html', {'qr_token': str(qr_obj.token)})


@login_required
@require_POST
def regenerate_qr(request):
    qr_obj, _ = StaffQRToken.objects.get_or_create(user=request.user)
    qr_obj.regenerate()
    messages.success(request, "QR code regenerated.")
    return redirect('checkin:my_qr_code')   # ← fixed




# Visitor Check-in


def visitor_checkin(request):
    """
    Visitor check-in view - accessible to both staff and public users
    - Staff users: Can check in visitors on their behalf
    - Public users: Can self-check-in as visitors
    """
    # For public users, use the tenant from the request (subdomain)
    if request.user.is_authenticated:
        tenant = request.user.tenant
        checked_in_by = request.user
        is_self_checkin = False
    else:
        # Public/guest user - use tenant from subdomain
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            messages.error(request, "Please access this page from an organization's subdomain.")
            return redirect('tenant_home')
        checked_in_by = None  # Will be set to None for self check-ins
        is_self_checkin = True

    if request.method == 'POST':
        form = VisitorCheckInForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            d     = form.cleaned_data
            phone = d['phone_number']

            # Upsert visitor profile (name + phone required; email optional)
            visitor, _ = Visitor.objects.update_or_create(
                tenant=tenant,
                phone_number=phone,
                defaults={
                    'name':  d['name'],
                    'email': d.get('email') or None,
                },
            )

            tag = VisitorTagCounter.get_next_tag(tenant)

            doc_file = request.FILES.get('document_scan')
            log = VisitorLog.objects.create(
                tenant=tenant,
                visitor=visitor,
                visitor_tag=tag,
                purpose=d.get('purpose') or None,
                purpose_detail=d.get('purpose_detail') or None,
                visitee=d.get('visitee'),
                on_appointment=d.get('on_appointment', False),
                id_type=d.get('id_type') or None,
                id_number=d.get('id_number') or None,
                has_document=bool(doc_file),
                document_scan=doc_file,
                checked_in_by=checked_in_by,  # None for self check-ins
                notes=d.get('notes') or None,
            )
            
            # For public users, show a success message and redirect to quick services
            if is_self_checkin:
                messages.success(request, f"Welcome! Your visitor tag is {tag}. Please show this to the receptionist.")
                return render(request, 'checkin/visitor_tag.html', {
                    'log': log,
                    'is_public_view': True
                })
            else:
                return redirect('checkin:visitor_tag_display', log_id=log.id)
    else:
        form = VisitorCheckInForm(tenant=tenant)

    return render(request, 'checkin/visitor_checkin.html', {
        'form': form,
        'is_self_checkin': is_self_checkin
    })


@checkin_required
def visitor_tag_display(request, log_id):
    log = get_object_or_404(VisitorLog, id=log_id, tenant=request.user.tenant)
    return render(request, 'checkin/visitor_tag.html', {'log': log})


# Visitor Check-out  (by tag number)
@checkin_required
@require_POST
def visitor_checkout(request):
    tag   = request.POST.get('visitor_tag', '').strip().zfill(4)
    today = timezone.now().date()
    try:
        log = VisitorLog.objects.get(
            tenant=request.user.tenant,
            visitor_tag=tag,
            date=today,
            time_out__isnull=True,
        )
        log.time_out       = timezone.now()
        log.checked_out_by = request.user
        log.save(update_fields=['time_out', 'checked_out_by'])
        messages.success(request, f"{log.visitor.name} (Tag {tag}) signed out.")
    except VisitorLog.DoesNotExist:
        messages.error(request, f"No active visitor with tag {tag} today.")
    return redirect('checkin:visitor_dashboard')   # ← fixed

# Visitor Dashboard

@checkin_required
def visitor_dashboard(request):
    tenant = request.user.tenant
    today  = timezone.now().date()

    # Optional date filter
    date_str = request.GET.get('date', '')
    try:
        from datetime import date as dt
        filter_date = dt.fromisoformat(date_str) if date_str else today
    except ValueError:
        filter_date = today

    logs = (
        VisitorLog.objects
        .filter(tenant=tenant, date=filter_date)
        .select_related('visitor', 'visitee', 'checked_in_by')
        .order_by('-time_in')
    )

    checkout_form = VisitorCheckOutForm()

    context = {
        'logs':          logs,
        'inside':        logs.filter(time_out__isnull=True),
        'exited':        logs.filter(time_out__isnull=False),
        'filter_date':   filter_date,
        'today':         today,
        'checkout_form': checkout_form,
    }
    return render(request, 'checkin/visitor_dashboard.html', context)


# AJAX helpers

@login_required
@require_GET
def visitor_lookup(request):
    """Pre-fill returning visitor details by phone number."""
    phone = request.GET.get('phone', '').strip()
    if not phone:
        return JsonResponse({'found': False})
    try:
        v = Visitor.objects.get(tenant=request.user.tenant, phone_number=phone)
        return JsonResponse({'found': True, 'name': v.name, 'email': v.email or ''})
    except Visitor.DoesNotExist:
        return JsonResponse({'found': False})


@login_required
@require_GET
def qr_lookup(request):
    """Return staff info for a scanned QR token (used by JS scanner)."""
    token = request.GET.get('token', '').strip()
    try:
        qr_obj = StaffQRToken.objects.select_related('user').get(token=token)
        u = qr_obj.user
        if u.tenant != request.user.tenant:
            raise ValueError
        return JsonResponse({
            'found':     True,
            'username':  u.username,
            'full_name': u.get_full_name() or u.username,
        })
    except (StaffQRToken.DoesNotExist, ValueError):
        return JsonResponse({'found': False})






# checkin_dashboard view with this 

# @checkin_required
# def checkin_dashboard(request):
#     tenant = request.user.tenant
#     today  = timezone.now().date()

#     # ── Staff counts ─
#     total_staff = CustomUser.objects.filter(
#         tenant=tenant, is_active=True
#     ).count()

#     # Today's check-in records
#     staff_today = StaffCheckIn.objects.filter(
#         tenant=tenant, date=today
#     ).select_related('staff').order_by('-check_in_time')

#     # Presently at work = checked in but not yet checked out
#     checked_in_count  = staff_today.filter(
#         check_in_time__isnull=False, check_out_time__isnull=True
#     ).count()

#     checked_out_count = staff_today.filter(
#         check_out_time__isnull=False
#     ).count()

#     late_count  = staff_today.filter(is_late=True).count()

#     # Early arrivals = checked in and NOT late
#     early_count = staff_today.filter(
#         check_in_time__isnull=False, is_late=False
#     ).count()

#     present_today = staff_today.filter(check_in_time__isnull=False).count()

#     absent_count = max(total_staff - present_today, 0)

#     # Attendance rate as a percentage of total staff
#     attendance_rate = round((present_today / total_staff * 100), 1) if total_staff else 0

#     # Percentage slices for the progress bar
#     early_pct = round((early_count / total_staff * 100), 1) if total_staff else 0
#     late_pct  = round((late_count  / total_staff * 100), 1) if total_staff else 0

#     # ── Rankings 
#     # Top 10 earliest arrivals (smallest check_in_time first)
#     top_early_arrivals = staff_today.filter(
#         check_in_time__isnull=False
#     ).order_by('check_in_time')[:10]

#     # Top 10 earliest leavers (smallest check_out_time first)
#     top_early_leavers = staff_today.filter(
#         check_out_time__isnull=False
#     ).order_by('check_out_time')[:10]

#     # ── Visitors ─
#     visitors_inside = VisitorLog.objects.filter(
#         tenant=tenant, date=today, time_out__isnull=True
#     ).select_related('visitor', 'visitee').order_by('-time_in')

#     recent_visitor_checkouts = VisitorLog.objects.filter(
#         tenant=tenant, date=today, time_out__isnull=False
#     ).select_related('visitor').order_by('-time_out')[:8]

#     visitors_count = VisitorLog.objects.filter(tenant=tenant, date=today).count()

#     # ── Schedule ────────
#     schedule = getattr(tenant, 'work_schedule', None)

#     # ── Forms ─
#     manual_form   = ManualCheckInForm(tenant=tenant)
#     checkout_form = VisitorCheckoutForm()

#     return render(request, 'checkin/checkin_dashboard.html', {
#         'today':                   today,
#         'schedule':                schedule,

#         # Metrics
#         'total_staff':             total_staff,
#         'checked_in_count':        checked_in_count,
#         'checked_out_count':       checked_out_count,
#         'late_count':              late_count,
#         'early_count':             early_count,
#         'present_today':           present_today,
#         'absent_count':            absent_count,
#         'attendance_rate':         attendance_rate,
#         'early_pct':               early_pct,
#         'late_pct':                late_pct,

#         # Rankings
#         'top_early_arrivals':      top_early_arrivals,
#         'top_early_leavers':       top_early_leavers,

#         # Tables
#         'staff_today':             staff_today,
#         'visitors_inside':         visitors_inside,
#         'recent_visitor_checkouts': recent_visitor_checkouts,
#         'visitors_count':          visitors_count,

#         # Forms
#         'manual_form':             manual_form,
#         'checkout_form':           checkout_form,
#     })









MANAGER_ROLES = {'HR', 'Admin', 'Receptionist'}

@checkin_required
def checkin_dashboard(request):
    user   = request.user
    tenant = user.tenant
    today  = timezone.now().date()

    # ── Determine access level 
    # is_staff / is_superuser always get full dashboard.
    # Users with HR, Admin or Receptionist role also get full dashboard.
    user_role_names = set(user.roles.values_list('name', flat=True))
    is_manager = user.is_staff or user.is_superuser or bool(user_role_names & MANAGER_ROLES)

    # ── Today's check-in record for the current user (all roles need this)
    my_checkin = StaffCheckIn.objects.filter(
        tenant=tenant, staff=user, date=today
    ).first()

    # ── Forms (manual form only for managers)
    manual_form   = ManualCheckInForm(tenant=tenant) if is_manager else None
    checkout_form = VisitorCheckoutForm()

    # ── Schedule 
    schedule = getattr(tenant, 'work_schedule', None)

    # ── Ordinary staff: return early with minimal context 
    if not is_manager:
        return render(request, 'checkin/checkin_dashboard.html', {
            'today':        today,
            'schedule':     schedule,
            'is_manager':   False,
            'my_checkin':   my_checkin,
            'manual_form':  None,
            'checkout_form': checkout_form,
        })

    # ── Manager-only context 
    total_staff = CustomUser.objects.filter(tenant=tenant, is_active=True).count()

    staff_today = StaffCheckIn.objects.filter(
        tenant=tenant, date=today
    ).select_related('staff').order_by('-check_in_time')

    checked_in_count  = staff_today.filter(check_in_time__isnull=False, check_out_time__isnull=True).count()
    checked_out_count = staff_today.filter(check_out_time__isnull=False).count()
    late_count        = staff_today.filter(is_late=True).count()
    early_count       = staff_today.filter(check_in_time__isnull=False, is_late=False).count()
    present_today     = staff_today.filter(check_in_time__isnull=False).count()
    absent_count      = max(total_staff - present_today, 0)

    attendance_rate = round(present_today / total_staff * 100, 1) if total_staff else 0
    early_pct       = round(early_count   / total_staff * 100, 1) if total_staff else 0
    late_pct        = round(late_count    / total_staff * 100, 1) if total_staff else 0

    top_early_arrivals = staff_today.filter(check_in_time__isnull=False).order_by('check_in_time')[:10]
    top_early_leavers  = staff_today.filter(check_out_time__isnull=False).order_by('check_out_time')[:10]

    visitors_inside = VisitorLog.objects.filter(
        tenant=tenant, date=today, time_out__isnull=True
    ).select_related('visitor', 'visitee').order_by('-time_in')

    recent_visitor_checkouts = VisitorLog.objects.filter(
        tenant=tenant, date=today, time_out__isnull=False
    ).select_related('visitor').order_by('-time_out')[:8]

    visitors_count = VisitorLog.objects.filter(tenant=tenant, date=today).count()

    return render(request, 'checkin/checkin_dashboard.html', {
        'today':                    today,
        'schedule':                 schedule,
        'is_manager':               True,
        'my_checkin':               my_checkin,

        # Metrics
        'total_staff':              total_staff,
        'checked_in_count':         checked_in_count,
        'checked_out_count':        checked_out_count,
        'late_count':               late_count,
        'early_count':              early_count,
        'present_today':            present_today,
        'absent_count':             absent_count,
        'attendance_rate':          attendance_rate,
        'early_pct':                early_pct,
        'late_pct':                 late_pct,

        # Rankings
        'top_early_arrivals':       top_early_arrivals,
        'top_early_leavers':        top_early_leavers,

        # Tables
        'staff_today':              staff_today,
        'visitors_inside':          visitors_inside,
        'recent_visitor_checkouts': recent_visitor_checkouts,
        'visitors_count':           visitors_count,

        # Forms
        'manual_form':              manual_form,
        'checkout_form':            checkout_form,
    })



# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC PIN REQUEST (No login required)
# ══════════════════════════════════════════════════════════════════════════════

def get_pin_public(request):
    """
    Public view for PIN assistance (no login required).
    Creates a support ticket for admin to help with PIN setup.
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from documents.models import Ticket, Notification, UserNotification, CustomUser
    from django.contrib.contenttypes.models import ContentType
    
    tenant = getattr(request, 'tenant', None)
    request_sent = False
    error_message = None
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        identifier = request.POST.get('identifier', '').strip()
        message = request.POST.get('message', '').strip()
        
        if not name or not identifier:
            error_message = "Please provide your name and email/phone number."
        else:
            try:
                # Create a support ticket for PIN assistance
                ticket_description = f"""
PIN Assistance Request:
----------------------
Name: {name}
Contact: {identifier}
Message: {message or 'No additional message'}

Requested At: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}

Action Required:
Please assist this person with PIN setup or retrieval.
- If they have an account, help them access Check-in > My PIN
- If they don't have an account, create one and set up their PIN
"""
                
                ticket = Ticket.objects.create(
                    tenant=tenant,
                    title=f"PIN Assistance - {name}",
                    description=ticket_description,
                    guest_name=name,
                    guest_email=identifier if '@' in identifier else '',
                    guest_phone=identifier if '@' not in identifier else '',
                    status='new',
                    source='online'
                )
                
                # Create notification for staff
                notification = Notification.objects.create(
                    tenant=tenant,
                    title=f"PIN Assistance Request from {name}",
                    message=f"{name} needs help with PIN setup/retrieval",
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
                
                # Send email notification to staff
                try:
                    admin_emails = staff_users.values_list('email', flat=True)
                    if admin_emails:
                        send_mail(
                            subject=f'PIN Assistance Request from {name}',
                            message=ticket_description,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=list(admin_emails),
                            fail_silently=True,
                        )
                except Exception as e:
                    print(f"Email notification failed: {e}")
                
                request_sent = True
                
            except Exception as e:
                print(f"Error creating PIN request: {e}")
                error_message = "An error occurred. Please try again or contact support directly."
    
    return render(request, 'checkin/get_pin_public.html', {
        'tenant': tenant,
        'request_sent': request_sent,
        'error_message': error_message,
    })
