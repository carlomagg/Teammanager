# For handling mails

import logging

from documents.models import CustomUser, GuestUser, Conference, ConferenceParticipant
from raadaa import settings
from .mail_connection import get_email_smtp_connection
from .helper_funcs.access_urls import build_user_activity_dashboard_url, build_guest_dashboard_url, build_conference_access_url
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse
from urllib.parse import urlencode
from .helper_funcs.generate_qr import _generate_qr_data_uri

logger = logging.getLogger(__name__)



def admin_reg_confirm(user):
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
    protocol = "http" if settings.DEBUG else "https"
    login_url = f"{protocol}://{user.tenant.slug}.{base_domain}/accounts/login"
    profile_url = f"{protocol}://{user.tenant.slug}.{base_domain}/dashboard/my-profile"
    company_profile_url = f"{protocol}://{user.tenant.slug}.{base_domain}/company-profile"
    admin_dashboard_url = f"{protocol}://{user.tenant.slug}.{base_domain}/admins/dashboard"
    email_config_url = f"{protocol}://{user.tenant.slug}.{base_domain}/dashboard/email-config"
    roles = user.roles.all().values_list('name', flat=True)
    now = timezone.now()
    context = {'user': user, 
               'admin_name': user.staff_profile.get_full_name() or user.username,
               'admin_email': user.email,
               'tenant_name': user.tenant.name,
               'login_url': login_url, 
               'now': now, 
               'my_profile_url': profile_url,
               'company_profile_url': company_profile_url,
               'admin_dashboard_url': admin_dashboard_url,
               'roles': roles,
               }

    # Render HTML content
    html_content = render_to_string('emails/admin_reg_confirm.html', context)

    subject = f"Registration Confirmation: {user.username}"
    
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if connection:
        try:
            # Create and send HTML email
            email = EmailMessage(
                subject=subject,
                body=html_content,
                from_email=superuser.email_address,
                to=[user.email],
                connection=connection
            )
            # Specify that this is HTML email
            email.content_subtype = "html"
            email.send()
            print("Email sent successfully via superuser")
        except Exception as e:
            print(f"Failed to send approval email: {e}")
    else:
        print(f"SMTP Connection Failed for superuser: {error_message}")

def personal_user_reg_confirm(request, user):
    superuser = CustomUser.objects.get(is_superuser=True, is_active=True)
    base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
    protocol = "http" if settings.DEBUG else "https"
    login_url = f"{protocol}://{base_domain}/accounts/login"
    my_profile_url = f"{protocol}://{base_domain}/admins/user-profile"
    now = timezone.now()
    context = {'user': user, 'login_url': login_url, 'now': now, 'my_profile': my_profile_url,}

    # Render HTML content
    html_content = render_to_string('emails/personal_user_reg_confirm.html', context)

    subject = f"Registration Confirmation: {user.username}"
    
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if connection:
        try:
            # Create and send HTML email
            email = EmailMessage(
                subject=subject,
                body=html_content,
                from_email=superuser.email_address,
                to=[user.email],
                connection=connection
            )
            # Specify that this is HTML email
            email.content_subtype = "html"
            email.send()
            print("Email sent successfully via superuser")
        except Exception as e:
            print(f"Failed to send approval email: {e}")
    else:
        print(f"SMTP Connection Failed for superuser: {error_message}")

def send_user_account_pending_approval(request, user, admin_user, superuser):
    context = {'user': user, 'admin_user': admin_user, 'tenant_name': request.tenant.name}

    # Render HTML content
    html_content = render_to_string('emails/account_pending_approval.html', context)

    subject = f"Account Pending Approval: {user.username}"
    
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if connection:
        try:
            # Create and send HTML email
            email = EmailMessage(
                subject=subject,
                body=html_content,
                from_email=superuser.email_address,
                to=[user.email],
                connection=connection
            )
            # Specify that this is HTML email
            email.content_subtype = "html"
            email.send()
            print("Email sent successfully via superuser")
        except Exception as e:
            print(f"Failed to send approval email: {e}")
    else:
        print(f"SMTP Connection Failed for superuser: {error_message}")

def send_admin_account_pending_approval(request, user, admin_user, superuser, approval_url):
    context = {'user': user, 'admin_user': admin_user, 'tenant_name': request.tenant.name, 'approval_url': approval_url}

    # Render HTML content
    html_content = render_to_string('emails/admin_account_pending_approval.html', context)

    subject = f"Account Pending Approval: {user.username}"
    
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if connection:
        try:
            # Create and send HTML email
            email = EmailMessage(
                subject=subject,
                body=html_content,
                from_email=superuser.email_address,
                to=[admin_user.email],
                connection=connection
            )
            # Specify that this is HTML email
            email.content_subtype = "html"
            email.send()
            print("Email sent successfully via superuser")
        except Exception as e:
            print(f"Failed to send approval email: {e}")
    else:
        print(f"SMTP Connection Failed for superuser: {error_message}")

# Send Account registration Confirmation
def send_reg_confirm(request, user, admin_user, superuser, password):
    base_domain = "127.0.0.1:8000" if settings.DEBUG else "teammanager.ng"
    protocol = "http" if settings.DEBUG else "https"
    login_url = f"{protocol}://{request.tenant.slug}.{base_domain}/accounts/login"

    # Prepare context for the template
    context = {
        'user_name': user.username,
        'user_email': user.email,
        'user_password': password,
        'login_url': login_url,
        'tenant_name': request.tenant.name,
        'admin_name': admin_user.staff_profile.get_full_name() or admin_user.username,
        'admin_email': admin_user.email,
        'my_profile': f"{protocol}://{request.tenant.slug}.{base_domain}/dashboard/my-profile",
        'comp_profile': f"{protocol}://{request.tenant.slug}.{base_domain}/company-profile",
        'email_config': f"{protocol}://{request.tenant.slug}.{base_domain}/dashboard/email-config"
    }

    # Render HTML content
    html_content = render_to_string('emails/reg_confirm.html', context)

    subject = f"Account Approved: {user.username}"

    if superuser.email_provider and superuser.email_address and superuser.email_password:
        sender_password = superuser.get_smtp_password()
        connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, sender_password)
        if connection:
            try:
                # Create and send HTML email
                email = EmailMessage(
                    subject=subject,
                    body=html_content,
                    from_email=superuser.email_address,
                    to=[user.email],
                    connection=connection
                )
                # Specify that this is HTML email
                email.content_subtype = "html"
                email.send()
                print("Email sent successfully via superuser")
                return  # Success — exit early
            except Exception as e:
                print(f"Failed to send via superuser: {e}")
                connection = None  # Force fallback
        else:
            print(f"SMTP Connection Failed for superuser: {error_message}")

    print("Email sent failed")

# Send Password Reset
def send_password_reset_email(user, reset_url, superuser):
    sender_password = superuser.get_smtp_password()
    if superuser.email_provider and superuser.email_address and sender_password:
        connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, sender_password)
        now = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
        context = {
            'reset_url': reset_url,
            'user_name': user.username,
            'tenant_name': user.tenant.name,
            'now': now,
        }

        html_content = render_to_string('emails/forgot_password.html', context)
        # Send email (customize content as needed)
        subject = 'TeamManager Password Reset Request'
        
        email = EmailMessage(subject=subject, body=html_content, from_email=superuser.email_address, to=[user.email], connection=connection)
        email.content_subtype = "html"
        email.send()

def send_approval_request(document, sender_provider, sender_email, sender_password, bdm_emails, sender):
    sender_password = sender.get_smtp_password()
    connection, error_message = get_email_smtp_connection(sender_provider, sender_email, sender_password)

    base_domain = "127.0.0.1:8000" if settings.DEBUG else "teammanager.ng"
    protocol = "http" if settings.DEBUG else "https"
    document_link = f"{protocol}://{document.tenant.slug}.{base_domain}/media/documents/pdf/{document.pdf_file.url}"
    # Prepare context for the template
    context = {
        'company_name': document.company_name,
        'creator_name': document.created_by.get_full_name(),
        'creator_title': getattr(document.created_by, 'title', ''),
        'created_date': document.created_at.strftime('%B %d, %Y'),
        'document_type': getattr(document, 'document_type', ''),
        'document_link': document_link,
    }

    # Render HTML content
    html_content = render_to_string('emails/approval_request.html', context)

    subject = f"Approval Request: {document.company_name}"

    print("Sending mail...")

    # Create email with HTML content and attachment
    email = EmailMessage(
        subject=subject,
        body=html_content,  # HTML content as the body
        from_email=sender_email,
        to=list(bdm_emails),
        connection=connection
    )
    
    # Specify that this is HTML email
    email.content_subtype = "html"
    
    # Attach the PDF file
    email.attach_file(document.pdf_file.path)
    
    email.send()
    
    print("Mail Sent")

def send_doc_approved_bdm(request, document, sender_provider, sender_email, sender_password):
    # Configure SMTP settings dynamically
    connection, error_message = get_email_smtp_connection(sender_provider, sender_email, sender_password)

    base_domain = "127.0.0.1:8000" if settings.DEBUG else "teammanager.ng"
    protocol = "http" if settings.DEBUG else "https"
    document_link = f"{protocol}://{document.tenant.slug}.{base_domain}/media/documents/pdf/{document.pdf_file.url}"

    # Ensure the document's creator belongs to the same tenant
    if document.created_by.tenant != request.tenant:
        return HttpResponseForbidden("Invalid document creator for this company.")

    # Prepare context for the template
    context = {
        'creator_name': document.created_by.get_full_name() or document.created_by.username,
        'approver_name': request.user.get_full_name() or request.user.username,
        'company_name': document.company_name,
        'tenant_name': request.tenant.name,
        'document_type': getattr(document, 'document_type', ''),
        'document_link': document_link,
    }

    # Render HTML content
    html_content = render_to_string('emails/document_approved.html', context)

    subject = f"Document Approved for {request.tenant.name}"

    # Create and send HTML email
    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=sender_email,
        to=[document.created_by.email],
        connection=connection
    )
    
    # Specify that this is HTML email
    email.content_subtype = "html"
    
    # Attach the PDF file
    email.attach_file(document.pdf_file.path)
    
    email.send()

def send_approved_email_client(sender_provider, sender_email, sender_password, document, recipient, cc_list):
    connection, error_message = get_email_smtp_connection(sender_provider, sender_email, sender_password)

    context = {
        'company_name': document.company_name,
        'creator_name': document.created_by.get_full_name(),
        'creator_title': 'Executive Assistant',
        'phone_number': getattr(document.created_by, 'phone_number', ''),
        'creator_email': document.created_by.email,
        'document_type': document.document_type,
    }

    if document.document_type == "approval":
        template_name = 'emails/aws_approval_client.html'
        subject = f"{document.company_name} - Approved by AWS"
    else:  # SLA Document
        template_name = 'emails/sla_document_client.html'
        subject = f"{document.company_name} - SLA"

    html_content = render_to_string(template_name, context)

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=sender_email,
        to=recipient,
        cc=cc_list,
        connection=connection
    )
    
    email.content_subtype = "html"
    
    email.attach_file(document.pdf_file.path)
    
    email.send()
    

def send_vac_app_received_email(company, candidate_name, vacancy_application, vacancy, sender, hrs):
    sender_password = sender.get_smtp_password()
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender_password)
    if error_message:
        print(f"SMTP Connection Failed: {error_message}")
        return  # Or raise/log as needed
    
    now = timezone.now()

    context = {
        'candidate_name': candidate_name,
        'vacancy_title': vacancy.title,
        'company_name': company,
        'application_date': vacancy_application.created_at.strftime('%B %d, %Y'),
        'vacancy_application': vacancy_application,  # For ID in footer
        'year': now.year,
        'created_by': vacancy.created_by,
    }

    html_content = render_to_string('emails/application_received.html', context)
    subject = f"Application Received for {vacancy.title} Role"

    print(f"Sending application confirmation to {vacancy_application.email}...")

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=sender.email_address,
            to=[vacancy_application.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send()
        print("Application received email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")
        # Optionally log or notify admin

def send_vac_app_accepted_email(sender, company, candidate_name, hr, cc, vacancy_application, vacancy):
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    if error_message:
        print(f"SMTP Error: {error_message}")
        return  # Handle gracefully

    context = {
        'candidate_name': candidate_name,
        'vacancy_title': vacancy.title,
        'company_name': company,
        'hr_email': hr.email,
        'hr_name': hr.get_full_name() or hr.username,
        'vacancy_application': vacancy_application,  # For ID
    }

    html_content = render_to_string('emails/application_accepted.html', context)
    subject = f"You're Moving Forward! Next Steps for the {vacancy.title} Role"

    print(f"Sending acceptance email to {vacancy_application.email}...")

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=sender.email_address,
            to=[vacancy_application.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send()
        print("Acceptance email sent successfully.")
    except Exception as e:
        print(f"Email failed: {e}")
        # Log or notify admin

def send_vac_app_rejected_email(sender, company, candidate_name, hr, cc, vacancy_application, vacancy):
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    if error_message:
        print(f"SMTP Error: {error_message}")
        return

    context = {
        'candidate_name': candidate_name,
        'vacancy_title': vacancy.title,
        'company_name': company,
        'hr_email': hr.email,
        'hr_name': hr.get_full_name() or hr.username,
        'vacancy_application': vacancy_application,  # For ID
    }

    html_content = render_to_string('emails/application_rejected.html', context)
    subject = f"An Update on Your Application for {vacancy.title} Role"

    print(f"Sending rejection email to {vacancy_application.email}...")

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=sender.email_address,
            to=[vacancy_application.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send()
        print("Rejection email sent.")
    except Exception as e:
        print(f"Email failed: {e}")


def send_interview_scheduled_email(sender, hr, cc, vacancy_application, interview):
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    if error_message:
        print(f"SMTP Error: {error_message}")
        return

    context = {
        'candidate_name': vacancy_application.get_full_name() or f"{vacancy_application.first_name} {vacancy_application.last_name}",
        'vacancy_title': interview.vacancy.title,
        'company_name': interview.tenant.name,
        'hr_email': hr.email,
        'hr_name': hr.get_full_name() or hr.username,
        'vacancy_application': vacancy_application,  # For ID
        'interview_date': interview.schedule_start.strftime('%B %d, %Y'),
        'interview_type': interview.is_virtual,
        'interview_time': interview.schedule_start.strftime('%I:%M %p'),
        'interview_timezone': interview.timezone,
        'interview_location': interview.physical_location,
        'interview_link': interview.virtual_link or interview.google_meet_link,
    }

    html_content = render_to_string('emails/interview_scheduled.html', context)
    subject = f"Your Interview for {interview.vacancy.title} Role"

    print(f"Sending interview scheduled email to {vacancy_application.email}...")

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=sender.email_address,
            to=[vacancy_application.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send()
        print("Interview scheduled email sent.")
    except Exception as e:
        print(f"Email failed: {e}")

def send_interview_updated_email(hr, vacancy_application, interview, old_schedule_start=None, old_was_virtual=None):
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(
        superuser.email_provider, superuser.email_address, superuser.get_smtp_password()
    )
    if error_message:
        print(f"SMTP Error: {error_message}")
        return
    if interview.tenant is not None:
        cc = [interview.scheduled_by.email, interview.tenant.admin.email]
    else:
        cc = [interview.scheduled_by.email]

    context = {
        'candidate_name': vacancy_application.get_full_name() or vacancy_application.email,
        'vacancy_title': interview.vacancy.title,
        'company_name': interview.tenant.name,
        'hr_email': hr.email,
        'hr_name': hr.get_full_name() or hr.username,
        'interview': interview,
        'new_interview_date': interview.schedule_start.strftime('%B %d, %Y'),
        'new_interview_time': interview.schedule_start.strftime('%I:%M %p'),
        'interview_timezone': interview.timezone,
        'interview_type': interview.is_virtual,
        'interview_location': interview.physical_location or "Not specified",
        'interview_link': interview.virtual_link or interview.google_meet_link,
        'old_schedule_start': old_schedule_start,
        'old_was_virtual': old_was_virtual,
    }

    html_content = render_to_string('emails/interview_updated.html', context)
    subject = f"Updated: Your Interview for {interview.vacancy.title}"

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=superuser.email_address,
            to=[vacancy_application.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send()
        print(f"Interview UPDATED email sent to {vacancy_application.applicant.email}")
    except Exception as e:
        print(f"Email failed (updated): {e}")

def send_interview_cancelled_email(hr, vacancy_application, interview):
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if error_message:
        print(f"SMTP Error: {error_message}")
        return

    context = {
        'candidate_name': vacancy_application.get_full_name() or f"{vacancy_application.first_name} {vacancy_application.last_name}",
        'vacancy_title': interview.vacancy.title,
        'company_name': interview.tenant.name,
        'hr_email': hr.email,
        'hr_name': hr.get_full_name() or hr.username,
        'vacancy_application': vacancy_application,  # For ID
    }

    html_content = render_to_string('emails/interview_cancelled.html', context)
    subject = f"Your Interview for {interview.vacancy.title} Role"

    print(f"Sending interview cancelled email to {vacancy_application.email}...")
    if interview.tenant is not None:
        cc = [interview.scheduled_by.email, interview.tenant.admin.email]
    else:
        cc = [interview.scheduled_by.email]

    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=superuser.email_address,
            to=[vacancy_application.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send()
        print("Interview cancelled email sent.")
    except Exception as e:
        print(f"Email failed: {e}")

def send_job_offer_email(request, application, interview, offer):
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if error_message:
        print(f"SMTP Error: {error_message}")
        return
    response_url = request.build_absolute_uri(
        reverse('offer_response', args=[offer.offer_token])
    )
    hr = interview.scheduled_by
    context = {
        'application': application,
        'offer': offer,
        'offer_response_url': response_url,
        'hr_name': hr.staff_profile.get_full_name() or hr.username,
        'hr_email': hr.email,
        'now': timezone.now(),
    }

    html_content = render_to_string('emails/job_offer.html', context)
    subject = f"Job Offer: {interview.vacancy.title}"

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=superuser.email_address,
        to=[application.email],
        cc=[hr.email, interview.tenant.admin.email],
        connection=connection
    )
    email.content_subtype = "html"

    # Attach the offer letter
    if offer.offer_letter:
        email.attach(
            filename=offer.offer_letter.name.split('/')[-1],
            content=offer.offer_letter.read(),
            mimetype='application/pdf'  # adjust if needed
        )
        offer.offer_letter.seek(0)  # reset file pointer

    try:
        email.send()
        offer.status = "sent"
        offer.sent_at = timezone.now()
        offer.save(update_fields=["status", "sent_at"])
        print(f"→ Job offer email sent to {application.email}")
    except Exception as e:
        print(f"Email sending failed: {e}")

def send_onboard_employee(request, application, user, password):
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())

    login_url = request.build_absolute_uri(reverse("login"))

    subject = "Welcome to the Team – Your Account Details"
    from_email = superuser.email_address
    to_email = [user.email]

    context = {
        "first_name": application.first_name,
        "email": user.email,
        "password": password,
        "login_url": login_url,
        "company_name": request.effective_tenant.name,
    }

    html_content = render_to_string(
        "emails/new_employee_onboarding.html",
        context
    )

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=from_email,
        to=to_email,
        cc=[application.vacancy.created_by.email, application.tenant.admin.email],
        connection=connection
    )

    email.content_subtype = "html"

    try:
        email.send()
        print(f"→ Onboarding email sent to {user.email}")
    except Exception as e:
        print(f"Email sending failed: {e}")

def send_conf_reg_pending(participant, access_url, dashboard_url, sender, cc):
    """
    Send HTML confirmation email via EmailMessage.
    participant: ConferenceParticipant instance
    access_url: absolute URL participant can use to view updates
    """
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    conference = participant.conference
    guest_user = get_object_or_404(GuestUser, email__iexact=participant.email)
    context = {
        'participant': participant,
        'conference': conference,
        # 'access_url': access_url,
        'dashboard_url': dashboard_url,
        'guest_user': guest_user
    }
    subject = f"Registration Confirmed: {conference.title}"
    html_body = render_to_string("emails/conf_reg_pending.html", context)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
    to = [participant.email]

    email = EmailMessage(subject=subject, body=html_body, from_email=sender.email_address, to=to, connection=connection)
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        # In production log error instead of failing user flow
        pass

def send_conf_reg_accepted(participant, access_url, dashboard_url, sender, cc):
    """Email sent to participant when organizer accepts the registration."""
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    conference = participant.conference
    qr_data_uri = _generate_qr_data_uri(access_url)
    context = {'participant': participant, 'conference': conference, 'access_url': access_url, 'dashboard_url': dashboard_url, "qr_data_uri": qr_data_uri,}
    subject = f"Registration confirmed: {conference.title}"
    html_body = render_to_string("emails/conf_reg_accepted.html", context)
    # from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
    email = EmailMessage(subject=subject, body=html_body, from_email=sender.email_address, to=[participant.email], connection=connection)
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass

def send_conf_reg_declined(participant, sender, cc):
    """Email sent to participant when registration is declined."""
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    conference = participant.conference
    context = {'participant': participant, 'conference': conference, 'organizer_contact': conference.organizer.email}
    subject = f"Registration declined: {conference.title}"
    html_body = render_to_string("emails/conf_reg_declined.html", context)
    # from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
    email = EmailMessage(subject=subject, body=html_body, from_email=sender.email_address, to=[participant.email])
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass

def send_payment_failed_email(participant, conference, retry_url, sender, cc):
    """Email sent to participant when organizer accepts the registration."""
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    conference = participant.conference
    context = {'participant': participant, 'conference': conference, 'access_url': retry_url}
    subject = f"Registration confirmed: {conference.title}"
    html_body = render_to_string("emails/payment_failed.html", context)
    # from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')
    email = EmailMessage(subject=subject, body=html_body, from_email=sender.email_address, to=[participant.email], connection=connection)
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass


def send_conference_reminder(participant, conference, sender, cc):
    connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email_address, sender.get_smtp_password())
    guest_user = GuestUser.objects.filter(email__iexact=participant.email).first()
    if guest_user is not None:
        dashboard_url = build_guest_dashboard_url(guest_user.token)
        is_guest_user = True
    else:
        user = CustomUser.objects.filter(email__iexact=participant.email).first()
        if user is not None:
            dashboard_url = build_user_activity_dashboard_url(user)
    access_url = build_conference_access_url(conference, participant)
    qr_data_uri = _generate_qr_data_uri(access_url)
    context = {'participant': participant, 'conference': conference, 'access_url': access_url, 'dashboard_url': dashboard_url, 
                'is_guest_user': is_guest_user, 'guest_user': guest_user, "qr_data_uri": qr_data_uri,}
    subject = f"Reminder: {conference.title}"
    html_body = render_to_string("emails/conference_reminder.html", context)
    # for participant in participants:
    email = EmailMessage(subject=subject, body=html_body, from_email=sender.email_address, to=[participant.email], connection=connection)
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass

def send_conference_update_email(participant, conference):

    guest_user = GuestUser.objects.filter(email__iexact=participant.email).first()
    if guest_user is not None:
        dashboard_url = build_guest_dashboard_url(guest_user.token)
    else:
        user = CustomUser.objects.filter(email__iexact=participant.email).first()
        if user is not None:
            dashboard_url = build_user_activity_dashboard_url(user)
    access_url = build_conference_access_url(conference, participant)
    qr_data_uri = _generate_qr_data_uri(access_url)

    subject = f"Update: {conference.title}"
    context = {
        'conference': conference,
        'participant_name': participant.full_name if participant.full_name else participant.first_name or "Participant",
        'participant_attendance_mode': participant.attendance_mode if hasattr(participant, 'attendance_mode') else None,
        'access_url': access_url,
        'dashboard_url': dashboard_url,  # or your dashboard URL name
        'site_name': "TeamManager",
        'company_name': "TeamManager Inc.",
        'current_year': timezone.now().year,
        'qr_data_uri': qr_data_uri,
    }
    html_content = render_to_string('emails/update_conference_participants.html', context)
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    email = EmailMessage(subject=subject, body=html_content, from_email=superuser.email_address, to=[participant], connection=connection)
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        # In production log error instead of failing user flow
        print("Error sending email:", error_message)
        pass


def send_remittance_success_email(request, remittance):
    """Send email notification for successful remittance"""
    wallet_url = request.build_absolute_uri(reverse("tenant_wallet"))
    # admin_wallet_url = request.build_absolute_uri(reverse("admin_remittance_dashboard"))

    
    subject = f"Payment {remittance.reference} Completed Successfully"
    if remittance.company_profile and remittance.company_profile.email:
        tenant_email = remittance.company_profile.email

    elif remittance.tenant and remittance.tenant.admin.email:
        tenant_email = remittance.tenant.admin.email
    
    context = {
        'remittance': remittance,
        'tenant': remittance.tenant,
        'company_profile': remittance.company_profile,
        'amount': remittance.amount,
        'bank_reference': remittance.bank_reference,
        'completion_date': remittance.completion_date,
        'wallet_url': wallet_url,
        'current_date': timezone.now(),
    }
    
    html_message = render_to_string('emails/remittance_success.html', context)
    plain_message = render_to_string('emails/remittance_success.txt', context)
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    
    
    # Send to superuser
    email = EmailMessage(
        subject=f" {subject}",
        body=html_message,
        from_email=superuser.email_address,
        to=[superuser.email, tenant_email],
        connection=connection
    )
    email.content_subtype="html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass

def send_remittance_success_for_user_email(request, remittance):
    """Send email notification for successful remittance"""
    wallet_url = request.build_absolute_uri(reverse("tenant_wallet"))
    # admin_wallet_url = request.build_absolute_uri(reverse("admin_remittance_dashboard"))

    
    subject = f"Payment {remittance.reference} Completed Successfully"
    if remittance.company_profile and remittance.company_profile.user.email:
        user_email = remittance.company_profile.user.email

    elif remittance.owner and remittance.owner.email:
        user_email = remittance.owner.email
    
    context = {
        'remittance': remittance,
        'tenant': remittance.owner,
        'company_profile': remittance.company_profile,
        'amount': remittance.amount,
        'bank_reference': remittance.bank_reference,
        'completion_date': remittance.completion_date,
        'wallet_url': wallet_url,
        'current_date': timezone.now(),
    }
    
    html_message = render_to_string('emails/remittance_success.html', context)
    plain_message = render_to_string('emails/remittance_success.txt', context)
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    
    
    # Send to superuser
    email = EmailMessage(
        subject=f" {subject}",
        body=html_message,
        from_email=superuser.email_address,
        to=[superuser.email, user_email],
        connection=connection
    )
    email.content_subtype="html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass

def send_remittance_failed_email(request, remittance, reason):
    """Send email notification for failed remittance"""
    wallet_url = request.build_absolute_uri(reverse("admin_remittance_dashboard"))
    retry_url = request.build_absolute_uri(reverse("retry_remittance"))
    
    subject = f"Remittance {remittance.reference} Failed"
    
    context = {
        'remittance': remittance,
        'tenant': remittance.tenant,
        'company_profile': remittance.company_profile,
        'amount': remittance.amount,
        'reason': reason,
        'wallet_url': wallet_url,
        'retry_url': retry_url,
        'current_date': timezone.now(),
    }
    
    html_message = render_to_string('emails/remittance_failed.html', context)
    plain_message = render_to_string('emails/remittance_failed.txt', context)
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    email = EmailMessage(
            subject=f"[URGENT] {subject}",
            body=html_message,
            from_email=superuser.email_address,
            to=[superuser.email],
            connection=connection
        )
    email.content_subtype="html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass


def send_remittance_for_user_failed_email(request, remittance, reason):
    """Send email notification for failed remittance"""
    wallet_url = request.build_absolute_uri(reverse("admin_remittance_dashboard"))
    retry_url = request.build_absolute_uri(reverse("retry_remittance"))
    
    subject = f"Remittance {remittance.reference} Failed"
    
    context = {
        'remittance': remittance,
        'tenant': remittance.owner,
        'company_profile': remittance.company_profile,
        'amount': remittance.amount,
        'reason': reason,
        'wallet_url': wallet_url,
        'retry_url': retry_url,
        'current_date': timezone.now(),
    }
    
    html_message = render_to_string('emails/remittance_failed.html', context)
    plain_message = render_to_string('emails/remittance_failed.txt', context)
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    email = EmailMessage(
            subject=f"[URGENT] {subject}",
            body=html_message,
            from_email=superuser.email_address,
            to=[superuser.email],
            connection=connection
        )
    email.content_subtype="html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass


def send_bank_verification_request_email(request, company_profile):
    if settings.DEBUG:
        edit_company_profile = f"http://{company_profile.tenant.slug}.localhost:8000/admins/company-profile/"
    else:
        edit_company_profile = f"https://{company_profile.tenant.slug}.teammanager.ng/admins/company-profile/"
    
    subject = f"Bank Verification Request - {company_profile.company_name}"
    
    context = {
        'company_profile': company_profile,
        'tenant': company_profile.tenant,
        'user': request.user,
        'edit_company_profile': edit_company_profile,
    }
    
    html_message = render_to_string('emails/bank_verification_request.html', context)
    plain_message = render_to_string('emails/bank_verification_request.txt', context)
    
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    admin_email = company_profile.email or company_profile.tenant.admin.email

    email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=superuser.email_address,
            to=[admin_email],
            connection=connection
        )
    email.content_subtype="html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass

def send_bank_verification_request_for_staff_email(request, staff_profile):
    edit_staff_profile = request.build_absolute_uri(reverse("edit_my_profile"))
    print(f"User Profile for bank verification: {staff_profile}")
    
    subject = f"Bank Verification Request - {staff_profile.user.username}"
    
    context = {
        'company_profile': staff_profile,
        'tenant': staff_profile.tenant,
        'user': request.user,
        'edit_company_profile': edit_staff_profile,
    }
    
    html_message = render_to_string('emails/bank_verification_request_for_user.html', context)
    
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    admin_email = staff_profile.user.email

    email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=superuser.email_address,
            to=[admin_email],
            connection=connection
        )
    email.content_subtype="html"
    try:
        print(f"Sending mail to {admin_email} for bank verification request")
        email.send(fail_silently=False)
        print(f"Email sent to {admin_email} successfully")
    except Exception:
        print(f"Email failed to send to {admin_email}")

def send_bank_verification_request_for_user_email(request, user_profile):
    edit_user_profile = request.build_absolute_uri(reverse("edit_user_profile"))
    print(f"User Profile for bank verification: {user_profile}")
    
    subject = f"Bank Verification Request - {user_profile.user.username}"
    
    context = {
        'company_profile': user_profile,
        'tenant': user_profile.user,
        'user': request.user,
        'edit_company_profile': edit_user_profile,
    }
    
    html_message = render_to_string('emails/bank_verification_request_for_user.html', context)
    
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 

    admin_email = user_profile.user.email

    email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=superuser.email_address,
            to=[admin_email],
            connection=connection
        )
    email.content_subtype="html"
    try:
        print(f"Sending mail to {admin_email} for bank verification request")
        email.send(fail_silently=False)
        print(f"Email sent to {admin_email} successfully")
    except Exception:
        print(f"Email failed to send to {admin_email}")

def send_bank_verification_confirmation_email(company_profile, admin_user):
    """Send email to tenant confirming bank verification"""
    
    subject = "Your Bank Details Have Been Verified"
    
    context = {
        'company_profile': company_profile,
        'tenant': company_profile.tenant,
        'admin_user': admin_user,
        'verification_date': company_profile.bank_verification_date,
    }
    
    html_message = render_to_string('emails/bank_verification_confirmation.html', context)
    plain_message = render_to_string('emails/bank_verification_confirmation.txt', context)
    
    tenant_email = company_profile.email or company_profile.tenant.admin.email
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    
    if tenant_email:
        email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=superuser.email_address,
                to=[tenant_email],
                connection=connection
            )
        email.content_subtype="html"
        try:
            email.send(fail_silently=False)
        except Exception:
            pass



def send_bank_verification_confirmation_for_user_email(user_profile, admin_user):
    """Send email to tenant confirming bank verification"""
    
    subject = "Your Bank Details Have Been Verified"
    
    context = {
        'company_profile': user_profile,
        'tenant': user_profile.user,
        'admin_user': admin_user,
        'verification_date': user_profile.bank_verification_date,
    }
    
    html_message = render_to_string('emails/bank_verification_confirmation.html', context)
    plain_message = render_to_string('emails/bank_verification_confirmation.txt', context)
    
    tenant_email = user_profile.user.email
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    
    if tenant_email:
        email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=superuser.email_address,
                to=[tenant_email],
                connection=connection
            )
        email.content_subtype="html"
        try:
            email.send(fail_silently=False)
        except Exception:
            pass

def send_bank_verification_rejection_email(request, company_profile):
    """Send email to tenant about bank verification rejection"""
    
    subject = "Bank Details Verification - Action Required"
    edit_company_profile = request.build_absolute_uri(reverse("edit_company_profile"))

    
    context = {
        'company_profile': company_profile,
        'tenant': company_profile.tenant,
        'admin_user': request.user,
        'edit_company_profile': edit_company_profile,
    }
    
    html_message = render_to_string('emails/bank_verification_rejection.html', context)
    plain_message = render_to_string('emails/bank_verification_rejection.txt', context)
    
    tenant_email = company_profile.email or company_profile.tenant.admin.email
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 
    if tenant_email:
        email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=superuser.email_address,
                to=[tenant_email],
                connection=connection
            )
        email.content_subtype="html"
        try:
            email.send(fail_silently=False)
        except Exception:
            pass

def send_bank_verification_rejection_for_user_email(request, user_profile):
    """Send email to tenant about bank verification rejection"""
    
    subject = "Bank Details Verification - Action Required"
    edit_user_profile = request.build_absolute_uri(reverse("edit_user_profile"))

    
    context = {
        'company_profile': user_profile,
        'tenant': user_profile.user,
        'admin_user': request.user,
        'edit_company_profile': edit_user_profile,
    }
    
    html_message = render_to_string('emails/bank_verification_rejection.html', context)
    plain_message = render_to_string('emails/bank_verification_rejection.txt', context)
    
    tenant_email = user_profile.user.email
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password()) 
    if tenant_email:
        email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=superuser.email_address,
                to=[tenant_email],
                connection=connection
            )
        email.content_subtype="html"
        try:
            print(f"Sending mail to {tenant_email}")
            email.send(fail_silently=False)
            print(f"Email sent to {tenant_email} successfully")
        except Exception:
            print(f"Email failed to send to {tenant_email}")
            # pass

def send_booking_request_email(booking):
    booking_type = booking.booking_type
    host_user = booking_type.host_user
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    subject=f"Booking Request!"
    if settings.DEBUG:
        if host_user.tenant:
            booking_list_url = f"http://{host_user.tenant.slug}.localhost:8000/bookings/list/"
        else:
            booking_list_url = f"http://localhost:8000/bookings/list/"
    else:
        if host_user.tenant:
            booking_list_url = f"https://{host_user.tenant.slug}.teammanager.ng/bookings/list/"
        else:
            booking_list_url = f"https://teammanager.ng/bookings/list/"
            
    context={"booking":booking, "booking_list_url":booking_list_url}
    html_message = render_to_string('emails/booking_request.html', context)
    if booking_type.host_user != booking_type.created_by:
        cc=[]
    else:
        cc=[booking_type.created_by.email]
    if connection:
        email = EmailMessage(subject=subject, body=html_message, from_email=superuser.email_address, 
                             cc=cc, to=[booking_type.host_user.email], connection=connection)
        email.content_subtype="html"
        try:
            print(f"Sending mail to booking request")
            email.send(fail_silently=False)
            print(f"Email sent")
        except Exception:
            print(f"Email failed to send booking request")
            # pass

def send_booking_received_email(booking):
    booking_type = booking.booking_type
    host_user = booking_type.host_user
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    subject=f"Booking Request!"
    if settings.DEBUG:
        if host_user.tenant:
            booking_list_url = f"http://{host_user.tenant.slug}.localhost:8000/bookings/list/"
        else:
            booking_list_url = f"http://localhost:8000/bookings/list/"
    else:
        if host_user.tenant:
            booking_list_url = f"https://{host_user.tenant.slug}.teammanager.ng/bookings/list/"
        else:
            booking_list_url = f"https://teammanager.ng/bookings/list/"
            
    context={"booking":booking, "booking_list_url":booking_list_url}
    html_message = render_to_string('emails/booking_received.html', context)
    
    if connection:
        email = EmailMessage(subject=subject, body=html_message, from_email=superuser.email_address, to=[booking.email], connection=connection)
        email.content_subtype="html"
        try:
            print(f"Sending mail to booking request")
            email.send(fail_silently=False)
            print(f"Email sent")
        except Exception:
            print(f"Email failed to send booking request")
            # pass

def send_booking_confirmed_email(booking):
    """
    Sent to the booker when booking moves to 'confirmed'
    """
    booking_type = booking.booking_type
    host_user = booking_type.host_user
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    if not superuser or not superuser.email_address:
        print("No superuser with email credentials found")
        return

    connection, error = get_email_smtp_connection(
        superuser.email_provider,
        superuser.email_address,
        superuser.get_smtp_password()
    )
    if not connection:
        print(f"SMTP connection failed: {error}")
        return
    if settings.DEBUG:
        if host_user.tenant:
            booking_list_url = f"http://{host_user.tenant.slug}.localhost:8000/bookings/list/"
        else:
            booking_list_url = f"http://localhost:8000/bookings/list/"
    else:
        if host_user.tenant:
            booking_list_url = f"https://{host_user.tenant.slug}.teammanager.ng/bookings/list/"
        else:
            booking_list_url = f"https://teammanager.ng/bookings/list/"

    subject = "Your Booking is Confirmed ✓"

    # Build context
    context = {
        "booking": booking,
        "booking_list_url": booking_list_url,
    }

    html_message = render_to_string('emails/booking_confirmed.html', context)

    email = EmailMessage(
        subject=subject,
        body=html_message,
        from_email=superuser.email_address,
        to=[booking.email],
        connection=connection,
    )
    email.content_subtype = "html"

    try:
        email.send(fail_silently=False)
        print(f"Confirmed email sent to {booking.email or booking.user}")
    except Exception as e:
        print(f"Failed to send confirmed email: {e}")


def send_booking_declined_email(booking):
    """
    Sent to the booker when booking is declined/rejected
    """
    booking_type = booking.booking_type
    host_user = booking_type.host_user
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    if not superuser or not superuser.email_address:
        return

    connection, error = get_email_smtp_connection(
        superuser.email_provider,
        superuser.email_address,
        superuser.get_smtp_password()
    )
    if not connection:
        return
    
    if settings.DEBUG:
        if host_user.tenant:
            booking_list_url = f"http://{host_user.tenant.slug}.localhost:8000/bookings/list/"
        else:
            booking_list_url = f"http://localhost:8000/bookings/list/"
    else:
        if host_user.tenant:
            booking_list_url = f"https://{host_user.tenant.slug}.teammanager.ng/bookings/list/"
        else:
            booking_list_url = f"https://teammanager.ng/bookings/list/"

    subject = "Update on Your Booking Request"

    context = {
        "booking": booking,
        "booking_list_url": booking_list_url,
    }

    html_message = render_to_string('emails/booking_declined.html', context)

    email = EmailMessage(
        subject=subject,
        body=html_message,
        from_email=superuser.email_address,
        to=[booking.email],
        connection=connection,
    )
    email.content_subtype = "html"

    try:
        email.send(fail_silently=False)
        print(f"Declined email sent to {booking.email or booking.user}")
    except Exception as e:
        print(f"Failed to send declined email: {e}")

def send_subscription_confirmation(subscription, detail_url, user=None, tenant=None):
    """
    Send email notification for successful subscription payment
    """
    subject = f"Subscription Activated: {subscription.plan.name} Plan"
    
    # Determine recipient email
    recipient_email = None
    if subscription.user and subscription.user.email:
        recipient_email = subscription.user.email
    elif subscription.tenant and subscription.tenant.admin.email:
        recipient_email = subscription.tenant.admin.email
    
    if not recipient_email:
        logger.error(f"No recipient email found for subscription {subscription.id}")
        return
    
    # Calculate next billing date (assuming monthly billing)
    next_billing_date = subscription.end_date
    
    context = {
        'subscription': subscription,
        'user': user,
        'tenant': tenant,
        'plan_name': subscription.plan.name,
        'amount': subscription.get_current_monthly_rate(),
        'start_date': subscription.start_date,
        'end_date': subscription.end_date,
        'next_billing_date': next_billing_date,
        'detail_url': detail_url,
        # 'is_trial': subscription.is_trial,
        'trial_end_date': subscription.trial_end_date,
        'current_date': timezone.now(),
    }
    
    html_message = render_to_string('emails/subscription_confirmation.html', context)
    
    # Get superuser as sender
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    
    if recipient_email:
        email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=superuser.email_address,
                to=[recipient_email],
                connection=connection
            )
        email.content_subtype="html"
        try:
            email.send(fail_silently=False)
        except Exception:
            pass

def send_subscription_payment_failed(subscription, retry_url, user=None, tenant=None):
    """
    Send email notification for failed subscription payment
    """
    subject = f"Payment Failed: {subscription.plan.name} Subscription"
    
    # Determine recipient email
    recipient_email = None
    if subscription.user and subscription.user.email:
        recipient_email = subscription.user.email
    elif subscription.tenant and subscription.tenant.admin.email:
        recipient_email = subscription.tenant.admin.email
    
    if not recipient_email:
        logger.error(f"No recipient email found for subscription {subscription.id}")
        return
    
    context = {
        'subscription': subscription,
        'user': user,
        'tenant': tenant,
        'plan_name': subscription.plan.name,
        'amount': subscription.get_current_monthly_rate(),
        'retry_url': retry_url,
        'current_date': timezone.now(),
        'support_email': settings.SUPPORT_EMAIL or 'support@teammanager.ng',
    }
    
    html_message = render_to_string('emails/subscription_payment_failed.html', context)
    
    # Get superuser as sender
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    
    if recipient_email:
        email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=superuser.email_address,
                to=[recipient_email],
                connection=connection
            )
        email.content_subtype="html"
        try:
            email.send(fail_silently=False)
        except Exception:
            pass

def send_external_event_invite_email(event, recipient_email: str, inviter, personal_message: str = ""):
    """
    Send an event invitation to an external (non-registered) participant.
 
    Args:
        event           – Event model instance
        recipient_email – Recipient's email address (string)
        inviter         – CustomUser who is sending the invite
        personal_message – Optional free-text note from the inviter
    """
    inviter_name = inviter.get_full_name() or inviter.username
 
    subject = f"You're invited: {event.title}"
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    connection, error = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
 
    # HTML version (optional – uses a template if you have one)
    try:
        html_body = render_to_string('emails/external_event_invite.html', {
            'event':            event,
            'inviter':          inviter,
            'inviter_name':     inviter_name,
            'personal_message': personal_message,
            'site_name':        getattr(settings, 'SITE_NAME', 'TeamManager'),
        })
    except Exception:
        html_body = None   # fall back to plain text if template missing
    email = EmailMessage(
        subject=subject, body=html_body, from_email=superuser.email_address, to=[recipient_email], connection=connection
    )
    email.content_subtype = "html"
    try:
        email.send(fail_silently=False)
    except Exception:
        pass


# def send_subscription_expiring_warning(subscription, days_remaining, recipient_email, is_admin=False, context=None):
#     """
#     Send email notification for subscription expiring soon
#     """
#     from django.template.loader import render_to_string
#     from django.core.mail import EmailMessage
#     from documents.models import CustomUser
    
#     if days_remaining <= 0:
#         subject = f"URGENT: Your subscription has expired"
#     elif days_remaining == 1:
#         subject = f"Your subscription expires TOMORROW!"
#     elif days_remaining <= 7:
#         subject = f"Your subscription expires in {days_remaining} days"
#     else:
#         subject = f"Your subscription expires in {days_remaining} days"
    
#     # Determine recipient type for email content
#     if is_admin:
#         subject = f"[ADMIN] {subject}"
    
#     # Prepare context
#     email_context = {
#         'subscription': subscription,
#         'days_remaining': days_remaining,
#         'end_date': subscription.end_date,
#         'plan_name': subscription.plan.name,
#         'is_admin': is_admin,
#         'current_date': timezone.now(),
#     }
    
#     if context:
#         email_context.update(context)
    
#     # Choose appropriate template
#     if is_admin:
#         html_message = render_to_string('emails/subscription_expiring_admin.html', email_context)
#     else:
#         html_message = render_to_string('emails/subscription_expiring_user.html', email_context)
    
#     # Get superuser as sender
#     superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
#     if not superuser:
#         logger.error("No superuser found for sending emails")
#         return
    
#     connection, error_message = get_email_smtp_connection(
#         superuser.email_provider, 
#         superuser.email_address, 
#         superuser.get_smtp_password()
#     )
    
#     if recipient_email:
#         email = EmailMessage(
#             subject=subject,
#             body=html_message,
#             from_email=superuser.email_address,
#             to=[recipient_email],
#             connection=connection
#         )
#         email.content_subtype = "html"
#         try:
#             email.send(fail_silently=False)
#             logger.info(f"Expiration warning email sent to {recipient_email} for subscription {subscription.id}")
#         except Exception as e:
#             logger.error(f"Failed to send expiration email to {recipient_email}: {str(e)}")

def send_subscription_expiring_warning(subscription, days_remaining, recipient_email, is_admin=None, context=None):
    """
    Send email notification for subscription expiring soon
    
    Args:
        subscription: The subscription object
        days_remaining: Number of days until expiration
        recipient_email: Email address to send to
        is_admin: True for admin users, False for regular users, 
                  None will auto-detect based on recipient
        context: Additional context for template
    """
    from django.template.loader import render_to_string
    from django.core.mail import EmailMessage
    from documents.models import CustomUser
    
    # Auto-detect if is_admin is not provided
    if is_admin is None:
        # Check if recipient is a tenant admin
        if subscription.tenant and subscription.tenant.admin and subscription.tenant.admin.email == recipient_email:
            is_admin = True
        # Check if recipient is superuser
        elif CustomUser.objects.filter(email=recipient_email, is_superuser=True).exists():
            is_admin = True
        else:
            is_admin = False
    
    # Determine email subject based on days remaining and admin status
    if days_remaining <= 0:
        subject = f"URGENT: Your subscription has expired"
    elif days_remaining == 1:
        subject = f"Your subscription expires TOMORROW!"
    elif days_remaining <= 7:
        subject = f"Your subscription expires in {days_remaining} days"
    else:
        subject = f"Your subscription expires in {days_remaining} days"
    
    # Add [ADMIN] prefix for admin emails
    if is_admin:
        subject = f"[ADMIN] {subject}"
    
    # Prepare context
    email_context = {
        'subscription': subscription,
        'days_remaining': days_remaining,
        'end_date': subscription.end_date,
        'plan_name': subscription.plan.name,
        'is_admin': is_admin,
        'current_date': timezone.now(),
    }
    
    if context:
        email_context.update(context)
    
    # Choose appropriate template based on admin status
    if is_admin:
        html_message = render_to_string('emails/subscription_expiring_admin.html', email_context)
    else:
        html_message = render_to_string('emails/subscription_expiring_user.html', email_context)
    
    # Get superuser as sender
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    if not superuser:
        logger.error("No superuser found for sending emails")
        return
    
    connection, error_message = get_email_smtp_connection(
        superuser.email_provider, 
        superuser.email_address, 
        superuser.get_smtp_password()
    )
    
    if recipient_email:
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=superuser.email_address,
            to=[recipient_email],
            connection=connection
        )
        email.content_subtype = "html"
        try:
            email.send(fail_silently=False)
            logger.info(f"Expiration warning email sent to {recipient_email} for subscription {subscription.id}")
        except Exception as e:
            logger.error(f"Failed to send expiration email to {recipient_email}: {str(e)}")

def send_trial_welcome_email(user, tenant=None, days=7, is_tenant_user=False):
    """
    Send welcome email to new user with trial information
    """
    from django.template.loader import render_to_string
    from django.core.mail import EmailMessage
    from django.urls import reverse
    from django.conf import settings
    
    subject = "Welcome! Start Your 7-Day Free Trial"
    
    # Build subscription URL
    if is_tenant_user:
        # Tenant user - they need to contact admin or admin can subscribe
        subscribe_url = None
        contact_admin = True
    else:
        # Personal user - can subscribe directly
        subscribe_url = settings.SITE_URL + reverse('create_subscription')
        contact_admin = False
    
    context = {
        'user': user,
        'tenant': tenant,
        'days': days,
        'trial_end_date': user.subscription_end_date,
        'is_tenant_user': is_tenant_user,
        'subscribe_url': subscribe_url,
        'contact_admin': contact_admin,
        'admin_email': tenant.admin.email if tenant and tenant.admin else None,
        'current_date': timezone.now(),
    }
    
    html_message = render_to_string('emails/trial_welcome.html', context)
    
    # Get superuser as sender
    from documents.models import CustomUser
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    if not superuser:
        logger.error("No superuser found for sending emails")
        return
    
    from .mail_connection import get_email_smtp_connection
    connection, error_message = get_email_smtp_connection(
        superuser.email_provider, 
        superuser.email_address, 
        superuser.get_smtp_password()
    )
    
    if user.email:
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=superuser.email_address,
            to=[user.email],
            connection=connection
        )
        email.content_subtype = "html"
        try:
            email.send(fail_silently=False)
            logger.info(f"Trial welcome email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send trial welcome email to {user.email}: {str(e)}")