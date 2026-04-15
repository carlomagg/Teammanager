import logging
from django.contrib.auth.decorators import login_required
from documents.forms import UserProfileForm
from documents.models import CompanyProfile, CustomUser, Department, Team, UserProfile
from tenants.models import Tenant
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from .helper_funcs.staff_tenant_or_user import get_tenant_or_staff


logger = logging.getLogger(__name__)

# @login_required
# def view_company_profile(request):
#     # Check if user is superuser (for admin dashboard access)
#     if request.user.is_superuser:
#         tenant_id = request.GET.get('tenant_id')
#         if tenant_id:
#             try:
#                 tenant = Tenant.objects.get(id=tenant_id)
#             except Tenant.DoesNotExist:
#                 return HttpResponseForbidden("Tenant not found.")
#         else:
#             # If no tenant_id provided for superuser, use their own tenant or return error
#             if hasattr(request.user, 'tenant'):
#                 tenant = request.user.tenant
#             else:
#                 return HttpResponseForbidden("No tenant specified.")
    
#     # Regular tenant user access
#     elif not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
#         logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
#         return HttpResponseForbidden("You are not authorized for this company.")
#     else:
#         tenant = request.tenant
    
#     print(f"User: {request.user.username}. Viewing profile for tenant: {tenant.name}")
    
#     try: 
#         tenant_profile, created = CompanyProfile.objects.get_or_create(
#             tenant=tenant
#         )

#         num_staff = CustomUser.objects.filter(tenant=tenant).count()
#         num_departments = Department.objects.filter(tenant=tenant).count()
#         num_teams = Team.objects.filter(tenant=tenant).count()

#         tenant_profile.num_staff = num_staff
#         tenant_profile.num_departments = num_departments
#         tenant_profile.num_teams = num_teams
#         tenant_profile.save()

#         depts = Department.objects.filter(tenant=tenant)
#         teams = Team.objects.filter(tenant=tenant)
        
#         context = {
#             'tenant_profile': tenant_profile, 
#             'depts': depts, 
#             'teams': teams,
#             'is_admin_view': request.user.is_superuser,  # Flag for template
#             'viewed_tenant': tenant,
#         }
#         return render(request, 'admin/company_profile.html', context)
#     except Exception as e:
#         logger.error(f"Error in view_company_profile: {e}")
#         return HttpResponse("An unexpected error occurred", status=500)

@login_required
# @user_passes_test(is_admin)
def edit_user_profile(request):
    """
    Edit company profile.

    :param request: The request object
    :return: A JSON response containing the company profile data
    :rtype: JsonResponse
    """
    user = request.effective_user

    if not user.is_personal:
        return HttpResponseForbidden("You are not authorized for this user.")

    
    user_profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={'first_name': user.username}
    )
    
    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=user_profile)
        if form.is_valid():
            form.save()
            return redirect("view_user_profile")
    else:
        form = UserProfileForm(instance=user_profile)
    return render(request, "users/edit_user_profile.html", {"form": form, 'profile': user_profile})

def view_company_profile(request):
    # Public access allowed - show basic company info
    # If logged in, show full details
    
    if not request.user.is_authenticated:
        # Public view - show basic company profile only
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return HttpResponseForbidden("No organization specified.")
        
        try:
            tenant_profile = CompanyProfile.objects.get(tenant=tenant)
            context = {
                'tenant_profile': tenant_profile,
                'is_public_view': True,
                'viewed_tenant': tenant,
            }
            return render(request, 'admin/company_profile.html', context)
        except CompanyProfile.DoesNotExist:
            return HttpResponseForbidden("Company profile not found.")
    
    # Logged in user - full access
    tenant = request.effective_tenant
    user = request.effective_user
    tenant_id = request.GET.get('tenant_id')
    if request.user.is_staff and tenant_id:
        if user.is_personal:
            try:
                tenant = CustomUser.objects.get(id=tenant_id)
            except CustomUser.DoesNotExist:
                return HttpResponseForbidden("User not found.")
        else:
            try:
                tenant = Tenant.objects.get(id=tenant_id)
            except Tenant.DoesNotExist:
                return HttpResponseForbidden("Tenant not found.")
    
    # Regular tenant user access
    elif not hasattr(request, 'tenant') or request.user.tenant != request.tenant or not hasattr(request, 'user'):
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    else:
        if user.is_personal and request.tenant == None:
            tenant = request.user
            printout = f"User: {request.user.username}. Viewing profile for tenant: {tenant.username}"
        elif user.tenant == request.tenant:
            tenant = request.tenant
            printout = f"User: {request.user.username}. Viewing profile for tenant: {tenant.name}"
    
            print(printout)
        else:
            return HttpResponseForbidden("You are not authorized for this company.")

    if user.is_personal:
        try: 
            tenant_profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                }
            )
            
            context = {
                'profile': tenant_profile, 
                'is_admin_view': request.user.is_superuser,  # Flag for template
            }
            return render(request, 'users/user_company_profile.html', context)
        except Exception as e:
            logger.error(f"Error in view_company_profile: {e}")
            return HttpResponse("An unexpected error occurred", status=500)
    else:
    
        try: 
            tenant_profile, created = CompanyProfile.objects.get_or_create(
                tenant=tenant
            )

            num_staff = CustomUser.objects.filter(tenant=tenant).count()
            num_departments = Department.objects.filter(tenant=tenant).count()
            num_teams = Team.objects.filter(tenant=tenant).count()

            tenant_profile.num_staff = num_staff
            tenant_profile.num_departments = num_departments
            tenant_profile.num_teams = num_teams
            tenant_profile.save()

            depts = Department.objects.filter(tenant=tenant)
            teams = Team.objects.filter(tenant=tenant)
            
            context = {
                'tenant_profile': tenant_profile, 
                'depts': depts, 
                'teams': teams,
                'is_admin_view': request.user.is_superuser,  # Flag for template
                'viewed_tenant': tenant,
            }
            return render(request, 'admin/company_profile.html', context)
        except Exception as e:
            logger.error(f"Error in view_company_profile: {e}")
            return HttpResponse("An unexpected error occurred", status=500)
    

