from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from django.urls import reverse
from django.contrib.sites.models import Site
from datetime import timedelta
from documents.models import Conference, ConferenceParticipant


class Command(BaseCommand):
    help = "Send configured conference reminders to participants. Intended to be run periodically."

    def handle(self, *args, **options):
        now = timezone.now()
        conferences = Conference.objects.filter(reminder_offsets__isnull=False).exclude(reminder_offsets=[])
        site_domain = None
        try:
            site = Site.objects.get_current()
            site_domain = site.domain
        except Exception:
            site_domain = getattr(settings, 'SITE_URL', None)

        for conf in conferences:
            start = conf.start_date
            offsets = conf.reminder_offsets or []
            # Ensure offsets are a list of floats
            normalized_offsets = []
            for o in offsets:
                try:
                    normalized_offsets.append(float(o))
                except Exception:
                    # skip invalid values
                    continue

            for offset in normalized_offsets:
                send_time = start - timedelta(days=offset)
                # only consider reminders that are due now or in the past
                # add a small window: only send if now is after send_time
                if now >= send_time:
                    participants = ConferenceParticipant.objects.filter(conference=conf)
                    for p in participants:
                        # skip if this offset already sent for this participant
                        reminders_sent = p.reminders_sent or []
                        # Compare offset as string to avoid floating-point tiny differences
                        offset_key = str(offset)
                        sent_keys = [str(x) for x in reminders_sent]
                        if offset_key in sent_keys:
                            continue

                        # Build access URL for this participant
                        access_path = reverse('conference_access', kwargs={'conference_id': conf.id, 'token': p.unique_token})
                        if site_domain:
                            # If site_domain is a full URL e.g. https://example.com or domain only, try best effort
                            if site_domain.startswith('http'):
                                access_url = site_domain.rstrip('/') + access_path
                            else:
                                access_url = 'https://' + site_domain.rstrip('/') + access_path
                        else:
                            # fallback relative
                            access_url = access_path

                        # Render reminder email and send
                        context = {
                            'participant': p,
                            'conference': conf,
                            'access_url': access_url,
                            'offset': offset,
                        }
                        subject = f"Reminder: {conf.title}"
                        html_body = render_to_string("emails/reminder.html", context)
                        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')

                        email = EmailMessage(subject=subject, body=html_body, from_email=from_email, to=[p.email])
                        email.content_subtype = "html"
                        try:
                            email.send(fail_silently=False)
                            # mark offset as sent
                            reminders_sent.append(offset)
                            p.reminders_sent = reminders_sent
                            # generic flag to say at least a reminder was sent
                            p.reminder_sent = True
                            p.save(update_fields=['reminders_sent', 'reminder_sent'])
                            self.stdout.write(self.style.SUCCESS(f"Sent reminder offset={offset} to {p.email} for conference {conf.pk}"))
                        except Exception as e:
                            self.stderr.write(f"Failed to send reminder to {p.email} for conference {conf.pk}: {e}")