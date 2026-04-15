# Authentication
# Custom Login, Login Redirects, Forgot password, and more

from raadaa import settings
from raadaa.tasks import create_default_folders_user
from documents.models import CustomUser, StaffProfile, Conference, Vacancy, UserProfile, Role, CompanyProfile
from django.utils import timezone
from documents.forms import ForgotPasswordForm, SignUpForm, CustomLoginForm
from django.contrib.auth import logout, get_user_model, update_session_auth_hash
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.views import LoginView
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode, url_has_allowed_host_and_scheme
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from .send_mails import send_reg_confirm, send_password_reset_email, send_user_account_pending_approval, send_admin_account_pending_approval, personal_user_reg_confirm, admin_reg_confirm
from .mail_connection import get_email_smtp_connection
from django.contrib.auth.forms import SetPasswordForm
from types import SimpleNamespace
from django.templatetags.static import static
from django.contrib import messages
from tenants.forms import TenantApplicationForm
from tenants.models import TenantApplication, Tenant
from raadaa.tasks import create_default_folders_org, create_default_folders_user
import logging

logger = logging.getLogger(__name__)


User = get_user_model()

# User account registration
def register(request):
    if settings.DEBUG:
        base_register_url = "http://localhost:8000/register/"
        tenant_register_url = "http://localhost:8000/tenants/apply-tenant/"
    else:
        base_register_url = "https://teammanager.ng/register/"
        tenant_register_url = "https://teammanager.ng/tenants/apply-tenant/"
    if request.tenant is not None and request.tenant.slug != "group":
        messages.error(request, "You do not have permission to signup on this Organization.")
        return render(request, 'tenant_reg_error.html', {
            'error_code': '403',
            'message': f"You do not have permission to signup on this Organization: {request.tenant.name}",
            'user_register': base_register_url,
            'tenant_register': tenant_register_url,
            'tenant_name': request.tenant.name,
        })
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.username = form.cleaned_data["email"]
            user.set_password(form.cleaned_data["password"])
            phone_number = form.cleaned_data["phone_number"]
            if not request.tenant:
                # return HttpResponseForbidden("No company associated with this request.")
                user.is_personal = True
                user.is_active = True
                user.save()
                personal_user_reg_confirm(request, user)
                userprofile = UserProfile.objects.create(user=user, first_name=user.first_name, last_name=user.last_name, email=user.email, phone_number=phone_number)
                userprofile.save()
            else:
                # user.tenant = request.tenant
                # user.is_active = False
                # user.save()
                # admin_user = CustomUser.objects.filter(
                #     tenant=request.tenant, roles__name="Admin"
                # ).first()
                # notify_user_admin(request, user, admin_user)
                messages.error(request, "You do not have permission to signup on this Organization.")
                return render(request, 'tenant_reg_error.html', {
                    'error_code': '403',
                    'message': f"You do not have permission to signup on this Organization: {request.tenant.name}",
                    'user_register': base_register_url,
                    'tenant_register': tenant_register_url,
                    'tenant_name': request.tenant.name,
                })
            
            # Create default folders
            create_default_folders_user.delay(user.id)
            
            return redirect("account_activation_sent", user_id=user.id)
    else:
        form = SignUpForm()
    return render(request, "registration/register.html", {"form": form})

def notify_user_admin(request, user, admin_user):
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    send_user_account_pending_approval(request, user, admin_user, superuser)

    approval_url = reverse('edit_user', args=[user.id])
    send_admin_account_pending_approval(request, user, admin_user, superuser, approval_url)
    return redirect("account_activation_sent", user_id=user.id)

# account activation 
def account_activation_sent(request, user_id=None):
    if user_id is not None:
        user = CustomUser.objects.get(id=user_id)
        if request.tenant:
            tenant = request.tenant
        else:
            tenant = None
            login_url = reverse('login')
    else:
        user = None
        tenant = None
        login_url = reverse('login')
    return render(request, "registration/account_activation_sent.html", {'tenant': tenant, 'user': user, 'login_url': login_url})


class CustomLoginView(LoginView):
    form_class = CustomLoginForm
    template_name = 'registration/login.html'  # Make sure to use your template

    def form_valid(self, form):
        # The rest of your existing logic remains the same
        response = super().form_valid(form)
        user = self.request.user

        # 🔑 GET NEXT SAFELY
        next_url = self.request.POST.get('next') or self.request.GET.get('next')

        if user.is_superuser:
            # return response
            return redirect(next_url or settings.LOGIN_REDIRECT_URL or '/')
        
        if user.is_staff and not user.tenant:
            # return response
            return redirect(next_url or settings.LOGIN_REDIRECT_URL or '/')

        if user.is_personal:
            # return response
            return redirect(next_url or settings.LOGIN_REDIRECT_URL or '/')
        
        expected_subdomain = (
            user.tenant.slug
            if hasattr(user, 'tenant') and user.tenant
            else None
        )
        if expected_subdomain is None:
            return HttpResponseForbidden("You are not associated with this company. Please ensure your subdomain is correct or contact contact@teammanager.ng")
        
        base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
        protocol = "http" if settings.DEBUG else "https"
        
        # # 🔑 GET NEXT SAFELY
        # next_url = self.request.POST.get('next') or self.request.GET.get('next')

        tenant_redirect = f"{protocol}://{expected_subdomain}.{base_domain}{next_url}"

        return redirect(tenant_redirect)

    def get(self, request, *args, **kwargs):
        # Your existing get method logic remains the same
        if request.user.is_authenticated:
            if request.user.is_superuser:
                return redirect(settings.LOGIN_REDIRECT_URL or '/')
            if request.user.is_staff and not request.user.tenant:
                return redirect(settings.LOGIN_REDIRECT_URL or '/')
            expected_subdomain = (
                request.user.tenant.slug
                if hasattr(request.user, 'tenant') and request.user.tenant
                else None
            )
            if expected_subdomain is None:
                return HttpResponseForbidden("You are not associated with this company. Please ensure your subdomain is correct or contact contact@teammanager.ng")
            base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
            protocol = "http" if settings.DEBUG else "https"
            return redirect(f"{protocol}://{expected_subdomain}.{base_domain}/")
        return super().get(request, *args, **kwargs)


# Fetch Tenant URL for redirecting users
def get_tenant_url(request):
    if hasattr(request, 'user') and request.user.is_authenticated:
        if not CustomUser.objects.filter(id=request.user.id, tenant=request.tenant).exists():
            print(f"User {request.user.username} not associated with tenant {request.tenant.slug if request.tenant else 'None'}")
            expected_subdomain = (
                request.user.tenant.slug
                if hasattr(request.user, 'tenant') and request.user.tenant
                else None
            )
            if expected_subdomain is None:
                logout(request)
                raise PermissionDenied("You have no associated tenant. Contact support. contact@teammanager.ng")
            print(f"Wrong user tenant slug: {expected_subdomain}")
            base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
            protocol = "http" if settings.DEBUG else "https"
            home_url = f"{protocol}://{expected_subdomain}.{base_domain}/"
            print(f"Redirecting to tenant home: {home_url}")
            return home_url
    
# Forgot password view
def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            # form.save(commit=False)
            email = form.cleaned_data['email']
            user = CustomUser.objects.get(email=email)
            # Generate token and UID
            token = default_token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            # Build reset URL
            reset_url = request.build_absolute_uri(
                reverse('reset_password', kwargs={'uidb64': uidb64, 'token': token})
            )
            superuser = CustomUser.objects.get(is_superuser=True)
            send_password_reset_email(user, reset_url, superuser)
            return redirect('password_reset_sent')  # Or a 'email sent' page if you want to add one
    else:
        form = ForgotPasswordForm()
    return render(request, 'registration/forgot_password.html', {'form': form})


def reset_password(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # Check if user exists and token is valid
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                # Update session auth hash if user is logged in
                update_session_auth_hash(request, form.user)
                return redirect('password_reset_success')
        else:
            form = SetPasswordForm(user)
        
        context = {
            'form': form,
            'validlink': True
        }
        return render(request, 'registration/reset_password.html', context)
    else:
        # Invalid link
        context = {
            'form': None,
            'validlink': False,
            'error': 'Invalid or expired password reset link. Please request a new one.'
        }
        return render(request, 'registration/reset_password.html', context)

def password_reset_success(request):
    return render(request, 'registration/password_reset_success.html')


# Password reset sent view
def password_reset_sent(request):
    return render(request, 'registration/password_reset_sent.html')

# Post login redirect
def post_login_redirect(request):
    if not request.user.is_authenticated or request.user.is_superuser:
        return redirect('tenant_home')
    return redirect('home')

# Home page
def home(request):
    tenant = getattr(request, "tenant", None)

    # Default tenant home
    
    # Carousels (conferences and vacancies) only for unauthenticated users
    conferences = []
    vacancies = []
    
    if not request.user.is_authenticated:
        # Show upcoming conferences and active vacancies for this tenant in carousels.
        now = timezone.now()
        
        conferences = Conference.objects.filter(end_date__gte=now, is_posted=True).order_by('start_date')[:8]
        vacancies = Vacancy.objects.filter(status='active', is_shared=True).order_by('-created_at')[:8]

        # Debug output
        print(f"Conferences count: {conferences.count() if hasattr(conferences, 'count') else len(conferences)}")
        print(f"Vacancies count: {vacancies.count() if hasattr(vacancies, 'count') else len(vacancies)}")

        # No tenant → marketing / landing page
        if tenant is None:
            return render(request, "home.html", {'tenant': tenant, 'conferences': conferences, 'vacancies': vacancies})

        # Tenant-specific routing
        if tenant.slug == "group":
            return redirect('company_group_dashboard')

    return render(request, "home.html", {'tenant': tenant, 'conferences': conferences, 'vacancies': vacancies})


# Unified signup view for both individual and company accounts
def unified_signup(request):
    """
    Unified signup page with tabs for individual and company registration
    """
    if settings.DEBUG:
        base_register_url = "http://localhost:8000/signup/"
        tenant_register_url = "http://localhost:8000/tenants/apply-tenant/"
    else:
        base_register_url = "https://teammanager.ng/signup/"
        tenant_register_url = "https://teammanager.ng/tenants/apply-tenant/"
    
    # Check if user is on a tenant subdomain (not allowed for signup)
    if hasattr(request, 'tenant') and request.tenant is not None and request.tenant.slug != "group":
        messages.error(request, "You do not have permission to signup on this Organization.")
        return render(request, 'tenant_reg_error.html', {
            'error_code': '403',
            'message': f"You do not have permission to signup on this Organization: {request.tenant.name}",
            'user_register': base_register_url,
            'tenant_register': tenant_register_url,
            'tenant_name': request.tenant.name,
        })
    
    user_form = SignUpForm()
    tenant_form = TenantApplicationForm()
    
    if request.method == "POST":
        form_type = request.POST.get('form_type')
        
        if form_type == 'individual':
            # Handle individual user signup
            user_form = SignUpForm(request.POST)
            if user_form.is_valid():
                user = user_form.save(commit=False)
                user.email = user_form.cleaned_data["email"]
                user.username = user_form.cleaned_data["email"]
                user.set_password(user_form.cleaned_data["password"])
                phone_number = user_form.cleaned_data["phone_number"]
                
                user.is_personal = True
                user.is_active = True
                user.save()
                
                # Send confirmation email
                personal_user_reg_confirm(request, user)
                
                # Create user profile
                userprofile = UserProfile.objects.create(
                    user=user, 
                    first_name=user.first_name, 
                    last_name=user.last_name, 
                    email=user.email, 
                    phone_number=phone_number
                )
                userprofile.save()
                
                # Create default folders
                create_default_folders_user.delay(user.id)
                
                return redirect("account_activation_sent", user_id=user.id)
        
        elif form_type == 'company':
            # Handle company/tenant application
            tenant_form = TenantApplicationForm(request.POST)
            if tenant_form.is_valid():
                application = tenant_form.save(commit=False)
                application.status = 'approved'
                application.username = tenant_form.cleaned_data["email"]
                application.save()
                first_name = tenant_form.cleaned_data["first_name"]
                last_name = tenant_form.cleaned_data["last_name"]
                email = tenant_form.cleaned_data["email"]
                org_name = tenant_form.cleaned_data["organization_name"]
                phone_number = tenant_form.cleaned_data["phone_number"]
                password = tenant_form.cleaned_data["password"]
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
                    user = CustomUser.objects.create(
                        first_name=first_name,
                        last_name=last_name,
                        username=email,
                        email=email,
                        password=password,
                        phone_number=phone_number,
                        tenant=tenant
                    )
                    user.save()
                    profile, created = StaffProfile.objects.get_or_create(tenant=user.tenant, user=user)
                    profile.first_name = user.first_name
                    profile.last_name = user.last_name
                    profile.email = user.email
                    profile.save()
                    logger.info(f"Created tenant: {tenant.slug}")
                    admin_role, _ = Role.objects.get_or_create(name='Admin')
                    roles = Role.objects.all()
                    logger.info(f"Tenant application created: {application.organization_name} by {application.username}")
                    user.roles.add(admin_role)
                    for role in roles:
                        user.roles.add(role)
                    user.set_password(password)
                    user.is_active = True
                    user.save()
                    tenant.admin = user
                    tenant.save()
                    application.status = 'approved'
                    application.save()
                    # logger.debug(f"Assigned Admin role to user {tenant.admin.username} for tenant {tenant.slug}")
                    print(f"Assigned Admin role to user {tenant.admin.username} for tenant {tenant.slug}")
                    # Login redirect
                    base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
                    protocol = "http" if settings.DEBUG else "https"
                    login_url = f"{protocol}://{application.slug}.{base_domain}/accounts/login"
                    # return redirect('login')
                    admin_reg_confirm(user)
                    # Folder Creation
                    create_default_folders_user.delay(user.id)
                    create_default_folders_org.delay(tenant.id)
                
                    # Redirect to application status page
                    return redirect('application_status', identifier=application.id)
                except Exception as e:
                    logger.error(f"Error creating tenant for application {application.organization_name}: {str(e)}")
                    return HttpResponseForbidden(f"Error creating tenant: {str(e)}")
        
    
    context = {
        'user_form': user_form,
        'tenant_form': tenant_form,
    }
    
    return render(request, "registration/unified_signup.html", context)
