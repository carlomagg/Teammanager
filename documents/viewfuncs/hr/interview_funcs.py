from documents.models import Interview, InterviewParticipant, Vacancy, VacancyApplication, CustomUser
from documents.forms import InterviewRescheduleForm, JobOfferForm
from documents.viewfuncs.rba_decorators import is_hr, is_admin
from documents.viewfuncs.helper_funcs.google_meet_calendar import create_meet, get_auth_url
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from django.db.models import Q
from documents.viewfuncs.send_mails import send_interview_cancelled_email, send_interview_updated_email

@login_required
@user_passes_test(is_hr)
def interview_list(request):
    tab = request.GET.get('tab', 'all')

    # Base querysets
    all_interviews = Interview.objects.filter(tenant=request.tenant)
    my_interviews = all_interviews.filter(scheduled_by=request.user)

    search = request.GET.get("search")
    if search:
        all_interviews = all_interviews.filter(
            Q(vacancy__title__icontains=search) |
            Q(scheduled_by__username__icontains=search) |
            Q(interviewers__username__icontains=search) |
            Q(status__icontains=search)
        )
        my_interviews = my_interviews.filter(
            Q(vacancy__title__icontains=search) |
            Q(interviewers__username__icontains=search) |
            Q(scheduled_by__username__icontains=search) |
            Q(status__icontains=search)
        )

    # Apply filters
    status = request.GET.get('status')
    vacancy_id = request.GET.get('vacancy')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if status:
        all_interviews = all_interviews.filter(status=status)
        my_interviews = my_interviews.filter(status=status)
    if vacancy_id:
        all_interviews = all_interviews.filter(vacancy_id=vacancy_id)
        my_interviews = my_interviews.filter(vacancy_id=vacancy_id)
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            all_interviews = all_interviews.filter(schedule_start__date__gte=df.date())
            my_interviews = my_interviews.filter(schedule_start__date__gte=df.date())
        except:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d')
            all_interviews = all_interviews.filter(schedule_start__date__lte=dt.date())
            my_interviews = my_interviews.filter(schedule_start__date__lte=dt.date())
        except:
            pass

    # Order
    all_interviews = all_interviews.order_by('-schedule_start')
    my_interviews = my_interviews.order_by('-schedule_start')

    # Pagination
    paginator_all = Paginator(all_interviews, 25)
    paginator_my = Paginator(my_interviews, 25)

    page = request.GET.get('page')
    filtered_all_interviews = paginator_all.get_page(page)
    filtered_my_interviews = paginator_my.get_page(page)

    # For vacancy dropdown
    vacancies = Vacancy.objects.filter(tenant=request.tenant).order_by('title')

    context = {
        'all_interviews': all_interviews,  # for count badge
        'my_interviews': my_interviews,    # for count badge
        'filtered_all_interviews': filtered_all_interviews,
        'filtered_my_interviews': filtered_my_interviews,
        'vacancies': vacancies,
    }
    return render(request, 'hr/interviews/interview_list.html', context)

@login_required
@user_passes_test(is_hr)
def interview_detail(request, interview_id):
    interview = Interview.objects.get(id=interview_id)
    reschedule_form = InterviewRescheduleForm(
        instance=interview,
        tenant=request.tenant
    )
    job_offer_form = JobOfferForm(tenant=request.effective_tenant)
    return render(request, 'hr/interviews/interview_detail.html', {'interview': interview, "reschedule_form": reschedule_form, "job_offer_form": job_offer_form})

from documents.forms import InterviewForm, SelectedInterviewForm

@login_required
def load_applications_ajax(request):
    vacancy_id = request.GET.get('vacancy_id')
    if not vacancy_id:
        return JsonResponse([], safe=False)

    applications = VacancyApplication.objects.filter(
        vacancy_id=vacancy_id,
        vacancy__tenant=request.user.tenant,   # critical!
        tenant=request.user.tenant,
        status='accepted',
        # interviews__isnull=True
    ).select_related('vacancy')

    data = [
        {"id": app.id, "text": f"{app.first_name} {app.last_name}"} 
        for app in applications
    ]
    return JsonResponse(data, safe=False)
@login_required
@user_passes_test(is_hr)
def schedule_interview_from_scratch(request):
    if request.method == "POST":
        form = InterviewForm(request.POST, user=request.user)
        print("POST DATA:", request.POST)
        print("FORM VALID?", form.is_valid())
        print("FORM ERRORS:", form.errors)
        if form.is_valid():
            # Save Interview WITHOUT m2m
            interview = form.save(commit=False)
            interview.tenant = request.user.tenant
            interview.scheduled_by = request.user
            interview.save()  # <-- save instance first!
            print("saved interview")
            # Now handle interviewers m2m
            interview.interviewers.set(form.cleaned_data['interviewers'])
            print("saved interviewers")
            form.save_m2m()

            # Save interview ID in session so we can resume after OAuth
            request.session['pending_interview_id'] = interview.id

            # Link selected applications as Interview Participants
            apps = form.cleaned_data['applications']
            for app in apps:
                InterviewParticipant.objects.create(
                    interview=interview,
                    application=app
                )

            # Update application phase
            # apps.update(phase='interview')

            print("Interview schedule successful")
            if interview.google_meet:
                try:
                    create_meet(interview)
                except ValueError:
                    # User not connected – trigger OAuth
                    auth_url = get_auth_url(request, request.user)
                    return redirect(auth_url)
            # Send mail
            from ..send_mails import send_interview_scheduled_email
            # sender = CustomUser.objects.filter(tenant=request.user.tenant, roles__name="HR").first()
            # if not sender:
            sender = CustomUser.objects.filter(is_superuser=True).first()  # fallback

            # Build CC list properly
            cc_emails = list(interview.interviewers.values_list('email', flat=True))
            cc_emails.append(interview.scheduled_by.email)

            for application in interview.applications.all():
                candidate_email = application.email  # assuming applicant has email
                
                print(f"Sending interview scheduled email to: {candidate_email}...")
                
                send_interview_scheduled_email(
                    sender=sender,
                    hr=request.user,
                    cc=cc_emails,  # now a clean list: ['john@company.com', 'jane@company.com']
                    vacancy_application=application,
                    interview=interview
                )

            return redirect('interview_detail', interview.id)

    else:
        form = InterviewForm(user=request.user)

    return render(request, 'hr/interviews/schedule_from_scratch.html', {
        'form': form,
        'title': 'Schedule Interview (From Scratch)'
    })


@login_required
def schedule_interview_from_applications(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, tenant=request.user.tenant, id=vacancy_id)

    # Extract application IDs from POST first, then GET
    app_ids_str = request.POST.get('application_ids') or request.GET.get('application_ids')

    print("app_ids_str:", app_ids_str)

    selected_ids = [
        int(x) for x in app_ids_str.split(',') if x.strip().isdigit()
    ] if app_ids_str else []


    selected_applications = VacancyApplication.objects.filter(id__in=selected_ids) if selected_ids else None

    if not selected_applications:
        print("No applications selected.")
        return redirect('fetch_accepted_applications', vacancy_id)

    if request.method == "POST":
        form = SelectedInterviewForm(
            request.POST,
            user=request.user,
            vacancy=vacancy,
            applications=selected_applications,
        )
        if form.is_valid():
            interview = form.save(commit=False)
            interview.tenant = request.user.tenant
            interview.vacancy = vacancy
            interview.scheduled_by = request.user
            interview.save()
            interview.applications.set(selected_applications)
            form.save_m2m()

            for app in form.cleaned_data['applications']:
                InterviewParticipant.objects.create(interview=interview, application=app)

            try:
                create_meet(interview)
            except ValueError:
                auth_url = get_auth_url(request, request.user)
                return redirect(auth_url)
            
            # Send mail
            from ..send_mails import send_interview_scheduled_email
            # sender = CustomUser.objects.filter(tenant=request.user.tenant, roles__name="HR").first()
            # if not sender:
            sender = CustomUser.objects.filter(is_superuser=True).first()  # fallback

            # Build CC list properly
            cc_emails = list(interview.interviewers.values_list('email', flat=True))
            cc_emails.append(interview.scheduled_by.email)

            for application in interview.applications.all():
                candidate_email = application.email  # assuming applicant has email
                
                print(f"Sending interview scheduled email to: {candidate_email}...")
                
                send_interview_scheduled_email(
                    sender=sender,
                    hr=request.user,
                    cc=cc_emails,  # now a clean list: ['john@company.com', 'jane@company.com']
                    vacancy_application=application,
                    interview=interview
                )

            messages.success(request, "Interview scheduled successfully!")
            return redirect('interview_detail', interview.id)

    else:
        form = SelectedInterviewForm(
            user=request.user,
            vacancy=vacancy,
            applications=selected_applications,
            data=None,
        )

    return render(request, 'hr/interviews/schedule_from_selected.html', {
        'form': form,
        'vacancy': vacancy,
        'selected_ids': selected_ids,
        'selected_count': selected_applications.count() if selected_applications else 0,
        'selected_applications': selected_applications,
        'title': f'Schedule Interview for {vacancy.title}',
    })

@login_required
@user_passes_test(is_hr)
def update_interview(request, interview_id):
    interview = get_object_or_404(Interview, tenant=request.user.tenant, id=interview_id)
    # Save old values before update
    old_start = interview.schedule_start
    old_was_virtual = interview.is_virtual
    old_virtual_link = interview.virtual_link
    old_location = interview.physical_location
    old_timezone = interview.timezone
    if request.method == 'POST':
        form = InterviewForm(request.POST, instance=interview, user=request.user)
        if form.is_valid():
            form.save(commit=False)
            # form.updated_by = request.user
            form.updated_at = timezone.now()
            form.save()
            form.save_m2m()

            sender = CustomUser.objects.filter(tenant=request.user.tenant, roles__name="HR").first()                
            if not sender:
                sender = CustomUser.objects.filter(is_superuser=True).first()
            cc_emails = list(interview.interviewers.values_list('email', flat=True))
            if interview.schedule_start != old_start or interview.is_virtual != old_was_virtual or interview.virtual_link != old_virtual_link or interview.physical_location != old_location or old_timezone != interview.timezone:
                for application in interview.applications.all():
                    print(f"Sending interview updated email to: {application.email}")
                    send_interview_updated_email(hr=request.user, vacancy_application=application,
                        interview=interview,
                        old_schedule_start=old_start,
                        old_was_virtual=old_was_virtual
                    )

            return redirect('interview_detail', interview.id)
    else:
        form = InterviewForm(instance=interview, user=request.user)
    return render(request, 'hr/interviews/update_interview.html', {'form': form, 'title': 'Update Interview', 'interview': interview})

@login_required
@user_passes_test(is_hr)
def cancel_interview(request, interview_id):
    interview = get_object_or_404(Interview, tenant=request.user.tenant, id=interview_id)
    interview.status = 'cancelled'
    interview.save()
    for app in interview.applications.all():
        send_interview_cancelled_email(hr=request.effective_user, vacancy_application=app, interview=interview)
    next_url = request.GET.get("next")
    return redirect(next_url or'interview_list')

@login_required
@user_passes_test(is_hr)
def reschedule_interview(request, interview_id):
    interview = get_object_or_404(Interview,  id=interview_id, tenant=request.tenant, status="cancelled")
    old_start = interview.schedule_start
    old_was_virtual = interview.is_virtual
    old_virtual_link = interview.virtual_link
    old_location = interview.physical_location
    old_timezone = interview.timezone

    if request.method == "POST":
        form = InterviewRescheduleForm(request.POST, instance=interview, tenant=request.tenant)
        if form.is_valid():
            interview = form.save(commit=False)
            interview.status = "rescheduled"
            interview.save()
            form.save_m2m()
            new_interview = Interview.objects.get(id=interview.id)
            for app in interview.applications.all():
                send_interview_updated_email(hr=request.user, vacancy_application=app,
                    interview=interview,
                    old_schedule_start=old_start,
                    old_was_virtual=old_was_virtual)

            messages.success(request, "Interview rescheduled successfully.")
            return redirect("interview_detail", interview.id)
    else:
        form = InterviewRescheduleForm(
            instance=interview,
            tenant=request.tenant
        )

    return render(request, "hr/interviews/interview_detail.html", {
        "interview": interview,
        "reschedule_form": form,
        "open_reschedule_modal": True
    })

@login_required
def complete_interview(request, interview_id):
    interview = get_object_or_404(
        Interview,
        id=interview_id,
        tenant=request.tenant,
        status__in=["scheduled", "rescheduled"]
    )

    if request.method == "POST":
        interview.status = "completed"
        interview.save(update_fields=["status", "updated_at"])
        messages.success(request, "Interview marked as completed.")

    return redirect("interview_detail", interview.id)


@login_required
@user_passes_test(is_hr)
def delete_interview(request, interview_id):
    interview = get_object_or_404(Interview, tenant=request.user.tenant, id=interview_id)
    interview.delete()
    next_url = request.GET.get("next")
    return redirect(next_url or 'interview_list')