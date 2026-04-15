from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import transaction
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class Command(BaseCommand):
    help = 'Migrate all existing users from free access to trial mode on a specific date'

    def add_arguments(self, parser):
        parser.add_argument(
            '--go-live-date',
            type=str,
            required=True,
            help='Date when trial starts (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--trial-days',
            type=int,
            default=7,
            help='Number of trial days (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually changing'
        )
        parser.add_argument(
            '--exclude-superusers',
            action='store_true',
            help='Exclude superusers from trial migration'
        )

    def handle(self, *args, **options):
        go_live_date = datetime.strptime(options['go_live_date'], '%Y-%m-%d').date()
        trial_days = options['trial_days']
        dry_run = options['dry_run']
        exclude_superusers = options['exclude_superusers']
        
        today = timezone.now().date()
        trial_end_date = go_live_date + timedelta(days=trial_days)
        
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("TRIAL MIGRATION REPORT"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"Go-live date: {go_live_date}")
        self.stdout.write(f"Today's date: {today}")
        self.stdout.write(f"Trial duration: {trial_days} days")
        self.stdout.write(f"Trial end date: {trial_end_date}")
        self.stdout.write(f"Dry run: {dry_run}")
        self.stdout.write(f"Exclude superusers: {exclude_superusers}")
        self.stdout.write("")
        
        # Validate go-live date
        if go_live_date < today:
            self.stdout.write(
                self.style.WARNING(f"Warning: Go-live date {go_live_date} is in the past. "
                                  "Users will be set to trial immediately.")
            )
        
        # Get all users
        users = User.objects.all()
        if exclude_superusers:
            users = users.exclude(is_superuser=True)
        
        # Only migrate users who are currently active/inactive (not already subscribed)
        # This preserves users who already have active subscriptions
        users_to_migrate = users.filter(
            subscription_status__in=['inactive']  # Only migrate inactive users
        )
        
        total_users = users.count()
        users_to_migrate_count = users_to_migrate.count()
        
        self.stdout.write(f"\nTotal users in system: {total_users}")
        self.stdout.write(f"Users to migrate (currently inactive): {users_to_migrate_count}")
        self.stdout.write(f"Users already active/trial: {total_users - users_to_migrate_count}")
        
        if dry_run:
            self.stdout.write("\n" + self.style.WARNING("DRY RUN - No changes will be made"))
            self.stdout.write("\nSample of users that will be affected:")
            for user in users_to_migrate[:10]:
                self.stdout.write(
                    f"  - {user.email} | Tenant: {user.tenant.slug if user.tenant else 'Personal'} | "
                    f"Current status: {user.subscription_status}"
                )
            return
        
        # Perform the migration
        self.stdout.write("\n" + self.style.SUCCESS("Starting migration..."))
        
        with transaction.atomic():
            updated_count = 0
            
            for user in users_to_migrate:
                old_status = user.subscription_status
                
                # Update user fields - ONLY on the User model
                user.subscription_status = 'trial'
                user.subscription_end_date = trial_end_date
                user.save()
                
                updated_count += 1
                self.stdout.write(f"  ✅ Updated {user.email} from '{old_status}' to 'trial' (ends {trial_end_date})")
            
            self.stdout.write("\n" + self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("MIGRATION COMPLETE"))
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(f"✅ Users updated to trial: {updated_count}")
            self.stdout.write(f"📅 Trial ends on: {trial_end_date}")
            self.stdout.write(f"ℹ️  Users with active subscriptions were preserved")
            
            logger.info(
                f"Trial migration completed on {timezone.now().date()}. "
                f"Updated {updated_count} users to trial status. "
                f"Trial ends {trial_end_date}"
            )