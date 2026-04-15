from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from documents.models import Role  # Adjust to your Role model path

class Command(BaseCommand):
    help = "Assign the Admin role to a user's roles ManyToManyField"

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]

        try:
            user = User.objects.get(username=username)
            # Ensure user is staff (required for admin panel access)
            user.save()

            # Get or create the Admin role
            admin_role, created = Role.objects.get_or_create(name="Admin")
            if created:
                self.stdout.write(self.style.WARNING("Admin role created. Configure permissions if needed."))

            # Assign the Admin role to the user's roles ManyToManyField
            user.roles.add(admin_role)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"User '{username}' assigned Admin role"))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' does not exist"))