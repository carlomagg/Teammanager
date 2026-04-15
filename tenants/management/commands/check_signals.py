from django.core.management.base import BaseCommand
from django.db.models.signals import post_save
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check if signals are properly registered'

    def handle(self, *args, **options):
        self.stdout.write("Checking signal registration...")
        
        # Get all receivers for post_save
        receivers = [r for r in post_save.receivers]
        
        self.stdout.write(f"Total post_save receivers: {len(receivers)}")
        
        # Check if our signals are registered
        found = False
        for receiver in receivers:
            receiver_str = str(receiver)
            if 'handle_tenant_user_change' in receiver_str:
                found = True
                self.stdout.write(self.style.SUCCESS(f"✓ Found signal: {receiver_str}"))
        
        if not found:
            self.stdout.write(self.style.ERROR("✗ Subscription signals not found!"))
        
        self.stdout.write(self.style.SUCCESS("Signal check complete"))