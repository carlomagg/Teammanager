from django.contrib.auth.decorators import user_passes_test
from documents.models import Folder
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator

@user_passes_test(is_admin)
def admin_folder_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    folders = Folder.objects.filter(tenant=request.tenant)
    paginator = Paginator(folders, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/folder_list.html", {"folders": page_obj})

@user_passes_test(is_admin)
def admin_folder_details(request, folder_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the folder, ensuring it belongs to the same tenant
    try:
        folder_view = Folder.objects.get(id=folder_id, tenant=request.tenant)
    except Folder.DoesNotExist:
        return HttpResponseForbidden("Folder not found or does not belong to your company.")

    return render(request, "admin/view_folder_details.html", {"folder_view": folder_view})

@user_passes_test(is_admin)
def admin_delete_folder(request, folder_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the folder, ensuring it belongs to the same tenant
    folder = get_object_or_404(Folder, id=folder_id, created_by=request.user, tenant=request.tenant)
    folder.delete()
    return redirect("admin_folder_list")