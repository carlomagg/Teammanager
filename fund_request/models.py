import os
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from tenants.models import Tenant


def upload_to_fund_request_attachments(instance, filename):
    """Upload path for fund_request attachments."""
    if instance.fund_request and instance.fund_request.tenant:
        tenant_name = instance.fund_request.tenant.name
    else:
        tenant_name = "Personal"
    return os.path.join('fund_request_attachments', tenant_name, filename)


class FundRequestCategory(models.Model):
    """Categories for organizing fund requests (e.g. Travel, Office Supplies, Training)."""
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='fund_request_categories'
    )
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_fund_request_categories'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'FundRequest Categories'
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class FundRequestType(models.Model):
    """Request types for fund requests (e.g. Advance, Reimbursement, Petty Cash)."""
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        null=True, blank=True, related_name='fund_request_types'
    )
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='created_fund_request_types'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'FundRequest Types'
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name


class FundRequest(models.Model):
    """
    Core fund_request/mail entity.
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
        null=True, blank=True, related_name='fund_requests'
    )
    reference_number = models.CharField(
        max_length=50, unique=True, editable=False
    )
    title = models.CharField(max_length=255)
    description = models.TextField(help_text="Purpose of fund request")
    category = models.ForeignKey(
        FundRequestCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fund_requests'
    )
    
    # Fund Request-specific fields
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount requested")
    currency = models.CharField(max_length=3, default='NGN', help_text="Currency code")
    request_type = models.ForeignKey(
        'FundRequestType', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fund_requests',
        help_text="Type of fund request"
    )
    expense_date = models.DateField(null=True, blank=True, help_text="Date of expense")
    
    # Bank account details
    account_name = models.CharField(max_length=255, blank=True, null=True, help_text="Account holder name")
    bank_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of the bank")
    account_number = models.CharField(max_length=50, blank=True, null=True, help_text="Bank account number")
    
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
        null=True, blank=True, related_name='held_fund_requests',
        help_text="Who currently has this fund_request"
    )
    to_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='fund_requests_to_me',
        help_text="Initial recipients of this fund request (send to field)"
    )
    cc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='fund_requests_cc',
        help_text="CC recipients of this fund request"
    )
    bcc_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='fund_requests_bcc',
        help_text="BCC recipients of this fund request"
    )

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_fund_requests'
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
        """Generate a unique reference number like FUND_REQUEST-20260311-XXXX."""
        date_str = timezone.now().strftime('%Y%m%d')
        last = FundRequest.objects.filter(
            reference_number__startswith=f'FUND_REQUEST-{date_str}-'
        ).order_by('-reference_number').first()
        if last:
            try:
                last_num = int(last.reference_number.split('-')[-1])
            except (ValueError, IndexError):
                last_num = 0
            next_num = last_num + 1
        else:
            next_num = 1
        return f'FUND_REQUEST-{date_str}-{next_num:04d}'

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_closed(self):
        return self.status == 'closed'

    @property
    def can_be_acted_on(self):
        """Check if fund_request is in a state where actions can be taken."""
        return self.status not in ('completed', 'closed')

    @property
    def submitter_display(self):
        """Display name of the person who submitted the fund_request."""
        if self.is_external:
            return self.external_name or self.external_email or "External"
        if self.created_by:
            return self.created_by.get_full_name() or self.created_by.username
        return "Unknown"
    
    def get_absolute_url(self):
        """Return the URL to view this fund_request."""
        from django.urls import reverse
        return reverse('fund_request:memo_detail', kwargs={'pk': self.pk})


class FundRequestStep(models.Model):
    """
    Each routing step (hand-off) in the fund_request trail.
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

    fund_request = models.ForeignKey(
        FundRequest, on_delete=models.CASCADE, related_name='steps'
    )
    step_number = models.PositiveIntegerField()
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fund_request_steps_sent'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fund_request_steps_received'
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
            models.Index(fields=['fund_request', 'step_number']),
        ]

    def __str__(self):
        return f"Step {self.step_number}: {self.get_action_display()} — {self.fund_request.reference_number}"


class FundRequestAttachment(models.Model):
    """
    Attachments on a fund_request. Can be attached at creation or at any step.
    """
    fund_request = models.ForeignKey(
        FundRequest, on_delete=models.CASCADE, related_name='attachments'
    )
    step = models.ForeignKey(
        FundRequestStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='attachments',
        help_text="Step this attachment was added at (null = at creation)"
    )
    file = models.FileField(upload_to=upload_to_fund_request_attachments)
    original_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fund_request_attachments'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_name} — {self.fund_request.reference_number}"


class FundRequestComment(models.Model):
    """
    Comments/notes on the fund_request trail.
    Can be private (only sender & current recipient) or public (everyone in trail).
    """
    fund_request = models.ForeignKey(
        FundRequest, on_delete=models.CASCADE, related_name='comments'
    )
    step = models.ForeignKey(
        FundRequestStep, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='fund_request_comments'
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
        return f"Comment by {author_name} on {self.fund_request.reference_number}"


class FundRequestSetting(models.Model):
    """Per-tenant fund_request settings."""
    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name='fund_request_settings'
    )
    notify_external_on_move = models.BooleanField(
        default=True,
        help_text="Email external users when fund_request moves to next step"
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
        return f"FundRequest Settings — {self.tenant.name}"
