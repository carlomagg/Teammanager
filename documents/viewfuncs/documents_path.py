# For upload to documents folder in storage
import os

# Templated documents word
def upload_to_documents_word(document):
    tenant_name = document.tenant.name
    username = document.created_by.username if document.created_by else "anonymous"
    return os.path.join('documents', tenant_name, username, 'word')

# Templated documents pdf
def upload_to_documents_pdf(document):
    tenant_name = document.tenant.name
    username = document.created_by.username if document.created_by else "anonymous"
    return os.path.join('documents', tenant_name, username, 'pdf')

# Editor created documents word
def documents_word_upload(request):
    tenant_name = request.tenant.name
    username = request.user.username if request.user else "anonymous"
    return os.path.join('documents', tenant_name, username, 'word')

# Editor created documents pdf
def documents_pdf_upload(request):
    tenant_name = request.tenant.name
    username = request.user.username if request.user else "anonymous"
    return os.path.join('documents', tenant_name, username, 'pdf')