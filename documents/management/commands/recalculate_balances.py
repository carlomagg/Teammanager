# management/commands/recalculate_balances.py
from django.core.management.base import BaseCommand
from documents.models import TenantBalance, CustomUser
from tenants.models import Tenant
from django.db import transaction

class Command(BaseCommand):
    help = 'Recalculate all tenant balances with proper deductions'

    def handle(self, *args, **options):
        self.stdout.write('Starting balance recalculation...')
        
        tenants = Tenant.objects.all()
        total_tenants = tenants.count()

        users = CustomUser.objects.filter(is_personal=True, tenant__is_null=True)
        total_users = users.count()

        
        for i, tenant in enumerate(tenants, 1):
            try:
                balance = TenantBalance.get_or_create_for_tenant(tenant=tenant, owner=None)
                result = balance.update_balance()
                
                self.stdout.write(
                    f"[{i}/{total_tenants}] {tenant.name}: "
                    f"Earned={result['total_earned']}, "
                    f"Remitted={result['total_remitted']}, "
                    f"Available={result['available_balance']}"
                )
                
            except Exception as e:
                self.stderr.write(f"Error processing {tenant.name}: {str(e)}")
        
        for i, user in enumerate(users, 1):
            try:
                balance = TenantBalance.get_or_create_for_tenant(tenant=None, owner=user)
                result = balance.update_balance()
                
                self.stdout.write(
                    f"[{i}/{total_users}] {user.username}: "
                    f"Earned={result['total_earned']}, "
                    f"Remitted={result['total_remitted']}, "
                    f"Available={result['available_balance']}"
                )
                
            except Exception as e:
                self.stderr.write(f"Error processing {user.username}: {str(e)}")
        
        self.stdout.write(self.style.SUCCESS('Balance recalculation completed!'))