from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from documents.models import JobOffer, VacancyApplication, CustomUser, StaffProfile, OnboardingLog, Interview
from documents.forms import JobOfferForm, InterviewRescheduleForm
from documents.viewfuncs.send_mails import send_job_offer_email, send_onboard_employee
from ..rba_decorators import is_hr
import secrets

@login_required
@user_passes_test(lambda u: is_hr(u) or u.is_superuser or u.roles.filter(name="Admin").exists())
def send_offer(request, application_id, interview_id):
    application = get_object_or_404(
        VacancyApplication,
        id=application_id,
        vacancy__tenant=request.effective_tenant
    )

    interview = get_object_or_404(Interview, id=interview_id, tenant=request.effective_tenant)

    if not application.interviews.filter(status="completed").exists():
        messages.error(request, "Interview must be completed before sending an offer.")
        return redirect("interview_detail", interview_id)

    if hasattr(application, "offer"):
        messages.warning(request, "Job offer already exists for this candidate.")
        return redirect("interview_detail", interview_id)

    if request.method == "POST":
        form = JobOfferForm(request.POST, request.FILES, tenant=request.effective_tenant)
        if form.is_valid():
            offer = form.save(commit=False)
            offer.tenant = request.effective_tenant
            offer.application = application
            offer.created_by = request.effective_user
            offer.save()

            # Optional: send email here
            # send_offer_email(application, offer)
            send_job_offer_email(request,application, interview, offer)

            messages.success(request, f"Job offer sent to {application.get_full_name()}.")
            return redirect("interview_detail", interview_id)   # ← important!

        # if form invalid → fall through to render with errors
    else:
        form = JobOfferForm(tenant=request.effective_tenant)

    # GET or invalid POST → render detail page with form (for modal)
    reschedule_form = InterviewRescheduleForm(instance=interview, tenant=request.effective_tenant)
    return render(request, 'hr/interviews/interview_detail.html', {
        'interview': interview,
        'reschedule_form': InterviewRescheduleForm(instance=interview, tenant=request.effective_tenant),
        'job_offer_form': form,
        'open_send_offer_modal': True,
        'open_send_offer_modal_for': application.id,   # new flag
    })

def offer_response(request, token):
    offer = get_object_or_404(JobOffer, offer_token=token)

    if offer.status != "sent":
        return render(request, "offers/already_responded.html", {"offer": offer})

    if request.method == "POST":
        decision = request.POST.get("decision")

        if decision in ["accept", "accept_with_document"]:
            offer.status = "accepted"
            offer.responded_at = timezone.now()

            if decision == "accept_with_document" and 'signed_document' in request.FILES:
                signed_file = request.FILES['signed_document']
                offer.signed_document.save(
                    f"signed_{offer.offer_token}_{signed_file.name}",
                    signed_file
                )

            offer.save()
            messages.success(request, "Thank you! Your response has been recorded.")
            return redirect('offer_thank_you')  # or render thank_you.html

        elif decision == "decline":
            offer.status = "declined"
            offer.responded_at = timezone.now()
            offer.save()
            messages.info(request, "Your decision has been noted. Thank you.")
            return redirect('offer_thank_you')

    return render(request, "hr/offers/offer_response.html", {"offer": offer})

def offer_thank_you(request):
    return render(request, "hr/offers/offer_thank_you.html")


@login_required
@user_passes_test(lambda u: is_hr(u) or u.is_superuser or u.roles.filter(name="Admin").exists())
def onboard_employee(request, application_id, interview_id):
    application = get_object_or_404(
        VacancyApplication,
        id=application_id,
        vacancy__tenant=request.effective_tenant,
        onboarding_status="pending",
        offer__status="accepted"
    )

    interview = get_object_or_404(Interview, id=interview_id, tenant=request.effective_tenant, status="completed")
    
    password = secrets.token_urlsafe(10)

    user = CustomUser.objects.create_user(
        username=application.email,
        email=application.email,
        password=password,
        tenant=request.effective_tenant,
        must_reset_password=True,
    )

    StaffProfile.objects.create(
        tenant=request.effective_tenant,
        user=user,
        first_name=application.first_name,
        last_name=application.last_name
    )

    application.onboarding_status = "onboarded"
    application.onboarded_user = user
    application.save()

    OnboardingLog.objects.create(
        tenant=request.effective_tenant,
        application=application,
        onboarded_by=request.effective_user
    )

    send_onboard_employee(request, application, user, password)

    messages.success(request, "Employee onboarded successfully.")
    return redirect("interview_detail", interview.id)

@login_required
@user_passes_test(lambda u: is_hr(u) or u.is_superuser or u.roles.filter(name="Admin").exists())
def offer_list(request):
    queryset = JobOffer.objects.all()

    # Tenant filtering
    if request.effective_tenant is not None:
        queryset = queryset.filter(tenant=request.effective_tenant)
    else:
        queryset = queryset.filter(created_by=request.user)  # more common than request.effective_user

    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(application__first_name__icontains=search_query) |
            Q(application__last_name__icontains=search_query) |
            Q(application__vacancy__title__icontains=search_query)
        )

    # Ordering (newest first)
    queryset = queryset.order_by('-sent_at')   # or '-created_at' if you prefer

    # Pagination
    paginator = Paginator(queryset, 15)  # 15 offers per page – adjust as needed
    page = request.GET.get('page', 1)

    try:
        job_offers = paginator.page(page)
    except PageNotAnInteger:
        job_offers = paginator.page(1)
    except EmptyPage:
        job_offers = paginator.page(paginator.num_pages)

    context = {
        'job_offers': job_offers,
        'page_obj': job_offers,           # for pagination template
        'paginator': paginator,
        'search_query': search_query,     # to keep the search term in input
        'is_paginated': job_offers.has_other_pages(),
    }

    return render(request, "hr/offers/offer_list.html", context)