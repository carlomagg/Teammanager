# documents/kyc_models.py
from django.db import models
from django.conf import settings
from tenants.models import Tenant
import os


def upload_to_kyc_documents(instance, filename):
    """Upload path for KYC documents"""
    if hasattr(instance, 'user_profile'):
        username = instance.user_profile.user.username
        return os.path.join('kyc_documents', 'users', username, filename)
    elif hasattr(instance, 'staff_profile'):
        username = instance.staff_profile.user.username
        tenant_name = instance.staff_profile.tenant.name
        return os.path.join('kyc_documents', 'staff', tenant_name, username, filename)
    return os.path.join('kyc_documents', 'unknown', filename)


def upload_to_kyb_documents(instance, filename):
    """Upload path for KYB documents"""
    tenant_name = instance.company_profile.tenant.name
    return os.path.join('kyb_documents', tenant_name, filename)


def upload_to_director_documents(instance, filename):
    """Upload path for director documents"""
    tenant_name = instance.company_profile.tenant.name
    director_name = f"{instance.first_name}_{instance.last_name}".replace(' ', '_')
    return os.path.join('kyb_documents', tenant_name, 'directors', director_name, filename)


class UserKYC(models.Model):
    """KYC information for UserProfile (personal accounts)"""
    
    KYC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    ID_TYPE_CHOICES = [
        ('nin', 'National ID Card / NIN'),
        ('passport', 'International Passport'),
        ('drivers_license', 'Driver\'s License'),
        ('voters_card', 'Voter\'s Card'),
    ]
    
    user_profile = models.OneToOneField('documents.UserProfile', on_delete=models.CASCADE, related_name='kyc')
    
    # Identity Information
    nin = models.CharField(max_length=11, blank=True, null=True, verbose_name="National Identification Number")
    bvn = models.CharField(max_length=11, blank=True, null=True, verbose_name="Bank Verification Number")
    
    # ID Document
    id_type = models.CharField(max_length=50, choices=ID_TYPE_CHOICES, blank=True, null=True)
    id_number = models.CharField(max_length=100, blank=True, null=True)
    id_front_file = models.FileField(upload_to=upload_to_kyc_documents, blank=True, null=True, verbose_name="ID Front")
    id_back_file = models.FileField(upload_to=upload_to_kyc_documents, blank=True, null=True, verbose_name="ID Back")
    
    # Proof of Address
    utility_bill_file = models.FileField(upload_to=upload_to_kyc_documents, blank=True, null=True, verbose_name="Utility Bill or Bank Statement (≤ 3 months)")
    
    # Next of Kin Information
    next_of_kin_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Next of Kin Full Name")
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, null=True, verbose_name="Relationship")
    next_of_kin_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Next of Kin Phone")
    next_of_kin_address = models.TextField(blank=True, null=True, verbose_name="Next of Kin Address")
    
    # Status
    kyc_status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default='pending')
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_rejection_reason = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_user_kycs')
    
    class Meta:
        verbose_name = "User KYC"
        verbose_name_plural = "User KYCs"
        permissions = [
            ('verify_kyc', 'Can verify KYC/KYB submissions'),
        ]
    
    def __str__(self):
        return f"KYC for {self.user_profile.user.username} - {self.kyc_status}"
    
    def get_absolute_url(self):
        """Return the URL to view this KYC status"""
        from django.urls import reverse
        return reverse('kyc_status')
    
    def is_complete(self):
        """Check if basic KYC information is complete"""
        return all([
            self.nin or self.bvn,
            self.id_type,
            self.id_front_file,
        ])


class StaffKYC(models.Model):
    """KYC information for StaffProfile (tenant staff accounts)"""
    
    KYC_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    ID_TYPE_CHOICES = [
        ('nin', 'National ID Card / NIN'),
        ('passport', 'International Passport'),
        ('drivers_license', 'Driver\'s License'),
        ('voters_card', 'Voter\'s Card'),
    ]
    
    staff_profile = models.OneToOneField('documents.StaffProfile', on_delete=models.CASCADE, related_name='kyc')
    
    # Identity Information
    nin = models.CharField(max_length=11, blank=True, null=True, verbose_name="National Identification Number")
    bvn = models.CharField(max_length=11, blank=True, null=True, verbose_name="Bank Verification Number")
    
    # ID Document
    id_type = models.CharField(max_length=50, choices=ID_TYPE_CHOICES, blank=True, null=True)
    id_number = models.CharField(max_length=100, blank=True, null=True)
    id_front_file = models.FileField(upload_to=upload_to_kyc_documents, blank=True, null=True, verbose_name="ID Front")
    id_back_file = models.FileField(upload_to=upload_to_kyc_documents, blank=True, null=True, verbose_name="ID Back")
    
    # Proof of Address
    utility_bill_file = models.FileField(upload_to=upload_to_kyc_documents, blank=True, null=True, verbose_name="Utility Bill or Bank Statement (≤ 3 months)")
    
    # Next of Kin Information
    next_of_kin_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Next of Kin Full Name")
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, null=True, verbose_name="Relationship")
    next_of_kin_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Next of Kin Phone")
    next_of_kin_address = models.TextField(blank=True, null=True, verbose_name="Next of Kin Address")
    
    # Status
    kyc_status = models.CharField(max_length=20, choices=KYC_STATUS_CHOICES, default='pending')
    kyc_verified_at = models.DateTimeField(null=True, blank=True)
    kyc_rejection_reason = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_staff_kycs')
    
    class Meta:
        verbose_name = "Staff KYC"
        verbose_name_plural = "Staff KYCs"
    
    def __str__(self):
        return f"KYC for {self.staff_profile.user.username} - {self.kyc_status}"
    
    def get_absolute_url(self):
        """Return the URL to view this KYC status"""
        from django.urls import reverse
        return reverse('kyc_status')
    
    def is_complete(self):
        """Check if basic KYC information is complete"""
        return all([
            self.nin or self.bvn,
            self.id_type,
            self.id_front_file,
        ])


class CompanyKYB(models.Model):
    """KYB information for CompanyProfile (business accounts)"""
    
    KYB_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]
    
    company_profile = models.OneToOneField('documents.CompanyProfile', on_delete=models.CASCADE, related_name='kyb')
    
    # Tax & Registration
    rc_number = models.CharField(max_length=50, blank=True, null=True, verbose_name="Business Registration Number (RC Number)")
    tin = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tax Identification Number")
    
    # Legal Documents
    cac_certificate_file = models.FileField(upload_to=upload_to_kyb_documents, blank=True, null=True, verbose_name="CAC Certificate of Incorporation")
    memart_file = models.FileField(upload_to=upload_to_kyb_documents, blank=True, null=True, verbose_name="Memorandum & Articles of Association")
    status_report_file = models.FileField(upload_to=upload_to_kyb_documents, blank=True, null=True, verbose_name="CAC Status Report / Form CAC 1.1")
    scuml_certificate_file = models.FileField(upload_to=upload_to_kyb_documents, blank=True, null=True, verbose_name="SCUML Certificate (if applicable)")
    
    # Proof of Address
    utility_bill_file = models.FileField(upload_to=upload_to_kyb_documents, blank=True, null=True, verbose_name="Utility Bill or Bank Statement (≤ 3 months)")
    
    # Status
    kyb_status = models.CharField(max_length=20, choices=KYB_STATUS_CHOICES, default='pending')
    kyb_verified_at = models.DateTimeField(null=True, blank=True)
    kyb_rejection_reason = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_company_kybs')
    
    class Meta:
        verbose_name = "Company KYB"
        verbose_name_plural = "Company KYBs"
    
    def __str__(self):
        return f"KYB for {self.company_profile.company_name} - {self.kyb_status}"
    
    def get_absolute_url(self):
        """Return the URL to view this KYB status"""
        from django.urls import reverse
        return reverse('kyc_status')
    
    def is_complete(self):
        """Check if basic KYB information is complete"""
        return all([
            self.tin,
            self.cac_certificate_file,
        ])


class CompanyDirector(models.Model):
    """Directors/Beneficial Owners for business accounts"""
    
    ID_TYPE_CHOICES = [
        ('nin', 'National ID Card / NIN'),
        ('passport', 'International Passport'),
        ('drivers_license', 'Driver\'s License'),
        ('voters_card', 'Voter\'s Card'),
    ]
    
    company_profile = models.ForeignKey('documents.CompanyProfile', on_delete=models.CASCADE, related_name='directors')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, help_text="Link to platform user if applicable")
    
    # Personal Information
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True, help_text="Director, Proprietor, CEO, etc.")
    
    # Identity Information
    nin = models.CharField(max_length=11, blank=True, null=True, verbose_name="National Identification Number")
    bvn = models.CharField(max_length=11, blank=True, null=True, verbose_name="Bank Verification Number")
    
    # ID Document
    id_type = models.CharField(max_length=50, choices=ID_TYPE_CHOICES, blank=True, null=True)
    id_front = models.FileField(upload_to=upload_to_director_documents, blank=True, null=True, verbose_name="ID Front")
    id_back = models.FileField(upload_to=upload_to_director_documents, blank=True, null=True, verbose_name="ID Back")
    photo = models.ImageField(upload_to=upload_to_director_documents, blank=True, null=True)
    
    # Ownership
    percentage_ownership = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Percentage ownership for UBO")
    
    # Next of Kin Information
    next_of_kin_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Next of Kin Full Name")
    next_of_kin_relationship = models.CharField(max_length=100, blank=True, null=True, verbose_name="Relationship")
    next_of_kin_phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Next of Kin Phone")
    next_of_kin_address = models.TextField(blank=True, null=True, verbose_name="Next of Kin Address")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Company Director"
        verbose_name_plural = "Company Directors"
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.designation or 'Director'}"
    
    def is_complete(self):
        """Check if director information is complete"""
        return all([
            self.first_name,
            self.last_name,
            self.nin or self.bvn,
            self.id_type,
            self.id_front,
        ])



# Import for field-level approval
from django.contrib.contenttypes.fields import GenericRelation


# Add to UserKYC model
UserKYC.add_to_class('field_approvals', GenericRelation(
    'documents.FieldApprovalStatus',
    content_type_field='content_type',
    object_id_field='object_id',
    related_query_name='user_kyc'
))

# Add to StaffKYC model
StaffKYC.add_to_class('field_approvals', GenericRelation(
    'documents.FieldApprovalStatus',
    content_type_field='content_type',
    object_id_field='object_id',
    related_query_name='staff_kyc'
))

# Add to CompanyKYB model
CompanyKYB.add_to_class('field_approvals', GenericRelation(
    'documents.FieldApprovalStatus',
    content_type_field='content_type',
    object_id_field='object_id',
    related_query_name='company_kyb'
))

# Add to CompanyDirector model
CompanyDirector.add_to_class('field_approvals', GenericRelation(
    'documents.FieldApprovalStatus',
    content_type_field='content_type',
    object_id_field='object_id',
    related_query_name='company_director'
))


# Helper methods for KYC models
def get_or_create_field_approvals(instance, field_config):
    """
    Create field approval records for all reviewable fields.
    field_config: dict mapping field_name to field_label
    """
    from documents.kyc_field_approval_models import FieldApprovalStatus
    from django.contrib.contenttypes.models import ContentType
    
    content_type = ContentType.objects.get_for_model(instance)
    
    for field_name, field_info in field_config.items():
        field_label = field_info.get('label', field_name)
        field_type = field_info.get('type', 'text')
        
        FieldApprovalStatus.objects.get_or_create(
            content_type=content_type,
            object_id=instance.pk,
            field_name=field_name,
            defaults={
                'field_label': field_label,
                'field_type': field_type,
                'status': 'pending'
            }
        )


def get_field_approval_summary(instance):
    """Get summary of field approval statuses"""
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


# Add helper methods to models
UserKYC.get_or_create_field_approvals = lambda self: get_or_create_field_approvals(self, {
    'nin': {'label': 'National Identification Number', 'type': 'text'},
    'bvn': {'label': 'Bank Verification Number', 'type': 'text'},
    'id_type': {'label': 'ID Type', 'type': 'text'},
    'id_number': {'label': 'ID Number', 'type': 'text'},
    'id_front_file': {'label': 'ID Front Image', 'type': 'file'},
    'id_back_file': {'label': 'ID Back Image', 'type': 'file'},
    'utility_bill_file': {'label': 'Utility Bill/Proof of Address', 'type': 'file'},
    'next_of_kin_name': {'label': 'Next of Kin Name', 'type': 'text'},
    'next_of_kin_relationship': {'label': 'Next of Kin Relationship', 'type': 'text'},
    'next_of_kin_phone': {'label': 'Next of Kin Phone', 'type': 'text'},
    'next_of_kin_address': {'label': 'Next of Kin Address', 'type': 'text'},
})

UserKYC.get_field_approval_summary = lambda self: get_field_approval_summary(self)

StaffKYC.get_or_create_field_approvals = lambda self: get_or_create_field_approvals(self, {
    'nin': {'label': 'National Identification Number', 'type': 'text'},
    'bvn': {'label': 'Bank Verification Number', 'type': 'text'},
    'id_type': {'label': 'ID Type', 'type': 'text'},
    'id_number': {'label': 'ID Number', 'type': 'text'},
    'id_front_file': {'label': 'ID Front Image', 'type': 'file'},
    'id_back_file': {'label': 'ID Back Image', 'type': 'file'},
    'utility_bill_file': {'label': 'Utility Bill/Proof of Address', 'type': 'file'},
    'next_of_kin_name': {'label': 'Next of Kin Name', 'type': 'text'},
    'next_of_kin_relationship': {'label': 'Next of Kin Relationship', 'type': 'text'},
    'next_of_kin_phone': {'label': 'Next of Kin Phone', 'type': 'text'},
    'next_of_kin_address': {'label': 'Next of Kin Address', 'type': 'text'},
})

StaffKYC.get_field_approval_summary = lambda self: get_field_approval_summary(self)

CompanyKYB.get_or_create_field_approvals = lambda self: get_or_create_field_approvals(self, {
    'rc_number': {'label': 'RC Number', 'type': 'text'},
    'tin': {'label': 'Tax Identification Number', 'type': 'text'},
    'cac_certificate_file': {'label': 'CAC Certificate', 'type': 'file'},
    'memart_file': {'label': 'MEMART Document', 'type': 'file'},
    'status_report_file': {'label': 'CAC Status Report', 'type': 'file'},
    'scuml_certificate_file': {'label': 'SCUML Certificate', 'type': 'file'},
    'utility_bill_file': {'label': 'Utility Bill/Proof of Address', 'type': 'file'},
})

CompanyKYB.get_field_approval_summary = lambda self: get_field_approval_summary(self)
