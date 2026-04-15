from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from documents.models import GuestUser, ConferenceParticipant, VacancyApplication, Interview, Conference, Vacancy, Feedback
from raadaa import settings

def guest_dashboard(request):
    
    guest_user = None
    token_from_url = request.GET.get('token')

    # 1. Try to authenticate via URL token (magic link)
    if token_from_url:
        try:
            guest_user = GuestUser.objects.get(token=token_from_url)
            # Reinforce the cookie for future visits
            response = None  # we'll set cookie later if rendering
        except GuestUser.DoesNotExist:
            messages.error(request, "Invalid access token.")
            return redirect('home')  # or wherever your homepage is
    else:
        # 2. Try to authenticate via cookie
        token_from_cookie = request.COOKIES.get('guest_token')
        if token_from_cookie:
            try:
                guest_user = GuestUser.objects.get(token=token_from_cookie)
            except GuestUser.DoesNotExist:
                pass  # invalid cookie, ignore

    # If still no guest_user, they are not recognized
    if not guest_user:
        messages.info(request, "Please register for a conference or apply for a job to access your dashboard.")
        return redirect('home')  # or a public landing page

    # Update last access
    guest_user.update_access()

    email = guest_user.email.lower()

    now = timezone.now()

    # ==================== CONFERENCES ====================
    conference_regs = ConferenceParticipant.objects.filter(
        email__iexact=email
    ).select_related('conference').order_by('-registered_at')

    pending_conferences = conference_regs.filter(is_confirmed=False)

    approved_conferences = conference_regs.filter(is_confirmed=True)
    upcoming_conferences = approved_conferences.filter(
        conference__end_date__gte=now
    ).order_by('conference__start_date')

    past_conferences_qs = approved_conferences.filter(
        Q(conference__end_date__lt=now) | Q(check_in_status=True)
    ).order_by('-conference__start_date')
    # Convert to list so we can attach attributes
    past_conferences = list(past_conferences_qs.select_related('conference'))

    if past_conferences:
        conference_ids = [reg.conference.id for reg in past_conferences]
        ct = ContentType.objects.get_for_model(Conference)
        existing_feedback_ids = set(
            Feedback.objects.filter(
                guest_user=guest_user,
                content_type=ct,
                object_id__in=conference_ids
            ).values_list('object_id', flat=True)
        )

        for reg in past_conferences:
            reg.has_feedback = reg.conference.id in existing_feedback_ids

    # ==================== JOB APPLICATIONS ====================
    applications = VacancyApplication.objects.filter(
        email__iexact=email
    ).select_related('vacancy').order_by('-created_at')

    # ==================== INTERVIEWS ====================
    # Interviews linked to any of the guest's applications
    interviews = Interview.objects.filter(
        applications__email__iexact=email
    ).select_related('vacancy').distinct().order_by('schedule_start')

    upcoming_interviews = interviews.filter(
        schedule_start__gte=now,
        status='scheduled'
    )

    past_interviews = interviews.exclude(
        id__in=upcoming_interviews
    ).order_by('-schedule_start')

    context = {
        'guest_email': guest_user.email,
        'pending_conferences': pending_conferences,
        'upcoming_conferences': upcoming_conferences,
        'past_conferences': past_conferences,
        'applications': applications,
        'upcoming_interviews': upcoming_interviews,
        'past_interviews': past_interviews,
        'has_activity': (
            conference_regs.exists() or
            applications.exists() or
            interviews.exists()
        ),
    }

    # Set/reinforce cookie if we got here via URL token
    response = render(request, 'guest/guest_dashboard.html', context)
    if token_from_url:
        response.set_cookie(
            'guest_token',
            str(guest_user.token),
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            secure=not settings.DEBUG,
            samesite='Lax',
            path='/'
        )

    return response

def guest_give_feedback(request, conference_id):
    # === Guest authentication (same pattern as dashboard) ===
    guest_user = None
    token_from_cookie = request.COOKIES.get('guest_token')
    if token_from_cookie:
        try:
            guest_user = GuestUser.objects.get(token=token_from_cookie)
        except GuestUser.DoesNotExist:
            pass

    if not guest_user:
        messages.error(request, "Please log in to your dashboard first.")
        return redirect('guest_dashboard')

    # === Verify participant access to this conference ===
    participant = get_object_or_404(
        ConferenceParticipant,
        conference_id=conference_id,
        email__iexact=guest_user.email
    )
    conference = participant.conference

    # Optional: restrict to truly past/attended (adjust as needed)
    now = timezone.now()
    if conference.end_date >= now and not participant.check_in_status:
        messages.info(request, "Feedback is only available after the conference ends or upon check-in.")
        return redirect('guest_dashboard')

    # === Feedback handling ===
    ct = ContentType.objects.get_for_model(Conference)
    feedback = Feedback.objects.filter(
        guest_user=guest_user,
        content_type=ct,
        object_id=conference.id
    ).first()

    if request.method == 'POST':
        rating = request.POST.get('rating')
        topic = request.POST.get('topic', '').strip()
        comment = request.POST.get('comment', '').strip()

        if not rating and not comment:
            messages.error(request, "Please provide at least a rating or a comment.")
        else:
            Feedback.objects.update_or_create(
                guest_user=guest_user,
                content_type=ct,
                object_id=conference.id,
                defaults={
                    'tenant': conference.tenant,  # assuming Conference has .tenant
                    'rating': int(rating) if rating else None,
                    'topic': topic or None,
                    'comment': comment or None,
                }
            )
            messages.success(request, "Thank you! Your feedback has been saved.")
            return redirect('guest_dashboard')

    context = {
        'conference': conference,
        'feedback': feedback,  # may be None
        'participant': participant,
    }
    response = render(request, 'guest/feedback_form.html', context)
    return response