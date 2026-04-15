from django.contrib.auth.decorators import user_passes_test
from documents.models import File
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator

@user_passes_test(is_admin)
def admin_file_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    files = File.objects.filter(tenant=request.tenant)
    paginator = Paginator(files, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/file_list.html", {"files": page_obj})

@user_passes_test(is_admin)
def admin_delete_file(request, file_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the file, ensuring it belongs to the same tenant
    file = get_object_or_404(File, id=file_id, uploaded_by=request.user, tenant=request.tenant)
    file.delete()
    return redirect("admin_file_list")