# documents/kyc_field_approval_models.py
"""
Field-level approval tracking for KYC/KYB submissions.
Allows admins to approve or reject individual fields/sections.
"""
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class FieldApprovalStatus(models.Model):
    """Track approval status for individual fields in KYC/KYB/Loan submissions"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('resubmitted', 'Resubmitted'),
    ]
    
    # Generic relation to support multiple models (UserKYC, StaffKYC, CompanyKYB, ConferenceLoan)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Field information
    field_name = models.CharField(
        max_length=100,
        help_text="Name of the field being reviewed"
    )
    field_label = models.CharField(
        max_length=255,
        help_text="Human-readable label for the field"
    )
    field_type = models.CharField(
        max_length=50,
        choices=[
            ('text', 'Text Field'),
            ('file', 'File Upload'),
            ('section', 'Section Group'),
        ],
        default='text'
    )
    
    # Approval status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Rejection details
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for rejecting this field"
    )
    
    # Audit fields
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='field_approvals'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['field_name']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status']),
        ]
        unique_together = ['content_type', 'object_id', 'field_name']
        verbose_name = 'Field Approval Status'
        verbose_name_plural = 'Field Approval Statuses'
    
    def __str__(self):
        return f"{self.field_label} - {self.get_status_display()}"
    
    def approve(self, reviewer):
        """Approve this field"""
        from django.utils import timezone
        self.status = 'approved'
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = None
        self.save()
    
    def reject(self, reason, reviewer):
        """Reject this field with a reason"""
        from django.utils import timezone
        self.status = 'rejected'
        self.rejection_reason = reason
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save()
    
    def mark_resubmitted(self):
        """Mark this field as resubmitted after user updates it"""
        from django.utils import timezone
        self.status = 'resubmitted'
        self.updated_at = timezone.now()
        # Keep rejection_reason for reference but clear reviewed_by/at
        self.reviewed_by = None
        self.reviewed_at = None
        self.save()


class FieldApprovalGroup(models.Model):
    """Group related fields together for easier management"""
    
    # Generic relation
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    group_name = models.CharField(max_length=100)
    group_label = models.CharField(max_length=255)
    field_names = models.JSONField(
        default=list,
        help_text="List of field names in this group"
    )
    
    class Meta:
        ordering = ['group_name']
        unique_together = ['content_type', 'object_id', 'group_name']
        verbose_name = 'Field Approval Group'
        verbose_name_plural = 'Field Approval Groups'
    
    def __str__(self):
        return self.group_label
    
    def get_approval_statuses(self):
        """Get all field approval statuses for this group"""
        return FieldApprovalStatus.objects.filter(
            content_type=self.content_type,
            object_id=self.object_id,
            field_name__in=self.field_names
        )
    
    def get_group_status(self):
        """Get overall status of the group"""
        statuses = self.get_approval_statuses()
        if not statuses.exists():
            return 'pending'
        
        if statuses.filter(status='rejected').exists():
            return 'rejected'
        elif statuses.filter(status='pending').exists():
            return 'pending'
        elif statuses.filter(status='approved').count() == len(self.field_names):
            return 'approved'
        return 'pending'
