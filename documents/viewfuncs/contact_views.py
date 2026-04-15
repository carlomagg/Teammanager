import logging
from django.contrib.auth.decorators import login_required
from documents.forms import ContactForm, SupportForm
from django.core.mail import EmailMessage
from documents.models import Contact
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.db.models import Q

from documents.viewfuncs.mail_connection import get_email_smtp_connection


logger = logging.getLogger(__name__)

@login_required
def contact_list(request):
    # if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
    #     print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
    #     # return HttpResponseForbidden("You are not authorized for this company.")
    #     return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user

    is_tenant_mode = request.effective_tenant is not None

    if effective_user.is_personal:
        contact_list_dept = Contact.objects.none()
    else:
        contact_list_dept = Contact.objects.filter(tenant=effective_tenant, department=request.user.department, is_public=True)
    
    contact_list_personal = Contact.objects.filter(tenant=effective_tenant, created_by=effective_user)
    contact_list = contact_list_dept | contact_list_personal
    paginator = Paginator(contact_list, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    paginator_dept = Paginator(contact_list_dept, 10)  # 10 users per page
    page_obj_dept = paginator_dept.get_page(page_number)
    paginator_personal = Paginator(contact_list_personal, 10)  # 10 users per page
    page_obj_personal = paginator_personal.get_page(page_number)
    return render(request, 'dashboard/contact_list.html', {'contact_list': page_obj, 'contact_list_dept': page_obj_dept, 'contact_list_personal': page_obj_personal, 'is_tenant_mode': is_tenant_mode})

@login_required
def create_contact(request):
    # if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
    #     print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
    #     # return HttpResponseForbidden("You are not authorized for this tenant.")
    #     return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    effective_tenant = request.effective_tenant
    effective_user   = request.effective_user
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.tenant = request.tenant
            contact.created_by = request.user
            if not effective_user.is_personal:
                contact.department = request.user.department
                contact.team = request.user.teams.first()
            contact.save()
            return redirect("contact_list")
    else:
        form = ContactForm()
    return render(request, "dashboard/create_contact.html", {"form": form})

@login_required
def view_contact_detail(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id, tenant=request.tenant)
    data = {
        'id': contact.id,
        'name': contact.name,
        'email': contact.email,
        'phone': contact.phone or '',
        'organization': contact.organization or '',
        'designation': contact.designation or '',
        'priority': contact.priority or '',
        'department': contact.department.name if contact.department else None,
        'team': contact.team.name if contact.team else None,
        'is_public': contact.is_public,
        'created_by': contact.created_by.username,
        'created_at': contact.created_at.isoformat(),
        'updated_by': contact.updated_by.username if contact.updated_by else None,
        'updated_at': contact.updated_at.isoformat()
    }
    return JsonResponse(data)

@login_required
def edit_contact(request, contact_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        # return HttpResponseForbidden("You are not authorized for this tenant.")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    contact = get_object_or_404(Contact, id=contact_id, tenant=request.tenant)
    print(f"Contact to edit: {contact}")
    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.tenant = request.tenant
            contact.updated_by = request.user
            contact.save()
            return redirect("contact_list")
    else:
        form = ContactForm(instance=contact)
    return render(request, "dashboard/edit_contact.html", {"form": form})

@login_required
def delete_contact(request, contact_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        # return HttpResponseForbidden("You are not authorized for this tenant.")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})
    contact = get_object_or_404(Contact, id=contact_id, tenant=request.tenant)
    if contact.created_by != request.user:
        return JsonResponse({'success': False, 'errors': {'folder': ['You can only delete your own contacts']}}, status=403)
    contact.delete()
    return redirect("contact_list")