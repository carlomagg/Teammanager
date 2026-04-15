from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Run all vacancy data imports (skills and tags)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip if data already exists',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting vacancy data setup...')
        
        # Run skills import
        self.stdout.write('Importing comprehensive skills...')
        try:
            call_command('import_comprehensive_skills')
            self.stdout.write(self.style.SUCCESS('✓ Skills imported successfully'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Skills import failed: {e}'))
        
        # Run tags import
        self.stdout.write('Importing comprehensive tags...')
        try:
            call_command('import_comprehensive_tags')
            self.stdout.write(self.style.SUCCESS('✓ Tags imported successfully'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Tags import failed: {e}'))
        
        # Run specialized imports
        self.stdout.write('Importing specialized data...')
        try:
            call_command('industry_specific_skills')
            call_command('specialized_tags')
            call_command('comprehensive_tags_list')
            call_command('comprehensive_skills_list')
            self.stdout.write(self.style.SUCCESS('✓ Specialized data imported successfully'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠ Specialized data import issues: {e}'))
        
        self.stdout.write(self.style.SUCCESS('Vacancy data setup completed!'))