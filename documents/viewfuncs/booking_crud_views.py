# documents/viewfunc/booking_crud_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from uuid import UUID
from datetime import timedelta, datetime, date, time
import pytz

from documents.models import BookingType, Event
from documents.forms import BookingTypeForm, BookingTypeScheduleFormSet
from .helper_funcs.permissions import user_can_manage_booking_type


@login_required
def booking_type_list(request):
    user = request.user
 
    if hasattr(user, 'tenant') and user.tenant:
        booking_types = (
            BookingType.objects
            .filter(tenant=user.tenant)
            .filter(Q(created_by=user) | Q(managers=user))
            .distinct()
            .select_related('tenant')
            .order_by('name')
        )
        is_personal = False
        tenant = user.tenant
    else:
        booking_types = (
            BookingType.objects
            .filter(created_by=user, tenant__isnull=True)
            .order_by('name')
        )
        is_personal = True
        tenant = None
 
    # Ensure shareable links are populated for public types
    for bt in booking_types:
        if bt.is_public:
            bt.shareable_link = bt.get_shareable_link()
            bt.save(update_fields=['shareable_link'])
 
    context = {
        'booking_types': booking_types,
        'is_personal': is_personal,
        'tenant': tenant,
        'user': user,
    }
    return render(request, 'booking/booking_type_list.html', context)
 
 
@login_required
def booking_type_create(request):
    user = request.user
    is_personal = user.is_personal
 
    if request.method == 'POST':
        form         = BookingTypeForm(request.POST, user=user)
        schedule_fs  = BookingTypeScheduleFormSet(request.POST)
 
        if form.is_valid() and schedule_fs.is_valid():
            # ── Save parent ────────────────────────────────────────────────
            booking_type = form.save(commit=False)
 
            if user.is_personal:
                booking_type.booking_for = 'personal'
                booking_type.created_by  = user
                booking_type.tenant      = None
                booking_type.host_user   = user
            else:
                booking_type.created_by = user
                booking_type.tenant     = user.tenant
                if booking_type.booking_for == 'personal':
                    pass  # host_user already set by form.clean()
 
            booking_type.save()
            form.save_m2m()
 
            # ── Save schedule rows ─────────────────────────────────────────
            schedule_fs.instance = booking_type
            schedule_fs.save()
 
            messages.success(request, f"Booking service '{booking_type.name}' created successfully!")
            return redirect('booking_type_list')
        # Fall through to re-render with errors
    else:
        form        = BookingTypeForm(user=user)
        form.fields['booking_for'].initial = 'organization' if not is_personal else 'personal'
        schedule_fs = BookingTypeScheduleFormSet()
 
    context = {
        'form':        form,
        'schedule_fs': schedule_fs,
        'is_personal': is_personal,
        'action':      'Create',
    }
    return render(request, 'booking/booking_type_form.html', context)
 
 
@login_required
def booking_type_update(request, uuid):
    user         = request.user
    booking_type = get_object_or_404(BookingType, uuid=uuid)
 
    # ── Permission check ───────────────────────────────────────────────────
    if booking_type.tenant:
        if not (hasattr(user, 'tenant') and user.tenant == booking_type.tenant):
            messages.error(request, "You do not have permission to edit this booking service.")
            return redirect('booking_type_list')
        if not user_can_manage_booking_type(user, booking_type):
            messages.error(request, "You do not have permission to edit this booking service.")
            return redirect('booking_type_list')
    else:
        if booking_type.created_by != user:
            messages.error(request, "You do not have permission to edit this booking service.")
            return redirect('booking_type_list')
 
    if request.method == 'POST':
        form        = BookingTypeForm(request.POST, instance=booking_type, user=user)
        schedule_fs = BookingTypeScheduleFormSet(request.POST, instance=booking_type)
 
        if form.is_valid() and schedule_fs.is_valid():
            form.save()
            schedule_fs.save()
            messages.success(request, f"Booking service '{booking_type.name}' updated successfully!")
            return redirect('booking_type_list')
    else:
        form        = BookingTypeForm(instance=booking_type, user=user)
        schedule_fs = BookingTypeScheduleFormSet(instance=booking_type)
 
    context = {
        'form':         form,
        'schedule_fs':  schedule_fs,
        'booking_type': booking_type,
        'is_personal':  booking_type.is_personal(),
        'action':       'Update',
    }
    return render(request, 'booking/booking_type_form.html', context)
 
 
@login_required
def booking_type_delete(request, uuid):
    user         = request.user
    booking_type = get_object_or_404(BookingType, uuid=uuid)
 
    if booking_type.tenant:
        if not (hasattr(user, 'tenant') and user.tenant == booking_type.tenant):
            messages.error(request, "You do not have permission to delete this booking service.")
            return redirect('booking_type_list')
        if not user_can_manage_booking_type(user, booking_type):
            messages.error(request, "You do not have permission to delete this booking service.")
            return redirect('booking_type_list')
    else:
        if booking_type.created_by != user:
            messages.error(request, "You do not have permission to delete this booking service.")
            return redirect('booking_type_list')
 
    name = booking_type.name
    booking_type.delete()
    messages.success(request, f"Booking service '{name}' deleted successfully!")
    return redirect('booking_type_list')