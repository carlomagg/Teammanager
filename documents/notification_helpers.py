# documents/notification_helpers.py
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import Notification, UserNotification


def create_notification(
    tenant,
    title,
    message,
    notification_type,
    users,
    content_object=None,
    link=None,
    expires_at=None,
    is_active=True
):
    """
    Helper function to create notifications with optional links to source objects.
    
    Args:
        tenant: Tenant instance (can be None for personal users)
        title: Notification title
        message: Notification message
        notification_type: Type from Notification.NotificationType choices
        users: List of users or single user to notify
        content_object: Optional - the object this notification is about (Task, Event, etc.)
        link: Optional - custom URL to redirect to (overrides content_object link)
        expires_at: Optional - when notification expires
        is_active: Whether notification is active (default True)
    
    Returns:
        Notification instance
    
    Example:
        # Notify about a task
        task = Task.objects.get(id=1)
        create_notification(
            tenant=request.tenant,
            title=f"New Task: {task.title}",
            message=f"You have been assigned to: {task.title}",
            notification_type=Notification.NotificationType.ALERT,
            users=task.assigned_to.all(),
            content_object=task
        )
        
        # Notify with custom link
        create_notification(
            tenant=request.tenant,
            title="Birthday Reminder",
            message=f"It's {staff.full_name}'s birthday!",
            notification_type=Notification.NotificationType.BIRTHDAY,
            users=[request.user],
            link="/staff/profile/123/"
        )
    """
    # Ensure users is a list
    if not isinstance(users, (list, tuple)):
        if hasattr(users, '__iter__'):
            users = list(users)
        else:
            users = [users]
    
    # Create the notification
    notification_data = {
        'tenant': tenant,
        'title': title,
        'message': message,
        'type': notification_type,
        'is_active': is_active,
    }
    
    # Add content object if provided
    if content_object:
        notification_data['content_type'] = ContentType.objects.get_for_model(content_object)
        notification_data['object_id'] = content_object.pk
    
    # Add custom link if provided
    if link:
        notification_data['link'] = link
    
    # Add expiration if provided
    if expires_at:
        notification_data['expires_at'] = expires_at
    
    notif = Notification.objects.create(**notification_data)
    
    # Create UserNotification for each user
    for user in users:
        UserNotification.objects.create(
            tenant=tenant,
            user=user,
            notification=notif
        )
    
    return notif


def create_task_notification(task, users, action='created'):
    """
    Create a notification for task creation or update.
    
    Args:
        task: Task instance
        users: List of users to notify
        action: 'created', 'updated', or 'reassigned'
    """
    # Get the creator's name for the message
    creator_name = "Someone"
    if task.created_by:
        try:
            # Try to get staff profile name first
            if hasattr(task.created_by, 'staff_profile'):
                staff_profile = task.created_by.staff_profile
                creator_name = f"{staff_profile.first_name} {staff_profile.last_name}".strip()
                if not creator_name:
                    creator_name = task.created_by.username
            # Try user profile name
            elif hasattr(task.created_by, 'user_profile'):
                user_profile = task.created_by.user_profile
                creator_name = f"{user_profile.first_name} {user_profile.last_name}".strip()
                if not creator_name:
                    creator_name = task.created_by.username
            # Fallback to Django user fields
            elif task.created_by.first_name or task.created_by.last_name:
                creator_name = f"{task.created_by.first_name} {task.created_by.last_name}".strip()
            else:
                creator_name = task.created_by.username
        except Exception as e:
            creator_name = task.created_by.username if task.created_by else "Someone"
    
    # Customize message based on action
    # Note: Bell icon shows full message with "by [name]"
    # Browser notification will show shorter message without "by [name]"
    if action == 'created':
        title = f"New Task: {task.title}"
        message = f"A new task has been assigned to you by {creator_name}."
    elif action == 'reassigned':
        title = f"Task Reassigned: {task.title}"
        message = f"Task '{task.title}' has been reassigned to you by {creator_name}."
    else:  # updated
        title = f"Task Updated: {task.title}"
        message = f"Task '{task.title}' has been updated by {creator_name}."
    
    return create_notification(
        tenant=task.tenant,
        title=title,
        message=message,
        notification_type=Notification.NotificationType.ALERT,
        users=users,
        content_object=task,
        link=f"/tasks/{task.id}/",
        expires_at=task.due_date if task.due_date else None
    )


def create_event_notification(event, users):
    """
    Create a notification for event/meeting creation.
    
    Args:
        event: Event/Meeting instance
        users: List of users to notify
    """
    title = f"New Event: {event.title}"
    message = f"You have been invited to: {event.title}"
    
    return create_notification(
        tenant=getattr(event, 'tenant', None),
        title=title,
        message=message,
        notification_type=Notification.NotificationType.EVENT,
        users=users,
        content_object=event,
        link=f"/admins/events/edit/{event.id}/",
        expires_at=getattr(event, 'start_time', None)
    )


def create_birthday_notification(staff_profile, tenant):
    """
    Create a birthday notification.
    
    Args:
        staff_profile: StaffProfile instance
        tenant: Tenant instance
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    title = f"It's {staff_profile.full_name}'s Birthday Today! 🎉"
    message = f"Wish {staff_profile.full_name} a happy birthday!"
    
    # Notify all users in the tenant
    users = User.objects.filter(tenant=tenant)
    
    # Check if notification already exists today
    from django.utils import timezone
    today = timezone.now().date()
    if Notification.objects.filter(
        title=title,
        type=Notification.NotificationType.BIRTHDAY,
        created_at__date=today
    ).exists():
        return None
    
    return create_notification(
        tenant=tenant,
        title=title,
        message=message,
        notification_type=Notification.NotificationType.BIRTHDAY,
        users=users,
        content_object=staff_profile,
        expires_at=timezone.now() + timezone.timedelta(days=1)
    )


def create_memo_notification(memo, user):
    """
    Create a notification for memo submission.
    
    Args:
        memo: Memo instance
        user: User to notify
    """
    title = f"New Memo: {memo.title}"
    message = f"A new memo has been submitted: {memo.title}"
    
    return create_notification(
        tenant=getattr(memo, 'tenant', None),
        title=title,
        message=message,
        notification_type=Notification.NotificationType.MEMO,
        users=[user],
        content_object=memo,
        link=f"/memo/{memo.pk}/"
    )


def create_kyc_notification(kyc_instance, status, user, tenant=None):
    """
    Create a notification for KYC approval/rejection.
    
    Args:
        kyc_instance: KYC instance
        status: 'approved' or 'rejected'
        user: User to notify
        tenant: Tenant instance (optional)
    """
    title = f"KYC {status.capitalize()}"
    message = f"Your KYC verification has been {status}."
    
    return create_notification(
        tenant=tenant,
        title=title,
        message=message,
        notification_type=Notification.NotificationType.ALERT,
        users=[user],
        content_object=kyc_instance
    )


def send_notification_email(user_notification, sender_user=None):
    """
    Send an email alert to the user when they receive a notification.
    
    Args:
        user_notification: UserNotification instance
        sender_user: The user who triggered/sent the notification (optional)
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    from django.core.mail import EmailMessage
    from django.template.loader import render_to_string
    from django.conf import settings
    from .models import CustomUser
    from .viewfuncs.mail_connection import get_email_smtp_connection
    
    notification = user_notification.notification
    recipient = user_notification.user
    
    # Skip if user has no email
    if not recipient.email:
        print(f"Cannot send notification email: User {recipient.username} has no email")
        return False
    
    # Get superuser for email credentials
    superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    if not superuser or not superuser.email_address:
        print("No superuser with email credentials found for notification email")
        return False
    
    # Build notification link
    notification_link = None
    if notification.link:
        notification_link = notification.link
    elif notification.get_absolute_url():
        notification_link = notification.get_absolute_url()
    
    # Build full URL if it's a relative path
    if notification_link and not notification_link.startswith('http'):
        base_domain = "localhost:8000" if settings.DEBUG else "teammanager.ng"
        protocol = "http" if settings.DEBUG else "https"
        if recipient.tenant and recipient.tenant.slug:
            notification_link = f"{protocol}://{recipient.tenant.slug}.{base_domain}{notification_link}"
        else:
            notification_link = f"{protocol}://{base_domain}{notification_link}"
    
    # Determine sender name
    if sender_user:
        sender_name = sender_user.get_full_name() or sender_user.username
        if hasattr(sender_user, 'staff_profile') and sender_user.staff_profile:
            sender_name = sender_user.staff_profile.get_full_name() or sender_name
    else:
        sender_name = "TeamManager System"
    
    # Get recipient's display name
    recipient_name = recipient.get_full_name() or recipient.username
    if hasattr(recipient, 'staff_profile') and recipient.staff_profile:
        recipient_name = recipient.staff_profile.get_full_name() or recipient_name
    
    # Prepare context for email template
    context = {
        'recipient_name': recipient_name,
        'recipient_email': recipient.email,
        'sender_name': sender_name,
        'notification_title': notification.title,
        'notification_message': notification.message,
        'notification_type': notification.type,
        'notification_link': notification_link,
        'notification_date': notification.created_at.strftime('%B %d, %Y at %I:%M %p'),
        'tenant_name': recipient.tenant.name if recipient.tenant else None,
        'current_year': timezone.now().year,
    }
    
    # Render HTML email
    html_content = render_to_string('emails/notification_alert.html', context)
    
    # Build subject based on notification type
    type_labels = {
        'news': 'News',
        'birthday': 'Birthday Reminder',
        'alert': 'Alert',
        'event': 'Event',
        'memo': 'Memo',
    }
    type_label = type_labels.get(notification.type, 'Notification')
    subject = f"[{type_label}] {notification.title}"
    
    # Get SMTP connection
    connection, error_message = get_email_smtp_connection(
        superuser.email_provider, 
        superuser.email_address, 
        superuser.get_smtp_password()
    )
    
    if not connection:
        print(f"SMTP connection failed for notification email: {error_message}")
        return False
    
    # Send email
    try:
        email = EmailMessage(
            subject=subject,
            body=html_content,
            from_email=superuser.email_address,
            to=[recipient.email],
            connection=connection
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        print(f"Notification email sent successfully to {recipient.email}")
        return True
    except Exception as e:
        print(f"Failed to send notification email to {recipient.email}: {e}")
        return False
