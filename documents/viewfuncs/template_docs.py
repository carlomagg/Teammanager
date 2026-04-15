# Template Document functions
# Contains create for Document model (for template type)

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.forms import formset_factory
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.core.exceptions import ValidationError, PermissionDenied
from datetime import datetime
from docx import Document as DocxDocument
from raadaa import settings
from .documents_path import upload_to_documents_word, upload_to_documents_pdf
from .custom_auth import get_tenant_url
from .send_mails import send_approval_request, send_doc_approved_bdm, send_approved_email_client
from documents.forms import DocumentForm
from documents.models import Folder, File, Document, CustomUser
from documents.placeholders import replace_placeholders
import os, platform, shutil, subprocess

# Create template documents
@login_required
def create_document(request):
    if not hasattr(request, 'tenant') or not request.user.tenant == request.tenant:
        # return HttpResponseForbidden("You are not authorized to perform actions for this tenant.")
        tenant_url = get_tenant_url(request)
        return render(request, 'tenant_error.html', {'error_code': '401', 'message': 'Access denied.', 'user': request.user, 'tenant_url': tenant_url,}) 
    
    if request.user.tenant.slug not in ["raadaa", "transnet-cloud"]:
        # return HttpResponseForbidden("Unauthorized: User can not view this page.")
        raise PermissionDenied()
    
    DocumentFormSet = formset_factory(DocumentForm, extra=1)
    
    if request.method == "POST":
        print("POST request received")
        formset = DocumentFormSet(request.POST, request.FILES)
        print("Formset data:", request.POST)
        print("Files:", request.FILES)

        if formset.is_valid():
            print("Formset is valid")
            for form in formset:
                if form.has_changed():
                    print("Processing form:", form.cleaned_data)
                    document = form.save(commit=False)
                    document.created_by = request.user
                    document.tenant = request.tenant  # Set tenant from middleware
                    # Validate that the user belongs to the same tenant
                    if document.created_by.tenant != request.tenant:
                        return HttpResponse("Unauthorized: User does not belong to the current company.", status=403)

                    # Get or create the "Template Document" folder
                    user = request.user
                    department = user.department if hasattr(user, 'department') else None
                    team = user.teams.first() if hasattr(user, 'teams') and user.teams.exists() else None

                    # Ensure user has a department or team
                    if not department and not team:
                        return HttpResponse("Error: User must be associated with a department or team.", status=403)

                    # Choose department or team for the folder (prefer department if available)
                    folder_defaults = {
                        'created_by': user,
                        'is_public': True,
                    }

                    try:
                        template_folder, created = Folder.objects.get_or_create(
                            tenant=request.tenant,
                            name="Template Document",
                            defaults=folder_defaults
                        )
                    except ValidationError as e:
                        print(f"Folder creation error: {e}")
                        return HttpResponse(f"Error creating Template Document folder: {e}", status=400)
                        # raise BadRequest(f"Error creating Template Document folder: {e}")

                    # Validate folder access (similar to create_public_folder)
                    # if template_folder.department and template_folder.department != user.department:
                    #     return HttpResponse("Invalid Department for Template Document folder.", status=403)
                    # if template_folder.team and template_folder.team not in user.teams.all():
                    #     return HttpResponse("Invalid Team for Template Document folder.", status=403)

                    document.save()

                    creation_method = form.cleaned_data['creation_method']
                    if settings.DEBUG:
                        word_dir = os.path.join(settings.MEDIA_ROOT, upload_to_documents_word(document))
                        pdf_dir = os.path.join(settings.MEDIA_ROOT, upload_to_documents_pdf(document))
                    else:
                        word_dir = f"{settings.MEDIA_URL}{upload_to_documents_word(document).rstrip('/')}/"
                        pdf_dir = f"{settings.MEDIA_URL}{upload_to_documents_pdf(document).rstrip('/')}/"
                    os.makedirs(word_dir, exist_ok=True)
                    os.makedirs(pdf_dir, exist_ok=True)

                    base_filename = f"{document.company_name}_{document.id}"

                    if creation_method == 'template':
                        template_filename = "Approval Letter Template.docx" if document.document_type == "approval" else "SLA Template.docx"
                        template_path = os.path.join(settings.BASE_DIR, "documents/templates/docx_templates", template_filename)
                        if not os.path.exists(template_path):
                            print(f"Template not found: {template_path}")
                            return HttpResponse(f"Error: Template not found at {template_path}", status=500)
                        
                        today = datetime.today()
                        if document.document_type == "approval":
                            day = today.day
                            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
                            formatted_date = today.strftime("%d") + suffix + " " + today.strftime("%d %B, %Y")
                        else:
                            formatted_date = today.strftime("%m/%d/%Y")

                        doc = DocxDocument(template_path)
                        replacements = {
                            "{{Company Name}}": document.company_name,
                            "{{Company Address}}": document.company_address,
                            "{{Contact Person Name}}": document.contact_person_name,
                            "{{Contact Person Email}}": document.contact_person_email,
                            "{{Contact Person Designation}}": document.contact_person_designation + ",",
                            "{{Sales Rep}}": document.sales_rep,
                            "{{Date}}": formatted_date,
                        }
                        doc = replace_placeholders(doc, replacements, document.document_type)

                        word_filename = f"{base_filename}.docx"
                        word_path = os.path.join(word_dir, word_filename)
                        doc.save(word_path)
                        document.word_file = os.path.join(upload_to_documents_word(document), word_filename)

                        # Save Word file to File
                        public_word_file = File(
                            tenant=request.tenant,
                            original_name=word_filename,
                            file=os.path.join(upload_to_documents_word(document), word_filename),
                            folder=template_folder,
                            uploaded_by=user
                        )
                        public_word_file.save()
                    else:
                        uploaded_file = form.cleaned_data['uploaded_file']
                        file_extension = uploaded_file.name.lower().split('.')[-1]

                        if file_extension == 'docx':
                            word_filename = f"{base_filename}.docx"
                            word_path = os.path.join(word_dir, word_filename)
                            with open(word_path, 'wb') as f:
                                for chunk in uploaded_file.chunks():
                                    f.write(chunk)
                            document.word_file = os.path.join(upload_to_documents_word(document), word_filename)

                            # Save Word file to File
                            public_word_file = File(
                                tenant=request.tenant,
                                original_name=word_filename,
                                file=os.path.join(upload_to_documents_word(document), word_filename),
                                folder=template_folder,
                                uploaded_by=user
                            )
                            public_word_file.save()
                        elif file_extension == 'pdf':
                            pdf_filename = f"{base_filename}.pdf"
                            pdf_path = os.path.join(pdf_dir, pdf_filename)
                            with open(pdf_path, 'wb') as f:
                                for chunk in uploaded_file.chunks():
                                    f.write(chunk)
                            document.pdf_file = os.path.join(upload_to_documents_pdf(document), pdf_filename)
                            document.save()

                            # Save PDF file to File
                            public_pdf_file = File(
                                tenant=request.tenant,
                                original_name=pdf_filename,
                                file=os.path.join(upload_to_documents_pdf(document), pdf_filename),
                                folder=template_folder,
                                uploaded_by=user
                            )
                            public_pdf_file.save()

                            # print("Sending email for uploaded PDF")
                            # send_approval_request(document, sender_provider, sender_email, sender_password, bdm_emails)
                            continue

                    pdf_filename = f"{base_filename}.pdf"
                    if settings.DEBUG:
                        relative_pdf_path = os.path.join(upload_to_documents_pdf(document), pdf_filename)
                    else:
                        relative_pdf_path = f"{settings.MEDIA_URL}{upload_to_documents_pdf(document).rstrip('/')}/{pdf_filename}"
                    
                    if settings.DEBUG:
                        absolute_pdf_path = os.path.join(settings.MEDIA_ROOT, relative_pdf_path)
                    else:
                        absolute_pdf_path = f"{settings.MEDIA_URL}{relative_pdf_path.rstrip('/')}/"

                    # Choose the right LibreOffice path
                    if platform.system() == "Windows":
                        paths = [
                            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                            r"C:\Program Files\LibreOffice\program\soffice.exe"
                        ]
                        libreoffice_path = next((p for p in paths if os.path.exists(p)), None)
                    else:
                        libreoffice_path = shutil.which("libreoffice")

                    # Check if LibreOffice exists
                    if not libreoffice_path or not os.path.exists(libreoffice_path):
                        raise FileNotFoundError("LibreOffice not found. Make sure it's installed and in PATH.")

                    try:
                        print("Starting PDF conversion with LibreOffice")
                        
                        # Ensure paths are absolute
                        abs_word_path = os.path.abspath(word_path)
                        abs_output_dir = os.path.dirname(os.path.abspath(absolute_pdf_path))

                        print("abs_word_path: ", abs_word_path)

                        # Run LibreOffice to convert .docx to .pdf
                        result = subprocess.run(
                            [libreoffice_path, "--headless", "--convert-to", "pdf", "--outdir", abs_output_dir, abs_word_path],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=True
                        )

                        print("LibreOffice stdout:", result.stdout.decode())
                        print("LibreOffice stderr:", result.stderr.decode())

                        # Confirm output PDF file path
                        if os.path.exists(absolute_pdf_path):
                            document.pdf_file = relative_pdf_path
                            document.save()

                            # Save PDF file to File
                            public_pdf_file = File(
                                tenant=request.tenant,
                                original_name=pdf_filename,
                                file=relative_pdf_path,
                                folder=template_folder,
                                uploaded_by=user
                            )
                            public_pdf_file.save()
                        else:
                            return HttpResponse("PDF file was not generated.", status=500)

                    except subprocess.CalledProcessError as e:
                        print(f"LibreOffice conversion error: {e.stderr.decode()}")
                        return HttpResponse(f"Error converting to PDF: {e.stderr.decode()}", status=500)

                    except Exception as e:
                        print(f"Unexpected error: {e}")
                        return HttpResponse(f"Unexpected error converting to PDF: {e}", status=500)
                    
                    # Send 
                    # Get all BDM emails for the document's tenant
                    bdm_emails = CustomUser.objects.filter(
                        tenant=document.tenant,  # Filter by the document's tenant
                        roles__name="BDM"
                    ).values_list("email", flat=True)

                    # Ensure there are BDMs to notify
                    if not bdm_emails:
                        return
                    
                    # Ensure the document's creator is from the same tenant
                    if document.created_by.tenant != document.tenant:
                        # return HttpResponseForbidden("Unauthorized: Creator does not belong to the document's tenant.")
                        return render('error.html', {
                        'error_code': '403',
                        'message': 'Unauthorized: User does not belong to the document\'s company.'
                    }, status=403)

                    # sender_provider = document.created_by.email_provider
                    # sender_email = document.created_by.email_address
                    # sender_password = document.created_by.get_smtp_password()

                    sender = document.created_by

                    if not sender.email_address or not sender.email_password:
                        return HttpResponseForbidden("Your email credentials are missing. Contact admin.")
                    print("Sending email")
                    send_approval_request(document, sender.email_provider, sender.email_address, sender.email_password, bdm_emails, sender)

            print("Redirecting to document_list")
            return redirect("document_list")
        else:
            print("Formset errors:", formset.errors)
            print("Non-form errors:", formset.non_form_errors())
    else:
        print("GET request received")
        formset = DocumentFormSet()
    
    return render(request, "documents/create_document.html", {"formset": formset})

# BDM approve Template Documents
@login_required
def approve_document(request, document_id):
    # Ensure the user belongs to the current tenant
    if not hasattr(request, 'tenant') or not request.user.tenant == request.tenant:
        return HttpResponseForbidden("You are not authorized to perform actions for this company.")

    # Fetch the document, ensuring it belongs to the current tenant
    document = get_object_or_404(Document, id=document_id, tenant=request.tenant)

    # Restrict approval to users with the BDM role
    if not request.user.roles.filter(name="BDM").exists():
        return HttpResponseForbidden("You are not allowed to approve this document.")

    # Update document status and approved_by
    document.status = "approved"
    document.approved_by = request.user
    document.save()

    # Send Email to BDMs
    # Ensure the BDM has SMTP credentials (or use tenant-specific SMTP settings)
    sender_provider = request.user.email_provider
    sender_email = request.user.email_address
    sender_password = request.user.get_smtp_password()

    if not sender_email or not sender_password:
        return HttpResponseForbidden("Your email credentials are missing. Contact admin.")

    send_doc_approved_bdm(request, document, sender_provider, sender_email, sender_password)

    return redirect("document_list")  # Redirect to tenant-scoped document list

@login_required
def autocomplete_sales_rep(request):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    if 'term' in request.GET:
        qs = CustomUser.objects.filter(
            tenant = request.tenant,
            roles__name='Sales Rep',
            username__icontains=request.GET.get('term')
        ).distinct()
        names = list(qs.values_list('username', flat=True))
        return JsonResponse(names, safe=False)
    

def send_approved_email(request, document_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    document = get_object_or_404(Document, id=document_id, tenant=request.tenant)

    # Ensure the document is approved before sending an email
    if document.status != "approved":
        return HttpResponseForbidden("This document is not approved yet.")

    # Check if the email was already sent
    if document.email_sent:
        return HttpResponseForbidden("Email has already been sent.")

    # Ensure the PDF file exists
    if not document.pdf_file or not os.path.exists(document.pdf_file.path):
        return HttpResponseForbidden("PDF file not found.")

    # Get sender credentials from the logged-in 
    sender_provider = request.user.email_provider
    sender_email = request.user.email_address
    sender_password = request.user.get_smtp_password()

    if not sender_email or not sender_password:
        return HttpResponseForbidden("Your email credentials are missing. Contact admin.")
    
    # Define recipient, CC, and attachment

    # Main recipient
    raw_recipients = document.contact_person_email  # e.g., "email1@example.com, email2@example.com"
    recipient = [email.strip() for email in raw_recipients.split(",") if email.strip()] # in case of multiple emails
    if not recipient:
        return HttpResponseForbidden("No valid recipient email provided.")

    # recipient = [document.contact_person_email]

    # Get Sales Rep email
    sales_rep_email = CustomUser.objects.filter(username=document.sales_rep, tenant=request.tenant).values_list("email", flat=True)

    # Get all BDM emails
    bdm_emails = CustomUser.objects.filter(roles__name="BDM", tenant=request.tenant).values_list("email", flat=True)

    # Combine into a single list
    cc_list = list(sales_rep_email) + list(bdm_emails)

    # send mail
    send_approved_email_client(sender_provider, sender_email, sender_password, document, recipient, cc_list)

    # Update email status
    document.email_sent = True
    document.save()

    return redirect("document_list")  # Redirect to the document list

