"""
Management command to backfill source tracking for existing GuestUser records.

This script attempts to find the source (Conference, Vacancy, etc.) for each GuestUser
by looking at ConferenceParticipant records that match the guest user's email.

Usage:
    python manage.py backfill_guestuser_sources
"""
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from documents.models import GuestUser, ConferenceParticipant, Conference


class Command(BaseCommand):
    help = 'Backfill source tracking for existing GuestUser records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get all GuestUser records without a source
        guest_users = GuestUser.objects.filter(source_content_type__isnull=True)
        total_count = guest_users.count()
        
        self.stdout.write(f'Found {total_count} GuestUser records without source tracking')
        
        updated_count = 0
        conference_ct = ContentType.objects.get_for_model(Conference)
        
        for guest_user in guest_users:
            # Try to find a ConferenceParticipant with matching email
            participant = ConferenceParticipant.objects.filter(
                email__iexact=guest_user.email
            ).order_by('registered_at').first()
            
            if participant:
                conference = participant.conference
                
                if dry_run:
                    self.stdout.write(
                        f'Would update GuestUser {guest_user.email} -> '
                        f'Conference: {conference.title} (ID: {conference.id})'
                    )
                else:
                    guest_user.source_content_type = conference_ct
                    guest_user.source_object_id = conference.id
                    guest_user.save(update_fields=['source_content_type', 'source_object_id'])
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated GuestUser {guest_user.email} -> '
                            f'Conference: {conference.title}'
                        )
                    )
                
                updated_count += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'No source found for GuestUser {guest_user.email}'
                    )
                )
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(f'Total GuestUsers processed: {total_count}')
        self.stdout.write(f'GuestUsers updated: {updated_count}')
        self.stdout.write(f'GuestUsers without source: {total_count - updated_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('\nBackfill completed!'))
