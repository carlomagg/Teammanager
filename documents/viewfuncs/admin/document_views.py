from django.contrib.auth.decorators import user_passes_test
from documents.models import Document
from ..rba_decorators import is_admin 
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from django.core.paginator import Paginator

@user_passes_test(is_admin)
def admin_documents_list(request):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    documents = Document.objects.filter(tenant=request.tenant)
    paginator = Paginator(documents, 10)  # 10 users per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "admin/documents_list.html", {"documents": page_obj})

@user_passes_test(is_admin)
def admin_document_details(request, document_id):
    # Validate that the admin belongs to the current tenant
    if request.user.tenant != request.tenant:
        return HttpResponseForbidden("Unauthorized: Admin does not belong to this company.")

    # Get the document, ensuring it belongs to the same tenant
    try:
        document_view = Document.objects.get(id=document_id, tenant=request.tenant)
    except Document.DoesNotExist:
        return HttpResponseForbidden("Document not found or does not belong to your company.")

    return render(request, "admin/view_document_details.html", {"document_view": document_view})

@user_passes_test(is_admin)
def admin_delete_document(request, document_id):
    if hasattr(request, 'tenant') and request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized to perform actions for this company.")
    document = get_object_or_404(Document, id=document_id, tenant=request.tenant)

    # Ensure document files are deleted from storage
    if document.word_file:
        document.word_file.delete(save=False)
    if document.pdf_file:
        document.pdf_file.delete(save=False)

    document.delete()
    return redirect("admin_document_list")  # Redirect back to the list
