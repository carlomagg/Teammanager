from django.utils import timezone
import logging
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from documents.models import Notification, UserNotification

logger = logging.getLogger(__name__)

@login_required
def notifications_view(request):
    # Validate tenant access
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        logger.error(f"Unauthorized access by user {request.user.username}: tenant mismatch")
        return HttpResponseForbidden("You are not authorized for this company.")

    # Fetch active UserNotifications for the current user (only those explicitly assigned)
    active_notifications = UserNotification.objects.filter(
        user=request.effective_user,
        tenant=request.effective_user.tenant,
        notification__is_active=True,
        dismissed=False
    ).select_related('notification').order_by('-notification__created_at')

    # Fetch dismissed UserNotifications for the current user
    dismissed_notifications = UserNotification.objects.filter(
        user=request.user,
        tenant=request.user.tenant,
        dismissed=True
    ).select_related('notification').order_by('-seen_at')

    return render(request, 'users/notifications.html', {
        'active_notifications': active_notifications,
        'dismissed_notifications': dismissed_notifications
    })

@require_POST
@login_required
def dismiss_notification(request):
    notification_id = request.POST.get('notification_id')
    try:
        notification = Notification.objects.get(id=notification_id, tenant=request.user.tenant)
        user_notification, created = UserNotification.objects.get_or_create(
            tenant=request.user.tenant,
            user=request.user,
            notification=notification,
            defaults={'seen_at': timezone.now()}
        )
        user_notification.dismissed = True
        user_notification.save()
        return JsonResponse({'status': 'success'})
    except Notification.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Notification not found'}, status=404)

@require_POST
@login_required
def dismiss_all_notifications(request):
    try:
        # Update all non-dismissed UserNotifications for the user
        user_notifications = UserNotification.objects.filter(
            tenant=request.user.tenant,
            user=request.user,
            dismissed=False
        )
        updated_count = user_notifications.update(
            dismissed=True,
            seen_at=timezone.now()
        )
        return JsonResponse({'success': True, 'updated_count': updated_count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def notification_redirect(request, notification_id):
    """
    Redirect to the source object of a notification and mark it as seen.
    """
    try:
        # Get the notification
        notification = get_object_or_404(Notification, id=notification_id)
        
        # Verify user has access to this notification
        user_notification = UserNotification.objects.filter(
            user=request.user,
            notification=notification
        ).first()
        
        if not user_notification:
            logger.warning(f"User {request.user.username} attempted to access notification {notification_id} without permission")
            return HttpResponseForbidden("You don't have access to this notification.")
        
        # Mark as seen (but not dismissed) - update the timestamp
        user_notification.seen_at = timezone.now()
        user_notification.save(update_fields=['seen_at'])
        
        # Get the redirect URL from the notification model
        redirect_url = notification.get_absolute_url()
        
        if redirect_url:
            return redirect(redirect_url)
        
        # ── Fallback for older notifications missing link / content_type ──
        # Try to find the correct URL based on notification type and content
        redirect_url = _find_fallback_url(notification, request.user)
        if redirect_url:
            # Backfill the link for future clicks
            notification.link = redirect_url
            notification.save(update_fields=['link'])
            return redirect(redirect_url)
        
        # Last resort: redirect based on notification type to the relevant app
        type_dashboard_map = {
            'memo': 'memo:dashboard',
            'event': 'event_list',
            'task': 'task_list',
        }
        dashboard_url = type_dashboard_map.get(notification.type)
        if dashboard_url:
            try:
                return redirect(dashboard_url)
            except Exception:
                pass
        
        # Default: go to notifications page
        return redirect('notifications')
            
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return redirect('notifications')
    except Exception as e:
        logger.error(f"Error redirecting notification {notification_id}: {str(e)}", exc_info=True)
        return redirect('notifications')


def _find_fallback_url(notification, user):
    """
    Try to find the correct redirect URL for an old notification that is
    missing the link / content_type fields. Works for all notification types.
    """
    import re
    notif_type = notification.type or ''
    title = (notification.title or '').lower()
    message = notification.message or ''
    
    try:
        # ── Memo notifications ──
        if notif_type == 'memo' or (
            notif_type == 'alert' and any(kw in title for kw in ['memo', 'external memo'])
        ):
            return _find_memo_url(notification)
        
        # ── Task notifications ──
        if notif_type == 'alert' and any(kw in title for kw in ['task']):
            return _find_task_url(notification)
        
        # ── Event notifications ──
        if notif_type == 'event':
            return _find_event_url(notification)
        
        # ── KYC/KYB notifications ──
        if any(kw in title for kw in ['kyc', 'kyb']):
            # Redirect to KYC status page instead of generic profile
            return '/dashboard/kyc/'
        
    except Exception as e:
        logger.error(f"Error in fallback URL for notification {notification.id}: {e}")
    
    return None


def _find_memo_url(notification):
    """Find the memo URL from notification content."""
    import re
    try:
        from memo.models import Memo

        # Strategy 1: If object_id is set, use it directly
        if notification.object_id:
            try:
                memo = Memo.objects.get(pk=notification.object_id)
                return f"/memo/{memo.pk}/"
            except Memo.DoesNotExist:
                pass

        # Strategy 2: Look for a MEMO reference number in the message
        ref_match = re.search(r'(MEMO-\d{8}-\d{4})', notification.message or '')
        if ref_match:
            try:
                memo = Memo.objects.get(reference_number=ref_match.group(1))
                return f"/memo/{memo.pk}/"
            except Memo.DoesNotExist:
                pass

        # Strategy 3: Look for a memo title quoted in the message
        title_match = re.search(r"'([^']+)'", notification.message or '')
        if title_match:
            memo_title = title_match.group(1)
            memo = Memo.objects.filter(
                title=memo_title,
                tenant=notification.tenant,
            ).order_by('-created_at').first()
            if memo:
                return f"/memo/{memo.pk}/"

    except Exception as e:
        logger.error(f"Error in memo fallback for notification {notification.id}: {e}")
    return None


def _find_task_url(notification):
    """Find the task URL from notification content."""
    import re
    try:
        from documents.models import Task

        # Strategy 1: If object_id is set, use it directly
        if notification.object_id:
            try:
                task = Task.objects.get(pk=notification.object_id)
                return f"/tasks/{task.id}/"
            except Task.DoesNotExist:
                pass

        # Strategy 2: Look for task title quoted in the message
        title_match = re.search(r"'([^']+)'", notification.message or '')
        if title_match:
            task_title = title_match.group(1)
            task = Task.objects.filter(
                title=task_title,
                tenant=notification.tenant,
            ).order_by('-created_at').first()
            if task:
                return f"/tasks/{task.id}/"

    except Exception as e:
        logger.error(f"Error in task fallback for notification {notification.id}: {e}")
    return None


def _find_event_url(notification):
    """Find the event URL from notification content."""
    try:
        from documents.models import Event

        # Strategy 1: If object_id is set, use it directly
        if notification.object_id:
            try:
                event = Event.objects.get(pk=notification.object_id)
                return f"/bookings/dashboard/"
            except Event.DoesNotExist:
                pass

        # Strategy 2: Match event by title (notification title often IS the event title)
        event_title = notification.title or ''
        # Strip common prefixes like "New Event: " or "Upcoming Event: "
        for prefix in ['New Event: ', 'Upcoming Event: ', 'Event Reminder: ']:
            if event_title.startswith(prefix):
                event_title = event_title[len(prefix):]
                break
        
        if event_title:
            event = Event.objects.filter(
                title=event_title,
                tenant=notification.tenant,
            ).order_by('-created_at').first()
            if event:
                return f"/bookings/dashboard/"

    except Exception as e:
        logger.error(f"Error in event fallback for notification {notification.id}: {e}")
    return None

