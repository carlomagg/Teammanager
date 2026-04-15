from django.core.management.base import BaseCommand
from memo.models import MemoCategory
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Seeds default memo categories for all tenants'

    def handle(self, *args, **options):
        default_categories = [
            'Human Resources (HR)',
            'Finance / Accounting',
            'Sales and Marketing',
            'Operations',
            'Customer Service / Support',
            'Information Technology (IT)',
            'Research & Development (R&D)',
            'Legal / Compliance',
            'Procurement / Supply Chain',
            'General'
        ]

        tenants = Tenant.objects.all()
        
        if not tenants.exists():
            self.stdout.write(self.style.WARNING('No tenants found. Creating categories without tenant...'))
            tenants = [None]

        created_count = 0
        skipped_count = 0

        for tenant in tenants:
            tenant_name = tenant.name if tenant else 'No Tenant'
            
            for category_name in default_categories:
                # Check if category already exists for this tenant
                if tenant:
                    exists = MemoCategory.objects.filter(
                        tenant=tenant,
                        name=category_name
                    ).exists()
                else:
                    exists = MemoCategory.objects.filter(
                        tenant__isnull=True,
                        name=category_name
                    ).exists()

                if not exists:
                    MemoCategory.objects.create(
                        tenant=tenant,
                        name=category_name,
                        created_by=None
                    )
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created category "{category_name}" for {tenant_name}'
                        )
                    )
                else:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'Category "{category_name}" already exists for {tenant_name}'
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted! Created {created_count} categories, skipped {skipped_count} existing.'
            )
        )
