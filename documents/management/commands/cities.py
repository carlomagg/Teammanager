from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Load all cities data for all countries'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force download even if data exists',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting to load all cities data...')
        
        if options['force']:
            self.stdout.write('Clearing existing data...')
            call_command('cities_light_clear')
        
        self.stdout.write('Downloading all countries and cities...')
        call_command('cities_light')
        
        self.stdout.write(
            self.style.SUCCESS('Successfully loaded all cities data!')
        )