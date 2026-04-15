from django.core.management.base import BaseCommand
from memo.models import Memo, MemoStep
from documents.models import CustomUser


class Command(BaseCommand):
    help = 'Test memo recipients and steps'

    def add_arguments(self, parser):
        parser.add_argument('memo_id', type=int, help='Memo ID to check')

    def handle(self, *args, **options):
        memo_id = options['memo_id']
        
        try:
            memo = Memo.objects.get(id=memo_id)
            self.stdout.write(self.style.SUCCESS(f'\nMemo: {memo.reference_number} - {memo.title}'))
            self.stdout.write(f'Status: {memo.status}')
            self.stdout.write(f'Current Holder: {memo.current_holder}')
            
            self.stdout.write(self.style.SUCCESS('\n--- TO USERS (from to_users field) ---'))
            to_users = memo.to_users.all()
            if to_users:
                for user in to_users:
                    self.stdout.write(f'  - {user.username} ({user.get_full_name()})')
            else:
                self.stdout.write('  None')
            
            self.stdout.write(self.style.SUCCESS('\n--- CC USERS ---'))
            cc_users = memo.cc_users.all()
            if cc_users:
                for user in cc_users:
                    self.stdout.write(f'  - {user.username} ({user.get_full_name()})')
            else:
                self.stdout.write('  None')
            
            self.stdout.write(self.style.SUCCESS('\n--- BCC USERS ---'))
            bcc_users = memo.bcc_users.all()
            if bcc_users:
                for user in bcc_users:
                    self.stdout.write(f'  - {user.username} ({user.get_full_name()})')
            else:
                self.stdout.write('  None')
            
            self.stdout.write(self.style.SUCCESS('\n--- MEMO STEPS ---'))
            steps = memo.steps.all().order_by('step_number')
            if steps:
                for step in steps:
                    self.stdout.write(f'  Step {step.step_number}: {step.get_action_display()}')
                    self.stdout.write(f'    From: {step.from_user.username if step.from_user else "External"}')
                    self.stdout.write(f'    To: {step.to_user.username if step.to_user else "None"}')
                    if step.note:
                        self.stdout.write(f'    Note: {step.note[:50]}...')
            else:
                self.stdout.write('  No steps found')
            
            self.stdout.write(self.style.SUCCESS('\n--- WHO CAN SEE THIS MEMO IN INBOX ---'))
            # Test the inbox query
            users_with_steps = CustomUser.objects.filter(
                memo_steps_received__memo=memo
            ).distinct()
            
            if users_with_steps:
                for user in users_with_steps:
                    self.stdout.write(f'  - {user.username} ({user.get_full_name()})')
            else:
                self.stdout.write('  No users found with steps')
                
        except Memo.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Memo with ID {memo_id} not found'))
