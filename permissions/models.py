import os
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from tenants.models import Tenant


def upload_to_permissions_attachments(instance, filename):
    """Upload path for permissions attachments."""
    if instance.permissions and instance.permissions.tenant:
        tenant_name = instance.permissions.tenant.name
    else:
        tenant_name = "Personal"
    return os.path.join('permissions_attachments', tenant_name, filename)


class PermissionCategory(models.Model):
    """Categories for organizing permissions (e.g. Medical Appointment, Personal Errand)."""
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='permission_categories'
    )
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_permissions_categories'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Permission Categories'
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class Permission(models.Model):
    """
    Core permissions/mail entity.
    Supports internal creation and external submission.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('in_view', 'In View'),
        ('escalated', 'Escalated'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('positive_response', 'Positive Response'),
        ('negative_response', 'Negative Response'),
        ('completed', 'Completed'),
        ('closed', 'Closed'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='permissions'
    )
    reference_number = models.CharField(
        max_length=50, unique=True, editable=False
    )
    title = models.CharField(max_length=255)
    description = models.TextField(help_text="Reason for permission")
    category = models.ForeignKey(
        PermissionCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='permissions'
    )
    
    # Permission-specific fields
    start_date = models.DateField(null=True, blank=True, help_text="Start date of permission")
    end_date = models.DateField(null=True, blank=True, help_text="End date of permission")
    
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default='medium'
    )
    
    # External submission flag (always False for internal-only app)
    is_external = models.BooleanField(default=False)
    external_name = models.CharField(max_length=255, blank=True, null=True)
    external_email = models.EmailField(blank=True, null=True)

    # Routing
    current_holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='held_permissionss',
        help_text="Who currently has this permissions"
    )
    to_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='permissions_to_me',
        help_text="Initial recipients of this permission (send to field)"
    )
    cc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='permissions_cc',
        help_text="CC recipients of this permission"
    )
    bcc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='permissions_bcc',
        help_text="BCC recipients of this permission"
    )

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_permissionss'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'current_holder']),
            models.Index(fields=['tenant', 'created_by']),
        ]

    def __str__(self):
        return f"{self.reference_number} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_reference()
        super().save(*args, **kwargs)

    def _generate_reference(self):
        """Generate a unique reference number like PERMISSIONS-20260311-XXXX."""
        date_str = timezone.now().strftime('%Y%m%d')
        last = Permission.objects.filter(
            reference_number__startswith=f'PERMISSIONS-{date_str}-'
        ).order_by('-reference_number').first()
        if last:
            try:
                last_num = int(last.reference_number.split('-')[-1])
            except (ValueError, IndexError):
                last_num = 0
            next_num = last_num + 1
        else:
            next_num = 1
        return f'PERMISSIONS-{date_str}-{next_num:04d}'

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_closed(self):
        return self.status == 'closed'

    @property
    def can_be_acted_on(self):
        """Check if permissions is in a state where actions can be taken."""
        return self.status not in ('completed', 'closed')

    @property
    def submitter_display(self):
        """Display name of the person who submitted the permissions."""
        if self.is_external:
            return self.external_name or self.external_email or "External"
        if self.created_by:
            return self.created_by.get_full_name() or self.created_by.username
        return "Unknown"
    
    def get_absolute_url(self):
        """Return the URL to view this permissions."""
        from django.urls import reverse
        return reverse('permissions:memo_detail', kwargs={'pk': self.pk})


class PermissionStep(models.Model):
    """
    Each routing step (hand-off) in the permissions trail.
    Records who sent it, who received it, and what action was taken.
    """
    ACTION_CHOICES = [
        ('drafted', 'Drafted'),
        ('created', 'Created'),
        ('forwarded', 'Forwarded'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('escalated', 'Escalated'),
        ('returned', 'Returned'),
        ('received', 'Received (External)'),
        ('positive_response', 'Positive Response'),
        ('negative_response', 'Negative Response'),
        ('kept_in_view', 'Kept In View'),
        ('withdrawn', 'Withdrawn'),
        ('request_info', 'Request for More Information'),
    ]

    permissions = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name='steps'
    )
    step_number = models.PositiveIntegerField()
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='permission_steps_sent'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='permission_steps_received'
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    note = models.TextField(blank=True, help_text="Note for the next person")
    is_private_note = models.BooleanField(
        default=False,
        help_text="If true, only sender and recipient can see this note"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['step_number']
        indexes = [
            models.Index(fields=['permissions', 'step_number']),
        ]

    def __str__(self):
        return f"Step {self.step_number}: {self.get_action_display()} — {self.permissions.reference_number}"


class PermissionAttachment(models.Model):
    """
    Attachments on a permissions. Can be attached at creation or at any step.
    """
    permissions = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name='attachments'
    )
    step = models.ForeignKey(
        PermissionStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='attachments',
        help_text="Step this attachment was added at (null = at creation)"
    )
    file = models.FileField(upload_to=upload_to_permissions_attachments)
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='permissions_attachments'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_name} — {self.permissions.reference_number}"


class PermissionComment(models.Model):
    """
    Comments/notes on the permissions trail.
    Can be private (only sender & current recipient) or public (everyone in trail).
    """
    permissions = models.ForeignKey(
        Permission, on_delete=models.CASCADE, related_name='comments'
    )
    step = models.ForeignKey(
        PermissionStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='permission_comments'
    )
    external_author_name = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Name if comment is from external user"
    )
    content = models.TextField()
    is_private = models.BooleanField(
        default=False,
        help_text="Private = only sender and current recipient can see"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        author_name = self.author.username if self.author else self.external_author_name or "Unknown"
        return f"Comment by {author_name} on {self.permissions.reference_number}"


class PermissionSetting(models.Model):
    """Per-tenant permissions settings."""
    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name='permission_settings'
    )
    notify_external_on_move = models.BooleanField(
        default=True,
        help_text="Email external users when permissions moves to next step"
    )
    allow_external_escalation = models.BooleanField(
        default=True,
        help_text="Allow external users to escalate their memos"
    )
    allow_external_completion = models.BooleanField(
        default=True,
        help_text="Allow external users to mark their memos as completed"
    )

    def __str__(self):
        return f"Permission Settings — {self.tenant.name}"
