# documents/viewfuncs/notification_api.py
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.utils import timezone
from datetime import timedelta
from documents.models import UserNotification
import logging

logger = logging.getLogger(__name__)


@require_GET
@login_required
def check_new_notifications(request):
    """
    API endpoint to check for new notifications.
    Returns notifications created in the last 90 seconds.
    """
    try:
        # Get notifications from the last 90 seconds (to account for polling delays)
        time_threshold = timezone.now() - timedelta(seconds=90)
        
        new_notifications = UserNotification.objects.filter(
            user=request.user,
            tenant=getattr(request, 'tenant', None),
            dismissed=False,
            notification__is_active=True,
            notification__created_at__gte=time_threshold
        ).select_related('notification').order_by('-notification__created_at')
        
        # Debug logging
        logger.info(f"Checking notifications for user {request.user.username}, tenant: {getattr(request, 'tenant', None)}")
        logger.info(f"Found {new_notifications.count()} new notifications")
        
        # Get total unseen count
        total_count = UserNotification.objects.filter(
            user=request.user,
            tenant=getattr(request, 'tenant', None),
            dismissed=False,
            notification__is_active=True
        ).count()
        
        # Format notifications for browser notification
        notifications_data = []
        for user_notif in new_notifications:
            notif = user_notif.notification
            
            # Get the redirect URL from the notification (same as bell icon)
            redirect_url = notif.get_absolute_url() or f'/notifications/{notif.id}/'
            
            # For browser notifications, remove "by [name]" from the message
            # to keep it shorter and cleaner
            browser_message = notif.message
            if ' by ' in browser_message:
                # Remove everything after " by " for browser notifications
                browser_message = browser_message.split(' by ')[0] + '.'
            
            notif_data = {
                'id': notif.id,
                'title': notif.title,
                'message': browser_message,  # Use shortened message for browser
                'type': notif.type,
                'created_at': notif.created_at.isoformat(),
                'url': redirect_url,
            }
            notifications_data.append(notif_data)
            logger.info(f"Notification {notif.id}: {notif.title} - URL: {redirect_url}")
        
        return JsonResponse({
            'success': True,
            'notifications': notifications_data,
            'total_count': total_count
        })
        
    except Exception as e:
        logger.error(f"Error checking new notifications: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_GET
@login_required
def notification_settings(request):
    """
    API endpoint to get/update notification settings.
    """
    try:
        # For now, just return browser notification permission status
        return JsonResponse({
            'success': True,
            'browser_notifications_enabled': True,  # This is checked on client side
        })
    except Exception as e:
        logger.error(f"Error getting notification settings: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
