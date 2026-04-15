from django.core.management.base import BaseCommand
from django.db import transaction
from crm.models import PipelineStage
from tenants.models import Tenant
from documents.models import CustomUser


class Command(BaseCommand):
    help = 'Seed default pipeline stages for all tenants and personal users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Seed stages for a specific tenant ID only',
        )
        parser.add_argument(
            '--personal-user-id',
            type=int,
            help='Seed stages for a specific personal user ID only',
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        personal_user_id = options.get('personal_user_id')

        # Default pipeline stages for each category
        LEAD_STAGES = [
            {'name': 'Qualification', 'order': 1, 'is_terminal': False},
            {'name': 'Prospecting', 'order': 2, 'is_terminal': False},
            {'name': 'Proposal', 'order': 3, 'is_terminal': False},
            {'name': 'Submitted', 'order': 4, 'is_terminal': False},
            {'name': 'Presentation / Meetings', 'order': 5, 'is_terminal': False},
        ]

        DEAL_STAGES = [
            {'name': 'Negotiation', 'order': 1, 'is_terminal': False},
            {'name': 'Finance Discussion', 'order': 2, 'is_terminal': False},
            {'name': 'Agreement Preparation', 'order': 3, 'is_terminal': False},
            {'name': 'Closed Won', 'order': 4, 'is_terminal': True},
            {'name': 'Closed Lost', 'order': 5, 'is_terminal': True},
        ]

        CUSTOMER_STAGES = [
            {'name': 'Happy Customer', 'order': 1, 'is_terminal': False},
            {'name': 'Dissatisfied Customer', 'order': 2, 'is_terminal': False},
            {'name': 'Pending Customer', 'order': 3, 'is_terminal': False},
            {'name': 'Lost Customer', 'order': 4, 'is_terminal': True},
        ]

        created_count = 0

        with transaction.atomic():
            if tenant_id:
                # Seed for specific tenant
                try:
                    tenant = Tenant.objects.get(id=tenant_id)
                    created_count += self._seed_for_tenant(tenant, LEAD_STAGES, DEAL_STAGES, CUSTOMER_STAGES)
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully seeded stages for tenant: {tenant.name}')
                    )
                except Tenant.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'Tenant with ID {tenant_id} does not exist')
                    )
                    return

            elif personal_user_id:
                # Seed for specific personal user
                try:
                    user = CustomUser.objects.get(id=personal_user_id, is_personal=True)
                    created_count += self._seed_for_personal_user(user, LEAD_STAGES, DEAL_STAGES, CUSTOMER_STAGES)
                    self.stdout.write(
                        self.style.SUCCESS(f'Successfully seeded stages for personal user: {user.username}')
                    )
                except CustomUser.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'Personal user with ID {personal_user_id} does not exist')
                    )
                    return

            else:
                # Seed for all tenants
                tenants = Tenant.objects.all()
                for tenant in tenants:
                    created_count += self._seed_for_tenant(tenant, LEAD_STAGES, DEAL_STAGES, CUSTOMER_STAGES)
                    self.stdout.write(f'Seeded stages for tenant: {tenant.name}')

                # Seed for all personal users
                personal_users = CustomUser.objects.filter(is_personal=True)
                for user in personal_users:
                    created_count += self._seed_for_personal_user(user, LEAD_STAGES, DEAL_STAGES, CUSTOMER_STAGES)
                    self.stdout.write(f'Seeded stages for personal user: {user.username}')

        self.stdout.write(
            self.style.SUCCESS(f'\nTotal stages created: {created_count}')
        )

    def _seed_for_tenant(self, tenant, lead_stages, deal_stages, customer_stages):
        """Seed pipeline stages for a tenant"""
        created_count = 0
        admin_user = tenant.admin

        # Create Lead stages
        for stage_data in lead_stages:
            stage, created = PipelineStage.objects.get_or_create(
                tenant=tenant,
                category='Lead',
                name=stage_data['name'],
                defaults={
                    'order': stage_data['order'],
                    'is_terminal': stage_data['is_terminal'],
                    'created_by': admin_user,
                }
            )
            if created:
                created_count += 1

        # Create Deal stages
        for stage_data in deal_stages:
            stage, created = PipelineStage.objects.get_or_create(
                tenant=tenant,
                category='Deal',
                name=stage_data['name'],
                defaults={
                    'order': stage_data['order'],
                    'is_terminal': stage_data['is_terminal'],
                    'created_by': admin_user,
                }
            )
            if created:
                created_count += 1

        # Create Customer stages
        for stage_data in customer_stages:
            stage, created = PipelineStage.objects.get_or_create(
                tenant=tenant,
                category='Customer',
                name=stage_data['name'],
                defaults={
                    'order': stage_data['order'],
                    'is_terminal': stage_data['is_terminal'],
                    'created_by': admin_user,
                }
            )
            if created:
                created_count += 1

        return created_count

    def _seed_for_personal_user(self, user, lead_stages, deal_stages, customer_stages):
        """Seed pipeline stages for a personal user"""
        created_count = 0

        # Create Lead stages
        for stage_data in lead_stages:
            stage, created = PipelineStage.objects.get_or_create(
                tenant=None,
                category='Lead',
                name=stage_data['name'],
                created_by=user,
                defaults={
                    'order': stage_data['order'],
                    'is_terminal': stage_data['is_terminal'],
                }
            )
            if created:
                created_count += 1

        # Create Deal stages
        for stage_data in deal_stages:
            stage, created = PipelineStage.objects.get_or_create(
                tenant=None,
                category='Deal',
                name=stage_data['name'],
                created_by=user,
                defaults={
                    'order': stage_data['order'],
                    'is_terminal': stage_data['is_terminal'],
                }
            )
            if created:
                created_count += 1

        # Create Customer stages
        for stage_data in customer_stages:
            stage, created = PipelineStage.objects.get_or_create(
                tenant=None,
                category='Customer',
                name=stage_data['name'],
                created_by=user,
                defaults={
                    'order': stage_data['order'],
                    'is_terminal': stage_data['is_terminal'],
                }
            )
            if created:
                created_count += 1

        return created_count
