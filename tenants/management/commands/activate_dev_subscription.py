"""
Management command to activate subscription for development/testing on localhost
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from documents.models import CustomUser
from tenants.models import Subscription, SubscriptionType, Tenant


class Command(BaseCommand):
    help = 'Activate subscription for a user or tenant for development purposes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Email of the user to activate subscription for',
        )
        parser.add_argument(
            '--tenant',
            type=str,
            help='Tenant slug or ID to activate subscription for',
        )
        parser.add_argument(
            '--all-users',
            action='store_true',
            help='Activate subscription for all users',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Number of days for the subscription (default: 365)',
        )

    def handle(self, *args, **options):
        email = options.get('email')
        tenant_identifier = options.get('tenant')
        all_users = options.get('all_users')
        days = options.get('days')

        # Get or create a free subscription plan
        plan, created = SubscriptionType.objects.get_or_create(
            name='Development Plan',
            defaults={
                'price': 0,
                'duration': days,
                'discount_percentage': 0,
                'is_active': True,
                'description': 'Free development/testing plan',
                'max_users': None,  # Unlimited
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created Development Plan'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Using existing Development Plan'))

        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=days)

        # Handle all users
        if all_users:
            users = CustomUser.objects.filter(is_superuser=False)
            count = 0
            for user in users:
                sub, created = self._create_or_update_subscription(
                    user=user,
                    plan=plan,
                    start_date=start_date,
                    end_date=end_date
                )
                if created:
                    count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Activated subscription for {user.email}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Updated subscription for {user.email}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Activated subscriptions for {count} users')
            )
            return

        # Handle specific tenant
        if tenant_identifier:
            try:
                # Try to get tenant by slug first, then by ID
                try:
                    tenant = Tenant.objects.get(slug=tenant_identifier)
                except Tenant.DoesNotExist:
                    tenant = Tenant.objects.get(id=int(tenant_identifier))
                
                sub, created = self._create_or_update_subscription(
                    tenant=tenant,
                    plan=plan,
                    start_date=start_date,
                    end_date=end_date,
                    user_scope='all'
                )
                
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Activated subscription for tenant: {tenant.name} (all users)'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Updated subscription for tenant: {tenant.name}'
                        )
                    )
                
                # Show covered users
                covered_users = sub.get_covered_users()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  Covers {covered_users.count()} users in the tenant'
                    )
                )
                
            except Tenant.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Tenant not found: {tenant_identifier}')
                )
                return
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f'Invalid tenant ID: {tenant_identifier}')
                )
                return

        # Handle specific user
        elif email:
            try:
                user = CustomUser.objects.get(email=email)
                sub, created = self._create_or_update_subscription(
                    user=user,
                    plan=plan,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Activated subscription for {user.email}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Updated subscription for {user.email}')
                    )
                
            except CustomUser.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'User not found: {email}')
                )
                return

        else:
            self.stdout.write(
                self.style.ERROR(
                    'Please provide --email, --tenant, or --all-users'
                )
            )
            self.stdout.write('\nExamples:')
            self.stdout.write('  python manage.py activate_dev_subscription --email user@example.com')
            self.stdout.write('  python manage.py activate_dev_subscription --tenant my-company')
            self.stdout.write('  python manage.py activate_dev_subscription --all-users')
            self.stdout.write('  python manage.py activate_dev_subscription --email user@example.com --days 30')

    def _create_or_update_subscription(self, plan, start_date, end_date, 
                                      user=None, tenant=None, user_scope='all'):
        """Create or update subscription for user or tenant"""
        
        # Check for existing active subscription
        if user:
            existing = Subscription.objects.filter(
                user=user,
                status='active'
            ).first()
        elif tenant:
            existing = Subscription.objects.filter(
                tenant=tenant,
                status='active',
                user_scope=user_scope
            ).first()
        else:
            existing = None
        
        if existing:
            # Update existing subscription
            existing.end_date = end_date
            existing.is_free = True
            existing.free_reason = 'Development/Testing'
            existing.status = 'active'
            existing.save()
            return existing, False
        else:
            # Create new subscription
            sub = Subscription.objects.create(
                user=user,
                tenant=tenant,
                plan=plan,
                status='active',
                start_date=start_date,
                end_date=end_date,
                is_free=True,
                free_reason='Development/Testing',
                user_scope=user_scope if tenant else 'selected',
                duration_months=12,
            )
            return sub, True
