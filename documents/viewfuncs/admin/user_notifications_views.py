from django.contrib.auth.decorators import user_passes_test
from documents.models import UserNotification
from documents.forms import UserNotificationForm
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator

@user_passes_test(is_admin)
def user_notification_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    user_notifications = UserNotification.objects.filter(tenant=request.tenant)
    paginator = Paginator(user_notifications, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/user_notification_list.html", {"user_notifications": page_obj})

@user_passes_test(is_admin)
def create_user_notification(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    if request.method == "POST":
        form = UserNotificationForm(request.POST, user=request.user)
        if form.is_valid():
            user_notification = form.save(commit=False)
            user_notification.tenant = request.tenant
            user_notification.save()
            return redirect("admin_notification_list")
    else:
        form = UserNotificationForm(user=request.user)
    return render(request, "admin/create_user_notification.html", {"form": form})

@user_passes_test(is_admin)
def edit_user_notification(request, user_notification_id):
    # Validate taht the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")
    
    user_notification = get_object_or_404(UserNotification, id=user_notification_id, tenant=request.tenant)

    if request.method == "POST":
        form = UserNotificationForm(request.POST, instance=user_notification, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("user_notification_list")
    else:
        form = UserNotificationForm(instance=user_notification, user=request.user)
    return render(request, "admin/edit_user_notification.html", {"form": form})

@user_passes_test(is_admin)
def delete_user_notification(request, user_notification_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the event, ensuring it belongs to the same tenant
    user_notification = get_object_or_404(UserNotification, id=user_notification_id, tenant=request.tenant)
    user_notification.delete()
    return redirect("user_notification_list")