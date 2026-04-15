"""
generate_engagement_nudges.py

Daily management command that checks user activity across key features
(Folders/Files, Tasks, Profile) and creates friendly notification nudges
to encourage engagement.

Usage:
    python manage.py generate_engagement_nudges
    python manage.py generate_engagement_nudges --days 7
    python manage.py generate_engagement_nudges --profile-threshold 80
"""
import random
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from documents.models import (
    CustomUser, Notification, UserNotification,
    File, Task, StaffProfile, UserProfile,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Message pools — a random one is picked each time to keep it fresh
# ──────────────────────────────────────────────────────────────────────
FOLDER_MESSAGES = [
    ("📁 Your folders are looking quiet!",
     "You haven't uploaded a file in {days}+ days. Keep your workspace organized — upload something today!"),
    ("📁 Time to refresh your folders!",
     "It's been {days}+ days since your last upload. Drop a file in to stay on top of things."),
    ("📁 Your folders miss you!",
     "No new files in {days}+ days. Upload a document to keep your workspace lively."),
]

TASK_MESSAGES = [
    ("✅ Haven't done something challenging today?",
     "Create a task now and crush your goals! No recent task activity in {days}+ days."),
    ("✅ No recent tasks — time to set a goal!",
     "It's been {days}+ days since your last task activity. Stay productive — create or complete a task."),
    ("✅ Your task board is waiting for you!",
     "You haven't interacted with tasks in {days}+ days. Plan your next win today."),
]

PROFILE_MESSAGES = [
    ("👤 Your profile is only {pct}% complete!",
     "Fill in your details so your team knows you better. A complete profile builds trust."),
    ("👤 Complete your profile to stand out!",
     "You're at {pct}% — add a few more details and let people know who you are."),
    ("👤 Almost there — finish your profile!",
     "Your profile is {pct}% done. A little more effort and you'll have a polished presence."),
]

# Unique prefix used to identify engagement nudges (for filtering / dedup)
NUDGE_PREFIX = "[Nudge]"


class Command(BaseCommand):
    help = "Generate engagement nudge notifications for inactive users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="Inactivity threshold in days for files and tasks (default: 3).",
        )
        parser.add_argument(
            "--profile-threshold",
            type=int,
            default=70,
            help="Profile completion percentage below which a nudge is sent (default: 70).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        profile_threshold = options["profile_threshold"]
        cutoff = timezone.now() - timedelta(days=days)
        now = timezone.now()

        active_users = CustomUser.objects.filter(is_active=True)
        created_count = 0

        for user in active_users:
            tenant = getattr(user, "tenant", None)

            # ── 1. Folder / File nudge ──────────────────────────────
            recent_files = File.objects.filter(
                uploaded_by=user,
                uploaded_at__gte=cutoff,
            ).exists()

            if not recent_files:
                title, message = self._pick(FOLDER_MESSAGES, days=days)
                if self._create_nudge(user, tenant, title, message, now):
                    created_count += 1

            # ── 2. Task nudge ───────────────────────────────────────
            recent_tasks = Task.objects.filter(
                Q(created_by=user) | Q(assigned_to=user),
                created_at__gte=cutoff,
            ).exists()

            if not recent_tasks:
                title, message = self._pick(TASK_MESSAGES, days=days)
                if self._create_nudge(user, tenant, title, message, now):
                    created_count += 1

            # ── 3. Profile completeness nudge ───────────────────────
            pct = self._get_profile_completion(user)
            if pct is not None and pct < profile_threshold:
                title, message = self._pick(PROFILE_MESSAGES, pct=pct)
                if self._create_nudge(user, tenant, title, message, now):
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — {created_count} engagement nudge(s) created."
            )
        )

    # ─────────────────────────── helpers ──────────────────────────────

    @staticmethod
    def _pick(pool, **kwargs):
        """Pick a random message from the pool and format it."""
        title_tpl, msg_tpl = random.choice(pool)
        return (
            f"{NUDGE_PREFIX} {title_tpl.format(**kwargs)}",
            msg_tpl.format(**kwargs),
        )

    @staticmethod
    def _get_profile_completion(user):
        """Return profile completion % or None if no profile exists."""
        if user.is_personal:
            try:
                return user.user_profile.profile_completion
            except UserProfile.DoesNotExist:
                return 0  # No profile at all → nudge them
        else:
            try:
                return user.staff_profile.profile_completion
            except StaffProfile.DoesNotExist:
                return 0

    @staticmethod
    def _create_nudge(user, tenant, title, message, now):
        """
        Create a Notification + UserNotification pair if no active
        (non-dismissed) nudge with the same title prefix exists for this user
        within the last 3 days.
        """
        # Deduplication: check if an active nudge of the same *category*
        # already exists for this user. We match on '[Nudge] <emoji>' which
        # is reliably ≤12 chars and uniquely identifies each feature category.
        # e.g.  '[Nudge] 📁'  /  '[Nudge] ✅'  /  '[Nudge] 👤'
        category_key = title[:12]

        already_exists = UserNotification.objects.filter(
            user=user,
            dismissed=False,
            notification__title__startswith=category_key,
            notification__created_at__gte=now - timedelta(days=3),
            notification__is_active=True,
        ).exists()

        if already_exists:
            return False

        notif = Notification.objects.create(
            tenant=tenant,
            title=title,
            message=message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            expires_at=now + timedelta(days=3),
        )
        UserNotification.objects.create(
            tenant=tenant,
            user=user,
            notification=notif,
        )
        logger.info("Created nudge for user %s: %s", user.username, title)
        return True
