import json
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Count, Q
from django.shortcuts import render
from django.utils import timezone

from documents.models import (
    Conference,
    ConferenceParticipant,
    CustomQuestion,
    Feedback,
)


@login_required
@user_passes_test(lambda u: u.is_staff)
def track_conference(request):
    now = timezone.now()

   
    # 1.  Summary cards                                                   #
   
    total_conferences  = Conference.objects.count()
    total_upcoming     = Conference.objects.filter(start_date__gte=now).count()
    total_past         = Conference.objects.filter(end_date__lt=now).count()
    total_participants = ConferenceParticipant.objects.count()

    # Feature-flag cards
    with_questions     = Conference.objects.filter(
        custom_questions__isnull=False
    ).distinct().count()
    with_upload_folders = Conference.objects.filter(
        upload_folder__isnull=False
    ).count()
    with_speakers      = Conference.objects.filter(
        speakers__isnull=False
    ).distinct().count()

    # Average feedback (Feedback uses a GenericFK → look up via ContentType)
    conf_ct = ContentType.objects.get_for_model(Conference)
    avg_feedback = round(
        float(
            Feedback.objects.filter(content_type=conf_ct)
            .aggregate(avg=Avg("rating"))["avg"] or 0
        ),
        2,
    )

   
    # 2.  Paid vs Free  (ticket_price == 0  →  Free)                     #
    
    paid_count = Conference.objects.filter(ticket_price__gt=0).count()
    free_count = Conference.objects.filter(ticket_price=0).count()

  
    # 3.  Conference type  (physical / virtual / hybrid)                  #
  
    physical_count = Conference.objects.filter(conference_type="physical").count()
    virtual_count  = Conference.objects.filter(conference_type="virtual").count()
    hybrid_count   = Conference.objects.filter(conference_type="hybrid").count()

    
    # 4.  Per-tenant breakdowns                                           #

    conferences_per_tenant = list(
        Conference.objects.values("tenant__id", "tenant__name", "organizer__first_name", "organizer__username")
        .annotate(conference_count=Count("id"))
        .order_by("-conference_count")[:20]
    )

    participants_per_tenant = list(
        ConferenceParticipant.objects.values("tenant__id", "tenant__name")
        .annotate(participant_count=Count("id"))
        .order_by("-participant_count")[:20]
    )

    # 5.  Per-user breakdowns  (organizer)                               #
  
    conferences_per_user = list(
        Conference.objects.values(
            "tenant__name",
            "organizer__id",
            "organizer__username",
            "organizer__first_name",
            "organizer__last_name",
        )
        .annotate(conference_count=Count("id"))
        .order_by("-conference_count")[:20]
    )

    participants_per_user = list(
        ConferenceParticipant.objects.values(
            "conference__organizer__id",
            "conference__organizer__username",
            "conference__organizer__first_name",
            "conference__organizer__last_name",
        )
        .annotate(participant_count=Count("id"))
        .order_by("-participant_count")[:20]
    )

    # 6.  Top 10 by attendance  (check_in_status=True)                   #
    top_by_attendance = list(
        Conference.objects.annotate(
            attendance=Count(
                "participants",
                filter=Q(participants__check_in_status=True),
            )
        )
        .order_by("-attendance")
        .values("id", "title", "tenant__name", "attendance", "organizer__first_name", "organizer__username")[:10]
    )

    # 7.  Top 10 by registration  (all participants regardless of status) #
    top_by_registration = list(
        Conference.objects.annotate(
            registration_count=Count("participants")
        )
        .order_by("-registration_count")
        .values("id", "title", "tenant__name", "registration_count", "organizer__first_name", "organizer__username")[:10]
    )

    # 8.  Chart.js–ready JSON  (mirrors track_vacancy pattern)           #
    # Tenant bar chart
    tenant_chart_labels = json.dumps(
        [t["tenant__name"] or t["organizer__first_name"] for t in conferences_per_tenant]
    )
    tenant_chart_data = json.dumps(
        [t["conference_count"] for t in conferences_per_tenant]
    )

    # Pie: paid vs free
    paid_free_labels = json.dumps(["Paid", "Free"])
    paid_free_data   = json.dumps([paid_count, free_count])

    # Pie: conference type
    type_labels = json.dumps(["In-Person", "Virtual", "Hybrid"])
    type_data   = json.dumps([physical_count, virtual_count, hybrid_count])

    context = {
        # --- cards ---
        "total_conferences":   total_conferences,
        "total_upcoming":      total_upcoming,
        "total_past":          total_past,
        "total_participants":  total_participants,
        "with_questions":      with_questions,
        "with_upload_folders": with_upload_folders,
        "with_speakers":       with_speakers,
        "avg_feedback":        avg_feedback,
        "paid_count":          paid_count,
        "free_count":          free_count,
        "physical_count":      physical_count,
        "virtual_count":       virtual_count,
        "hybrid_count":        hybrid_count,
        # --- tables ---
        "conferences_per_tenant":  conferences_per_tenant,
        "participants_per_tenant": participants_per_tenant,
        "conferences_per_user":    conferences_per_user,
        "participants_per_user":   participants_per_user,
        "top_by_attendance":       top_by_attendance,
        "top_by_registration":     top_by_registration,
        # --- chart JSON ---
        "tenant_chart_labels": tenant_chart_labels,
        "tenant_chart_data":   tenant_chart_data,
        "paid_free_labels":    paid_free_labels,
        "paid_free_data":      paid_free_data,
        "type_labels":         type_labels,
        "type_data":           type_data,
    }

    return render(request, "tracking/conference_dashboard.html", context)