from django.contrib.auth.decorators import user_passes_test
from documents.models import Task
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.core.paginator import Paginator

@user_passes_test(is_admin)
def admin_task_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    tasks = Task.objects.filter(tenant=request.tenant)
    paginator = Paginator(tasks, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/task_list.html", {"tasks": page_obj})

@user_passes_test(is_admin)
def admin_task_detail(request, task_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the task, ensuring it belongs to the same tenant
    try:
        task_view = Task.objects.get(id=task_id, tenant=request.tenant)
    except Task.DoesNotExist:
        return HttpResponseForbidden("Task not found or does not belong to your company.")

    return render(request, "admin/view_task_details.html", {"task_view": task_view})
