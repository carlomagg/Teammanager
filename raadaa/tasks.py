from celery import shared_task
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from tenants.models import Tenant
from documents.models import ConferenceParticipant, Conference,  GuestUser, CustomUser, Folder
from documents.viewfuncs.helper_funcs.access_urls import build_conference_access_url, build_guest_dashboard_url, build_user_activity_dashboard_url
from documents.viewfuncs.send_mails import send_conf_reg_accepted, send_conference_update_email, send_conference_reminder
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def conf_bulk_accept_and_notify(self, participant_ids, conference_id, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        conference = Conference.objects.get(id=conference_id)
        requesting_user = User.objects.get(id=user_id)

        if not (requesting_user == conference.organizer or requesting_user.is_staff):
            raise PermissionDenied("No permission")

        participants = ConferenceParticipant.objects.filter(
            id__in=participant_ids,
            conference=conference,
            status="pending"
        )

        accepted_count = 0
        errors = []

        superuser = CustomUser.objects.filter(is_superuser=True).first()

        for participant in participants:
            try:
                print(f"Accepting participant: {participant}")
                participant.accept()  # your existing method

                access_url = build_conference_access_url(conference, participant)

                guest_user = GuestUser.objects.filter(email__iexact=participant.email).first()
                if guest_user:
                    dashboard_url = build_guest_dashboard_url(guest_user.token)
                else:
                    user = CustomUser.objects.filter(email__iexact=participant.email).first()
                    dashboard_url = build_user_activity_dashboard_url(user) if user else None

                cc = [conference.organizer.email] if conference.organizer.email else []

                send_conf_reg_accepted(
                    participant,
                    access_url,
                    dashboard_url,
                    sender=superuser,
                    cc=cc
                )

                accepted_count += 1

            except Exception as exc:
                errors.append(f"Participant {participant.id} ({participant.email}): {str(exc)}")
                self.retry(exc=exc, countdown=60)  # optional: retry single failure

        result = {
            "success": True,
            "accepted": accepted_count,
            "total_requested": len(participant_ids),
            "errors": errors,
        }

        return result

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    
@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_conference_update_notifications(self, conference_id):
    try:
        conference = Conference.objects.get(id=conference_id)
    except Conference.DoesNotExist:
        return {"success": False, "reason": "Conference not found"}

    # Find participants who should receive the update
    participants = ConferenceParticipant.objects.filter(
        conference_id=conference_id,
        status='accepted',
        is_confirmed=True
    )

    if not participants.exists():
        return {"success": True, "sent": 0, "message": "No accepted/confirmed participants"}

    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    if not superuser:
        return {"success": False, "reason": "No superuser found for email sending"}

    sent_count = 0
    errors = []

    for participant in participants.iterator():  # memory efficient
        try:
            send_conference_update_email(participant, conference)

            sent_count += 1

        except Exception as exc:
            errors.append(f"Participant {participant.id} ({participant.email}): {str(exc)}")
            # Optional: self.retry(exc=exc) — but usually better to continue with others

    return {
        "success": True,
        "sent": sent_count,
        "total": participants.count(),
        "errors": errors[:10],  # limit to avoid huge result payload
        "errors_count": len(errors),
    }

@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_conference_reminders_task(self, conference_id, sender_id, cc_emails):
    """
    Background task to send reminder emails to all accepted & confirmed participants
    of a conference.
    """
    try:
        conference = Conference.objects.get(id=conference_id)
        sender = CustomUser.objects.get(id=sender_id)
    except (Conference.DoesNotExist, CustomUser.DoesNotExist) as e:
        logger.error("Cannot send reminders: %s", e)
        return {"success": False, "reason": str(e)}

    participants = ConferenceParticipant.objects.filter(
        conference=conference,
        status='accepted',
        is_confirmed=True
    )

    if not participants.exists():
        return {"success": True, "sent": 0, "message": "No participants to remind"}

    sent_count = 0
    errors = []

    # We cannot use request.build_absolute_uri() here → we need to build URLs manually
    # Assuming your site runs on https://example.com – best to use settings
    from django.conf import settings
    base_url = getattr(settings, 'BASE_SITE_URL', 'https://yourdomain.com')
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()

    for participant in participants.iterator():
        try:
            send_conference_reminder(participant, conference, sender, cc_emails)

            sent_count += 1

            # Optional gentle rate limiting
            # import time
            # time.sleep(0.4)   # ~150 emails / minute

        except Exception as exc:
            errors.append(f"Participant {participant.id} ({participant.email}): {exc}")
            logger.exception("Failed to send reminder to %s", participant.email)

    result = {
        "success": True,
        "sent": sent_count,
        "total": participants.count(),
        "errors_count": len(errors),
    }

    if errors:
        logger.warning("Reminder batch completed with %d errors", len(errors))

    return result

@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def create_default_folders_user(self, user_id):
    try:
        user = CustomUser.objects.get(id=user_id)
        tenant = getattr(user, 'tenant', None)
        default_folders = [
            {"name": "Personal", "parent": None, "description": "Personal Documents", "tenant": tenant},
            {"name": "Work", "parent": None, "description": "Work Documents", "tenant": tenant},
            {"name": "My Pictures", "parent": None, "description": "My Pictures", "tenant": tenant},
            {"name": "My Videos", "parent": None, "description": "My Videos", "tenant": tenant},
            {"name": "My Certificates", "parent": None, "description": "My Certificates", "tenant": tenant},
            {"name": "External", "parent": None, "description": "External Folder to receive files", "tenant": tenant},
        ]
        for folder in default_folders:
            Folder.objects.create(**folder, created_by=user)
        logger.info("Created %d default folders for user %s", len(default_folders), user_id)
        return True
    except CustomUser.DoesNotExist:
        logger.error("create_default_folders_user: User %s not found", user_id)
        return False
    except Exception as exc:
        logger.exception("create_default_folders_user failed for user %s: %s", user_id, exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def create_default_folders_org(self, tenant_id):
    try:
        tenant = Tenant.objects.get(id=tenant_id)
        default_folders = [
            {"name": "Company Policy", "parent": None, "description": "Company Policy Documents", "tenant": tenant, "is_public": True},
            {"name": "Employment Letters", "parent": None, "description": "Staff Employment or Offer Letters", "tenant": tenant},
            {"name": "KYC Forms", "parent": None, "description": "Staff KYC Forms", "tenant": tenant},
            {"name": "Performance Reports", "parent": None, "description": "Staff Performance Reports", "tenant": tenant, "is_public": True},
            {"name": "Products or Services", "parent": None, "description": "Company Products or Services", "tenant": tenant, "is_public": True},
            {"name": "CAC and Incorporation Folder", "parent": None, "description": "CAC and Incorporation Documents", "tenant": tenant},
            {"name": "Tax and Fees", "parent": None, "description": "Tax and Fees Documents", "tenant": tenant},
            {"name": "Brand Identity", "parent": None, "description": "Brand Identity Documents: Logos, Colours, etc", "tenant": tenant, "is_public": True},
            {"name": "Annual Reports", "parent": None, "description": "Annual Reports", "tenant": tenant, "is_public": True},
            {"name": "External", "parent": None, "description": "External Folder to receive files", "tenant": tenant, "is_public": True},
        ]
        for folder in default_folders:
            Folder.objects.create(**folder, created_by=tenant.admin)
        logger.info("Created default org folders for tenant %s", tenant_id)
        return True
    except Tenant.DoesNotExist:
        logger.error("create_default_folders_org: Tenant %s not found", tenant_id)
        return False
    except Exception as exc:
        logger.exception("create_default_folders_org failed for tenant %s: %s", tenant_id, exc)
        raise self.retry(exc=exc, countdown=60)