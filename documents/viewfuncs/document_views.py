# RUD functions for Document model
# Create function for Template documents in templated_docs.py
# Create function for Editor documents in editor_docs.py

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from documents.models import Document, CustomUser
from .rba_decorators import is_admin

# List Document (both templated and Editor docs)
@login_required
def document_list(request):
    # Validate that the user belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: User does not belong to this company.")
    
    # if request.user.tenant.slug not in ["raadaa", "transnet-cloud"]:
    #     return HttpResponseForbidden("Unauthorized: User can not view this page.")

    # Start with documents filtered by the current tenant
    documents = Document.objects.filter(tenant=request.tenant)

    # Get filter parameters from the request
    company = request.GET.get('company', '').strip()
    doc_type = request.GET.get('type', '').strip()
    status = request.GET.get('status', '').strip()
    created = request.GET.get('created', '').strip()
    created_by = request.GET.get('created_by', '').strip()
    approved_by = request.GET.get('approved_by', '').strip()
    send_email = request.GET.get('send_email', '').strip()

    # Apply filters
    if company:
        documents = documents.filter(company_name__iexact=company)
        print(f"Filtering by company: {company}")
    if doc_type:
        documents = documents.filter(document_type__iexact=doc_type)
        print(f"Filtering by document_type: {doc_type}")
    if status:
        documents = documents.filter(status__iexact=status)
        print(f"Filtering by status: {status}")
    if created:
        try:
            documents = documents.filter(created_at__date=created)
            print(f"Filtering by created_at: {created}")
        except ValueError:
            print(f"Invalid date format for created: {created}")
    if created_by:
        documents = documents.filter(created_by__username__iexact=created_by, created_by__tenant=request.tenant)
        print(f"Filtering by created_by: {created_by}")
    if approved_by:
        documents = documents.filter(approved_by__username__iexact=approved_by, approved_by__tenant=request.tenant)
        print(f"Filtering by approved_by: {approved_by}")
    if send_email:
        email_sent = send_email.lower() == 'sent'
        documents = documents.filter(email_sent=email_sent)
        print(f"Filtering by email_sent: {email_sent}")

    # Paginate filtered documents
    paginator = Paginator(documents, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Get distinct values for filter dropdowns, scoped to the tenant
    distinct_companies = Document.objects.filter(tenant=request.tenant).values_list('company_name', flat=True).distinct()
    distinct_type = Document.objects.filter(tenant=request.tenant).values_list('document_type', flat=True).distinct()
    distinct_created_by = CustomUser.objects.filter(
        tenant=request.tenant,
        id__in=Document.objects.filter(tenant=request.tenant).values_list('created_by', flat=True).distinct()
    ).values_list('username', flat=True)
    distinct_approved_by = CustomUser.objects.filter(
        tenant=request.tenant,
        id__in=Document.objects.filter(tenant=request.tenant).values_list('approved_by', flat=True).distinct()
    ).exclude(username__isnull=True).values_list('username', flat=True)

    # Debug filtered document count
    print(f"Filtered documents count: {documents.count()}")

    return render(request, "documents/document_list.html", {
        "documents": page_obj,
        "page_obj": page_obj,
        "filter_params": {
            'company': company,
            'type': doc_type,
            'status': status,
            'created': created,
            'created_by': created_by,
            'approved_by': approved_by,
            'send_email': send_email,
        },
        "distinct_companies": distinct_companies,
        "distinct_type": distinct_type,
        "distinct_created_by": distinct_created_by,
        "distinct_approved_by": distinct_approved_by
    })

# Delete Document
@login_required
@user_passes_test(is_admin)
def delete_document(request, document_id):
    import os
    from documents.models import File

    if hasattr(request, 'tenant') and request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized to perform actions for this company.")
    document = get_object_or_404(Document, id=document_id, tenant=request.tenant)

    # Delete any automatically generated "File" objects used for tasks and attachments
    # These share the exact basename of the document's word_file or pdf_file
    if document.word_file:
        word_basename = os.path.basename(document.word_file.name)
        File.objects.filter(tenant=request.tenant, original_name=word_basename).delete()
        document.word_file.delete(save=False)
        
    if document.pdf_file:
        pdf_basename = os.path.basename(document.pdf_file.name)
        File.objects.filter(tenant=request.tenant, original_name=pdf_basename).delete()
        document.pdf_file.delete(save=False)

    document.delete()
    return redirect("document_list")  # Redirect back to the list