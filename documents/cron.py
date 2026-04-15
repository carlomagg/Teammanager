from django_cron import CronJobBase, Schedule
from datetime import date, timedelta
from django.utils.timezone import now
from documents.models import StaffProfile, Notification, Event, Conference, ConferenceParticipant, CustomUser
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from django.urls import reverse
from datetime import timedelta
import logging,json
from typing import List, Optional, Any

from tenants.models import Subscription
from .viewfuncs.mail_connection import get_email_smtp_connection

class BirthdayNotificationCronJob(CronJobBase):
    RUN_AT_TIMES = ['00:00']  # 12 AM daily

    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'documents.birthday_notification_cron'  # unique identifier

    def do(self):
        today = date.today()
        month = today.month
        day = today.day

        birthdays = StaffProfile.objects.filter(
            date_of_birth__month=month,
            date_of_birth__day=day
        )

        for staff in birthdays:
            title = f"It's {staff.full_name}'s Birthday Today! 🎉"
            if not Notification.objects.filter(title=title, type='birthday', created_at__date=today).exists():
                Notification.objects.create(
                    title=title,
                    type='birthday',
                    message='Wish them a happy birthday!',
                    is_active=True,
                    expires_at=now() + timedelta(hours=24)
                )


class EngagementNudgeCronJob(CronJobBase):
    """
    Daily cron job that generates engagement nudge notifications
    for users who haven't interacted with key features recently.
    """
    RUN_AT_TIMES = ['06:00']  # 6 AM daily

    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'documents.engagement_nudge_cron'

    def do(self):
        from django.core.management import call_command
        call_command('generate_engagement_nudges')

class EventReminderCronJob(CronJobBase):
    RUN_EVERY_MINS = 30

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'documents.event_reminder_cron'

    def do(self):
        print("Running event reminder cron job...")
        upcoming = now() + timedelta(minutes=30)
        events = Event.objects.filter(start_time__lte=upcoming, start_time__gte=now())

        for event in events:
            for participant in event.participants.all():
                # Your email sending logic
                print(f"Reminder: {participant.email} for {event.title}")

"""
Django-cron based reminder sender.

This file provides:
- ReminderSender: class encapsulating the reminder sending logic
- ConferenceReminderCronJob: django-cron CronJob class (uses Schedule)
  configured by settings via CONFERENCE_REMINDER_RUN_EVERY_MINS or CONFERENCE_REMINDER_RUN_AT_TIMES

How to use (summary):
1. pip install django-cron
2. Add 'django_cron' to INSTALLED_APPS
3. Add this class path to CRON_CLASSES in settings:
    CRON_CLASSES = [
        'documents.cron.ConferenceReminderCronJob',
    ]
4. Optionally set scheduler settings:
    CONFERENCE_REMINDER_RUN_EVERY_MINS = 15
    # OR
    CONFERENCE_REMINDER_RUN_AT_TIMES = ['09:00', '15:00']
5. Run `python manage.py runcrons` regularly via system cron (e.g., every 5-15 minutes)
   The django-cron package will call ConferenceReminderCronJob.do() according to the Schedule.
"""


logger = logging.getLogger(__name__)

# ReminderSender encapsulates the business logic and can be invoked independently (e.g. in tests)
class ConferenceReminderSender:
    def __init__(self, now: Optional[Any] = None):
        self.now = now or timezone.now()

    def run(self):
        conferences = self._get_conferences_with_offsets()
        logger.info("ConferenceReminderSender: scanning %d conferences", conferences.count())
        for conf in conferences:
            try:
                self._process_conference(conf)
            except Exception:
                logger.exception("Failed processing conference %d", conf.pk)

    def _get_conferences_with_offsets(self):
        # Only conferences with offsets and reminder_count > 0
        return Conference.objects.filter(reminder_offsets__isnull=False).exclude(reminder_offsets=[]).filter(reminder_count__gt=0)

    def _normalize_offsets(self, offsets: Any) -> List[float]:
        normalized = []
        if not offsets:
            return normalized
        for o in offsets:
            try:
                normalized.append(float(o))
            except Exception:
                logger.warning("Invalid offset %r for conference offsets: skipped", o)
        # sort ascending (earliest > largest days before)
        normalized.sort(reverse=True)  # larger offsets (e.g., 30 days) processed first
        return normalized

    def _build_absolute_access_url(self, conference: Conference, participant: ConferenceParticipant) -> str:
        try:
            access_path = reverse('conference_access', kwargs={'conference_id': conference.id, 'token': participant.unique_token})
            access_url = settings.SITE_URL.rstrip('/') + access_path
        except Exception:
            # Fallback to SITE_URL from settings
            base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
            protocol = "http" if settings.DEBUG else "https"
            access_url = f"{protocol}://{conference.tenant.slug}.{base_domain}/conference/participant/access/{conference.id}/{participant.unique_token}"
        return access_url

    def _participant_sent_offsets(self, participant: ConferenceParticipant) -> List[str]:
        raw = getattr(participant, 'reminders_sent', None) or []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            logger.debug("Could not parse reminders_sent for participant %d: %r", participant.pk, raw)
        return []

    def _mark_offset_sent(self, participant: ConferenceParticipant, offset: float):
        try:
            raw = getattr(participant, 'reminders_sent', None) or []
            if isinstance(raw, list):
                raw.append(offset)
                participant.reminders_sent = raw
            else:
                try:
                    parsed = json.loads(raw or "[]")
                except Exception:
                    parsed = []
                parsed.append(offset)
                participant.reminders_sent = json.dumps(parsed)
            participant.reminder_sent = True
            try:
                participant.save(update_fields=['reminders_sent', 'reminder_sent'])
            except Exception:
                participant.save()
        except Exception:
            logger.exception("Failed to persist reminders_sent for participant %d", participant.pk)

    def _send_html_email(self, subject: str, template_name: str, context: dict, to_email: str, cc: str) -> bool:
        try:
            sender = CustomUser.objects.filter(is_superuser=True).first()
            connection, error_message = get_email_smtp_connection(sender.email_provider, sender.email, sender.get_smtp_password())
            html_body = render_to_string(template_name, context)
            from_email = sender.email
            email = EmailMessage(subject=subject, body=html_body, from_email=from_email, to=[to_email], connection=connection, cc=[cc])
            email.content_subtype = "html"
            email.send(fail_silently=False)
            return True
        except Exception:
            logger.exception("Failed to send email to %s", to_email)
            return False

    def _participant_needs_offset(self, participant: ConferenceParticipant, offset: float) -> bool:
        sent_keys = self._participant_sent_offsets(participant)
        return str(offset) not in sent_keys

    def _process_conference(self, conf: Conference):
        start = conf.start_date
        offsets = conf.reminder_offsets or []
        normalized = self._normalize_offsets(offsets)

        for offset in normalized:
            send_time = start - timedelta(days=offset)
            if self.now >= send_time:
                participants = ConferenceParticipant.objects.filter(conference=conf)
                for p in participants:
                    try:
                        if not self._participant_needs_offset(p, offset):
                            continue

                        access_url = self._build_absolute_access_url(conf, p)
                        context = {
                            'participant': p,
                            'conference': conf,
                            'access_url': access_url,
                            'offset': offset,
                        }
                        subject = f"Reminder: {conf.title}"
                        if self._send_html_email(subject, "emails/reminder.html", context, p.email, p.tenant.admin.email):
                            self._mark_offset_sent(p, offset)
                            logger.info("Sent reminder offset=%s to %s for conference %d", offset, p.email, conf.id)
                        else:
                            logger.warning("Failed to send reminder offset=%s to %s for conference %d", offset, p.email, conf.id)
                    except Exception:
                        logger.exception("Error while sending reminder to %s for conference %d", p.email, conf.id)


# django-cron CronJob class
try:
    from django_cron import CronJobBase, Schedule  # type: ignore
except Exception:
    CronJobBase = None
    Schedule = None

if CronJobBase and Schedule:
    class ConferenceReminderCronJob(CronJobBase):
        """
        django-cron CronJob integration.

        Configure schedule via settings:
          CONFERENCE_REMINDER_RUN_EVERY_MINS = 15
        OR
          CONFERENCE_REMINDER_RUN_AT_TIMES = ['09:00', '15:00']

        Then add the class path to settings.CR
        ON_CLASSES so runcrons will pick it up:
          CRON_CLASSES = ['documents.cron.ConferenceReminderCronJob']
        """
        code = 'documents.cron.ConferenceReminderCronJob'

        RUN_EVERY_MINS = getattr(settings, 'CONFERENCE_REMINDER_RUN_EVERY_MINS', None)
        RUN_AT_TIMES = getattr(settings, 'CONFERENCE_REMINDER_RUN_AT_TIMES', None)

        if RUN_AT_TIMES:
            schedule = Schedule(run_at_times=RUN_AT_TIMES)
        elif RUN_EVERY_MINS:
            schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
        else:
            schedule = Schedule(run_every_mins=getattr(settings, 'CONFERENCE_REMINDER_RUN_EVERY_MINS', 15))

        def do(self):
            try:
                ConferenceReminderSender().run()
            except Exception:
                logger.exception("ConferenceReminderCronJob failed")
else:
    ConferenceReminderCronJob = None


# Backwards-compatible helper to invoke sender (can be used if you want to call directly)
def send_conference_reminders():
    ConferenceReminderSender().run()


class SubscriptionExpirationReminderSender:
    """
    Sends notifications for subscriptions expiring within a specified number of days.
    Handles both tenant subscriptions (notifies admin and all covered users) 
    and individual user subscriptions.
    """
    
    def __init__(self, now: Optional[Any] = None):
        self.now = now or timezone.now()
    
    def run(self, days_threshold: int = 30):
        """
        Run the expiration reminder check.
        
        Args:
            days_threshold: Number of days before expiration to start sending reminders
        """
        today = self.now.date()
        expiry_threshold = today + timedelta(days=days_threshold)
        
        logger.info(f"SubscriptionExpirationReminderSender: checking subscriptions expiring between {today} and {expiry_threshold}")
        
        # Find active subscriptions expiring within the threshold
        expiring_subscriptions = Subscription.objects.filter(
            status='active',
            end_date__gte=today,
            end_date__lte=expiry_threshold
        ).select_related('plan', 'tenant', 'tenant__admin', 'user')

        expiring_trials = CustomUser.objects.filter(
            subscription_status='trial',
            subscription_end_date__gte=today,
            subscription_end_date__lte=expiry_threshold
        ).select_related('tenant', 'tenant__admin')
        
        notifications_sent = 0
        errors = 0
        
        for subscription in expiring_subscriptions:
            days_remaining = (subscription.end_date - today).days
            
            try:
                # Process tenant subscriptions
                if subscription.tenant:
                    # Notify tenant admin
                    if subscription.tenant.admin:
                        self._send_admin_notification(subscription, days_remaining)
                    
                    # Notify all covered users
                    covered_users = subscription.get_covered_users()
                    for user in covered_users:
                        self._send_user_notification(subscription, user, days_remaining)
                
                # Process individual user subscriptions
                elif subscription.user:
                    self._send_user_notification(subscription, subscription.user, days_remaining)
                
                notifications_sent += 1
                logger.info(f"Sent notifications for subscription {subscription.id} (expires in {days_remaining} days)")
                
            except Exception as e:
                errors += 1
                logger.error(f"Error sending notifications for subscription {subscription.id}: {str(e)}")
        # Process trial expirations
        for user in expiring_trials:
            days_remaining = (user.subscription_end_date - today).days
            self._send_trial_expiration_notification(user, days_remaining)
        
        logger.info(f"SubscriptionExpirationReminderSender completed. Sent: {notifications_sent}, Errors: {errors}")
        return notifications_sent, errors
    
    # def _send_trial_expiration_notification(self, user: CustomUser, days_remaining: int):
    #     """Send trial expiration notification to user"""
    #     recipient_email = user.email
        
    #     # Create dashboard notification
    #     self._create_trial_expiration_notification(user, days_remaining)
        
    #     # Prepare context
    #     context = {
    #         'user': user,
    #         'days_remaining': days_remaining,
    #         'trial_end_date': user.subscription_end_date,
    #         'is_tenant_user': bool(user.tenant),
    #         'tenant_name': user.tenant.name if user.tenant else None,
    #         'admin_email': user.tenant.admin.email if user.tenant and user.tenant.admin else None,
    #         'subscribe_url': settings.SITE_URL + reverse('create_subscription'),
    #     }
        
    #     # Send email
    #     self._send_trial_expiration_email(user, days_remaining, context)

    def _send_trial_expiration_notification(self, user: CustomUser, days_remaining: int):
        """Send trial expiration notification to user"""
        
        # Create dashboard notification
        self._create_trial_expiration_notification(user, days_remaining)
        
        # Prepare context
        context = {
            'user': user,
            'days_remaining': days_remaining,
            'trial_end_date': user.subscription_end_date,
            'is_tenant_user': bool(user.tenant),
            'tenant_name': user.tenant.name if user.tenant else None,
            'admin_email': user.tenant.admin.email if user.tenant and user.tenant.admin else None,
            'subscribe_url': settings.SITE_URL + reverse('create_subscription'),
        }
        
        # Send email - pass user directly, the email function will extract recipient
        self._send_trial_expiration_email(user, days_remaining, context)
    
    # def _send_trial_expiration_email(self, user: CustomUser, days_remaining: int, context: dict):
    #     """Send trial expiration email"""
    #     try:
    #         if days_remaining <= 0:
    #             subject = "URGENT: Your free trial has ended"
    #         elif days_remaining == 1:
    #             subject = "Your free trial ends TOMORROW!"
    #         elif days_remaining <= 3:
    #             subject = f"Your free trial ends in {days_remaining} days"
    #         else:
    #             subject = f"Your free trial ends in {days_remaining} days"
            
    #         template_name = 'emails/trial_expiring.html'
            
    #         # Get sender
    #         sender = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    #         if not sender:
    #             logger.error("No superuser found for sending emails")
    #             return
            
    #         connection, error_message = get_email_smtp_connection(
    #             sender.email_provider, 
    #             sender.email_address, 
    #             sender.get_smtp_password()
    #         )
            
    #         email_context = {
    #             'user': user,
    #             'days_remaining': days_remaining,
    #             'trial_end_date': user.subscription_end_date,
    #             'current_date': timezone.now(),
    #             **context
    #         }
            
    #         html_message = render_to_string(template_name, email_context)
            
    #         email = EmailMessage(
    #             subject=subject,
    #             body=html_message,
    #             from_email=sender.email_address,
    #             to=[recipient_email],
    #             connection=connection
    #         )
    #         email.content_subtype = "html"
    #         email.send(fail_silently=False)
            
    #         logger.info(f"Trial expiration email sent to {user.email}")
            
    #     except Exception as e:
    #         logger.error(f"Failed to send trial expiration email to {user.email}: {str(e)}")


    def _send_trial_expiration_email(self, user: CustomUser, days_remaining: int, context: dict):
        """Send trial expiration email"""
        try:
            if days_remaining <= 0:
                subject = "URGENT: Your free trial has ended"
            elif days_remaining == 1:
                subject = "Your free trial ends TOMORROW!"
            elif days_remaining <= 3:
                subject = f"Your free trial ends in {days_remaining} days"
            else:
                subject = f"Your free trial ends in {days_remaining} days"
            
            template_name = 'emails/trial_expiring.html'
            
            # Get sender
            sender = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
            if not sender:
                logger.error("No superuser found for sending emails")
                return
            
            connection, error_message = get_email_smtp_connection(
                sender.email_provider, 
                sender.email_address, 
                sender.get_smtp_password()
            )
            
            # Get recipient email from user
            recipient_email = user.email  # ← FIX: Add this line
            
            email_context = {
                'user': user,
                'days_remaining': days_remaining,
                'trial_end_date': user.subscription_end_date,
                'current_date': timezone.now(),
                **context
            }
            
            html_message = render_to_string(template_name, email_context)
            
            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=sender.email_address,
                to=[recipient_email],  # Now recipient_email is defined
                connection=connection
            )
            email.content_subtype = "html"
            email.send(fail_silently=False)
            
            logger.info(f"Trial expiration email sent to {user.email}")
            
        except Exception as e:
            logger.error(f"Failed to send trial expiration email to {user.email}: {str(e)}")
    
    
    def _send_expiration_email(self, subscription: Subscription, days_remaining: int, 
                                recipient_email: str, is_admin: bool = False, 
                                context: dict = None):
        """Generic function to send expiration email"""
        try:
            # Determine subject based on days remaining
            if days_remaining <= 0:
                subject = "URGENT: Your subscription has expired"
            elif days_remaining == 1:
                subject = "Your subscription expires TOMORROW!"
            elif days_remaining <= 7:
                subject = f"Your subscription expires in {days_remaining} days"
            else:
                subject = f"Your subscription expires in {days_remaining} days"
            
            # Add admin prefix if applicable
            if is_admin:
                subject = f"[ADMIN] {subject}"
            
            # Choose template based on admin status
            if is_admin:
                template_name = 'emails/subscription_expiring_admin.html'
            else:
                template_name = 'emails/subscription_expiring_user.html'
            
            # Get sender (superuser)
            sender = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
            if not sender:
                logger.error("No superuser found for sending emails")
                return
            
            # Get email connection
            connection, error_message = get_email_smtp_connection(
                sender.email_provider, 
                sender.email_address, 
                sender.get_smtp_password()
            )
            
            # Prepare email context
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
            
            # Render HTML message
            html_message = render_to_string(template_name, email_context)
            
            # Send email
            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=sender.email_address,
                to=[recipient_email],
                connection=connection
            )
            email.content_subtype = "html"
            email.send(fail_silently=False)
            
            logger.info(f"Expiration email sent to {recipient_email} for subscription {subscription.id}")
            
        except Exception as e:
            logger.error(f"Failed to send expiration email to {recipient_email}: {str(e)}")


# ============ Subscription Expiration Cron Job ============

if CronJobBase and Schedule:
    class SubscriptionExpirationCronJob(CronJobBase):
        """
        django-cron CronJob for subscription expiration reminders.
        
        Runs daily to check for subscriptions expiring within 30 days.
        Sends email notifications to admins and users, and creates dashboard notifications.
        
        Configure via settings:
          SUBSCRIPTION_REMINDER_RUN_AT_TIMES = ['09:00']  # Run at specific times
          SUBSCRIPTION_REMINDER_DAYS_THRESHOLD = 30  # Days before expiration to notify
        """
        code = 'tenants.cron.SubscriptionExpirationCronJob'
        
        # Run daily at 9 AM by default
        RUN_AT_TIMES = getattr(settings, 'SUBSCRIPTION_REMINDER_RUN_AT_TIMES', ['09:00'])
        
        if RUN_AT_TIMES:
            schedule = Schedule(run_at_times=RUN_AT_TIMES)
        else:
            schedule = Schedule(run_every_mins=1440)  # 24 hours
        
        def do(self):
            """Execute the cron job"""
            try:
                days_threshold = getattr(settings, 'SUBSCRIPTION_REMINDER_DAYS_THRESHOLD', 30)
                logger.info(f"SubscriptionExpirationCronJob: Running with threshold {days_threshold} days")
                
                sender = SubscriptionExpirationReminderSender()
                notifications_sent, errors = sender.run(days_threshold=days_threshold)
                
                logger.info(f"SubscriptionExpirationCronJob completed: {notifications_sent} notifications sent, {errors} errors")
                
            except Exception as e:
                logger.exception(f"SubscriptionExpirationCronJob failed: {str(e)}")


# ============ Urgent Subscription Expiration Cron Job (7 days) ============

if CronJobBase and Schedule:
    class UrgentSubscriptionExpirationCronJob(CronJobBase):
        """
        django-cron CronJob for urgent subscription expiration reminders.
        
        Runs daily to check for subscriptions expiring within 7 days.
        Sends more urgent notifications to admins and users.
        
        Configure via settings:
          URGENT_SUBSCRIPTION_REMINDER_RUN_AT_TIMES = ['09:00', '14:00']  # Multiple times per day
        """
        code = 'tenants.cron.UrgentSubscriptionExpirationCronJob'
        
        # Run twice daily by default (morning and afternoon)
        RUN_AT_TIMES = getattr(settings, 'URGENT_SUBSCRIPTION_REMINDER_RUN_AT_TIMES', ['09:00', '14:00'])
        
        if RUN_AT_TIMES:
            schedule = Schedule(run_at_times=RUN_AT_TIMES)
        else:
            schedule = Schedule(run_every_mins=720)  # 12 hours
        
        def do(self):
            """Execute the cron job for urgent reminders (7 days or less)"""
            try:
                days_threshold = 7
                logger.info(f"UrgentSubscriptionExpirationCronJob: Running with threshold {days_threshold} days")
                
                sender = SubscriptionExpirationReminderSender()
                notifications_sent, errors = sender.run(days_threshold=days_threshold)
                
                logger.info(f"UrgentSubscriptionExpirationCronJob completed: {notifications_sent} notifications sent, {errors} errors")
                
            except Exception as e:
                logger.exception(f"UrgentSubscriptionExpirationCronJob failed: {str(e)}")