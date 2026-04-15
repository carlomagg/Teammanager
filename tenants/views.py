# tenants/views.py
import json
from sqlite3 import IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.sessions.models import Session
from django.core.mail import send_mail, get_connection
from django.core.management import call_command
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.utils import timezone
from .models import Tenant, TenantApplication, CompanyGroup
from .forms import TenantApplicationForm, TenantForm, AddCompanyGroupMemberForm, EditCompanyGroupMemberForm, RemoveCompanyGroupMemberForm, BulkAddCompanyGroupMemberForm, CompanyGroupAdminForm, CompanyGroupForm
from documents.models import CustomUser, Role, Department, Team, StaffProfile, CompanyProfile, Contact, Email, Event, Task, Folder, File, Vacancy, VacancyApplication, Conference
from documents.viewfuncs.send_mails import admin_reg_confirm
from django.contrib.auth import authenticate, login
from django.db.models import Q, Count
import logging, csv
from raadaa import settings
from raadaa.tasks import create_default_folders_user, create_default_folders_org
from django.db import transaction
from datetime import timedelta
from django.urls import reverse
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet




# from tenants import models

logger = logging.getLogger(__name__)

def home(request):
    now = timezone.now()
    vacancies = Vacancy.objects.filter(status='active', is_shared=True).order_by('-created_at')
    vacancy_count = vacancies.count()
    conferences = Conference.objects.filter(end_date__gte=now).order_by('created_at', 'start_date')
    conference_count = conferences.count()

    return render(request, 'tenant_home.html', {'vacancy_count': vacancy_count, 'conference_count':conference_count})

def apply_for_tenant(request):
    if request.method == 'POST':
        form = TenantApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.status = 'approved'
            application.username = form.cleaned_data["email"]
            application.save()
            org_name = form.cleaned_data["organization_name"]
            phone_number = form.cleaned_data["phone_number"]
            try:
                # tenant_admin = CustomUser.objects.get(username=application.username)
                tenant = Tenant.objects.create(
                    name=application.organization_name,
                    slug=application.slug
                )
                tenant.save()
                company_profile = CompanyProfile.objects.create(
                    company_name=org_name,
                    tenant=tenant,
                    contact_details=phone_number,
                )
                company_profile.save()
                user = CustomUser.objects.create_user(
                        username=application.username,
                        email=application.email,
                        password=application.password,
                        tenant=tenant
                )
                user.save()
                profile, created = StaffProfile.objects.get_or_create(tenant=user.tenant, user=user)
                # profile.first_name = user.first_name
                # profile.last_name = user.last_name
                profile.email = user.email
                profile.save()
                logger.info(f"Created tenant: {tenant.slug}")
                admin_role, _ = Role.objects.get_or_create(name='Admin')
                roles = Role.objects.all()
                logger.info(f"Tenant application created: {application.organization_name} by {application.username}")
                user.roles.add(admin_role)
                for role in roles:
                    user.roles.add(role)
                user.set_password(form.cleaned_data["password"])
                user.is_active = True
                user.save()
                tenant.admin = user
                tenant.save()
                application.status = 'approved'
                application.save()
                logger.debug(f"Assigned Admin role to user {tenant.admin.username} for tenant {tenant.slug}")
                # Login redirect
                base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
                protocol = "http" if settings.DEBUG else "https"
                login_url = f"{protocol}://{application.slug}.{base_domain}/accounts/login"
                # return redirect('login')
                admin_reg_confirm(user)
                # Folder Creation
                create_default_folders_user.delay(user.id)
                create_default_folders_org.delay(tenant.id)
                return render(request, 'tenants/login_redirect.html', {'login_url': login_url})
            except Exception as e:
                logger.error(f"Error creating tenant for application {application.organization_name}: {str(e)}")
                return HttpResponseForbidden(f"Error creating tenant: {str(e)}")
        else:
            logger.error(f"Tenant application form validation failed: {form.errors}")
            messages.error(request, "Application submission failed. Please correct the errors below.")
    else:
        form = TenantApplicationForm()
    return render(request, 'tenants/apply_for_tenant.html', {'form': form})

def check_status(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            application = TenantApplication.objects.get(email=email)
            return redirect('application_status', identifier=str(application.id))
        except TenantApplication.DoesNotExist:
            messages.error(request, "No application found for the provided email.")
    return render(request, 'tenants/check_status.html')

# @login_required
def application_status(request, identifier):
    applications = TenantApplication.objects.filter(id=identifier)
    logger.debug(f"Listed {applications.count()} applications for identifier: {identifier}")
    if not applications:
        messages.warning(request, "No applications found for the provided identifier.")
    return render(request, 'tenants/application_status.html', {'applications': applications})

@login_required
def create_tenant(request, tenant_application_id):
    if not request.user.is_superuser:
        logger.warning(f"Unauthorized tenant creation attempt by user: {request.user.username}")
        return HttpResponseForbidden("You are not authorized to create a tenant.")
    
    try:
        application = TenantApplication.objects.get(id=tenant_application_id, status='pending')
    except TenantApplication.DoesNotExist:
        logger.error(f"Tenant application {tenant_application_id} not found or not pending")
        return HttpResponseForbidden("Invalid or non-pending application.")
    
    try:
        # tenant_admin = CustomUser.objects.get(username=application.username)
        tenant = Tenant.objects.create(
            name=application.organization_name,
            slug=application.slug,
            created_by=request.user
        )
        tenant.save()
        roles = Role.objects.all()
        user = CustomUser.objects.create_user(
                username=application.username,
                email=application.email,
                password=application.password,
                tenant=tenant,
        )
        user.save()
        logger.info(f"Created tenant: {tenant.slug}")
        admin_role, _ = Role.objects.get_or_create(name='Admin')
        logger.info(f"Tenant application created: {application.organization_name} by {application.username}")
        # user.roles.add(admin_role)
        for role in roles:
            user.roles.add(role)
        user.set_password = application.password
        user.is_active = True
        user.save()
        tenant.admin = user
        tenant.save()
        application.status = 'approved'
        application.save()
        logger.debug(f"Assigned Admin role to user {tenant.admin.username} for tenant {tenant.slug}")
        return redirect('tenant_applications')
    except Exception as e:
        logger.error(f"Error creating tenant for application {application.organization_name}: {str(e)}")
        return HttpResponseForbidden(f"Error creating tenant: {str(e)}")

@login_required
@user_passes_test(lambda u: u.is_superuser)
def reject_tenant(request, tenant_application_id):
    if not request.user.is_superuser:
        logger.warning(f"Unauthorized tenant rejection attempt by user: {request.user.username}")
        return HttpResponseForbidden("You are not authorized to reject a tenant.")
    
    try:
        tenant_app = TenantApplication.objects.get(id=tenant_application_id, status='pending')
        tenant_app.status = 'rejected'
        tenant_app.save()
    except Tenant.DoesNotExist:
        logger.error(f"Tenant {tenant_application_id} not found")
        return HttpResponseForbidden("Invalid tenant.")
    
    
    logger.info(f"Rejected tenant: {tenant_app.slug}")
    return redirect('tenant_list')
    
@login_required
def tenant_applications(request):
    if request.user.is_superuser or request.user.tenant.slug == 'track':
        tenant_apps = TenantApplication.objects.all()
    else:
        HttpResponseForbidden(f'You are not authorized to view this')
    return render(request, 'tenants/tenant_applications.html', {'tenants': tenant_apps})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_tenant_app(request, tenant_application_id):
    tenant_app = get_object_or_404(TenantApplication, id=tenant_application_id)
    tenant_app.delete()
    return redirect('tenant_applications')

@login_required
def tenant_list(request):
    if request.user.is_superuser or request.user.tenant.slug == 'track':
        tenants_qs = Tenant.objects.all()
    else:
        tenants_qs = Tenant.objects.filter(
            Q(created_by=request.user) | Q(admin=request.user) | Q(customuser__id=request.user.id)
        ).distinct()
    logger.debug(f"Listed {tenants_qs.count()} tenants for user: {request.user.username}")

    # Export handling (before pagination)
    if request.method == "POST" and "export" in request.POST:
        action = request.POST.get("export")
        tenant_ids = request.POST.getlist("tenant_ids")

        if "all" in action:
            tenants = tenants_qs
        elif "selected" in action and tenant_ids:
            tenants = tenants_qs.filter(id__in=tenant_ids)
        else:
            tenants = Tenant.objects.none()

        # Attach num_users
        for tenant in tenants_qs:
            tenant.num_users = CustomUser.objects.filter(tenant=tenant).count()

        if "csv" in action:
            return export_tenants_csv(tenants)
        elif "pdf" in action:
            return export_tenants_pdf(tenants)

    count = tenants_qs.count()

    for tenant in tenants_qs:
        tenant.num_users = CustomUser.objects.filter(tenant=tenant).count()

    paginator = Paginator(tenants_qs, 10)  # 10 users per page
    page_number = request.GET.get('page')
    tenants = paginator.get_page(page_number)
    return render(request, 'tenants/tenant_list.html', {'tenants': tenants, 'count':count})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_tenant(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    if request.method == 'POST':
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            return redirect('tenant_list')
    else:
        form = TenantForm(instance=tenant)
    return render(request, 'tenants/edit_tenant.html', {'form': form, 'tenant': tenant})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_tenant(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.delete()
    return redirect('tenant_list')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def verify_tenant(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.is_verified = True
    tenant.save()
    return redirect('tenant_list')

def export_tenants_csv(tenants):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="tenants_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Slug', 'Admin', 'Number of Users', 'Verified',
        'Subscription Plan', 'Subscription Status', 'Created By', 'Created At'
    ])

    for tenant in tenants:
        writer.writerow([
            tenant.name,
            tenant.slug,
            str(tenant.admin) if tenant.admin else '',
            tenant.num_users,
            'Yes' if tenant.is_verified else 'No',
            tenant.subscription_plan or '',
            tenant.subscription_status or '',
            str(tenant.created_by) if tenant.created_by else '',
            tenant.created_at.strftime("%Y-%m-%d %H:%M") if tenant.created_at else ''
        ])

    return response


def export_tenants_pdf(tenants):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=30)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Tenants Report – {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles['Heading1']))
    elements.append(Paragraph(f"Total: {tenants.count()}", styles['Normal']))
    elements.append(Spacer(1, 12))

    data = [[
        'Name', 'Slug', 'Admin', 'Users', 'Verified',
        'Plan', 'Status', 'Created By', 'Created At'
    ]]

    for tenant in tenants:
        data.append([
            tenant.name,
            tenant.slug,
            str(tenant.admin) if tenant.admin else '—',
            tenant.num_users,
            'Yes' if tenant.is_verified else 'No',
            tenant.subscription_plan or '—',
            tenant.subscription_status or '—',
            str(tenant.created_by) if tenant.created_by else '—',
            tenant.created_at.strftime("%Y-%m-%d %H:%M") if tenant.created_at else '—'
        ])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="tenants_report_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'
    response.write(buffer.getvalue())
    buffer.close()

    return response

@login_required
@user_passes_test(lambda u: u.is_superuser or u.tenant.slug == 'track')
def users_list(request):
    users = CustomUser.objects.all()
    paginator = Paginator(users, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    count = users.count()
    return render(request, "tenants/users_list.html", {"users": page_obj, 'count': count})
    
@login_required
@user_passes_test(lambda u: u.is_superuser or u.tenant.slug == 'track')
def superuser_dashboard(request):
    # Annotate with distinct counts to avoid duplicates from joins
    tenants = Tenant.objects.annotate(
        user_count=Count('customuser', distinct=True),  # Use distinct to count unique users
        dept_count=Count('department', distinct=True),  # Use distinct for departments
        team_count=Count('team', distinct=True),       # Use distinct for teams
    ).all()

    # If annotations still produce incorrect counts, compute separately as a fallback
    tenant_data = []
    for tenant in tenants:
        tenant_data.append({
            'name': tenant.name,  # Adjust to your Tenant field (e.g., tenant.slug or str(tenant))
            'slug': tenant.slug,
            'user_count': CustomUser.objects.filter(tenant=tenant).count(),
            'dept_count': Department.objects.filter(tenant=tenant).count(),
            'team_count': Team.objects.filter(tenant=tenant).count(),
        })

    users = CustomUser.objects.all()
    tenants_app = TenantApplication.objects.all()
    depts = Department.objects.all()
    teams = Team.objects.all()
    roles = Role.objects.all()
    staff_prof = StaffProfile.objects.all()
    comp_prof = CompanyProfile.objects.all()
    events = Event.objects.all()
    contacts = Contact.objects.all()
    emails = Email.objects.all()

    # Prepare chart data using tenant_data for reliability
    tenant_names = [tenant['name'] for tenant in tenant_data]
    user_counts = [tenant['user_count'] for tenant in tenant_data]
    dept_counts = [tenant['dept_count'] for tenant in tenant_data]
    team_counts = [tenant['team_count'] for tenant in tenant_data]

    context = {
        'tenants': tenants,
        'users': users,
        'tenants_app': tenants_app,
        'depts': depts,
        'teams': teams,
        'roles': roles,
        'staff_prof': staff_prof,
        'comp_prof': comp_prof,
        'events': events,
        'contacts': contacts,
        'emails': emails,
        'tenant_names': tenant_names,
        'user_counts': user_counts,
        'dept_counts': dept_counts,
        'team_counts': team_counts,
    }
    return render(request, 'tenants/dashboard.html', context)

def get_user_data():
    # get all unexpired sessions
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_ids = []
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            user_ids.append(user_id)
    
    # Get all users tied to active sessions
    active_users = CustomUser.objects.filter(id__in=user_ids)
    
    # Count totals
    total_active_users = active_users.count()
    
    # Aggregate per tenant
    active_users_per_tenant = list(
        active_users.values('tenant__id', 'tenant__name')
        .annotate(active_user_count=Count('id'))
        .order_by('-active_user_count')[:20]
    )
    
    return {
        'total_active_users': total_active_users,
        'active_users_per_tenant': active_users_per_tenant,
    }
    
# Tracking
@login_required
@user_passes_test(lambda u: u.is_superuser or u.tenant.slug == 'track')
def tracking_dashboard(request):
    # Task metrics (from task_dashboard logic)
    total_tasks = Task.objects.count()
    tasks_per_tenant = list(
        Task.objects.values('tenant__id', 'tenant__name')
        .annotate(task_count=Count('id'))
        .order_by('-task_count')[:20]
    )
    top_task_tenant_ids = [item['tenant__id'] for item in tasks_per_tenant]
    task_general_status_counts = list(
        Task.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('status')
    )
    task_status_per_tenant = list(
        Task.objects.filter(tenant__id__in=top_task_tenant_ids)
        .values('tenant__id', 'tenant__name', 'status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Folder/File metrics (from folder_file_dashboard logic)
    total_folders = Folder.objects.count()
    folders_per_tenant = list(
        Folder.objects.values('tenant__id', 'tenant__name')
        .annotate(folder_count=Count('id'))
        .order_by('-folder_count')[:20]
    )
    total_shared_folders = Folder.objects.filter(is_shared=True).count()
    shared_folders_per_tenant = list(
        Folder.objects.filter(is_shared=True)
        .values('tenant__id', 'tenant__name')
        .annotate(shared_folder_count=Count('id'))
        .order_by('-shared_folder_count')[:20]
    )
    total_files = File.objects.count()
    files_per_tenant = list(
        File.objects.values('tenant__id', 'tenant__name')
        .annotate(file_count=Count('id'))
        .order_by('-file_count')[:20]
    )
    total_shared_files = File.objects.filter(is_shared=True).count()
    shared_files_per_tenant = list(
        File.objects.filter(is_shared=True)
        .values('tenant__id', 'tenant__name')
        .annotate(shared_file_count=Count('id'))
        .order_by('-shared_file_count')[:20]
    )
    general_folder_shared = [{'shared': 'Shared', 'count': total_shared_folders}, {'shared': 'Non-Shared', 'count': total_folders - total_shared_folders}]
    general_file_shared = [{'shared': 'Shared', 'count': total_shared_files}, {'shared': 'Non-Shared', 'count': total_files - total_shared_files}]

    # Vacancy/Application metrics (from vacancy_dashboard logic)
    total_vacancies = Vacancy.objects.count()
    vacancies_per_tenant = list(
        Vacancy.objects.values('tenant__id', 'tenant__name')
        .annotate(vacancy_count=Count('id'))
        .order_by('-vacancy_count')[:20]
    )
    total_shared_vacancies = Vacancy.objects.filter(is_shared=True).count()
    shared_vacancies_per_tenant = list(
        Vacancy.objects.filter(is_shared=True)
        .values('tenant__id', 'tenant__name')
        .annotate(shared_vacancy_count=Count('id'))
        .order_by('-shared_vacancy_count')[:20]
    )
    general_work_mode_counts = list(
        Vacancy.objects.values('work_mode')
        .annotate(count=Count('id'))
        .order_by('work_mode')
    )
    work_mode_per_tenant = list(
        Vacancy.objects.values('tenant__id', 'tenant__name', 'work_mode')
        .annotate(count=Count('id'))
        .order_by('tenant__id', 'work_mode')
    )
    general_status_counts = list(
        Vacancy.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('status')
    )
    status_per_tenant = list(
        Vacancy.objects.values('tenant__id', 'tenant__name', 'status')
        .annotate(count=Count('id'))
        .order_by('tenant__id', 'status')
    )
    total_applications = VacancyApplication.objects.count()
    applications_per_tenant = list(
        VacancyApplication.objects.values('tenant__id', 'tenant__name')
        .annotate(application_count=Count('id'))
        .order_by('-application_count')[:20]
    )
    accepted_count = VacancyApplication.objects.filter(status='accepted').count()
    rejected_count = VacancyApplication.objects.filter(status='rejected').count()
    pending_count = VacancyApplication.objects.filter(Q(status__isnull=True) | Q(status='')).count()
    general_app_status_counts = [
        {'status': 'accepted', 'count': accepted_count},
        {'status': 'rejected', 'count': rejected_count},
        {'status': 'pending', 'count': pending_count},
    ]
    accepted_per_tenant = list(VacancyApplication.objects.filter(status='accepted').values('tenant__id', 'tenant__name').annotate(count=Count('id')))
    for item in accepted_per_tenant:
        item['status'] = 'accepted'
    rejected_per_tenant = list(VacancyApplication.objects.filter(status='rejected').values('tenant__id', 'tenant__name').annotate(count=Count('id')))
    for item in rejected_per_tenant:
        item['status'] = 'rejected'
    pending_per_tenant = list(VacancyApplication.objects.filter(Q(status__isnull=True) | Q(status='')).values('tenant__id', 'tenant__name').annotate(count=Count('id')))
    for item in pending_per_tenant:
        item['status'] = 'pending'
    app_status_per_tenant = accepted_per_tenant + rejected_per_tenant + pending_per_tenant
    general_vacancy_shared = [{'shared': 'Shared', 'count': total_shared_vacancies}, {'shared': 'Non-Shared', 'count': total_vacancies - total_shared_vacancies}]
    # Top 20 vacancies by application count
    top_vacancies_by_applications = list(
        VacancyApplication.objects.values('vacancy__id', 'vacancy__title', 'tenant__name')
        .annotate(application_count=Count('id'))
        .order_by('-application_count')[:20]
    )

    # User stats
    user_context = get_user_data()

    context = {
        # Task keys
        'total_tasks': total_tasks,
        'tasks_per_tenant': tasks_per_tenant,
        'task_general_status_counts': task_general_status_counts,
        'task_status_per_tenant': task_status_per_tenant,
        # Folder/File keys
        'total_folders': total_folders,
        'folders_per_tenant': folders_per_tenant,
        'total_shared_folders': total_shared_folders,
        'shared_folders_per_tenant': shared_folders_per_tenant,
        'total_files': total_files,
        'files_per_tenant': files_per_tenant,
        'total_shared_files': total_shared_files,
        'shared_files_per_tenant': shared_files_per_tenant,
        'general_folder_shared': general_folder_shared,
        'general_file_shared': general_file_shared,
        # Vacancy/Application keys
        'total_vacancies': total_vacancies,
        'vacancies_per_tenant': vacancies_per_tenant,
        'total_shared_vacancies': total_shared_vacancies,
        'shared_vacancies_per_tenant': shared_vacancies_per_tenant,
        'general_work_mode_counts': general_work_mode_counts,
        'work_mode_per_tenant': work_mode_per_tenant,
        'general_status_counts': general_status_counts,  
        'status_per_tenant': status_per_tenant, 
        'total_applications': total_applications,
        'applications_per_tenant': applications_per_tenant,
        'general_app_status_counts': general_app_status_counts,
        'app_status_per_tenant': app_status_per_tenant,
        'general_vacancy_shared': general_vacancy_shared,
        'top_vacancies_by_applications': top_vacancies_by_applications,
        # User keys
        'total_active_users': user_context['total_active_users'],
        'active_users_per_tenant': user_context['active_users_per_tenant'],
    }

    return render(request, 'tracking/dashboard.html', context)

@login_required
def track_user(request):
    context = get_user_data()
    return render(request, 'tracking/loggedin_users_dashboard.html', context)

@login_required
def track_tasks(request):
    # Total number of tasks (general tasks)
    total_tasks = Task.objects.count()

    # Number of tasks per tenant
    tasks_per_tenant = list(Task.objects.values('tenant__id', 'tenant__name').annotate(task_count=Count('id')).order_by('tenant__id'))

    # General status counts (across all tasks)
    general_status_counts = list(Task.objects.values('status').annotate(count=Count('id')).order_by('status'))

    # Status counts per tenant
    status_per_tenant = list(Task.objects.values('tenant__id', 'tenant__name', 'status').annotate(count=Count('id')).order_by('tenant__id', 'status'))

    context = {
        'total_tasks': total_tasks,
        'tasks_per_tenant': tasks_per_tenant,
        'task_general_status_counts': general_status_counts,
        'task_status_per_tenant': status_per_tenant,
    }

    return render(request, 'tracking/tasks_dashboard.html', context)

@login_required
def track_folder_file(request):
    # Folder metrics
    total_folders = Folder.objects.count()
    # Top 20 tenants by folder count
    folders_per_tenant = list(
        Folder.objects.values('tenant__id', 'tenant__name')  # Adjust 'tenant__name' if your Tenant model has a different field for name/display
            .annotate(folder_count=Count('id'))
            .order_by('-folder_count')[:20]
    )
    top_folder_tenant_ids = [item['tenant__id'] for item in folders_per_tenant]

    total_shared_folders = Folder.objects.filter(is_shared=True).count()
    # Shared folders per tenant, filtered to top 20 by shared count
    shared_folders_per_tenant = list(
        Folder.objects.filter(is_shared=True)
            .values('tenant__id', 'tenant__name')
            .annotate(shared_folder_count=Count('id'))
            .order_by('-shared_folder_count')[:20]
    )

    # File metrics
    total_files = File.objects.count()
    # Top 20 tenants by file count
    files_per_tenant = list(
        File.objects.values('tenant__id', 'tenant__name')  # Adjust 'tenant__name' as needed
            .annotate(file_count=Count('id'))
            .order_by('-file_count')[:20]
    )
    top_file_tenant_ids = [item['tenant__id'] for item in files_per_tenant]

    total_shared_files = File.objects.filter(is_shared=True).count()
    # Shared files per tenant, filtered to top 20 by shared count
    shared_files_per_tenant = list(
        File.objects.filter(is_shared=True)
            .values('tenant__id', 'tenant__name')
            .annotate(shared_file_count=Count('id'))
            .order_by('-shared_file_count')[:20]
    )

    # For general shared vs non-shared (for pie charts)
    general_folder_shared = [{'shared': 'Shared', 'count': total_shared_folders}, {'shared': 'Non-Shared', 'count': total_folders - total_shared_folders}]
    general_file_shared = [{'shared': 'Shared', 'count': total_shared_files}, {'shared': 'Non-Shared', 'count': total_files - total_shared_files}]

    context = {
        'total_folders': total_folders,
        'folders_per_tenant': folders_per_tenant,
        'total_shared_folders': total_shared_folders,
        'shared_folders_per_tenant': shared_folders_per_tenant,
        'total_files': total_files,
        'files_per_tenant': files_per_tenant,
        'total_shared_files': total_shared_files,
        'shared_files_per_tenant': shared_files_per_tenant,
        'general_folder_shared': general_folder_shared,
        'general_file_shared': general_file_shared,
    }

    return render(request, 'tracking/folder_file_dashboard.html', context)

@login_required
def track_vacancy(request):
    # Vacancy metrics
    total_vacancies = Vacancy.objects.count()
    # Top 20 tenants by vacancy count
    vacancies_per_tenant = list(
        Vacancy.objects.values('tenant__id', 'tenant__name')
            .annotate(vacancy_count=Count('id'))
            .order_by('-vacancy_count')[:20]
    )
    top_vacancy_tenant_ids = [item['tenant__id'] for item in vacancies_per_tenant]

    total_shared_vacancies = Vacancy.objects.filter(is_shared=True).count()
    # Top 20 tenants by shared vacancy count
    shared_vacancies_per_tenant = list(
        Vacancy.objects.filter(is_shared=True)
            .values('tenant__id', 'tenant__name')
            .annotate(shared_vacancy_count=Count('id'))
            .order_by('-shared_vacancy_count')[:20]
    )

    # Work mode counts (general)
    general_work_mode_counts = list(
        Vacancy.objects.values('work_mode')
            .annotate(count=Count('id'))
            .order_by('work_mode')
    )

    # Work mode counts per tenant (all tenants, will slice in JS to top 20 if needed)
    work_mode_per_tenant = list(
        Vacancy.objects.values('tenant__id', 'tenant__name', 'work_mode')
            .annotate(count=Count('id'))
            .order_by('tenant__id', 'work_mode')
    )

    # Status counts (general)
    general_status_counts = list(
        Vacancy.objects.values('status')
            .annotate(count=Count('id'))
            .order_by('status')
    )

    # Status counts per tenant (all tenants, will slice in JS)
    status_per_tenant = list(
        Vacancy.objects.values('tenant__id', 'tenant__name', 'status')
            .annotate(count=Count('id'))
            .order_by('tenant__id', 'status')
    )

    # VacancyApplication metrics
    total_applications = VacancyApplication.objects.count()

    # Top 20 tenants by application count
    applications_per_tenant = list(
        VacancyApplication.objects.values('tenant__id', 'tenant__name')
            .annotate(application_count=Count('id'))
            .order_by('-application_count')[:20]
    )

    accepted_count = VacancyApplication.objects.filter(status='accepted').count()
    rejected_count = VacancyApplication.objects.filter(status='rejected').count()
    pending_count = VacancyApplication.objects.filter(Q(status__isnull=True) | Q(status='')).count()
    general_app_status_counts = [
        {'status': 'accepted', 'count': accepted_count},
        {'status': 'rejected', 'count': rejected_count},
        {'status': 'pending', 'count': pending_count},
    ]

    accepted_per_tenant = list(
        VacancyApplication.objects.filter(status='accepted')
            .values('tenant__id', 'tenant__name')
            .annotate(count=Count('id'))
    )
    for item in accepted_per_tenant:
        item['status'] = 'accepted'

    rejected_per_tenant = list(
        VacancyApplication.objects.filter(status='rejected')
            .values('tenant__id', 'tenant__name')
            .annotate(count=Count('id'))
    )
    for item in rejected_per_tenant:
        item['status'] = 'rejected'

    pending_per_tenant = list(
        VacancyApplication.objects.filter(Q(status__isnull=True) | Q(status=''))
            .values('tenant__id', 'tenant__name')
            .annotate(count=Count('id'))
    )
    for item in pending_per_tenant:
        item['status'] = 'pending'

    app_status_per_tenant = accepted_per_tenant + rejected_per_tenant + pending_per_tenant

    general_vacancy_shared = [{'shared': 'Shared', 'count': total_shared_vacancies}, {'shared': 'Non-Shared', 'count': total_vacancies - total_shared_vacancies}]

    top_vacancies_by_applications = list(
        VacancyApplication.objects.values('vacancy__id', 'vacancy__title', 'tenant__name')
        .annotate(application_count=Count('id'))
        .order_by('-application_count')[:20]
    )

    context = {
        'total_vacancies': total_vacancies,
        'vacancies_per_tenant': vacancies_per_tenant,
        'total_shared_vacancies': total_shared_vacancies,
        'shared_vacancies_per_tenant': shared_vacancies_per_tenant,
        'general_work_mode_counts': general_work_mode_counts,
        'work_mode_per_tenant': work_mode_per_tenant,
        'general_status_counts': general_status_counts,
        'status_per_tenant': status_per_tenant,
        'total_applications': total_applications,
        'applications_per_tenant': applications_per_tenant,
        'general_app_status_counts': general_app_status_counts,
        'app_status_per_tenant': app_status_per_tenant,
        'general_vacancy_shared': general_vacancy_shared,
        'top_vacancies_by_applications': top_vacancies_by_applications,
    }

    return render(request, 'tracking/vacancy_dashboard.html', context)


@login_required
def company_group_dashboard(request):
    if request.user.is_superuser:
        return redirect('company_group_dashboard_admin')
    # if request.tenant.slug != 'group':
    #     return render(request, '403.html', {"message": "Access denied. Only government oversight users can access this page."}, status=403)
    
    groups = CompanyGroup.objects.filter(owner=request.user)
    
    total_groups = groups.count()
    # total_members = sum(group.members.count() for group in groups)
    unique_member_ids = set()
    all_members = []
    
    for group in groups.prefetch_related('members'):
        member_ids = group.members.all().values_list('id', flat=True)
        unique_member_ids.update(member_ids)
        # If you need the actual member objects for other purposes
        all_members.extend(group.members.all())
    
    total_members = len(unique_member_ids)    

    # Active Users
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_ids = []
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            user_ids.append(user_id)
    
    # Get all users tied to active sessions
    active_users = CustomUser.objects.filter(id__in=user_ids, tenant__in=all_members)
    
    active_tenant_ids = active_users.values_list('tenant_id', flat=True).distinct()
    
    # Get groups that have any of these active tenants as members
    active_groups = groups.filter(members__id__in=active_tenant_ids).distinct()
    
    # Count groups with active users (not counting multiple times if multiple users in same group)
    total_active_groups = active_groups.count()
    
    # Calculate active users per tenant (for the detailed breakdown)
    active_users_per_tenant = list(
        active_users.values('tenant__id', 'tenant__name')
        .annotate(active_user_count=Count('id'))
        .order_by('-active_user_count')[:20]
    )
    context = {
        'groups': groups,
        'total_groups': total_groups,
        'total_members': total_members,
        'recent_groups': groups.order_by('-created_at')[:5],
        'page_title': 'Company Groups Dashboard',
        'total_active_groups': total_active_groups,
        'active_users_per_tenant': active_users_per_tenant,
    }
    
    return render(request, 'company_groups/group_dashboard.html', context)



@login_required
@user_passes_test(lambda u: u.is_superuser)
def get_company_group_member(request, group_id, tenant_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    try:
        tenant = company_group.members.get(id=tenant_id)
    except Tenant.DoesNotExist:
        return JsonResponse({"error": "Member not found"}, status=404)
    
    return JsonResponse({
        "success": True,
        "data": {
            "tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "is_active": tenant.is_active
            },
            "group": {
                "id": company_group.id,
                "name": company_group.name
            },
            "is_member": True
        }
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_company_group_admin(request):    
    if request.method == 'POST':
        form = CompanyGroupAdminForm(request.POST)
        if form.is_valid():
            comp_group = form.save(commit=False)

            try:
                group_tenant = Tenant.objects.get(slug='group')
            except Tenant.DoesNotExist:
                group_tenant = Tenant.objects.create(
                    name='Government Oversight',
                    slug='group',
                    is_active=True,
                )
                messages.info(request, "Created 'group' tenant automatically.")
            
            comp_group.tenant = group_tenant
            comp_group.created_by = request.user
            
            comp_group.save()
            
            form.save_m2m()
            
            messages.success(request, f"Successfully created group: {form.cleaned_data['name']}")


            return redirect('company_group_detail', group_id=comp_group.pk)

    else:
        form = CompanyGroupAdminForm()
    
    return render(request, 'company_groups/create_comp_grp.html', {
        'form': form,
        'title': 'Create Company Group (Admin)'
    })



@login_required
def create_company_group(request):
    if request.method == 'POST':
        form = CompanyGroupForm(request.POST)
        if form.is_valid():
            try:
                comp_group = form.save(commit=False)
                # Get the group tenant (Tenant, not CompanyGroup!)
                grp_tenant = Tenant.objects.get(slug='group')  # FIXED THIS LINE
                comp_group.tenant = grp_tenant
                comp_group.created_by = request.user
                comp_group.owner = request.user
                comp_group.save()
                messages.success(request, f"Successfully created {comp_group.name}")
                return redirect('tenant_application_with_group', group_id=comp_group.pk)
            except Tenant.DoesNotExist:
                messages.error(request, "Group tenant not found. Please contact administrator.")
            except Exception as e:
                messages.error(request, f"Error creating company group: {str(e)}")
    else:
        form = CompanyGroupForm()
    
    return render(request, 'company_groups/create_comp_grp_by_user.html', {
        'form': form,
    })


@login_required
def edit_company_group(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    if request.user.is_superuser:
        return redirect('edit_company_group_admin', group_id=group_id)

    if request.method == 'POST':
        # Check if this is a member removal request
        if 'remove_member' in request.POST:
            member_id = request.POST.get('remove_member')
            try:
                member = Tenant.objects.get(id=member_id)
                # Check if user has permission to remove this member
                if member.created_by != request.user and not request.user.is_superuser:
                    messages.error(request, "You don't have permission to remove this company.")
                    return redirect('edit_company_group', group_id=group_id)
                
                company_group.members.remove(member)
                messages.success(request, f"Removed {member.name} from the group.")
                return redirect('company_group_detail', group_id=group_id)
            except Tenant.DoesNotExist:
                messages.error(request, "Member not found.")
        
        elif 'update_group' in request.POST:
            form = CompanyGroupForm(request.POST, instance=company_group)
            if form.is_valid():
                form.save()
                messages.success(request, "Group information updated successfully.")
                return redirect('company_group_detail', group_id=group_id)
        
        elif 'add_members' in request.POST:
            member_ids = request.POST.getlist('add_members')
            added_count = 0
            
            for member_id in member_ids:
                try:
                    member = Tenant.objects.get(id=member_id)
                    if member.created_by != request.user:
                        messages.error(request, f"You don't have permission to add {member.name} (not your company).")
                        continue
                    
                    if member not in company_group.members.all():
                        company_group.members.add(member)
                        added_count += 1
                    else:
                        messages.warning(request, f"{member.name} is already in the group.")
                        
                except Tenant.DoesNotExist:
                    messages.error(request, f"Company with ID {member_id} not found.")
            
            if added_count > 0:
                messages.success(request, f"Added {added_count} member(s) to the group.")
            elif member_ids:
                messages.warning(request, "No new members were added.")
            
            return redirect('edit_company_group', group_id=group_id)
    
    form = CompanyGroupForm(instance=company_group)
    
    current_members = company_group.members.all()
    
    user_tenants = Tenant.objects.filter(created_by=request.user).exclude(id__in=current_members).order_by('name')
    
    context = {
        'form': form,
        'company_group': company_group,
        'current_members': current_members,
        'available_tenants': user_tenants,
        'title': f'Edit {company_group.name}'
    }
    
    return render(request, 'company_groups/edit_comp_grp_by_user.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_company_group_admin(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    if request.method == 'POST':
        if 'remove_member' in request.POST:
            member_id = request.POST.get('remove_member')
            try:
                member = Tenant.objects.get(id=member_id)
                company_group.members.remove(member)
                messages.success(request, f"Removed {member.name} from the group.")
                return redirect('edit_company_group_admin', group_id=group_id)
            except Tenant.DoesNotExist:
                messages.error(request, "Member not found.")
        
        elif 'update_group' in request.POST:
            form = CompanyGroupAdminForm(request.POST, instance=company_group)
            if form.is_valid():
                instance = form.save(commit=False)
                instance.save()
                form.save_m2m()
                messages.success(request, f"Successfully updated {company_group.name}")
                return redirect('edit_company_group_admin', group_id=group_id)
        
        elif 'add_members' in request.POST:
            selected_member_ids = request.POST.getlist('add_members_selection')
            
            if not selected_member_ids:
                selected_member_ids = request.POST.getlist('add_members_selection[]')
            
            if selected_member_ids:
                selected_members = Tenant.objects.filter(id__in=selected_member_ids)
                
                company_group.members.add(*selected_members)
                
                messages.success(request, f"Added {selected_members.count()} member(s) to {company_group.name}")
            else:
                messages.warning(request, "No members selected to add.")
            
            return redirect('edit_company_group_admin', group_id=group_id)
    
    form = CompanyGroupAdminForm(instance=company_group)
    
    all_tenants = Tenant.objects.all().order_by('name')
    
    current_members = company_group.members.all()
    available_count = all_tenants.count() - current_members.count()

    context = {
        'form': form,
        'company_group': company_group,
        'available_count': available_count,
        'all_tenants': all_tenants,
        'current_members': current_members,
        'title': f'Edit {company_group.name}'
    }
    
    return render(request, 'company_groups/edit_comp_grp.html', context)
@login_required
def add_company_group_member(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)

    if request.method == 'POST':
        form = TenantApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.status = 'approved'
            application.username = form.cleaned_data["email"]
            application.save()
            
            try:
                # tenant_admin = CustomUser.objects.get(username=application.username)
                tenant = Tenant.objects.create(
                    name=application.organization_name,
                    slug=application.slug
                )
                tenant.save()
                user = CustomUser.objects.create_user(
                        username=application.username,
                        email=application.email,
                        password=application.password,
                        tenant=tenant
                )
                user.save()
                logger.info(f"Created tenant: {tenant.slug}")
                admin_role, _ = Role.objects.get_or_create(name='Admin')
                logger.info(f"Tenant application created: {application.organization_name} by {application.username}")
                user.roles.add(admin_role)
                user.set_password = application.password
                user.is_active = True
                user.save()
                tenant.admin = user
                tenant.created_by = request.user
                tenant.save()
                application.status = 'approved'
                application.save()
                company_group.members.add(tenant)
                logger.debug(f"Assigned Admin role to user {tenant.admin.username} for tenant {tenant.slug}")
            except Exception as e:
                logger.error(f"Error creating tenant for application {application.organization_name}: {str(e)}")
                return HttpResponseForbidden(f"Error creating tenant: {str(e)}")
        else:
            logger.error(f"Tenant application form validation failed: {form.errors}")
            messages.error(request, "Application submission failed. Please correct the errors below.")
    else:
        form = TenantApplicationForm()
    return render(request, 'tenants/apply_for_tenant.html', {'form': form})
                

@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_company_group_member(request, group_id, tenant_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    try:
        tenant = company_group.members.get(id=tenant_id)
    except Tenant.DoesNotExist:
        messages.error(request, "Member not found.")
        return redirect('company_group_detail', group_id=group_id)
    
    if request.method == 'POST':
        form = EditCompanyGroupMemberForm(request.POST, company_group=company_group, tenant=tenant)
        if form.is_valid():
            
            messages.success(request, f"Updated member {tenant.name} in {company_group.name}")
            return redirect('company_group_detail', group_id=group_id)
    else:
        form = EditCompanyGroupMemberForm(company_group=company_group, tenant=tenant)
    
    return render(request, 'company_groups/edit_member.html', {
        'form': form,
        'company_group': company_group,
        'tenant': tenant,
        'title': f'Edit {tenant.name} in {company_group.name}'
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def remove_company_group_member(request, group_id, tenant_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    try:
        tenant = company_group.members.get(id=tenant_id)
    except Tenant.DoesNotExist:
        messages.error(request, "Member not found.")
        return redirect('company_group_detail', group_id=group_id)
    
    if request.method == 'POST':
        form = RemoveCompanyGroupMemberForm(request.POST, company_group=company_group, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f"Removed {tenant.name} from {company_group.name}")
            return redirect('company_group_detail', group_id=group_id)
    else:
        form = RemoveCompanyGroupMemberForm(company_group=company_group, tenant=tenant)
    
    return render(request, 'company_groups/remove_member.html', {
        'form': form,
        'company_group': company_group,
        'tenant': tenant,
        'title': f'Remove {tenant.name} from {company_group.name}'
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def bulk_add_company_group_members(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    if request.method == 'POST':
        form = BulkAddCompanyGroupMemberForm(request.POST, company_group=company_group)
        if form.is_valid():
            added_count = form.save()
            messages.success(request, f"Successfully added {added_count} members to {company_group.name}")
            return redirect('company_group_detail', group_id=group_id)
    else:
        form = BulkAddCompanyGroupMemberForm(company_group=company_group)
    
    return render(request, 'company_groups/bulk_add_members.html', {
        'form': form,
        'company_group': company_group,
        'title': f'Bulk Add Members to {company_group.name}'
    })

@login_required
def company_group_detail(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    if company_group.owner != request.user and not request.user.is_superuser:
        messages.error(request, "You don't own this group.")
        return redirect('company_group_dashboard')
    
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_ids = []
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            user_ids.append(user_id)
    
    # Get all users tied to active sessions
    active_users = CustomUser.objects.filter(id__in=user_ids)
    
    # Count totals
    total_active_users = active_users.count()
    
    # Aggregate per tenant
    active_users_per_tenant = list(
        active_users.values('tenant__id', 'tenant__name')
        .annotate(active_user_count=Count('id'))
        .order_by('-active_user_count')[:20]
    )
            
    # Get all members
    members = company_group.members.all().order_by('name')
    
    # Get search form if needed
    from .forms import MemberSearchForm
    search_form = MemberSearchForm(request.GET)
    if search_form.is_valid():
        members = search_form.filter_queryset(members)
    
    return render(request, 'company_groups/group_detail.html', {
        'company_group': company_group,
        'members': members,
        'search_form': search_form,
        'title': company_group.name,
        'total_active_users': total_active_users,
        'active_users_per_tenant': active_users_per_tenant,
    })


@login_required
def company_group_detail_by_user(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)

    if company_group.owner != request.user and not request.user.is_superuser:
        messages.error(request, "You don't own this group.")
        return redirect('company_group_dashboard')    
    
    members = company_group.members.all().order_by('name')
    
    from .forms import MemberSearchForm
    search_form = MemberSearchForm(request.GET)
    if search_form.is_valid():
        members = search_form.filter_queryset(members)
    
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_ids = []
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            user_ids.append(user_id)
    
    active_users = CustomUser.objects.filter(id__in=user_ids)
    
    total_active_users = active_users.count()
    
    active_users_per_tenant = list(
        active_users.values('tenant__id', 'tenant__name')
        .annotate(active_user_count=Count('id'))
        .order_by('-active_user_count')[:20]
    )
    
    return render(request, 'company_groups/group_detail.html', {
        'company_group': company_group,
        'members': members,
        'search_form': search_form,
        'title': company_group.name,
        'active_users_per_tenant':active_users_per_tenant,
        'total_active_users':total_active_users,
    })



@login_required
def company_group_list(request):
    if request.user.is_superuser:
        groups = CompanyGroup.objects.all()
        message = "Showing all company groups"
    else:
        groups = CompanyGroup.objects.filter(owner=request.user)
        message = "Showing your company groups"
    
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    
    if search:
        groups = groups.filter(
            Q(name__icontains=search) | 
            Q(slug__icontains=search)
        )
        message += f" matching '{search}'"
    
    if status == 'active':
        groups = groups.filter(is_active=True)
        message += " (active only)"
    elif status == 'inactive':
        groups = groups.filter(is_active=False)
        message += " (inactive only)"
    
    groups = groups.order_by('name')
    
    total_groups = groups.count()
    # total_members = sum(g.members.count() for g in groups)

    unique_member_ids = set()
    all_members = []
    
    for group in groups.prefetch_related('members'):
        member_ids = group.members.all().values_list('id', flat=True)
        unique_member_ids.update(member_ids)
        # If you need the actual member objects for other purposes
        all_members.extend(group.members.all())
    
    total_members = len(unique_member_ids)    

    # Active Users
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_ids = []
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            user_ids.append(user_id)
    
    # Get all users tied to active sessions
    active_users = CustomUser.objects.filter(id__in=user_ids, tenant__in=all_members)
    
    # Count totals
    active_tenant_ids = active_users.values_list('tenant_id', flat=True).distinct()
    
    # Get groups that have any of these active tenants as members
    active_groups = groups.filter(members__id__in=active_tenant_ids).distinct()
    
    # Count groups with active users (not counting multiple times if multiple users in same group)
    total_active_groups = active_groups.count()
    
    # Calculate active users per tenant (for the detailed breakdown)
    active_users_per_tenant = list(
        active_users.values('tenant__id', 'tenant__name')
        .annotate(active_user_count=Count('id'))
        .order_by('-active_user_count')[:20]
    )
    
    context = {
        'groups': groups,
        'title': 'My Company Groups',
        'total_groups': total_groups,
        'total_members': total_members,
        'message': message,
        'is_superuser': request.user.is_superuser,
        'search_term': search,
        'status_filter': status,
        'total_active_groups': total_active_groups,
        'active_users_per_tenant': active_users_per_tenant,
    }
    
    return render(request, 'company_groups/group_list.html', context)

@login_required
def tenant_application_with_group(request, group_id):
    company_group = get_object_or_404(CompanyGroup, id=group_id)
    
    if company_group.owner != request.user:
        messages.error(request, "You don't own this group.")
        return redirect('company_group_detail', group_id=group_id)
    
    if request.method == 'POST':  
        from tenants.forms import GroupOwnerTenantCreationForm
        form = GroupOwnerTenantCreationForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    tenant = Tenant.objects.create(
                        name=form.cleaned_data['organization_name'],
                        slug=form.cleaned_data['slug'],
                        created_by=request.user,
                    )
                    
                    email = form.cleaned_data['email']
                    username = email.split('@')[0]
                    
                    base_username = username
                    counter = 1
                    while CustomUser.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                    
                    admin_user = CustomUser.objects.create_user(
                        username=username,
                        email=email,
                        password=form.cleaned_data['password'],
                        tenant=tenant,
                        is_active=True
                    )
                    
                    tenant.admin = admin_user
                    tenant.save()
                    
                    company_group.members.add(tenant)
                    
                    try:
                        from tenants.models import TenantApplication
                        TenantApplication.objects.create(
                            username=username,
                            email=email,
                            password=form.cleaned_data['password'],  
                            organization_name=form.cleaned_data['organization_name'],
                            slug=form.cleaned_data['slug'],
                            status='approved',  
                            created_by=request.user,
                        )
                    except Exception as e:
                        logger.warning(f"Could not create TenantApplication record: {str(e)}")
                    
                    logger.info(f"Group owner {request.user.username} created tenant {tenant.slug}")
                    
                    messages.success(request, 
                        f"✅ Successfully created '{tenant.name}' and added to your group '{company_group.name}'!"
                    ) 
                    return redirect('company_group_detail', group_id=group_id)
                    
            except IntegrityError as e:
                messages.error(request, "A company with this name or slug already exists.")
                logger.error(f"IntegrityError creating tenant: {str(e)}")
            except Exception as e:
                logger.error(f"Error creating tenant for group {company_group.id}: {str(e)}")
                messages.error(request, f"Error creating company: {str(e)}")
        else:
            # Form has errors
            messages.error(request, "Please correct the errors below.")
    
    else:
        from tenants.forms import GroupOwnerTenantCreationForm
        form = GroupOwnerTenantCreationForm()
    
    return render(request, 'company_groups/add_member_by_user.html', {
        'form': form,
        'company_group': company_group,
        'title': f'Create New Company for {company_group.name}'
    })

@login_required
@user_passes_test(lambda u: u.is_superuser)
def company_group_dashboard_admin(request):
    if not request.user.is_superuser:
        return render(request, '403.html', {"message": "Access denied. Only super admins have access here"}, status=403)
    
    if request.user.is_superuser:
        groups = CompanyGroup.objects.all()
        active_groups = groups.filter(is_active=True)
        inactive_groups = groups.filter(is_active=False)
    
    total_groups = groups.count()
    total_active_groups_2 = active_groups.count()
    total_inactive_groups = inactive_groups.count()

    # all_members = []
    # for group in groups:
    #     all_members.extend(group.members.all())
    # total_members = len(set(all_members))  # Unique members
    
    unique_member_ids = set()
    all_members = []
    
    for group in groups.prefetch_related('members'):
        member_ids = group.members.all().values_list('id', flat=True)
        unique_member_ids.update(member_ids)
        # If you need the actual member objects for other purposes
        all_members.extend(group.members.all())
    
    total_members = len(unique_member_ids)
    
    avg_per_group = total_members / total_groups if total_groups > 0 else 0
    
    recent_groups = groups.order_by('-created_at')[:5]

    this_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    groups_this_month = groups.filter(created_at__gte=this_month).count()

    # Active Users
    sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_ids = []
    for session in sessions:
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')
        if user_id:
            user_ids.append(user_id)
    
    # Get all users tied to active sessions
    active_users = CustomUser.objects.filter(id__in=user_ids, tenant__in=all_members)
    
    active_tenant_ids = active_users.values_list('tenant_id', flat=True).distinct()
    
    # Get groups that have any of these active tenants as members
    active_groups = groups.filter(members__id__in=active_tenant_ids).distinct()
    
    # Count groups with active users (not counting multiple times if multiple users in same group)
    total_active_groups = active_groups.count()
    
    # Calculate active users per tenant (for the detailed breakdown)
    active_users_per_tenant = list(
        active_users.values('tenant__id', 'tenant__name')
        .annotate(active_user_count=Count('id'))
        .order_by('-active_user_count')[:20]
    )
    
    context = {
        'groups': groups,
        'total_groups': total_groups,
        'total_active_groups_2': total_active_groups_2,
        'total_inactive_groups': total_inactive_groups,
        'total_members': total_members,
        'avg_per_group': round(avg_per_group, 1),
        'recent_groups': recent_groups,
        'groups_this_month': groups_this_month,
        'page_title': 'Company Groups Dashboard',
        'is_superuser': request.user.is_superuser,
        'total_active_groups': total_active_groups,
        'active_users_per_tenant': active_users_per_tenant,
    }
    
    return render(request, 'company_groups/group_dashboard_admin.html', context)



def quick_services(request):
    """
    Display external service links for the current tenant
    Accessible without login
    """
    from django.urls import reverse
    
    tenant = getattr(request, 'tenant', None)
    
    if not tenant:
        # If no tenant, show message or redirect
        return render(request, 'tenants/quick_services.html', {
            'services': [],
            'built_in_services': [],
            'no_tenant': True
        })
    
    # Get custom external services for this tenant
    custom_services = tenant.external_services.filter(is_active=True).order_by('display_order', 'name')
    
    # Build list of built-in external services
    built_in_services = []
    
    # Row 1: Primary Services
    # 1. External Memo Submission
    built_in_services.append({
        'name': 'Submit Memo',
        'description': 'Submit a memo or request to the organization without logging in',
        'url': reverse('memo:external_submit', kwargs={'slug': tenant.slug}),
        'icon': 'fa-envelope',
        'icon_color': '#319795',
        'open_in_new_tab': False,
    })
    
    # 2. Submit Support Ticket
    built_in_services.append({
        'name': 'Submit Support Ticket',
        'description': 'Create a support ticket and track its status',
        'url': reverse('ticket_submit_public'),
        'icon': 'fa-ticket-alt',
        'icon_color': '#e53e3e',
        'open_in_new_tab': False,
    })
    
    # 3. Check Ticket Status
    built_in_services.append({
        'name': 'Check Ticket Status',
        'description': 'Look up your ticket status using ticket number and contact info',
        'url': reverse('ticket_status_lookup'),
        'icon': 'fa-search',
        'icon_color': '#dd6b20',
        'open_in_new_tab': False,
    })
    
    # Row 2: Additional Services
    # 4. Book Appointment - Always show, let the booking page handle if no services available
    built_in_services.append({
        'name': 'Book Appointment',
        'description': 'Schedule an appointment or booking with the organization',
        'url': reverse('public_org_calendar', kwargs={'tenant_slug': tenant.slug}),
        'icon': 'fa-calendar-check',
        'icon_color': '#4299e1',
        'open_in_new_tab': False,
    })
    
    # 5. Send File - Always show, create general upload endpoint
    built_in_services.append({
        'name': 'Send File',
        'description': 'Upload and send documents or files to the organization',
        'url': reverse('public_file_upload', kwargs={'tenant_slug': tenant.slug}),
        'icon': 'fa-cloud-upload-alt',
        'icon_color': '#38b2ac',
        'open_in_new_tab': False,
    })
    
    # 6. Visitor Check-in
    built_in_services.append({
        'name': 'Visitor Check-in',
        'description': 'Register as a visitor and check-in to the organization',
        'url': reverse('checkin:visitor_checkin'),
        'icon': 'fa-user-check',
        'icon_color': '#667eea',
        'open_in_new_tab': False,
    })
    
    # 7. View Company Profile - Always show
    built_in_services.append({
        'name': 'View Company Profile',
        'description': 'View the organization\'s public profile and information',
        'url': reverse('view_company_profile'),
        'icon': 'fa-building',
        'icon_color': '#805ad5',
        'open_in_new_tab': False,
    })
    
    # 8. Send Invoice
    built_in_services.append({
        'name': 'Send Invoice',
        'description': 'Submit an invoice to the organization for processing',
        'url': reverse('invoice_submit_external', kwargs={'tenant_slug': tenant.slug}),
        'icon': 'fa-file-invoice-dollar',
        'icon_color': '#f6ad55',
        'open_in_new_tab': False,
    })
    
    # Row 3: Additional Services
    # 9. Job Board / Vacancies
    built_in_services.append({
        'name': 'View Job Openings',
        'description': 'Browse and apply for available job positions',
        'url': reverse('job_board'),
        'icon': 'fa-briefcase',
        'icon_color': '#48bb78',
        'open_in_new_tab': False,
    })
    
    # 10. Conference Board
    built_in_services.append({
        'name': 'View Events & Conferences',
        'description': 'Browse and register for upcoming events and conferences',
        'url': reverse('conference_board'),
        'icon': 'fa-users',
        'icon_color': '#ed8936',
        'open_in_new_tab': False,
    })
    
    # 11. Contact Support
    built_in_services.append({
        'name': 'Contact Support',
        'description': 'Get in touch with our support team',
        'url': reverse('contact_support'),
        'icon': 'fa-headset',
        'icon_color': '#9f7aea',
        'open_in_new_tab': False,
    })
    
    # Combine custom and built-in services
    all_services = list(custom_services) + built_in_services
    
    return render(request, 'tenants/quick_services.html', {
        'services': custom_services,
        'built_in_services': built_in_services,
        'all_services': all_services,
        'tenant': tenant,
        'no_tenant': False
    })
