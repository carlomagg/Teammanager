from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Force migrate request types by temporarily disabling foreign key checks'

    def handle(self, *args, **options):
        self.stdout.write('Forcing migration with disabled foreign key checks...')
        
        with connection.cursor() as cursor:
            # Disable foreign key checks
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            try:
                # Run the migration
                call_command('migrate', 'fund_request', verbosity=0)
                self.stdout.write(self.style.SUCCESS('Migration completed successfully!'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Migration failed: {e}'))
                return
            finally:
                # Re-enable foreign key checks
                cursor.execute("PRAGMA foreign_keys = ON")
        
        self.stdout.write('\nNow run: python manage.py setup_request_types')
