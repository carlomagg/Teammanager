from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from documents.models import GuestUser, ConferenceParticipant, VacancyApplication, Interview, Conference, Vacancy, Feedback
from raadaa import settings

@login_required
def user_activity_dashboard(request):

    user=request.user

    # If still no guest_user, they are not recognized
    if not user.is_authenticated:
        messages.info(request, "Please register for a conference or apply for a job to access your dashboard.")
        return redirect('home')  # or a public landing page

    email = user.email.lower()

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
                user=user,
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
        'user_email': email,
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
    
    return render(request, 'dashboard/user_activity_dashboard.html', context)

@login_required
def user_give_feedback(request, conference_id):
    # === Guest authentication (same pattern as dashboard) ===
    user = request.user

    if not user:
        messages.error(request, "Please log in to your dashboard first.")
        return redirect('user_activity_dashboard')

    # === Verify participant access to this conference ===
    participant = get_object_or_404(
        ConferenceParticipant,
        conference_id=conference_id,
        email__iexact=user.email
    )
    conference = participant.conference

    # Optional: restrict to truly past/attended (adjust as needed)
    now = timezone.now()
    if conference.end_date >= now and not participant.check_in_status:
        messages.info(request, "Feedback is only available after the conference ends or upon check-in.")
        return redirect('user_activity_dashboard')

    # === Feedback handling ===
    ct = ContentType.objects.get_for_model(Conference)
    feedback = Feedback.objects.filter(
        user=user,
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
                user=user,
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
            return redirect('user_activity_dashboard')

    context = {
        'conference': conference,
        'feedback': feedback,  # may be None
        'participant': participant,
    }
    response = render(request, 'dashboard/feedback_form.html', context)
    return response

@login_required
def view_feedback(request, feedback_id):
    feedback = get_object_or_404(Feedback, id=feedback_id)
    return render(request, 'dashboard/feedback_view.html', {'feedback': feedback})