# documents/management/commands/assign_ckeditor_permissions.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission
from documents.models import CustomUser
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Assign CKEditor upload permissions to all users'

    def handle(self, *args, **kwargs):
        permission = Permission.objects.get(codename='add_image', content_type__app_label='ckeditor')
        users = CustomUser.objects.all()
        for user in users:
            user.user_permissions.add(permission)
            self.stdout.write(self.style.SUCCESS(f'Assigned add_image permission to {user.username}'))