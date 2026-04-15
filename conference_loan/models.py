import os
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from tenants.models import Tenant


def upload_to_loan_documents(instance, filename):
    """Upload path for loan documents."""
    # Use loan ID for path to avoid relationship access issues during upload
    if instance.loan_id:
        return os.path.join('loan_documents', f'loan_{instance.loan_id}', filename)
    return os.path.join('loan_documents', 'temp', filename)


class ConferenceLoan(models.Model):
    """
    Loan/Financing for Conference Organizers in partnership with Transave.
    Only users with complete KYC/KYB can request loans.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Review'),
        ('submitted_to_transave', 'Submitted to Transave'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('disbursed', 'Disbursed'),
        ('repaying', 'Repaying'),
        ('completed', 'Completed'),
        ('defaulted', 'Defaulted'),
        ('cancelled', 'Cancelled'),
    ]

    # Core Information
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE,
        related_name='conference_loans',
        help_text="Tenant requesting the loan"
    )
    conference = models.ForeignKey(
        'documents.Conference', on_delete=models.PROTECT,
        related_name='loans',
        help_text="Conference this loan is for"
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='conference_loan_applications',
        help_text="User applying for the loan"
    )
    
    # Loan Details
    reference_number = models.CharField(
        max_length=50, unique=True, editable=False,
        help_text="Auto-generated loan reference"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Loan amount requested"
    )
    currency = models.CharField(
        max_length=3, default='NGN',
        help_text="Currency code (NGN, USD, etc.)"
    )
    reason = models.TextField(
        help_text="Reason for requesting the loan"
    )
    expected_date = models.DateField(
        help_text="Date when loan is expected/needed"
    )
    
    # Conference Information
    conference_description = models.TextField(
        help_text="Tell us about the conference (audience, expected attendance, etc.)"
    )
    expected_revenue = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Expected revenue from the conference"
    )
    expected_expenses = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Expected total expenses"
    )
    
    # Guarantor Details
    guarantor_name = models.CharField(
        max_length=255,
        help_text="Full name of guarantor"
    )
    guarantor_phone = models.CharField(
        max_length=20,
        help_text="Guarantor's phone number"
    )
    guarantor_email = models.EmailField(
        help_text="Guarantor's email address"
    )
    guarantor_address = models.TextField(
        help_text="Guarantor's residential address"
    )
    guarantor_relationship = models.CharField(
        max_length=100,
        help_text="Relationship to applicant"
    )
    guarantor_occupation = models.CharField(
        max_length=100,
        blank=True, null=True,
        help_text="Guarantor's occupation"
    )
    guarantor_id = models.FileField(
        upload_to='loan_documents/guarantor_ids/',
        blank=True, null=True,
        help_text="Guarantor's ID document"
    )
    guarantor_signature = models.FileField(
        upload_to='loan_documents/guarantor_signatures/',
        blank=True, null=True,
        help_text="Guarantor's signature"
    )
    
    # Status & Processing
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default='draft'
    )
    kyc_verified = models.BooleanField(
        default=False,
        help_text="Whether applicant's KYC/KYB is verified"
    )
    kyc_verification_date = models.DateTimeField(
        null=True, blank=True
    )
    
    # Transave Integration
    transave_loan_id = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Loan ID from Transave system"
    )
    transave_response = models.JSONField(
        default=dict, blank=True,
        help_text="Response data from Transave API"
    )
    
    # Approval/Rejection
    approved_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text="Approved loan amount (may differ from requested)"
    )
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Interest rate percentage"
    )
    repayment_period_months = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Repayment period in months"
    )
    rejection_reason = models.TextField(
        blank=True, null=True,
        help_text="Reason for rejection"
    )
    
    # Disbursement
    disbursement_date = models.DateTimeField(
        null=True, blank=True
    )
    disbursement_reference = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Disbursement transaction reference"
    )
    
    # Repayment Tracking
    total_repaid = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0.00'),
        help_text="Total amount repaid so far"
    )
    next_payment_date = models.DateField(
        null=True, blank=True
    )
    next_payment_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When loan was submitted for review"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_conference_loans'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Internal Notes
    internal_notes = models.TextField(
        blank=True, null=True,
        help_text="Internal notes (not visible to applicant)"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['applicant', 'status']),
            models.Index(fields=['conference']),
            models.Index(fields=['reference_number']),
        ]
        verbose_name = 'Conference Loan'
        verbose_name_plural = 'Conference Loans'

    def __str__(self):
        return f"{self.reference_number} - {self.conference.title} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            self.reference_number = self._generate_reference()
        super().save(*args, **kwargs)

    def _generate_reference(self):
        """Generate unique reference like LOAN-20260409-0001"""
        date_str = timezone.now().strftime('%Y%m%d')
        last = ConferenceLoan.objects.filter(
            reference_number__startswith=f'LOAN-{date_str}-'
        ).order_by('-reference_number').first()
        if last:
            try:
                last_num = int(last.reference_number.split('-')[-1])
            except (ValueError, IndexError):
                last_num = 0
            next_num = last_num + 1
        else:
            next_num = 1
        return f'LOAN-{date_str}-{next_num:04d}'

    def clean(self):
        """Validate loan application"""
        errors = {}
        
        # Check if conference belongs to the tenant (only if tenant is set)
        if self.conference and self.tenant_id and self.conference.tenant_id != self.tenant_id:
            errors['conference'] = "Conference must belong to your organization"
        
        # Check if conference is in the future
        if self.conference and self.conference.start_date < timezone.now():
            errors['conference'] = "Cannot request loan for past conferences"
        
        # Check if expected date is before conference
        if self.expected_date and self.conference:
            if self.expected_date > self.conference.start_date.date():
                errors['expected_date'] = "Expected date must be before conference start date"
        
        # Validate amount
        if self.amount and self.amount <= 0:
            errors['amount'] = "Loan amount must be greater than zero"
        
        if errors:
            raise ValidationError(errors)

    def check_kyc_eligibility(self):
        """
        Check if applicant has complete and verified KYC/KYB.
        Returns (is_eligible, message)
        """
        from documents.kyc_models import UserKYC, StaffKYC, CompanyKYB
        
        # Check if tenant has CompanyKYB
        try:
            company_profile = self.tenant.company_profile
            if hasattr(company_profile, 'kyb'):
                kyb = company_profile.kyb
                if kyb.kyb_status != 'verified':
                    return False, f"Company KYB is {kyb.kyb_status}. Only verified companies can request loans."
                if not kyb.is_complete():
                    return False, "Company KYB information is incomplete."
            else:
                return False, "Company KYB not found. Please complete KYB verification first."
        except Exception as e:
            return False, f"Company profile not found: {str(e)}"
        
        # Check applicant's KYC
        user = self.applicant
        kyc_found = False
        
        # Check UserKYC
        if hasattr(user, 'user_profile') and hasattr(user.user_profile, 'kyc'):
            kyc = user.user_profile.kyc
            kyc_found = True
            if kyc.kyc_status != 'verified':
                return False, f"Your KYC is {kyc.kyc_status}. Only verified users can request loans."
            if not kyc.is_complete():
                return False, "Your KYC information is incomplete."
        
        # Check StaffKYC
        elif hasattr(user, 'staff_profile') and hasattr(user.staff_profile, 'kyc'):
            kyc = user.staff_profile.kyc
            kyc_found = True
            if kyc.kyc_status != 'verified':
                return False, f"Your KYC is {kyc.kyc_status}. Only verified users can request loans."
            if not kyc.is_complete():
                return False, "Your KYC information is incomplete."
        
        if not kyc_found:
            return False, "KYC not found. Please complete KYC verification first."
        
        return True, "KYC/KYB verification complete"

    def submit_for_review(self):
        """Submit loan application for review"""
        # Check KYC eligibility
        is_eligible, message = self.check_kyc_eligibility()
        if not is_eligible:
            raise ValidationError(message)
        
        self.status = 'pending'
        self.submitted_at = timezone.now()
        self.kyc_verified = True
        self.kyc_verification_date = timezone.now()
        self.save()

    def submit_to_transave(self):
        """Submit loan to Transave for processing"""
        from .transave_service import get_transave_service
        
        transave = get_transave_service()
        
        if not transave.is_configured():
            raise ValidationError(
                "Transave API is not configured. Please contact support."
            )
        
        result = transave.submit_loan_application(self)
        
        if result['success']:
            self.transave_loan_id = result.get('loan_id')
            self.transave_response = result.get('data', {})
            self.status = 'submitted_to_transave'
            self.save()
            return True
        else:
            raise ValidationError(
                f"Failed to submit to Transave: {result.get('error')}"
            )
        
        return False

    def approve(self, approved_amount, interest_rate, repayment_months, reviewer):
        """Approve the loan"""
        self.status = 'approved'
        self.approved_amount = approved_amount
        self.interest_rate = interest_rate
        self.repayment_period_months = repayment_months
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save()

    def reject(self, reason, reviewer):
        """Reject the loan"""
        self.status = 'rejected'
        self.rejection_reason = reason
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save()

    def disburse(self, reference):
        """Mark loan as disbursed"""
        self.status = 'disbursed'
        self.disbursement_date = timezone.now()
        self.disbursement_reference = reference
        self.save()

    @property
    def outstanding_balance(self):
        """Calculate outstanding balance"""
        if self.approved_amount:
            return self.approved_amount - self.total_repaid
        return Decimal('0.00')

    @property
    def is_fully_repaid(self):
        """Check if loan is fully repaid"""
        return self.outstanding_balance <= 0

    def get_absolute_url(self):
        """Return URL to view this loan"""
        from django.urls import reverse
        return reverse('conference_loan:loan_detail', kwargs={'pk': self.pk})


class LoanDocument(models.Model):
    """Supporting documents for loan applications"""
    DOCUMENT_TYPE_CHOICES = [
        ('conference_proposal', 'Conference Proposal'),
        ('budget', 'Budget/Financial Plan'),
        ('business_plan', 'Business Plan'),
        ('cac', 'CAC Document'),
        ('memart', 'MEMART Document'),
        ('other', 'Other'),
    ]

    loan = models.ForeignKey(
        ConferenceLoan, on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.CharField(
        max_length=50, choices=DOCUMENT_TYPE_CHOICES
    )
    file = models.FileField(upload_to=upload_to_loan_documents)
    original_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.loan.reference_number}"


class LoanRepayment(models.Model):
    """Track loan repayments"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    loan = models.ForeignKey(
        ConferenceLoan, on_delete=models.CASCADE,
        related_name='repayments'
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Repayment amount"
    )
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_reference = models.CharField(
        max_length=255,
        help_text="Payment transaction reference"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )
    payment_method = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Payment method used"
    )
    notes = models.TextField(blank=True, null=True)
    
    # Transave tracking
    transave_payment_id = models.CharField(
        max_length=255, blank=True, null=True
    )
    transave_response = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Repayment {self.payment_reference} - {self.amount} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update loan's total_repaid if payment is completed
        if self.status == 'completed':
            self.loan.total_repaid += self.amount
            if self.loan.is_fully_repaid:
                self.loan.status = 'completed'
            else:
                self.loan.status = 'repaying'
            self.loan.save()


class LoanComment(models.Model):
    """Comments and notes on loan applications"""
    loan = models.ForeignKey(
        ConferenceLoan, on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    content = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal comments not visible to applicant"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.loan.reference_number}"


# Import for field-level approval
from django.contrib.contenttypes.fields import GenericRelation

# Add to ConferenceLoan model
ConferenceLoan.add_to_class('field_approvals', GenericRelation(
    'documents.FieldApprovalStatus',
    content_type_field='content_type',
    object_id_field='object_id',
    related_query_name='conference_loan'
))


def get_or_create_loan_field_approvals(instance):
    """Create field approval records for all reviewable loan fields"""
    from documents.kyc_field_approval_models import FieldApprovalStatus
    from django.contrib.contenttypes.models import ContentType
    
    content_type = ContentType.objects.get_for_model(instance)
    
    field_config = {
        'amount': {'label': 'Loan Amount', 'type': 'text'},
        'reason': {'label': 'Loan Reason', 'type': 'text'},
        'expected_date': {'label': 'Expected Date', 'type': 'text'},
        'conference_description': {'label': 'Conference Description', 'type': 'text'},
        'expected_revenue': {'label': 'Expected Revenue', 'type': 'text'},
        'expected_expenses': {'label': 'Expected Expenses', 'type': 'text'},
        'guarantor_name': {'label': 'Guarantor Name', 'type': 'text'},
        'guarantor_phone': {'label': 'Guarantor Phone', 'type': 'text'},
        'guarantor_email': {'label': 'Guarantor Email', 'type': 'text'},
        'guarantor_address': {'label': 'Guarantor Address', 'type': 'text'},
        'guarantor_relationship': {'label': 'Guarantor Relationship', 'type': 'text'},
        'guarantor_occupation': {'label': 'Guarantor Occupation', 'type': 'text'},
        'guarantor_id': {'label': 'Guarantor ID Document', 'type': 'file'},
        'guarantor_signature': {'label': 'Guarantor Signature', 'type': 'file'},
    }
    
    for field_name, field_info in field_config.items():
        FieldApprovalStatus.objects.get_or_create(
            content_type=content_type,
            object_id=instance.pk,
            field_name=field_name,
            defaults={
                'field_label': field_info['label'],
                'field_type': field_info['type'],
                'status': 'pending'
            }
        )


def get_loan_field_approval_summary(instance):
    """Get summary of field approval statuses for loan"""
    from documents.kyc_field_approval_models import FieldApprovalStatus
    from django.contrib.contenttypes.models import ContentType
    
    content_type = ContentType.objects.get_for_model(instance)
    approvals = FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=instance.pk
    )
    
    return {
        'total': approvals.count(),
        'approved': approvals.filter(status='approved').count(),
        'rejected': approvals.filter(status='rejected').count(),
        'pending': approvals.filter(status='pending').count(),
    }


# Add helper methods to ConferenceLoan
ConferenceLoan.get_or_create_field_approvals = lambda self: get_or_create_loan_field_approvals(self)
ConferenceLoan.get_field_approval_summary = lambda self: get_loan_field_approval_summary(self)
