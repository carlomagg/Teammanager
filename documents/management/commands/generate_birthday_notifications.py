from django.core.management.base import BaseCommand
from django.utils.timezone import now
from documents.models import StaffProfile, Notification
from datetime import date

class Command(BaseCommand):
    help = 'Generate birthday notifications for today'

    def handle(self, *args, **kwargs):
        today = date.today()
        month = today.month
        day = today.day

        birthdays = StaffProfile.objects.filter(
            date_of_birth__month=month,
            date_of_birth__day=day
        )

        for staff in birthdays:
            title = f"It's {staff.full_name}'s Birthday Today! 🎉"
            if not Notification.objects.filter(title=title, type='birthday', created_at__date=today).exists():
                Notification.objects.create(
                    title=title,
                    type='birthday',
                    message='Wish them a happy birthday!',
                    is_active=True
                )
                self.stdout.write(f"Notification created for {staff.user.get_full_name()}")
