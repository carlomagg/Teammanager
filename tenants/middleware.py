# import logging
# from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError
# from django.conf import settings
# from django.urls import reverse
# from urllib.parse import urlparse, urlunparse
# from django.shortcuts import redirect, render
# from django.contrib.auth import authenticate, login, logout
# from django.core.exceptions import PermissionDenied
# from documents.models import CustomUser
# from tenants.models import Tenant

# # Configure logging
# logger = logging.getLogger(__name__)

# class TenantMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         # Initialize tenant as None
#         request.tenant = None

#         # For GoogleOAUTH
#         if request.path_info.startswith('/oauth2callback'):
#             # Google OAuth callback — MUST bypass ALL tenant checks and redirects
#             print("GOOGLE OAUTH CALLBACK — bypassing tenant middleware")
#             return self.get_response(request)
        
#         # Early return for superusers to bypass tenant logic
#         if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_superuser:
#             print("Superuser detected, bypassing tenant assignment")
#             return self.get_response(request)
        
#         if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff and not request.user.tenant:
#             print("Staff user detected, bypassing tenant assignment")
#             return self.get_response(request)
        
#         # Extract host and remove port if present
#         host = request.get_host().split(':')[0]
#         print(f"Raw host: {request.get_host()}, Processed host: {host}, REMOTE_ADDR: {request.META.get('REMOTE_ADDR')}")

#         # Check if the request is for the main domain (no subdomain)
#         main_domain = settings.MAIN_DOMAIN.split(':')[0]  # e.g., 'teammanager.ng'
#         main_domain_parts = main_domain.split('.')  # e.g., ['teammanager', 'ng']
#         domain_parts = host.split('.')  # e.g., ['teammanager', 'ng'] or ['sub', 'teammanager', 'ng']

#         # NEW: Check if host matches main domain exactly or is localhost
#         if host == main_domain or host == 'localhost':
#             print("Request to main domain or localhost, no tenant required")
#             request.tenant = None
#             # Proceed to association check for authenticated users
#         else:
#             # Extract subdomain only if host has more parts than main domain
#             if len(domain_parts) > len(main_domain_parts):
#                 subdomain = domain_parts[0]  # e.g., 'sub' from 'sub.teammanager.ng'
#                 print(f"Extracted subdomain: {subdomain}")
#             else:
#                 print(f"Invalid host format or no subdomain: {host}")
#                 return HttpResponseNotFound("Invalid host format or no subdomain")

#             # Try to find tenant by subdomain
#             try:
#                 tenant = Tenant.objects.get(slug=subdomain)
#                 print(f"Found tenant: {tenant.slug}")
#                 request.tenant = tenant
#             except Tenant.DoesNotExist:
#                 print(f"Tenant with subdomain '{subdomain}' not found.")
#                 if settings.DEBUG:
#                     tenant = Tenant.objects.first()
#                     if tenant:
#                         print(f"Falling back to default tenant: {tenant.slug}")
#                         request.tenant = tenant
#                     else:
#                         print("No tenants found in the database.")
#                         return HttpResponseNotFound("No tenants found in the database.")
#                 else:
#                     return HttpResponseNotFound(f"Tenant with subdomain '{subdomain}' not found.")
#             except Exception as e:
#                 print(f"Unexpected error in tenant lookup: {e}")
#                 return HttpResponseServerError("An unexpected server error occurred.")

#         # Restrict access for authenticated non-superusers
#         if hasattr(request, 'user') and request.user.is_authenticated:
#             if not CustomUser.objects.filter(id=request.user.id, tenant=request.tenant).exists():
#                 print(f"User {request.user.username} not associated with tenant {request.tenant.slug if request.tenant else 'None'}")
#                 expected_subdomain = (
#                     request.user.tenant.slug
#                     if hasattr(request.user, 'tenant') and request.user.tenant
#                     else None
#                 )
#                 if expected_subdomain is None:
#                     logout(request)
#                     raise PermissionDenied("You have no associated tenant. Contact support. contact@teammanager.ng")
#                 print(f"Wrong user tenant slug: {expected_subdomain}")
#                 base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
#                 protocol = "http" if settings.DEBUG else "https"
#                 home_url = f"{protocol}://{expected_subdomain}.{base_domain}/"
#                 print(f"Redirecting to tenant home: {home_url}")
#                 return redirect(home_url)
#         print(f"Set request.tenant to: {request.tenant.slug if request.tenant else 'None'}")
#         return self.get_response(request)


import logging
from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.db import models
from documents.models import CustomUser
from documents.viewfuncs.rba_decorators import is_admin
from tenants.models import Tenant, Subscription
from django.contrib import messages
from django.utils import timezone



logger = logging.getLogger(__name__)

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Initialize tenant as None
        request.tenant = None

        # Bypass OAuth callback entirely
        if request.path_info.startswith('/oauth2callback'):
            print("GOOGLE OAUTH CALLBACK — bypassing tenant middleware")
            return self.get_response(request)
        
        if request.path_info.startswith('/conference/participant/access/'):
            print("Conference access link — bypass tenant check, allow on main domain")
            # We still set tenant=None explicitly so queries remain safe
            request.tenant = None
            # Proceed without any redirect or tenant enforcement
            return self.get_response(request)
        
        if request.path_info.startswith('/guest/dashboard/'):
            print("Conference access link — bypass tenant check, allow on main domain")
            # We still set tenant=None explicitly so queries remain safe
            request.tenant = None
            # Proceed without any redirect or tenant enforcement
            return self.get_response(request)

        # Extract host early (remove port)
        host = request.get_host().split(':')[0]
        main_domain = settings.MAIN_DOMAIN.split(':')[0]
        is_main_domain = host == main_domain or host == 'localhost'

        # === BYPASS RULES (superusers and global staff) ===
        if request.user.is_authenticated:
            if request.user.is_superuser:
                print("Superuser detected — full bypass")
                return self.get_response(request)

            if request.user.is_staff and request.user.tenant is None and not getattr(request.user, 'is_personal', False):
                print("Global staff (no tenant) detected — bypass tenant checks")
                return self.get_response(request)

        # === TENANT RESOLUTION (subdomain → tenant) ===
        if not is_main_domain:
            domain_parts = host.split('.')
            main_parts = main_domain.split('.')
            if len(domain_parts) > len(main_parts):
                subdomain = domain_parts[0]
                print(f"Extracted subdomain: {subdomain}")
                try:
                    tenant = Tenant.objects.get(slug=subdomain)
                    request.tenant = tenant
                    print(f"Tenant resolved: {tenant.slug}")
                except Tenant.DoesNotExist:
                    if settings.DEBUG:
                        tenant = Tenant.objects.first()
                        if tenant:
                            request.tenant = tenant
                            print(f"DEBUG fallback tenant: {tenant.slug}")
                        else:
                            return HttpResponseNotFound("No tenants in DB (debug mode)")
                    else:
                        return HttpResponseNotFound(f"Tenant '{subdomain}' not found")
                except Exception as e:
                    logger.error(f"Tenant lookup error: {e}")
                    return HttpResponseServerError("Server error")
            else:
                return HttpResponseNotFound("Invalid subdomain format")

        # === AUTHENTICATED USER ACCESS ENFORCEMENT ===
        if request.user.is_authenticated:
            user = request.user
            protocol = "https" if not settings.DEBUG else "http"
            base = "localhost:8000" if settings.DEBUG else "teammanager.ng"

            # Personal users (tenant=None, is_personal=True)
            if getattr(user, 'is_personal', False):
                if not is_main_domain:
                    # Personal users NOT allowed on subdomains → redirect to main domain, preserving full path + query (?next=...)
                    print(f"Personal user {user} attempted subdomain access — redirect to main")
                    main_url = f"{protocol}://{main_domain}{request.get_full_path()}"
                    return redirect(main_url)
                # On main domain → allowed, tenant remains None
                print("Personal user on main domain — access granted")
                return self.get_response(request)

            # Company users (have tenant)
            if user.tenant:
                expected_slug = user.tenant.slug
                if request.tenant is None:
                    # Company user on main domain → redirect to their subdomain, preserving full path + query (?next=...)
                    print(f"Company user {user} on main domain — redirect to {expected_slug}")
                    redirect_url = f"{protocol}://{expected_slug}.{base}{request.get_full_path()}"
                    return redirect(redirect_url)
                else:
                    # On subdomain → check match
                    if request.tenant == user.tenant:
                        print(f"Company user {user} correctly on {request.tenant.slug}")
                        return self.get_response(request)
                    else:
                        # Wrong subdomain → redirect to correct one, preserving full path + query (?next=...)
                        print(f"Company user {user} on wrong subdomain — redirect to {expected_slug}")
                        redirect_url = f"{protocol}://{expected_slug}.{base}{request.get_full_path()}"
                        return redirect(redirect_url)

            # Fallback: authenticated but no tenant and not personal → invalid state
            if not getattr(user, 'is_personal', False):
                print(f"User {user} has no tenant and not personal — denying access")
                raise PermissionDenied("Invalid account configuration. Contact support: contact@teammanager.ng")

        # Anonymous users or any other case → proceed (views will handle auth requirements)
        print(f"Final request.tenant: {getattr(request.tenant, 'slug', 'None')}")
        return self.get_response(request)


class EffectiveContextMiddleware:
    """
    Must be placed **after** TenantMiddleware in MIDDLEWARE list.

    Responsibilities:
    - Determine effective_tenant and effective_user (who/what are we acting as)
    - Support staff impersonation via ?tenant_id= & ?user_id=
    - Provide request.is_impersonating flag
    - Keep personal accounts (tenant=None) cleanly separated
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Defaults — important for anonymous & early failure cases
        request.effective_tenant = None
        request.effective_user   = request.user if request.user.is_authenticated else None
        request.is_impersonating = False

        if not request.user.is_authenticated:
            return self.get_response(request)

        # ── 1. Start from what TenantMiddleware already decided ───────────────
        tenant_from_subdomain = getattr(request, 'tenant', None)

        # ── 2. Effective tenant resolution ───────────────────────────────────
        if request.user.is_superuser:
            # Superusers can reach anywhere — most permissive
            request.effective_tenant = self._resolve_tenant_for_superuser(request, tenant_from_subdomain)

        elif request.user.is_staff:
            # Staff can switch tenants via query param (and fallback to own)
            request.effective_tenant = self._resolve_tenant_for_staff(request, tenant_from_subdomain)

        else:
            # Normal users — strict: must match what TenantMiddleware set
            # Personal users → None
            # Company users → must be on correct subdomain
            request.effective_tenant = tenant_from_subdomain

        # ── 3. Effective user resolution (impersonation) ─────────────────────
        if request.user.is_staff or request.user.is_superuser:
            request.effective_user = self._resolve_user_for_privileged(request)
        else:
            request.effective_user = request.user

        # ── 4. Impersonation flag ────────────────────────────────────────────
        own_tenant = getattr(request.user, 'tenant', None)

        request.is_impersonating = (
            request.effective_user != request.user
            or request.effective_tenant != own_tenant
        )

        # Optional: log impersonation / unusual access
        if request.is_impersonating:
            logger.info(
                "Impersonation context: actor=%s | as_user=%s | tenant=%s | path=%s",
                request.user.username,
                request.effective_user.username if request.effective_user else None,
                request.effective_tenant.slug if request.effective_tenant else "(personal)",
                request.path,
            )

        return self.get_response(request)

    # -------------------------------------------------------------------------
    #   Helpers
    # -------------------------------------------------------------------------

    def _resolve_tenant_for_superuser(self, request, tenant_from_subdomain):
        """Superusers can override via ?tenant_id= or stay on current subdomain"""
        tenant_id = request.GET.get('tenant_id') or request.POST.get('tenant_id')
        if tenant_id:
            try:
                return Tenant.objects.get(pk=tenant_id)
            except Tenant.DoesNotExist:
                logger.warning("Superuser requested invalid tenant_id=%s", tenant_id)
                # fall through → use subdomain or None
        return tenant_from_subdomain

    def _resolve_tenant_for_staff(self, request, tenant_from_subdomain):
        """
        Staff can switch tenant via ?tenant_id=, but only to tenants they have
        permission to access (customize this part according to your rules).
        """
        tenant_id = request.GET.get('tenant_id') or request.POST.get('tenant_id')
        if not tenant_id:
            return tenant_from_subdomain or getattr(request.user, 'tenant', None)

        try:
            target_tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise PermissionDenied("Requested tenant does not exist")

        # Optional — implement your own access policy here
        # Example: if not request.user.can_manage_tenant(target_tenant):
        #     raise PermissionDenied("You are not authorized to manage this company")

        return target_tenant

    def _resolve_user_for_privileged(self, request):
        """Staff / superuser can impersonate another user via ?user_id="""
        user_id = request.GET.get('user_id') or request.POST.get('user_id')
        if not user_id:
            return request.user

        try:
            target_user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            raise PermissionDenied("Requested user does not exist")

        # Safety rules — customize according to your policy
        if target_user.is_staff or target_user.is_superuser:
            raise PermissionDenied("Cannot impersonate staff / superuser accounts")

        # Optional: enforce tenant boundary
        if target_user.tenant and target_user.tenant != request.effective_tenant:
            raise PermissionDenied(
                "Cannot impersonate user from a different tenant "
                f"({target_user.tenant} ≠ {request.effective_tenant})"
            )

        # Personal users are allowed (tenant=None)
        return target_user
    
class ForcePasswordResetMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.must_reset_password
            and request.path not in [
                reverse("change_password"),
                reverse("logout")
            ]
        ):
            return redirect("change_password")
        return self.get_response(request)
    
class TenantNoIndexMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if hasattr(request, "tenant"):
            response["X-Robots-Tag"] = "noindex, nofollow"

        return response


# class SubscriptionCheckMiddleware:
#     """
#     Middleware to check if users have proper subscription status
#     """
    
#     def __init__(self, get_response):
#         self.get_response = get_response
#         # Paths that don't require subscription check
#         self.public_paths = [
#             # Admin and authentication
#             '/admin/',
#             '/accounts/login/',
#             '/logout/',
#             '/register/',
#             '/post-login/',
#             '/forgot-password/',
#             '/reset-password/',
#             '/password-reset-success/',
#             '/password-reset-sent/',
            
#             # Subscription related (they need access to subscribe)
#             '/subscriptions/',
#             '/subscriptions/plans/',
#             '/subscriptions/create/',
#             '/payment/',
#             '/validate-promo/',
            
#             # Payment webhooks and callbacks
#             '/webhook/paystack/',
#             '/paystack/callback/',
            
#             # Static and media
#             '/static/',
#             '/media/',
#             '/ckeditor/',
            
#             # Public pages
#             '/',
#             '/getting-started/',
#             '/policies/',
#             '/job-board/',
#             '/conference-board/',
#             '/conference-board/filters',
#             '/vacancy/post/',
#             '/conference/post/',
            
#             # Public booking pages
#             '/bookings/book/',
#             '/api/bookings/public-create/',
            
#             # SEO
#             '/sitemap.xml',
#             '/robots.txt',
#             '/.well-known/',
            
#             # Guest access
#             '/guest/dashboard/',
#             '/share/',
            
#             # API endpoints that might be public
#             '/api/',
#         ]
        
#         # Path prefixes that should be accessible to trial users
#         self.trial_allowed_paths = [
#             '/dashboard/',
#             '/calendar/',
#             '/tasks/',
#             '/folders/',
#             '/documents/',
#             '/staff/',
#             '/notifications/',
#             '/my-profile/',
#             '/company-profile/',
#             '/contacts/',
#             '/emails/',
#             '/hr/',
#             '/vacancy/',
#             '/interview/',
#             '/tracking/',
#             '/crm/',
#             '/wallet/',
#             '/conference/',
#             '/admins',
#             '/admin',
#         ]
    
#     def __call__(self, request):
#         # Skip for non-authenticated users
#         if not request.user.is_authenticated:
#             return self.get_response(request)
        
#         # Skip for superusers and staff
#         if request.user.is_superuser or request.user.is_staff:
#             return self.get_response(request)
        
#         path = request.path
        
#         # Check if path is public (no subscription needed)
#         if self._is_public_path(path):
#             return self.get_response(request)
        
#         # # Check subscription status for tenant users
#         # if request.user.tenant and not request.user.is_superuser:
#         #     return self._handle_tenant_user(request)
        
#         # # Check subscription status for personal users
#         # elif hasattr(request.user, 'is_personal') and request.user.is_personal:
#         #     return self._handle_personal_user(request)

#         has_access, redirect_url = self._check_subscription_access(request, request.user)
#         if has_access:
#             return self.get_response(request)
#         else:
#             # Allow access to subscription-related pages even when inactive
#             if path.startswith('/subscriptions/') or path.startswith('/payment/'):
#                 return self.get_response(request)
#             return redirect(redirect_url)

    
#     def _is_public_path(self, path):
#         """Check if path is public and doesn't require subscription"""
#         for public_path in self.public_paths:
#             if path.startswith(public_path):
#                 return True
#         return False
    
#     def _is_trial_allowed_path(self, path):
#         """Check if path is accessible during trial"""
#         for trial_path in self.trial_allowed_paths:
#             if path.startswith(trial_path):
#                 return True
#         return False

# def _check_subscription_access(self, request, user):
#     """Generic subscription check for both tenant and personal users"""
    
#     # Active subscription - full access
#     if user.subscription_status == 'active':
#         # Check if subscription is about to expire (warn if < 7 days)
#         if user.subscription_end_date:
#             days_left = (user.subscription_end_date - timezone.now().date()).days
#             if 0 <= days_left <= 7:
#                 messages.info(
#                     request,
#                     f"Your subscription expires in {days_left} days. Please renew to continue access."
#                 )
#         return True, None
    
#     # Trial subscription - full access with warnings
#     elif user.subscription_status == 'trial':
#         if user.subscription_end_date:
#             days_left = (user.subscription_end_date - timezone.now().date()).days
#             if days_left <= 3:
#                 messages.warning(
#                     request,
#                     f"Your trial ends in {days_left} days. Subscribe now to avoid interruption."
#                 )
#             elif days_left <= 0:
#                 # Trial expired, update status
#                 user.subscription_status = 'inactive'
#                 user.save(update_fields=['subscription_status'])
#                 messages.error(request, "Your trial has expired. Please subscribe to continue.")
#                 return False, 'subscription_base'
#         return True, None
    
#     # Inactive - no access
#     else:
#         return False, 'subscription_base'



# class SubscriptionCheckMiddleware:
#     """
#     Middleware to check if users have proper subscription status
#     Uses user.subscription_status and user.subscription_end_date directly
#     """
    
#     def __init__(self, get_response):
#         self.get_response = get_response
#         # Paths that don't require subscription check
#         self.public_paths = [
#             # Admin and authentication
#             '/admin/',
#             '/accounts/login/',
#             '/logout/',
#             '/register/',
#             '/post-login/',
#             '/forgot-password/',
#             '/reset-password/',
#             '/password-reset-success/',
#             '/password-reset-sent/',
            
#             # Subscription related (they need access to subscribe)
#             '/subscriptions/',
#             '/subscriptions/plans/',
#             '/subscriptions/create/',
#             '/payment/',
#             '/validate-promo/',
            
#             # Payment webhooks and callbacks
#             '/webhook/paystack/',
#             '/paystack/callback/',
            
#             # Static and media
#             '/static/',
#             '/media/',
#             '/ckeditor/',
            
#             # Public pages
#             '/',
#             '/getting-started/',
#             '/policies/',
#             '/job-board/',
#             '/conference-board/',
#             '/conference-board/filters',
#             '/vacancy/post/',
#             '/conference/post/',
            
#             # Public booking pages
#             '/bookings/book/',
#             '/api/bookings/public-create/',
            
#             # SEO
#             '/sitemap.xml',
#             '/robots.txt',
#             '/.well-known/',
            
#             # Guest access
#             '/guest/dashboard/',
#             '/share/',
            
#             # API endpoints that might be public
#             '/api/',
#         ]
        
#         # Track which users we've shown warnings to in this session
#         self.warning_shown_key = 'trial_warning_shown'
    
#     # def __call__(self, request):
#     #     # Skip for non-authenticated users
#     #     if not request.user.is_authenticated:
#     #         return self.get_response(request)
        
#     #     # Skip for superusers and staff
#     #     if request.user.is_superuser or request.user.is_staff:
#     #         return self.get_response(request)
        
#     #     path = request.path
        
#     #     # Check if path is public (no subscription needed)
#     #     if self._is_public_path(path):
#     #         return self.get_response(request)
        
#     #     # Check subscription access using User fields
#     #     has_access, redirect_url, days_left, message = self._check_subscription_access(request.user)
        
#     #     if has_access:
#     #         # Show trial warnings if needed
#     #         if days_left is not None and 0 < days_left <= 7:
#     #             self._maybe_show_trial_warning(request, days_left, message)
#     #         return self.get_response(request)
#     #     else:
#     #         # No access - redirect to subscription page
#     #         if not path.startswith('/subscriptions/') and not path.startswith('/payment/'):
#     #             messages.error(request, message or "Your subscription is inactive. Please subscribe to continue.")
#     #             return redirect(redirect_url or 'subscription_base')
#     #         return self.get_response(request)
    
#     # def _is_public_path(self, path):
#     #     """Check if path is public and doesn't require subscription"""
#     #     for public_path in self.public_paths:
#     #         if path.startswith(public_path):
#     #             return True
#     #     return False
    
#     # def _check_subscription_access(self, user):
#     #     """
#     #     Check subscription access using User model fields
#     #     Returns: (has_access, redirect_url, days_left, message)
#     #     """
#     #     today = timezone.now().date()
        
#     #     # Active subscription
#     #     if user.subscription_status == 'active':
#     #         if user.subscription_end_date:
#     #             days_left = (user.subscription_end_date - today).days
#     #             if days_left <= 0:
#     #                 # Subscription expired - update user status
#     #                 user.subscription_status = 'inactive'
#     #                 user.save(update_fields=['subscription_status'])
#     #                 return False, 'subscription_base', 0, "Your subscription has expired."
#     #             elif days_left <= 7:
#     #                 message = self._get_expiry_message(days_left, 'subscription')
#     #                 return True, None, days_left, message
#     #         return True, None, None, None
        
#     #     # Trial subscription
#     #     elif user.subscription_status == 'trial':
#     #         if user.subscription_end_date:
#     #             days_left = (user.subscription_end_date - today).days
#     #             if days_left <= 0:
#     #                 # Trial expired - update user status
#     #                 user.subscription_status = 'inactive'
#     #                 user.save(update_fields=['subscription_status'])
#     #                 return False, 'subscription_base', 0, "Your trial has expired. Please subscribe to continue."
#     #             elif days_left <= 7:
#     #                 message = self._get_expiry_message(days_left, 'trial')
#     #                 return True, None, days_left, message
#     #             return True, None, days_left, None
#     #         return True, None, None, None
        
#     #     # Inactive
#     #     else:
#     #         return False, 'subscription_base', 0, "Your account is inactive. Please subscribe to continue."
    
#     # def _get_expiry_message(self, days_left, subscription_type):
#     #     """Get appropriate warning message based on days left"""
#     #     if days_left <= 0:
#     #         return f"Your {subscription_type} has expired."
#     #     elif days_left == 1:
#     #         return f"Your {subscription_type} ends TOMORROW! Subscribe now to avoid interruption."
#     #     elif days_left <= 3:
#     #         return f"Your {subscription_type} ends in {days_left} days. Subscribe now to continue access."
#     #     elif days_left <= 7:
#     #         return f"Your {subscription_type} ends in {days_left} days. Don't forget to subscribe!"
#     #     return None
    
#     # def _maybe_show_trial_warning(self, request, days_left, message):
#     #     """Show warning but not on every request"""
#     #     if not message:
#     #         message = self._get_expiry_message(days_left, 'trial')
        
#     #     if not message:
#     #         return
        
#     #     # Check if we've shown warning in this session recently
#     #     last_shown = request.session.get(self.warning_shown_key)
#     #     now = timezone.now().timestamp()
        
#     #     # Show warning if not shown in last hour
#     #     if not last_shown or (now - last_shown) > 3600:
#     #         if days_left <= 3:
#     #             messages.warning(request, message)
#     #         else:
#     #             messages.info(request, message)
#     #         request.session[self.warning_shown_key] = now
#     def __call__(self, request):
#         # Skip for non-authenticated users
#         if not request.user.is_authenticated:
#             return self.get_response(request)
        
#         # Skip for superusers and staff
#         if request.user.is_superuser:
#             return self.get_response(request)
        
#         path = request.path
        
#         # Check if path is public
#         if self._is_public_path(path):
#             return self.get_response(request)
        
#         # FIRST: Check if user has a free/exempt subscription
#         if self._has_free_access(request.user):
#             # Free users have full access with no warnings
#             return self.get_response(request)
        
#         # THEN: Check regular subscription access
#         has_access, redirect_url, days_left, message = self._check_subscription_access(request.user)
        
#         if has_access:
#             # Show trial warnings if needed
#             if days_left is not None and 0 < days_left <= 7:
#                 self._maybe_show_trial_warning(request, days_left, message)
#             return self.get_response(request)
#         else:
#             # No access - redirect to subscription page
#             if not path.startswith('/subscriptions/') and not path.startswith('/payment/'):
#                 messages.error(request, message or "Your subscription is inactive. Please subscribe to continue.")
#                 return redirect(redirect_url or 'subscription_base')
#             return self.get_response(request)
    
#     def _has_free_access(self, user):
#         """Check if user has free/exempt access"""
        
#         # Check for active free subscription
#         if user.tenant and not user.is_personal:
#             # Tenant user - check tenant subscriptions
#             free_sub = Subscription.objects.filter(
#                 tenant=user.tenant,
#                 is_free=True,
#                 status='active'
#             ).first()
            
#             if free_sub:
#                 # Check if free access has expired
#                 if free_sub.free_expires_at and free_sub.free_expires_at < timezone.now().date():
#                     # Free access expired - update subscription
#                     free_sub.status = 'expired'
#                     free_sub.save()
#                     return False
                
#                 logger.info(f"User {user.email} has free tenant access: {free_sub.free_reason}")
#                 return True
        
#         elif user.is_personal:
#             # Personal user - check personal subscriptions
#             free_sub = Subscription.objects.filter(
#                 user=user,
#                 is_free=True,
#                 status='active'
#             ).first()
            
#             if free_sub:
#                 # Check if free access has expired
#                 if free_sub.free_expires_at and free_sub.free_expires_at < timezone.now().date():
#                     # Free access expired - update subscription
#                     free_sub.status = 'expired'
#                     free_sub.save()
#                     return False
                
#                 logger.info(f"User {user.email} has free personal access: {free_sub.free_reason}")
#                 return True
        
#         return False
    
#     def _check_subscription_access(self, user):
#         """Check subscription access using User model fields"""
#         today = timezone.now().date()
        
#         # Active subscription
#         if user.subscription_status == 'active':
#             if user.subscription_end_date:
#                 days_left = (user.subscription_end_date - today).days
#                 if days_left <= 0:
#                     user.subscription_status = 'inactive'
#                     user.save(update_fields=['subscription_status'])
#                     return False, 'subscription_base', 0, "Your subscription has expired."
#                 elif days_left <= 7:
#                     message = self._get_expiry_message(days_left, 'subscription')
#                     return True, None, days_left, message
#             return True, None, None, None
        
#         # Trial subscription
#         elif user.subscription_status == 'trial':
#             if user.subscription_end_date:
#                 days_left = (user.subscription_end_date - today).days
#                 if days_left <= 0:
#                     user.subscription_status = 'inactive'
#                     user.save(update_fields=['subscription_status'])
#                     return False, 'subscription_base', 0, "Your trial has expired. Please subscribe to continue."
#                 elif days_left <= 7:
#                     message = self._get_expiry_message(days_left, 'trial')
#                     return True, None, days_left, message
#                 return True, None, days_left, None
#             return True, None, None, None
        
#         # Inactive
#         else:
#             return False, 'subscription_base', 0, "Your account is inactive. Please subscribe to continue."
    
#     def _get_expiry_message(self, days_left, subscription_type):
#         """Get appropriate warning message"""
#         if days_left <= 0:
#             return f"Your {subscription_type} has expired."
#         elif days_left == 1:
#             return f"Your {subscription_type} ends TOMORROW! Subscribe now to avoid interruption."
#         elif days_left <= 3:
#             return f"Your {subscription_type} ends in {days_left} days. Subscribe now to continue access."
#         elif days_left <= 7:
#             return f"Your {subscription_type} ends in {days_left} days. Don't forget to subscribe!"
#         return None
    
#     def _maybe_show_trial_warning(self, request, days_left, message):
#         """Show warning but not on every request"""
#         if not message:
#             message = self._get_expiry_message(days_left, 'trial')
        
#         if not message:
#             return
        
#         # Check if we've shown warning in this session recently
#         last_shown = request.session.get(self.warning_shown_key)
#         now = timezone.now().timestamp()
        
#         # Show warning if not shown in last hour
#         if not last_shown or (now - last_shown) > 3600:
#             if days_left <= 3:
#                 messages.warning(request, message)
#             else:
#                 messages.info(request, message)
#             request.session[self.warning_shown_key] = now
    
#     def _is_public_path(self, path):
#         """Check if path is public"""
#         for public_path in self.public_paths:
#             if path.startswith(public_path):
#                 return True
#         return False


class SubscriptionCheckMiddleware:
    """
    Middleware to check if users have proper subscription status
    Simply checks the user.subscription_status field
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require subscription check
        self.public_paths = [
            '/admin/',
            '/accounts/login/',
            '/accounts/logout/',
            '/register/',
            '/signup/',
            '/post-login/',
            '/forgot-password/',
            '/reset-password/',
            '/password-reset-success/',
            '/password-reset-sent/',
            '/subscriptions/',
            '/subscriptions/plans/',
            '/subscriptions/create/',
            '/subscriptions/success/'
            '/payment/',
            '/validate-promo/',
            '/webhook/paystack/',
            '/paystack/callback/',
            '/static/',
            '/media/',
            '/ckeditor/',
            '/',
            '/getting-started/',
            '/policies/',
            '/job-board/',
            '/job-board/filters/',
            '/conference-board/',
            '/conference-board/filters',
            '/vacancy/post/',
            '/conference/post/',
            '/bookings/book/',
            '/api/bookings/public-create/',
            '/sitemap.xml',
            '/robots.txt',
            '/.well-known/',
            '/guest/dashboard/',
            '/share/',
            '/p/',
            '/api/',
            '/dashboard/my-profile/',
            '/dashboard/my-profile/edit/',
            '/company-profile/',
            '/staff/list/',
            '/admins/',
            '/staff/',
            '/pr/',
            '/conference/register/',
            '/conference-board/post/',
            '/vacancy/apply/',
            '/vacancy/withdraw/',
            '/vacancy/application/offer/response/',
            '/conference/registration/success/',
            '/conference-board/post/',
            '/notifications/',
            '/tenants/quick-services/',  # Quick Services page
            # Quick Service Items - all should be publicly accessible
            '/tickets/submit/',  # Submit support ticket (with or without tenant slug)
            '/tickets/check/',  # Check ticket status
            '/tickets/submitted/',  # Ticket submitted confirmation
            '/files/upload/public/',  # Send file (public upload)
            '/company-profile/',  # View company profile
            '/invoices/submit/',  # Send invoice (external submission)
            '/contact-support/',  # Contact support
            '/visitors/checkin/',  # Visitor check-in
            '/visitors/checkout/',  # Visitor checkout
            '/visitors/tag/',  # Visitor tag display
        ]
        
        # Path prefixes that should be accessible to trial users
        self.allowed_prefixes = [
            '/subscriptions',
            '/payment/',
            '/bookings/book/',  # Public booking pages
            '/memo/external/',  # External memo submission
        ]
        
        self.warning_shown_key = 'trial_warning_shown'
    
    def __call__(self, request):
        # Skip for superusers
        if request.user.is_superuser:
            return self.get_response(request)
        
        path = request.path
        
        # Check if path is public (always allowed) - BEFORE checking subscription
        if self._is_public_path(path):
            return self.get_response(request)
        
        # Check if path starts with allowed prefix
        if self._is_allowed_prefix_path(path):
            return self.get_response(request)
        
        # Only check subscription for authenticated users on non-public paths
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # For all other paths, check user's subscription_status
        if request.user.subscription_status == 'active':
            # User has active subscription - allow access
            self._maybe_show_warnings(request)
            return self.get_response(request)
        elif request.user.subscription_status == 'trial':
            # User is on trial - allow access but show warnings
            self._maybe_show_warnings(request)
            return self.get_response(request)
        else:
            # User has no active subscription or trial
            if request.user.is_personal:
                return render(request, 'subscription_required.html', {
                    "message": (
                        "You do not have an active subscription or trial. Please subscribe to continue accessing this feature. "
                    ),
                    "onclickbutton": "window.location.href='/subscriptions/create/'"
                },)
            else:
                if is_admin(request.user):
                    return render(request, 'subscription_required.html', {
                        "message": (
                            "Your company does not have an active subscription or trial. Please subscribe to continue accessing this feature. "
                        ),
                        "onclickbutton": "window.location.href='/subscriptions/create/'"
                    }, )
                else:
                    return render(request, 'subscription_required.html', {
                        "message": (
                            "Subscribe Now to continue accessing this feature. Choose your company, and select your email under selected users to subscribe. OR Contact your admin to subscribe for your company."
                        ),
                        "onclickbutton": "window.location.href='/subscriptions/create/'"
                    }, )
    
    def _maybe_show_warnings(self, request):
        """Show warnings for expiring trials/subscriptions"""
        user = request.user
        
        # Check if trial is ending soon
        if user.subscription_status == 'trial' and user.subscription_end_date:
            today = timezone.now().date()
            days_left = (user.subscription_end_date - today).days
            
            if 0 < days_left <= 7:
                last_shown = request.session.get(self.warning_shown_key)
                now = timezone.now().timestamp()
                
                if not last_shown or (now - last_shown) > 3600:
                    if days_left == 1:
                        # messages.warning(request, f'Your free trial ends TOMORROW! Subscribe now to continue access.')
                        return render(request, 'subscription_reminder.html', {
                            "message": (
                                "Your free trial ends TOMORROW! Subscribe now to continue access."
                            )
                        },)
                    elif days_left <= 3:
                        # messages.warning(request, f'Your free trial ends in {days_left} days. Subscribe now to continue access.')
                        return render(request, 'subscription_reminder.html', {
                            "message": (
                                "Your free trial ends in {days_left} days. Subscribe now to continue access."
                            )
                        },)
                    else:
                        # messages.info(request, f'Your free trial ends in {days_left} days. Remember to subscribe.')
                        return render(request, 'subscription_reminder.html', {
                            "message": (
                                "Your free trial ends in {days_left} days. Subscribe now to continue access."
                            )
                        },)
                request.session[self.warning_shown_key] = now
        
        # Check if subscription is ending soon
        elif user.subscription_status == 'active' and user.subscription_end_date:
            today = timezone.now().date()
            days_left = (user.subscription_end_date - today).days
            
            if 0 < days_left <= 7:
                last_shown = request.session.get(self.warning_shown_key)
                now = timezone.now().timestamp()
                
                if not last_shown or (now - last_shown) > 3600:
                    if days_left == 1:
                        # messages.warning(request, f'Your subscription ends TOMORROW! Renew now to avoid interruption.')
                        return render(request, 'subscription_reminder.html', {
                            "message": (
                                "Your free trial ends TOMORROW! Subscribe now to continue access."
                            )
                        },)
                    elif days_left <= 3:
                        # messages.warning(request, f'Your subscription ends in {days_left} days. Renew now to continue access.')
                        return render(request, 'subscription_reminder.html', {
                            "message": (
                                "Your free trial ends in {days_left} days. Subscribe now to continue access."
                            )
                        },)
                    else:
                        # messages.info(request, f'Your subscription ends in {days_left} days. Remember to renew.')
                        return render(request, 'subscription_reminder.html', {
                            "message": (
                                "Your free trial ends in {days_left} days. Subscribe now to continue access."
                            )
                        },)
                request.session[self.warning_shown_key] = now


    def _is_public_path(self, path):
        if path == '/':
            return True
        for public_path in self.public_paths:
            if public_path != '/' and path.startswith(public_path):
                return True
        return False
    
    def _is_allowed_prefix_path(self, path):
        """Check if path starts with an allowed prefix"""
        for prefix in self.allowed_prefixes:
            if path.startswith(prefix):
                return True
        return False
    
    # middleware.py

# class MetaEventSetupMiddleware:
#     """
#     Custom middleware to allow Meta's Event Setup Tool 
#     to load the website in an iframe for event creation.
    
#     This temporarily adds the 'frame-ancestors' directive 
#     in Content-Security-Policy header.
#     """
    
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         # Process the request and get the response
#         response = self.get_response(request)
        
#         # Add the CSP header that allows Meta to iframe your site
#         response['Content-Security-Policy'] = (
#             "frame-ancestors 'self' "
#             "https://www.facebook.com "
#             "https://business.facebook.com "
#             "https://connect.facebook.net;"
#         )
        
#         return response