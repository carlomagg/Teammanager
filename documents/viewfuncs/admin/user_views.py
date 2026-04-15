from django.contrib.auth.decorators import user_passes_test, login_required
from documents.forms import EditUserForm, UserForm
from documents.models import CustomUser, StaffProfile
from documents.viewfuncs.mail_connection import get_email_smtp_connection
from raadaa import settings
from raadaa.tasks import create_default_folders_user
from ..rba_decorators import is_admin, is_tenant_owner 
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.admin.models import LogEntry, CHANGE, ADDITION, DELETION
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from ..send_mails import send_reg_confirm
from django.db.models import Q
import secrets

@user_passes_test(is_admin)
def users_list(request):
    # Validate that the requesting user belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: User does not belong to this company.")

    # Filter users by the current tenant
    users = CustomUser.objects.filter(tenant=request.tenant).order_by('date_joined')
    search = request.GET.get("search")
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    paginator = Paginator(users, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    count = users.count()
    return render(request, "admin/users_list.html", {"users": page_obj, 'count': count})

@login_required
@user_passes_test(is_admin)
def create_user(request):
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")
    if request.method == "POST":
        form = UserForm(request.POST, tenant=request.tenant)
        password = secrets.token_urlsafe(10)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = form.cleaned_data['email']
            user.set_password(password)
            user.tenant = request.tenant
            user.must_reset_password = True
            user.save()
            LogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(CustomUser).pk,
                object_id=user.id,
                object_repr=user.username,
                action_flag=ADDITION,
                change_message='Created user'
            )
            next_url = request.GET.get("next")

        try:
            profile, created = StaffProfile.objects.get_or_create(tenant=user.tenant, user=user)
            profile.first_name = user.first_name
            profile.last_name = user.last_name
            profile.email = user.email
            profile.save()
        except ValidationError as e:
            print(f"Staff Profile creation error: {e}")
            # return redirect('view_my_profile')
        
            # Send confirmation email
        main_superuser = CustomUser.objects.filter(is_superuser=True).first()
        send_reg_confirm(request, user, request.user, main_superuser, password=password)
        create_default_folders_user.delay(user.id)

        return redirect(next_url or "users_list")
    else:
        form = UserForm(tenant=request.tenant)
    return render(request, "admin/create_user.html", {"form": form})

@login_required
@user_passes_test(is_admin)
def view_user_details(request, user_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the user, ensuring they belong to the same tenant
    try:
        user_view = CustomUser.objects.get(id=user_id, tenant=request.tenant)
        details = ['username', 'first_name', 'last_name', 'email', 
                 'is_active', 'roles', 'phone_number', 
                  'department', 'teams', 'email_address', 'email_password']
    except CustomUser.DoesNotExist:
        # return HttpResponseForbidden("User not found or does not belong to your tenant.")
        raise PermissionDenied("User not found or does not belong to your company.")

    return render(request, "admin/view_user_details.html", {"user_view": user_view, "details": details})


@login_required
@user_passes_test(is_admin)
def approve_user(request, user_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    try:
        user = CustomUser.objects.get(id=user_id, tenant=request.tenant)
    except CustomUser.DoesNotExist:
        return HttpResponseForbidden("User not found or does not belong to your company.")
    password = secrets.token_urlsafe(10)
    # Activate the user
    user.password = password
    user.is_active = True
    user.save()

    next_url = request.GET.get("next")

    try:
        profile, created = StaffProfile.objects.get_or_create(tenant=user.tenant, user=user)
        profile.first_name = user.first_name
        profile.last_name = user.last_name
        profile.email = user.email
        profile.save()
    except ValidationError as e:
        print(f"Staff Profile creation error: {e}")
        # return redirect('view_my_profile')
    
        # Send confirmation email
    main_superuser = CustomUser.objects.filter(is_superuser=True).first()
    send_reg_confirm(request, user, request.user, main_superuser, password=password)

    return redirect(next_url or "users_list")

@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the user, ensuring they belong to the same tenant
    user = get_object_or_404(CustomUser, id=user_id, tenant=request.tenant)

    # Block editing the tenant owner (unless it's themselves or superuser)
    if user == request.tenant.admin and not request.user.is_superuser:
        if request.user != user:
            return HttpResponseForbidden("You cannot edit the tenant owner.")

    # If target is an Admin, only Tenant Owner can edit
    if is_admin(user) and not is_tenant_owner(request.user, request.tenant) and not request.user.is_superuser:
        return HttpResponseForbidden("Only the tenant owner can edit Admin accounts.")

    if request.method == "POST":
        form = EditUserForm(request.POST, instance=user, tenant=request.tenant)
        if form.is_valid():
            # Ensure the tenant field cannot be changed
            form.instance.tenant = request.tenant
            form.save()
            LogEntry.objects.log_action(
                user_id=request.user.id,
                content_type_id=ContentType.objects.get_for_model(CustomUser).pk,
                object_id=user.id,
                object_repr=user.username,
                action_flag=CHANGE,
                change_message='Edited user profile'
            )
            next_url = request.GET.get("next")
            return redirect(next_url or "users_list")
    else:
        form = EditUserForm(instance=user, tenant=request.tenant)
    return render(request, "admin/edit_user.html", {"form": form})

@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the user, ensuring they belong to the same tenant
    user = get_object_or_404(CustomUser, id=user_id, tenant=request.tenant)

    # Prevent deleting yourself
    if user == request.user:
        return HttpResponseForbidden("You cannot delete your own account.")

    # Block deleting the tenant owner
    if user == request.tenant.admin and not request.user.is_superuser:
        return HttpResponseForbidden("You cannot delete the tenant owner.")

    # If target is an Admin, only Tenant Owner can delete
    if is_admin(user) and not is_tenant_owner(request.user, request.tenant) and not request.user.is_superuser:
        return HttpResponseForbidden("Only the tenant owner can delete Admin accounts.")

    user.delete()
    next_url = request.GET.get("next")
    return redirect(next_url or "users_list")