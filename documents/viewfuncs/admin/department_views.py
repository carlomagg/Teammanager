from django.contrib.auth.decorators import user_passes_test, login_required
from documents.models import Department, CustomUser, Role
from documents.forms import AssignUsersToDepartmentForm, DepartmentForm
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator
from django.contrib import messages
from django.db.models import Q


def assign_users_to_department(request, department_id):
    department = get_object_or_404(Department, id=department_id)
    tenant = department.tenant

    if request.method == 'POST':
        form = AssignUsersToDepartmentForm(request.POST, tenant=tenant)
        if form.is_valid():
            users = form.cleaned_data['users']
            for user in users:
                user.department = department
                user.save()
            messages.success(request, f"Users successfully assigned to {department.name}.")
            return redirect('department_list')
    else:
        form = AssignUsersToDepartmentForm(tenant=tenant)
    
    return render(request, 'admin/assign_users_to_department.html', {
        'form': form,
        'department': department,
    })

def department_members(request, department_id):
    department = get_object_or_404(Department, id=department_id, tenant=request.tenant)
    members = CustomUser.objects.filter(department=department)
    return render(request, 'admin/department_members.html', {'department': department, 'members': members})

@user_passes_test(is_admin)
def department_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")
    
    # Fetch all departments in that tenant
    departments = Department.objects.filter(tenant=request.tenant)
    search = request.GET.get("search")
    if search:
        departments = departments.filter(
            Q(name__icontains=search) |
            Q(hod__icontains=search)
        )
    paginator = Paginator(departments, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/department_list.html", {"departments": page_obj})

@user_passes_test(is_admin)
def create_department(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    if request.method == "POST":
        form = DepartmentForm(request.POST, user=request.user)
        if form.is_valid():
            department = form.save(commit=False)
            department.tenant = request.tenant
            department.save()

            # Handle HOD assignment only if provided
            hod = form.cleaned_data['hod']
            if hod:
                if not hod.is_hod():
                    hod.roles.add(Role.objects.get(name='HOD'))
                    hod.save(update_fields=['roles'])

                hod.department = department
                hod.save(update_fields=['department'])

            return redirect("department_list")
    else:
        form = DepartmentForm(user=request.user)
    return render(request, "admin/create_department.html", {"form": form})

@user_passes_test(is_admin)
def edit_department(request, department_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the department, ensuring it belongs to the same tenant
    department = get_object_or_404(Department, id=department_id, tenant=request.tenant)

    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department, user=request.user)
        if form.is_valid():
            department=form.save(commit=False)
            department.hod.department = department
            department.hod.save()
            department.save()
            next_url = request.GET.get("next")
            return redirect(next_url or "department_list")
    else:
        form = DepartmentForm(instance=department, user=request.user)
    return render(request, "admin/edit_department.html", {"form": form})

@user_passes_test(is_admin)
def delete_department(request, department_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the department, ensuring it belongs to the same tenant
    department = get_object_or_404(Department, id=department_id, tenant=request.tenant)
    department.delete()
    next_url = request.GET.get("next")
    return redirect(next_url or "department_list")