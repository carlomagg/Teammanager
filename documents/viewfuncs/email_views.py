from datetime import timezone
import logging
from django.contrib.auth.decorators import login_required
from documents.forms import EmailForm
from documents.models import Email, Attachment, CustomUser
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.core.mail import EmailMessage


from documents.viewfuncs.mail_connection import get_email_smtp_connection


logger = logging.getLogger(__name__)

@login_required
def email_list(request):
    # if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
    #     print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
    #     # return HttpResponseForbidden("You are not authorized for this tenant.")
    #     return render(request, 'error.html', {'message': 'You are not authorized for this company.'})

    effective_tenant = request.effective_tenant
    effective_user = request.effective_user

        
    email_list = Email.objects.filter(tenant=effective_tenant, sender=effective_user).order_by('-created_at')
    email_list_draft = Email.objects.filter(tenant=effective_tenant, sender=request.user, sent=False).order_by('-created_at')
    email_list_sent = Email.objects.filter(tenant=effective_tenant, sender=request.user, sent=True).order_by('-created_at')
    page_number = request.GET.get('page')
    paginator = Paginator(email_list, 10)  # 10 emails per page
    page_obj = paginator.get_page(page_number)
    paginator_draft = Paginator(email_list_draft, 10)  # 10 emails per page
    page_obj_draft = paginator_draft.get_page(page_number)
    paginator_sent = Paginator(email_list_sent, 10)  # 10 emails per page
    page_obj_sent = paginator_sent.get_page(page_number)
    return render(request, 'dashboard/email_list.html', {'email_list': page_obj, 'email_list_draft': page_obj_draft, 'email_list_sent': page_obj_sent})

@login_required
def edit_email(request, email_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return render(request, 'error.html', {'message': 'You are not authorized for this company.'})

    email = get_object_or_404(Email, id=email_id, tenant=request.tenant, sender=request.user)
    if email.sender != request.user:
        return render(request, 'error.html', {'message': 'You can only edit your own emails.'})
    if email.sent:
        return redirect('email_detail', email_id=email_id)
    
    attachments = email.attachments.all()

    if request.method == 'POST':
        form = EmailForm(request.POST, request.FILES, instance=email)
        
        if form.is_valid():
            email = form.save(commit=False)
            email.tenant = request.tenant
            email.sender = request.user
            email.sent = False
            email.save()

            # Handle attachment deletions if specified
            if 'delete_attachments' in request.POST:
                attachment_ids = request.POST.getlist('delete_attachments')
                Attachment.objects.filter(id__in=attachment_ids, email=email).delete()

            # Save new attachments (handled by form.save())
            form.save()

            # If user wants to send the email
            if 'send' in request.POST:
                sender_provider = request.user.email_provider
                sender_email = request.user.email_address
                sender_password = request.user.email_password
                connection, error_message = get_email_smtp_connection(sender_provider,sender_email, sender_password)
                email_msg = EmailMessage(
                    subject=email.subject,
                    body=email.body,
                    from_email=sender_email,
                    to=email.get_to_emails(),
                    cc=email.get_cc_emails(),
                    bcc=email.get_bcc_emails(),
                    connection=connection
                )
                # Attach all files
                for attachment in email.attachments.all():
                    email_msg.attach_file(attachment.file.path)
                email_msg.send()
                email.sent = True
                email.sent_at = timezone.now()
                email.save()
                return redirect('email_list')

            return redirect('email_list')
    else:
        form = EmailForm(instance=email)

    return render(request, 'dashboard/edit_email.html', {'form': form, 'email': email, 'attachments': attachments})

@login_required
def save_draft(request):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return render(request, 'error.html', {'message': 'You are not authorized for this tenant.'})

    if request.method == 'POST':
        form = EmailForm(request.POST, request.FILES)
        
        if form.is_valid():
            email = form.save(commit=False)
            email.tenant = request.tenant
            email.sender = request.user
            email.sent = False
            email.save()
            form.save()  # Save attachments
            return redirect('email_list')
    else:
        form = EmailForm()

    return render(request, 'dashboard/send_email.html', {'form': form})

# Update send_email view to handle multiple attachments
@login_required
def send_email(request):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return render(request, 'error.html', {'message': 'You are not authorized for this tenant.'})

    sender_provider = request.user.email_provider
    sender_email = request.user.email_address
    sender_password = request.user.email_password
    connection, error_message = get_email_smtp_connection(sender_provider,sender_email, sender_password)

    # superuser = CustomUser.objects.get(is_superuser=True)
    # if not connection:
    #     sender_provider = superuser.email_provider
    #     sender_email = superuser.email_address
    #     sender_password = superuser.email_password
    #     connection, error_message = get_email_smtp_connection(sender_provider,sender_email, sender_password)

    if request.method == 'POST':
        form = EmailForm(request.POST, request.FILES)
        
        if form.is_valid():
            email = form.save(commit=False)
            email.tenant = request.tenant
            email.sender = request.user
            email.sent = False
            email.save()
            form.save()  # Save attachments

            # Send email
            email_msg = EmailMessage(
                subject=email.subject,
                body=email.body,
                from_email=sender_email,
                to=email.get_to_emails(),
                cc=email.get_cc_emails(),
                bcc=email.get_bcc_emails(),
                connection=connection
            )
            for attachment in email.attachments.all():
                email_msg.attach_file(attachment.file.path)
            email_msg.send()
            email.sent = True
            email.sent_at = timezone.now()
            email.save()
            return redirect('email_list')
    else:
        form = EmailForm()

    return render(request, 'dashboard/send_email.html', {'form': form})
@login_required
def email_detail(request, email_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    email = get_object_or_404(Email, id=email_id, tenant=request.tenant, sender=request.user)
    return render(request, 'dashboard/email_detail.html', {'email': email})

def delete_email(request, email_id):
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        print(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")
    email = get_object_or_404(Email, id=email_id, tenant=request.tenant, sender=request.user)
    if email.sender != request.user:
        raise HttpResponseForbidden('You can only delete your own emails')
    email.delete()
    return redirect('email_list')

@login_required
def delete_email_attachment(request, email_id, attachment_id):
    email = get_object_or_404(Email, id=email_id, tenant=request.tenant)
    attachment = get_object_or_404(Attachment, id=attachment_id, tenant=request.tenant)
    if not (email.sender == request.user) or attachment not in email.attachmets.all():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        email.attachments.remove(attachment)
        if not email.attachments.exists():
            attachment.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Invalid request'}, status=400)