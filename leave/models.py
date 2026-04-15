import os
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from tenants.models import Tenant


def upload_to_leave_attachments(instance, filename):
    """Upload path for leave attachments."""
    if instance.leave and instance.leave.tenant:
        tenant_name = instance.leave.tenant.name
    else:
        tenant_name = "Personal"
    return os.path.join('leave_attachments', tenant_name, filename)


class LeaveCategory(models.Model):
    """Categories for organizing leaves (e.g. Annual Leave, Sick Leave)."""
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='leave_categories'
    )
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_leave_categories'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Leave Categories'
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class Leave(models.Model):
    """
    Core leave/mail entity.
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
        null=True, blank=True, related_name='leaves'
    )
    reference_number = models.CharField(
        max_length=50, unique=True, editable=False
    )
    title = models.CharField(max_length=255)
    description = models.TextField(help_text="Reason for leave")
    category = models.ForeignKey(
        LeaveCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leaves'
    )
    
    # Leave-specific fields
    start_date = models.DateField(help_text="Leave start date")
    end_date = models.DateField(help_text="Leave end date")
    days_requested = models.PositiveIntegerField(default=1, help_text="Number of days")
    
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
        null=True, blank=True, related_name='held_leaves',
        help_text="Who currently has this leave"
    )
    to_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='leaves_to_me',
        help_text="Initial recipients of this leave (send to field)"
    )
    cc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='leaves_cc',
        help_text="CC recipients of this leave"
    )
    bcc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='leaves_bcc',
        help_text="BCC recipients of this leave"
    )

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_leaves'
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
        """Generate a unique reference number like LEAVE-20260311-XXXX."""
        date_str = timezone.now().strftime('%Y%m%d')
        last = Leave.objects.filter(
            reference_number__startswith=f'LEAVE-{date_str}-'
        ).order_by('-reference_number').first()
        if last:
            try:
                last_num = int(last.reference_number.split('-')[-1])
            except (ValueError, IndexError):
                last_num = 0
            next_num = last_num + 1
        else:
            next_num = 1
        return f'LEAVE-{date_str}-{next_num:04d}'

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_closed(self):
        return self.status == 'closed'

    @property
    def can_be_acted_on(self):
        """Check if leave is in a state where actions can be taken."""
        return self.status not in ('completed', 'closed')

    @property
    def submitter_display(self):
        """Display name of the person who submitted the leave."""
        if self.is_external:
            return self.external_name or self.external_email or "External"
        if self.created_by:
            return self.created_by.get_full_name() or self.created_by.username
        return "Unknown"
    
    def get_absolute_url(self):
        """Return the URL to view this leave."""
        from django.urls import reverse
        return reverse('leave:memo_detail', kwargs={'pk': self.pk})


class LeaveStep(models.Model):
    """
    Each routing step (hand-off) in the leave trail.
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

    leave = models.ForeignKey(
        Leave, on_delete=models.CASCADE, related_name='steps'
    )
    step_number = models.PositiveIntegerField()
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leave_steps_sent'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leave_steps_received'
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
            models.Index(fields=['leave', 'step_number']),
        ]

    def __str__(self):
        return f"Step {self.step_number}: {self.get_action_display()} — {self.leave.reference_number}"


class LeaveAttachment(models.Model):
    """
    Attachments on a leave. Can be attached at creation or at any step.
    """
    leave = models.ForeignKey(
        Leave, on_delete=models.CASCADE, related_name='attachments'
    )
    step = models.ForeignKey(
        LeaveStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='attachments',
        help_text="Step this attachment was added at (null = at creation)"
    )
    file = models.FileField(upload_to=upload_to_leave_attachments)
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leave_attachments'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_name} — {self.leave.reference_number}"


class LeaveComment(models.Model):
    """
    Comments/notes on the leave trail.
    Can be private (only sender & current recipient) or public (everyone in trail).
    """
    leave = models.ForeignKey(
        Leave, on_delete=models.CASCADE, related_name='comments'
    )
    step = models.ForeignKey(
        LeaveStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leave_comments'
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
        return f"Comment by {author_name} on {self.leave.reference_number}"


class LeaveSetting(models.Model):
    """Per-tenant leave settings."""
    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name='leave_settings'
    )
    notify_external_on_move = models.BooleanField(
        default=True,
        help_text="Email external users when leave moves to next step"
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
        return f"Leave Settings — {self.tenant.name}"
