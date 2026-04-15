# management/commands/cleanup_abandoned_conference_registrations.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from documents.models import Payment, ConferenceParticipant
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Clean up abandoned paid conference registrations older than 2 hours"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=2)

        # Find pending payments for conference fees older than 2 hours
        abandoned_payments = Payment.objects.filter(
            payment_type='conference_fee',
            status='pending',
            created_at__lt=cutoff
        ).select_related('conference_registration')

        deleted_count = 0
        for payment in abandoned_payments:
            participant = payment.conference_registration
            if participant and participant.status == 'pending' and not participant.ticket_paid:
                try:
                    participant_name = participant.full_name
                    conference_title = participant.conference.title
                    participant.delete()  # This will also delete payment if cascade, or handle separately
                    logger.info(f"Cleaned up abandoned registration: {participant_name} for {conference_title}")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete abandoned registration: {e}")

        # Also clean up explicitly failed payments older than, say, 24 hours (optional)
        old_failed = Payment.objects.filter(
            payment_type='conference_fee',
            status='failed',
            created_at__lt=(timezone.now() - timedelta(hours=24)),
            conference_registration__status='pending'
        )
        for payment in old_failed:
            if payment.conference_registration:
                payment.conference_registration.delete()

        self.stdout.write(
            self.style.SUCCESS(f"Cleaned up {deleted_count} abandoned registrations.")
        )