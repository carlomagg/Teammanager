from django.core.management.base import BaseCommand
from fund_request.models import FundRequest, FundRequestType
from tenants.models import Tenant


class Command(BaseCommand):
    help = 'Create default request types and update existing fund requests'

    def handle(self, *args, **options):
        self.stdout.write('Setting up request types...')
        
        # Get all tenants
        tenants = list(Tenant.objects.all())
        tenants.append(None)  # Include None for personal accounts
        
        created_types = {}
        
        for tenant in tenants:
            # Create default request types for each tenant
            advance, _ = FundRequestType.objects.get_or_create(
                tenant=tenant,
                name='Advance',
                defaults={'created_by': None}
            )
            reimbursement, _ = FundRequestType.objects.get_or_create(
                tenant=tenant,
                name='Reimbursement',
                defaults={'created_by': None}
            )
            petty_cash, _ = FundRequestType.objects.get_or_create(
                tenant=tenant,
                name='Petty Cash',
                defaults={'created_by': None}
            )
            
            tenant_key = tenant.id if tenant else 'personal'
            created_types[tenant_key] = {
                'advance': advance,
                'reimbursement': reimbursement,
                'petty_cash': petty_cash
            }
            
            tenant_name = tenant.name if tenant else 'Personal'
            self.stdout.write(f'  Created types for: {tenant_name}')
        
        # Update existing fund requests
        self.stdout.write('\nUpdating existing fund requests...')
        
        for fund_request in FundRequest.objects.all():
            tenant_key = fund_request.tenant.id if fund_request.tenant else 'personal'
            
            # Set to Reimbursement as default (most common)
            if tenant_key in created_types:
                fund_request.request_type = created_types[tenant_key]['reimbursement']
                fund_request.save()
        
        total_updated = FundRequest.objects.count()
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully set up request types!'))
        self.stdout.write(self.style.SUCCESS(f'Updated {total_updated} fund requests'))
        self.stdout.write('\nYou can now manage request types at: /fund-request/request-types/')
