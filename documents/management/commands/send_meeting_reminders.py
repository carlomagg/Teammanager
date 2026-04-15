# from django.core.management.base import BaseCommand
# from django.utils.timezone import now, timedelta
# from documents.models import Meeting, MeetingParticipant
# from django.core.mail import send_mail

# class Command(BaseCommand):
#     help = 'Send meeting reminders 30 minutes before the start'

#     def handle(self, *args, **kwargs):
#         reminder_time = now() + timedelta(minutes=30)
#         meetings = Meeting.objects.filter(start_time__range=(reminder_time, reminder_time + timedelta(minutes=1)))
#         for meeting in meetings:
#             for participant in meeting.participants.all():
#                 send_mail(
#                     subject=f'Reminder: {meeting.title}',
#                     message=f'You have a meeting at {meeting.start_time}.',
#                     from_email='no-reply@raadaa.com',
#                     recipient_list=[participant.user.email],
#                     fail_silently=True,
#                 )


from django.core.management.base import BaseCommand
from django.utils.timezone import now, timedelta
from documents.models import Event, Notification, UserNotification
from django.core.mail import send_mail

class Command(BaseCommand):
    help = 'Send event reminders 30 minutes before start time'

    def handle(self, *args, **kwargs):
        target_time = now() + timedelta(minutes=30)
        events = Event.objects.filter(start_time__range=(target_time, target_time + timedelta(minutes=1)))

        for event in events:
            notif = Notification.objects.create(
                type=Notification.NotificationType.EVENT,
                title=f"Upcoming Event: {event.title}",
                message=f"You have an event starting at {event.start_time.strftime('%I:%M %p')}.",
                is_active=True,
                link=f"/admins/events/edit/{event.id}/"
            )
            for user in event.participants.all():
                UserNotification.objects.get_or_create(user=user, notification=notif)
                send_mail(
                    subject=notif.title,
                    message=notif.message,
                    from_email='no-reply@raadaa.com',
                    recipient_list=[user.email],
                    fail_silently=True,
                )
