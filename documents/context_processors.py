from django.utils import timezone
from django.utils.timezone import now, timedelta
from .models import StaffProfile, Notification, UserNotification, CustomUser, UserFeatureFlag,FeatureAnnouncement
import logging

logger = logging.getLogger(__name__)


def notification_count(request):
    """
    Bell icon badge count and recent notifications for dropdown.

    IMPORTANT: Use `effective_user` / `effective_tenant` when available because
    the app supports subdomain tenants and staff impersonation.
    """
    if not request.user.is_authenticated:
        return {
            'unseen_notification_count': 0,
            'recent_notifications': []
        }

    effective_user = getattr(request, 'effective_user', None) or request.user
    effective_tenant = getattr(request, 'effective_tenant', None) if hasattr(request, 'effective_tenant') else getattr(request, 'tenant', None)

    # Tenant safety: for non-privileged users, ensure we're counting within their tenant context.
    if not request.user.is_superuser and not request.user.is_staff:
        if getattr(effective_user, 'tenant', None) != effective_tenant:
            logger.error("Unauthorized notification_count access: tenant mismatch user=%s effective_tenant=%s",
                         getattr(request.user, 'username', None),
                         getattr(effective_tenant, 'slug', None))
            return {
                'unseen_notification_count': 0,
                'recent_notifications': []
            }

    qs = UserNotification.objects.filter(user=effective_user, dismissed=False)
    # Keep counts tenant-scoped for company users; allow personal (tenant=None) as well.
    qs = qs.filter(tenant=effective_tenant)

    # Get recent notifications for dropdown (last 5)
    recent_notifications = qs.select_related('notification').order_by('-notification__created_at')[:5]

    return {
        'unseen_notification_count': qs.count(),
        'recent_notifications': recent_notifications
    }

def notification_bar(request):
    """
    Context processor for notification bar.
    
    Returns engagement nudge notifications (prefixed with '[Nudge]') in the
    notification bar.  All other notification types remain bell-icon-only
    (handled by notification_count).
    """
    context = {
        'notification_bar_items': [],
        'birthday_self': False,
        'birthday_others': [],
    }

    if not request.user.is_authenticated:
        return context

    effective_user = getattr(request, 'effective_user', None) or request.user
    effective_tenant = (
        getattr(request, 'effective_tenant', None)
        if hasattr(request, 'effective_tenant')
        else getattr(request, 'tenant', None)
    )

    try:
        nudge_notifications = UserNotification.objects.filter(
            user=effective_user,
            tenant=effective_tenant,
            dismissed=False,
            notification__is_active=True,
            notification__title__startswith='[Nudge]',
        ).select_related('notification').order_by('-notification__created_at')[:5]

        context['notification_bar_items'] = [
            un.notification for un in nudge_notifications
        ]
    except Exception:
        pass  # Fail silently — never break every page for a nudge

    return context

def new_features_context(request):
    if not request.user.is_authenticated:
        return {'feature_badges': {}}

    # Get all active announcements
    active_announcements = FeatureAnnouncement.objects.filter(active=True)

    badges = {}

    for announcement in active_announcements:
        key = announcement.key

        # Get or create the user's flag
        flag, created = UserFeatureFlag.objects.get_or_create(
            user=request.user,
            feature_key=key,
            defaults={'first_seen': timezone.now()}
        )

        if flag.dismissed:
            continue

        cutoff = timezone.now() - timedelta(days=announcement.days_visible)
        if flag.first_seen > cutoff:
            badges[key] = announcement.label  # e.g., "new", "updated", etc.

    return {'feature_badges': badges}
