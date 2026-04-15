from django.contrib.auth.decorators import user_passes_test
from documents.models import Notification
from documents.forms import NotificationForm
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator

@user_passes_test(is_admin)
def admin_notification_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    notifications = Notification.objects.filter(tenant=request.tenant).order_by('created_at')
    paginator = Paginator(notifications, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/admin_notification_list.html", {"notifications": page_obj})

@user_passes_test(is_admin)
def create_notification(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    if request.method == "POST":
        form = NotificationForm(request.POST)
        if form.is_valid():
            notification = form.save(commit=False)
            notification.tenant = request.tenant
            notification.save()
            return redirect("admin_notification_list")
    else:
        form = NotificationForm()
    return render(request, "admin/create_notification.html", {"form": form})

@user_passes_test(is_admin)
def edit_notification(request, notification_id):
    # Validate taht the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")
    
    notification = get_object_or_404(Notification, id=notification_id, tenant=request.tenant)

    if request.method == "POST":
        form = NotificationForm(request.POST, instance=notification)
        if form.is_valid():
            form.save()
            return redirect("admin_notification_list")
    else:
        form = NotificationForm(instance=notification)
    return render(request, "admin/edit_notification.html", {"form": form})

@user_passes_test(is_admin)
def delete_notification(request, notification_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the event, ensuring it belongs to the same tenant
    notification = get_object_or_404(Notification, id=notification_id, tenant=request.tenant)
    notification.delete()
    return redirect("admin_notification_list")
