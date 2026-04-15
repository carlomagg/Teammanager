from django.core.mail import EmailMessage
import logging
from django.contrib.auth.decorators import login_required, user_passes_test
from documents.forms import VacancyApplicationForm
from documents.models import Vacancy, VacancyApplication, CustomUser
from documents.viewfuncs.mail_connection import get_email_smtp_connection
from ..rba_decorators import is_hr
from ..helper_funcs.permissions import can_manage_vacancies
from django.http import HttpResponseForbidden, JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.db.models import Count
from django.template.loader import render_to_string
from ..send_mails import send_vac_app_received_email, send_vac_app_accepted_email, send_vac_app_rejected_email
from django.contrib import messages


logger = logging.getLogger(__name__)

@login_required
def vacancy_application_list(request):
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to view vacancy applications.'
        })

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    if is_personal:
        vacancies = (
            Vacancy.objects
            .filter(created_by=user)
            .annotate(app_count=Count('applications', distinct=True))
            .order_by('-created_at')
        )
    else:
        if tenant is None:
            return render(request, 'tenant_error.html', {
                'error_code': '403',
                'message': 'No company context available.'
            })

        vacancies = (
            Vacancy.objects
            .filter(tenant=tenant)
            .annotate(app_count=Count('applications', distinct=True))
            .order_by('-created_at')
        )

    paginator = Paginator(vacancies, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'hr/vacancy_application_list.html', {
        'vacancies': page_obj,
        'is_personal_mode': is_personal,
    })

def send_vacancy_application_received(request, application_id):
    vacancy_application = get_object_or_404(VacancyApplication, id=application_id)
    vacancy = vacancy_application.vacancy
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    if vacancy.tenant is None:
        hrs=[]
        hr=None
    else:
        hrs = CustomUser.objects.filter(tenant=vacancy.tenant, is_active=True, roles__name='HR')
        hr = hrs[0]
    sender = superuser
    candidate_name = vacancy_application.first_name
    if vacancy_application.tenant is None:
        company = None
    else:
        company = vacancy_application.tenant.name

    # Send application received email
    send_vac_app_received_email(company, candidate_name, vacancy_application, vacancy, sender, hrs)
    
    print("Mail Sent")

def create_vacancy_application(request, vacancy_id):
    vacancy = get_object_or_404(Vacancy, id=vacancy_id)
    if request.method == 'POST':
        form = VacancyApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            vacancy_application = form.save(commit=False)
            vacancy_application.vacancy = vacancy
            if vacancy.tenant is None:
                vacancy_application.tenant = None
            else:
                vacancy_application.tenant = vacancy.tenant
            vacancy_application.save()
            send_vacancy_application_received(request, vacancy_application.id)
            return render(request, 'hr/vacancy_application_success.html', {'name':vacancy_application.first_name, 'vacancy': vacancy})
    else:
        form = VacancyApplicationForm()
    return render(request, 'hr/create_vacancy_application.html', {'form': form, 'vacancy': vacancy}) 

@login_required
def applications_per_vacancy(request, vacancy_id):
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {'error_code': '403', 'message': 'No permission.'})

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    if is_personal:
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, created_by=user)
        applications_qs = VacancyApplication.objects.filter(vacancy=vacancy)
    else:
        if tenant is None:
            raise Http404("No tenant context")
        vacancy = get_object_or_404(Vacancy, id=vacancy_id, tenant=tenant)
        applications_qs = VacancyApplication.objects.filter(vacancy=vacancy, tenant=tenant)

    paginator = Paginator(applications_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'hr/applications_per_vacancy.html', {
        'vacancy_applications': page_obj,
        'vacancy': vacancy,
        'is_personal_mode': is_personal,
    })

@login_required
def vacancy_application_detail(request, vacancy_id, application_id):
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {'error_code': '403', 'message': 'No permission.'})

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    if is_personal:
        # Personal user can only see their own created applications
        application = get_object_or_404(VacancyApplication, id=application_id, vacancy__id=vacancy_id, vacancy__created_by=user,)
    else:
        if tenant is None:
            raise Http404("No tenant context")
        application = get_object_or_404(VacancyApplication, id=application_id, vacancy__id=vacancy_id, vacancy__tenant=tenant, tenant=tenant)

    return render(request, 'hr/vacancy_application_detail.html', {
        'vacancy_application': application,
        'is_personal_mode': is_personal,
    })

@login_required
def delete_vacancy_application(request, vacancy_id, application_id):
    """
    Delete a vacancy application.
    
    Permission rules:
    - Personal users: can delete applications on vacancies they created
    - Company HR: can delete applications in their tenant
    - Staff / superuser: can delete in effective tenant context
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete applications.'
        })

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    try:
        if is_personal:
            # Personal mode
            application = get_object_or_404(VacancyApplication, id=application_id, vacancy__id=vacancy_id, vacancy__created_by=user, vacancy__tenant__isnull=True)
        else:
            # Company / staff / superuser context
            if tenant is None:
                # Should almost never reach here thanks to middleware + permission fn
                return render(request, 'tenant_error.html', {
                    'error_code': '403',
                    'message': 'No company context available for this action.'
                })

            application = get_object_or_404(VacancyApplication, id=application_id, vacancy__id=vacancy_id, vacancy__tenant=tenant, tenant=tenant)

        # ── Perform deletion ───────────────────────────────────────
        vacancy_id_for_redirect = application.vacancy.id
        application.delete()

        messages.success(request, "Application deleted successfully.")
        logger.info(f"Application {application_id} deleted by {request.user}")

        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
        else:
            redirect('applications_per_vacancy', vacancy_id=vacancy_id_for_redirect)

        # return redirect('applications_per_vacancy', vacancy_id=vacancy_id_for_redirect)

    except Http404:
        return render(request, 'tenant_error.html', {
            'error_code': '404',
            'message': 'Application or vacancy not found or you do not have access.'
        })

def send_vacancy_accepted_mail(request, application_id):
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete applications.'
        })
    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    
    if is_personal:
        # Personal mode
        vacancy_application = get_object_or_404(VacancyApplication, id=application_id, vacancy__created_by=user, vacancy__tenant__isnull=True)
    else:
        # Company / staff / superuser context
        if tenant is None:
            # Should almost never reach here thanks to middleware + permission fn
            return render(request, 'tenant_error.html', {
                'error_code': '403',
                'message': 'No company context available for this action.'
            })

        vacancy_application = get_object_or_404(VacancyApplication, id=application_id, vacancy__tenant=tenant, tenant=tenant)
    vacancy = vacancy_application.vacancy
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    hr = user
    cc = hr
    
    sender = superuser
    candidate_name = vacancy_application.first_name

    if vacancy_application.tenant is None:
        company = None
    else:
        company = vacancy_application.tenant.name
    
    print("CC: ", cc)

    # Send application accepted email
    send_vac_app_accepted_email(sender, company, candidate_name, hr, cc, vacancy_application, vacancy)
    
    print("Mail Sent")

def send_vacancy_rejected_mail(request, application_id):
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to delete applications.'
        })
    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    
    if is_personal:
        # Personal mode
        vacancy_application = get_object_or_404(VacancyApplication, id=application_id, vacancy__created_by=user, vacancy__tenant__isnull=True)
    else:
        # Company / staff / superuser context
        if tenant is None:
            # Should almost never reach here thanks to middleware + permission fn
            return render(request, 'tenant_error.html', {
                'error_code': '403',
                'message': 'No company context available for this action.'
            })

        vacancy_application = get_object_or_404(VacancyApplication, id=application_id, vacancy__tenant=tenant, tenant=tenant)
    vacancy = vacancy_application.vacancy
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    hr = user
    cc = hr
    
    sender = superuser
    candidate_name = vacancy_application.first_name

    if vacancy_application.tenant is None:
        company = None
    else:
        company = vacancy_application.tenant.name
    
    print("CC: ", cc)

    # Send application rejected email
    send_vac_app_rejected_email(sender, company, candidate_name, hr, cc, vacancy_application, vacancy)
    
    print("Mail Sent")
    
# non-form accept, reject vacancy application
@login_required
def accept_vac_app(request, application_id):
    """
    Accept a vacancy application (change status → 'accepted' + send email).

    Permission & context rules:
    - Personal users: can accept apps on vacancies they created (tenant=None)
    - Company users: HR role required in the effective tenant
    - Staff / superuser: allowed in any effective tenant context
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to accept applications.'
        })

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    try:
        if is_personal:
            # Personal mode: only applications on vacancies created by this user
            application = get_object_or_404(VacancyApplication, id=application_id, vacancy__created_by=user, vacancy__tenant__isnull=True, tenant__isnull=True)
        else:
            # Company / staff / superuser mode
            if tenant is None:
                return render(request, 'tenant_error.html', {
                    'error_code': '403',
                    'message': 'No company context available for this action.'
                })

            application = get_object_or_404(VacancyApplication, id=application_id, vacancy__tenant=tenant, tenant=tenant,)

        # ── Business rule guard ──────────────────────────────────────────────
        # if application.status not in ['pending', 'new', 'received']:  # adjust allowed statuses
        #     return render(request, 'tenant_error.html', {
        #         'error_code': '400',
        #         'message': f'Cannot accept an application in {application.status} status.'
        #     })

        # ── Change state ─────────────────────────────────────────────────────
        application.status = 'accepted'
        application.updated_by = user   # optional: track who accepted
        application.save(update_fields=['status', 'updated_by'])

        # ── Trigger email (side effect) ──────────────────────────────────────
        send_vacancy_accepted_mail(request, application_id)

        # ── Success redirect ─────────────────────────────────────────────────
        return redirect('vacancy_application_detail', vacancy_id=application.vacancy.id, application_id=application.id)

    except Http404:
        return render(request, 'tenant_error.html', {
            'error_code': '404',
            'message': 'Application not found or you do not have access to it.'
        })

@login_required
def reject_vac_app(request, application_id):
    """
    Reject a vacancy application.

    Permission rules:
    - Personal users: can reject applications on vacancies they created
    - Company HR: can reject applications in their tenant
    - Staff / superuser: can reject in effective tenant context

    Side effect: trigger email to candidate

    Returns:
    - If successful, redirects to the vacancy application detail page
    - If unauthorized, renders a 403 tenant error page
    - If the application is not found or the user does not have access, renders a 404 tenant error page
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to accept applications.'
        })

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    try:
        if is_personal:
            # Personal mode: only applications on vacancies created by this user
            application = get_object_or_404(VacancyApplication, id=application_id, vacancy__created_by=user, vacancy__tenant__isnull=True, tenant__isnull=True)
        else:
            # Company / staff / superuser mode
            if tenant is None:
                return render(request, 'tenant_error.html', {
                    'error_code': '403',
                    'message': 'No company context available for this action.'
                })

            application = get_object_or_404(VacancyApplication, id=application_id, vacancy__tenant=tenant, tenant=tenant,)
        # ── Change state ─────────────────────────────────────────────────────
        application.status = 'rejected'
        application.updated_by = user   # optional: track who accepted
        application.save(update_fields=['status', 'updated_by'])
        send_vacancy_rejected_mail(request, application_id)
        return redirect('vacancy_application_detail', vacancy_id=application.vacancy.id, application_id=application.id)
    except Http404:
        return render(request, 'tenant_error.html', {
            'error_code': '404',
            'message': 'Application not found or you do not have access to it.'
        })


@login_required
def fetch_accepted_applications(request, vacancy_id):
    """
    List accepted applications for a specific vacancy.
    
    - Personal users: see accepted applications on vacancies they created
    - Company users / staff / superuser: see accepted applications in effective tenant context
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to view accepted applications.'
        })

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    try:
        if is_personal:
            # Personal mode: vacancy must be created by this user
            vacancy = get_object_or_404(Vacancy, id=vacancy_id, created_by=user, tenant__isnull=True)
            applications = VacancyApplication.objects.filter(vacancy=vacancy, status='accepted')

        else:
            # Company / staff / superuser mode
            if tenant is None:
                return render(request, 'tenant_error.html', {
                    'error_code': '403',
                    'message': 'No company context available.'
                })

            vacancy = get_object_or_404(Vacancy, id=vacancy_id, tenant=tenant)
            applications = VacancyApplication.objects.filter(vacancy=vacancy, status='accepted', tenant=tenant)

        # ── Collect emails ───────────────────────────────────────────────────
        emails = [app.email for app in applications if app.email]

        # ── Pagination ───────────────────────────────────────────────────────
        paginator = Paginator(applications, 10)
        page = request.GET.get('page')
        page_obj = paginator.get_page(page)

        return render(request, 'hr/accepted_applications.html', {
            'applications': page_obj,
            'vacancy': vacancy,
            'emails': emails,                   # comma-separated list or whatever your template expects
            'is_personal_mode': is_personal,
        })

    except Http404:
        return render(request, 'tenant_error.html', {
            'error_code': '404',
            'message': 'Vacancy not found or you do not have access to it.'
        })

@login_required
def fetch_rejected_applications(request, vacancy_id):
    """
    Display the list of rejected applications for a specific vacancy.

    Filtering rules:
    • Personal users (is_personal=True): only vacancies they created → applications with status='rejected'
    • Company context / staff / superuser: applications in the effective tenant with status='rejected'
    """
    if not can_manage_vacancies(request):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to view rejected applications.'
        })

    user = request.effective_user
    tenant = request.effective_tenant
    is_personal = getattr(user, 'is_personal', False)

    try:
        if is_personal:
            # Personal account: only their own vacancies
            vacancy = get_object_or_404(Vacancy, id=vacancy_id, created_by=user, tenant__isnull=True)
            applications = VacancyApplication.objects.filter(vacancy=vacancy, status='rejected')

        else:
            # Company context, staff impersonating, or superuser
            if tenant is None:
                return render(request, 'tenant_error.html', {
                    'error_code': '403',
                    'message': 'No company context available.'
                })

            vacancy = get_object_or_404(Vacancy, id=vacancy_id, tenant=tenant)
            applications = VacancyApplication.objects.filter(vacancy=vacancy, status='rejected', tenant=tenant)

        # Collect emails of rejected applicants
        emails = [app.email for app in applications if app.email]

        # Pagination (10 per page, same as accepted view)
        paginator = Paginator(applications, 10)
        page = request.GET.get('page')
        page_obj = paginator.get_page(page)

        return render(request, 'hr/rejected_applications.html', {
            'applications': page_obj,
            'vacancy': vacancy,
            'emails': emails,                   # typically used for copy-to-clipboard or mailto:
            'is_personal_mode': is_personal,
        })

    except Http404:
        return render(request, 'tenant_error.html', {
            'error_code': '404',
            'message': 'Vacancy not found or you do not have access to it.'
        })