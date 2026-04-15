from django.contrib.auth.decorators import user_passes_test
from documents.models import Event, EventParticipant
from documents.forms import EventForm, EventParticipantForm
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator

@user_passes_test(is_admin)
def event_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    events = Event.objects.filter(tenant=request.tenant)
    paginator = Paginator(events, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/event_list.html", {"events": page_obj})

@user_passes_test(is_admin)
def create_event(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    if request.method == "POST":
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.tenant = request.tenant
            event.created_by = request.user
            event.save()
            return redirect("event_list")
    else:
        form = EventForm()
    return render(request, "admin/create_event.html", {"form": form})

@user_passes_test(is_admin)
def edit_event(request, event_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the event, ensuring it belongs to the same tenant
    event = get_object_or_404(Event, id=event_id, tenant=request.tenant)

    if request.method == "POST":
        form = EventForm(request.POST, instance=event, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("event_list")
    else:
        form = EventForm(instance=event, user=request.user)
    return render(request, "admin/edit_event.html", {"form": form})

@user_passes_test(is_admin)
def delete_event(request, event_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the event, ensuring it belongs to the same tenant
    event = get_object_or_404(Event, id=event_id, tenant=request.tenant)
    event.delete()
    return redirect("event_list")

@user_passes_test(is_admin)
def event_participant_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    participants = EventParticipant.objects.filter(tenant=request.tenant).order_by('event')
    paginator = Paginator(participants, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/event_participant_list.html", {"participants": page_obj})

@user_passes_test(is_admin)
def create_event_participant(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    if request.method == "POST":
        form = EventParticipantForm(request.POST, user=request.user)
        if form.is_valid():
            event_participant=form.save(commit=False)
            event_participant.tenant = request.tenant
            event_participant.save()
            return redirect("event_participant_list")
    else:
        form = EventParticipantForm(user=request.user)
    return render(request, "admin/create_event_participant.html", {"form": form})

@user_passes_test(is_admin)
def edit_event_participant(request, event_participant_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the event, ensuring it belongs to the same tenant
    event_participant = get_object_or_404(EventParticipant, id=event_participant_id, tenant=request.tenant)

    if request.method == "POST":
        form = EventParticipantForm(request.POST, instance=event_participant, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("event_participant_list")
    else:
        form = EventParticipantForm(instance=event_participant, user=request.user)
    return render(request, "admin/edit_event_participant.html", {"form": form})

@user_passes_test(is_admin)
def delete_event_participant(request, event_participant_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the event, ensuring it belongs to the same tenant
    event_participant = get_object_or_404(EventParticipant, id=event_participant_id, tenant=request.tenant)
    event_participant.delete()
    return redirect("event_participant_list")