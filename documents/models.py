# documents/models.py
from sre_parse import CATEGORIES
from functools import cached_property
from django.db import models
from django.db.models import Q, JSONField, UniqueConstraint
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.validators import MinValueValidator, MaxValueValidator
from django_countries.fields import CountryField
from djmoney.models.fields import CurrencyField
from raadaa import settings
from django.utils import timezone
from datetime import timedelta
import os, json, uuid, requests
from django.core.exceptions import ValidationError
from cryptography.fernet import Fernet
from tenants.models import Subscription, SubscriptionType, Tenant
from cities_light.models import Region 
from djmoney.money import Money
from moneyed.classes import Currency
from babel.core import Locale
from decimal import Decimal
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.core.mail import send_mail
from uuid import uuid4
from django.utils.text import slugify
# Import KYC/KYB models
from documents.kyc_models import UserKYC, StaffKYC, CompanyKYB, CompanyDirector
from documents.invoice_models import Invoice, InvoiceSendSchedule, Receipt, Ticket, TicketComment, TicketCategory, TicketPriority, TicketStatusHistory, QueueEntry



# Generate or load encryption key for SMTP password
if settings.FERNET_KEY:
    ENCRYPTION_KEY = settings.FERNET_KEY
    print(f"DJANGO_SECRET_KEY: {ENCRYPTION_KEY}")
    cipher = Fernet(key=ENCRYPTION_KEY)

def get_currency_choices():
    locale = Locale('en')
    return [(code, code) for code in locale.currencies.keys()]

def upload_to_documents_word(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    username = instance.created_by.username if instance.created_by else "anonymous"
    return os.path.join('documents', tenant_name, username, 'word', filename)

def upload_to_documents_pdf(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    username = instance.created_by.username if instance.created_by else "anonymous"
    return os.path.join('documents', tenant_name, username, 'pdf', filename)

class UserFeatureFlag(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feature_flags')
    feature_key = models.CharField(max_length=100, unique=False)  # e.g., "job_board", "conference_board"
    first_seen = models.DateTimeField(auto_now_add=True)
    dismissed = models.BooleanField(default=False)  # Optional: if user manually dismisses

    class Meta:
        unique_together = ('user', 'feature_key')

    def is_new(self, days=7):
        """Return True if feature is still considered 'new' for this user"""
        if self.dismissed:
            return False
        cutoff = timezone.now() - timedelta(days=days)
        return self.first_seen > cutoff
    
class FeatureAnnouncement(models.Model):
    LABEL_CHOICES = [
        ('new', 'New'),
        ('updated', 'Updated'),
        ('beta', 'Beta'),
    ]
    key = models.CharField(max_length=100, unique=True, help_text="Unique identifier, e.g., 'job_board'")
    label = models.CharField(max_length=20, default="new", choices=LABEL_CHOICES, help_text='Text to display, e.g., "new", "updated", "beta"')
    days_visible = models.PositiveIntegerField(default=7, help_text="How many days to show after first seen")
    active = models.BooleanField(default=True, help_text="Uncheck to disable globally")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.key} ({self.label})"

class Document(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ('approval', 'Approval Letter'),
        ('sla', 'SLA Document'),
        ('Uploaded', 'Uploaded Document'),
    ]

    DOCUMENT_SOURCE_CHOICES = [
        ('template', 'Use Template'),
        ('upload', 'Upload Document'),
        ('editor', 'Created in Editor'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    company_name = models.CharField(max_length=255)
    company_address = models.TextField()
    contact_person_name = models.CharField(max_length=255)
    contact_person_email = models.EmailField()
    contact_person_designation = models.CharField(max_length=255)
    sales_rep = models.CharField(max_length=255)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_documents")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_documents")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    word_file = models.FileField(upload_to=upload_to_documents_word)
    pdf_file = models.FileField(upload_to=upload_to_documents_pdf, null=True, blank=True)
    # uploaded_file = models.FileField(upload_to='documents/', blank=True, null=True)

    document_source = models.CharField(max_length=20, choices=DOCUMENT_SOURCE_CHOICES, default='template')

    # For editor-created documents: store raw title and HTML content to allow editing
    editor_title = models.CharField(max_length=255, blank=True, null=True)
    editor_content = models.TextField(blank=True, null=True)

    email_sent = models.BooleanField(default=False)  # Track if email was sent

    def __str__(self):
        return f"{self.document_type} - {self.company_name}"


from django.contrib.auth.models import AbstractUser
from django.db import models

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')

    def __str__(self):
        return self.name
    

class CustomUser(AbstractUser):
    EMAIL_PROVIDERS = [
        ('gmail', 'Gmail'),
        ('yahoo', 'Yahoo'),
        ('outlook', 'Outlook'),
        ('zoho', 'Zoho'),
        ('icloud', 'iCloud'),
        ('zeptomail', 'ZeptoMail'),
    ]

    SUB_STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('trial', 'Trial'),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, blank=True, null=True, related_name="customuser")
    roles = models.ManyToManyField(Role, blank=True)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    teams = models.ManyToManyField('Team', blank=True, related_name='members')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    email_address = models.EmailField(blank=True, null=True, help_text="Email address for email provider. To enable email sending.")
    email_password = models.CharField(max_length=1000, blank=True, null=True, help_text="Password for email provider or Send Token for Zepto Mail. To enable email sending.")  # Encrypted SMTP password
    email_provider = models.CharField(max_length=20, choices=EMAIL_PROVIDERS, blank=True, null=True)
    is_personal = models.BooleanField(default=False)
    must_reset_password = models.BooleanField(default=False)
    subscription_status = models.CharField(max_length=20, choices=SUB_STATUS_CHOICES, default='inactive')
    subscription_end_date = models.DateField(null=True, blank=True, help_text="When the user's access expires")
    subscription_plan = models.ForeignKey(SubscriptionType, on_delete=models.SET_NULL,  null=True, blank=True, related_name='users', help_text="Current subscription plan"
    )

    personal_external_token = models.UUIDField(default=uuid.uuid4, editable=False, null=True, blank=True, help_text="Unique token for external users to submit memos directly to this user")

    def save(self, *args, **kwargs):
        """Generate personal external token if not set"""
        if not self.personal_external_token:
            self.personal_external_token = uuid.uuid4()
        super().save(*args, **kwargs)

    def set_smtp_password(self, password):
        """Encrypt and store SMTP password or SendMail Token."""
        try:
            if password:
                self.email_password = cipher.encrypt(password.encode()).decode()
            else:
                self.email_password = None
        except Exception as e:
            raise ValueError(f"Encryption failed: {str(e)}")

    def get_smtp_password(self):
        """Decrypt and return SMTP password or SendMail Token."""
        try:
            if self.email_password:
                print("Encoded Password:", self.email_password)
                return cipher.decrypt(self.email_password.encode()).decode()
            return None
        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")

    def clean(self):
        """Validate SMTP credentials."""
        if self.email_address and not self.email_password:
            raise ValidationError("Chosen mail provider password is required if Chosen mail provider email is provided. Necessary for email sending.")
        if self.email_password and not self.email_address:
            raise ValidationError("Chosen mail provider email is required if Chosen mail provider password is provided. Necessary for email sending.")

    def is_hod(self):
        return self.roles.filter(name='HOD').exists()

    def __str__(self):
        return self.username
    
    def has_perm(self, perm, obj=None):
        if obj and hasattr(obj, 'tenant'):
            if self.tenant != obj.tenant:
                return False
        return super().has_perm(perm, obj)
    
    @cached_property
    def has_unremitted_remittance(self):
        """Check if user has any pending remittances"""
        # Use the string reference to avoid circular import
        from documents.models import Remittance
        return Remittance.objects.filter(
            owner=self,
            status__in=['pending', 'processing', 'failed']
        ).exists()
    
    @cached_property
    def pending_remittances(self):
        """Get pending remittances for this tenant"""
        # Use the string reference to avoid circular import
        from documents.models import Remittance
        return Remittance.objects.filter(
            owner=self,
            status__in=['pending', 'processing', 'failed']
        )
    

    @property
    def user_name(self):
        """Get user name from profile or fall back to tenant name"""
        profile = self.user_profile
        if profile and profile.user.user_name:
            return profile.user.user_name
        return self.user.user_name
    
    @property
    def has_public_bookings(self):
        """Check if user has any public booking services available for scheduling"""
        return self.created_booking_types.filter(is_public=True).exists()
    
    @property
    def bank_details_provided(self):
        """Check if bank details are provided"""
        profile = getattr(self, 'user_profile', None) or getattr(self, 'staff_profile', None)
        if not profile:
            return False
        
        # Check if it's StaffProfile and has the new fields or old fields
        if hasattr(profile, 'bank_account_name'):
             return all([
                profile.bank_name,
                getattr(profile, 'bank_account_name', None) or getattr(profile, 'account_name', None),
                getattr(profile, 'bank_account_number', None) or getattr(profile, 'account_number', None)
            ])
        
        return all([
            profile.bank_name,
            getattr(profile, 'bank_account_name', None),
            getattr(profile, 'bank_account_number', None)
        ])
    
    def has_active_subscription(self):
        """Check if user has an active subscription"""
        return self.subscription_status == 'active'
    
    def is_trial(self):
        """Check if user is in trial period"""
        return self.subscription_status == 'trial'
    
    def get_plan_display(self):
        """Get formatted plan name with price"""
        if self.subscription_plan:
            return f"{self.subscription_plan.name}"
        return "No Active Plan"


# Google OAuth
class GoogleOAuthToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="google_token")
    refresh_token = models.TextField()
    access_token = models.TextField(null=True, blank=True)
    token_uri = models.CharField(max_length=255, default="https://oauth2.googleapis.com/token")
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Google OAuth Token"
        verbose_name_plural = "Google OAuth Tokens"

    def __str__(self):
        return f"Google token for {self.user.email}"

class GoogleOAuthState(models.Model):
    state = models.CharField(max_length=128, unique=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)

class Folder(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_shared = models.BooleanField(default=False, help_text="Enable external sharing for this folders.")
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='shared_folders')
    share_time = models.DateTimeField(null=True, blank=True)
    share_time_end = models.DateTimeField(null=True, blank=True)
    share_subfolders = models.BooleanField(default=False, null=True, blank=True)
    share_files = models.BooleanField(default=False, null=True, blank=True)

    def get_shareable_link(self):
        from django.urls import reverse
        return reverse('shared_folder_view', kwargs={'token': str(self.share_token)})

    def __str__(self):
        return self.name
    
def upload_to_folder(instance, filename):
    if instance.folder:
        tenant_name = instance.folder.tenant.name if instance.folder.tenant else "Personal"
        username = instance.folder.created_by.username if instance.folder.created_by else "anonymous"
        folder_name = instance.folder.name
        
        # Handle anonymous subdir
        if instance.anon_name or instance.anon_email or instance.anon_phone:
            subdir = instance.anon_name or instance.anon_email or instance.anon_phone.replace(' ', '_').replace('/', '_')[:50]  # Sanitize
        else:
            subdir = "anonymous_uploads"
        
        return os.path.join('uploads', tenant_name, username, folder_name, subdir, filename)
    elif instance.tenant:
        tenant_name = instance.tenant.name if instance.tenant else "Personal"
        username = "anonymous"
        folder_name = "unassigned"
        return os.path.join('uploads', tenant_name, username, folder_name, filename)
    else:
        tenant_name = "unassigned" 
        username = "anonymous"
        folder_name = "unassigned"
        return os.path.join('uploads', tenant_name, username, folder_name, filename)


class File(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name='files', null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    anon_name = models.CharField(max_length=255, blank=True, null=True, help_text="Name of uploader if anonymous")
    anon_email = models.EmailField(blank=True, null=True, help_text="Email of uploader if anonymous")
    anon_phone = models.CharField(max_length=20, blank=True, null=True, help_text="Phone number of uploader if anonymous")
    file = models.FileField(upload_to=upload_to_folder)
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=False)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_shared = models.BooleanField(default=False, help_text="Enable external sharing for this file")
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='shared_files')
    share_time = models.DateTimeField(null=True, blank=True)
    share_time_end = models.DateTimeField(null=True, blank=True)

    def get_uploaded_by_display(self):
        if self.uploaded_by:
            return str(self.uploaded_by)
        elif self.anon_name:
            return self.anon_name
        return "Anonymous"

    def get_shareable_link(self):
        from django.urls import reverse
        return reverse('shared_file_view', kwargs={'token': str(self.share_token)})

    def __str__(self):
        return self.original_name

class Task(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255, help_text="Required. Title of the task")
    description = models.TextField(help_text="Any notes or details about the task")
    documents = models.ManyToManyField('File', blank=True, help_text="Attach documents for this task from Public Files")
    assigned_to = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, help_text="Select staff to assign this task to")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_tasks')
    opportunity = models.ForeignKey('crm.Opportunity', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', help_text="Link this task to an opportunity")
    product = models.ForeignKey('crm.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks', help_text="Link this task to a product")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', help_text="Current status of the task")
    due_date = models.DateTimeField(null=True, blank=True, help_text="Set a due date for the task")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        """Return the URL to view this task."""
        from django.urls import reverse
        return reverse('task_detail', kwargs={'task_id': self.id})


# class Organization(models.Model):
#     name = models.CharField(max_length=255, unique=True)

#     def __str__(self):
#         return self.name
    
class Department(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="department")
    name = models.CharField(max_length=255)
    # hod = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='hod_department')
    hod = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='hod')

    def save(self, *args, **kwargs):
        if self.hod and not self.hod.is_hod():
            # raise ValueError("HOD must have the 'HOD' role.")
            self.hod.roles.add(Role.objects.get(name='HOD'))
            self.hod.save()
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name
    
class Team(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="team")
    name = models.CharField(max_length=255)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, blank=True, null=True)
    team_leader = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='team_leader')

    class Meta:
        unique_together = ('tenant', 'name')

    def __str__(self):
        return self.name
    
def upload_to_staff_photos(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    username = instance.user.username if instance.user.username else "anonymous"
    return os.path.join('staff_photos', tenant_name, username, filename)
    
class StaffProfile(models.Model):
    RELIGION_CHOICES = [
        ('islam', 'Islam'),
        ('christianity', 'Christianity'),
        ('other', 'Other'),
    ]
    SEX_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]
    EMERGENCY_RELATIONSHIP_CHOICES = [
        ('husband', 'Husband'),
        ('wife', 'Wife'),
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('brother', 'Brother'),
        ('sister', 'Sister'),
        ('son', 'Son'),
        ('daughter', 'Daughter'),
    ]
    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ]
    RELATIONSHIP_CHOICES = [
        ("sibling", "Sibling"),
        ("parent", "Parent"),
        ("child", "Child"),
        ("spouse", "Spouse"),
        ("other", "Other"),
        ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="staff_profile")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    photo = models.ImageField(upload_to=upload_to_staff_photos, null=True, blank=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    home_address = models.CharField(max_length=255, null=True, blank=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, null=True, blank=True)
    religion = models.CharField(max_length=15, choices=RELIGION_CHOICES, null=True, blank=True)
    state_of_origin = models.CharField(max_length=255, null=True, blank=True)
    lga = models.CharField(max_length=255, null=True, blank=True)
    marital_status = models.CharField(max_length=255, choices=MARITAL_STATUS_CHOICES, null=True, blank=True)
    account_number = models.CharField(max_length=20, null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    account_name = models.CharField(max_length=100, null=True, blank=True)
    
    # New bank fields to match UserProfile
    bank_account_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_code = models.CharField(max_length=20, blank=True, null=True)
    bank_verified = models.BooleanField(default=False)
    bank_verification_note = models.CharField(max_length=255, blank=True, null=True)
    bank_rejection_reason = models.CharField(max_length=255, blank=True, null=True)
    bank_verification_date = models.DateTimeField(null=True, blank=True)
    # location = models.CharField(max_length=100, null=True, blank=True)
    employment_date = models.DateField(null=True, blank=True)
    official_email = models.EmailField(null=True, blank=True)
    department = models.ForeignKey('Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='staff')
    team = models.ForeignKey('Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    designation = models.CharField(max_length=120, null=True, blank=True)
    emergency_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_relationship = models.CharField(max_length=20, choices=EMERGENCY_RELATIONSHIP_CHOICES, null=True, blank=True)
    emergency_phone = models.CharField(max_length=20, null=True, blank=True)
    emergency_address = models.TextField(null=True, blank=True)
    emergency_email = models.EmailField(null=True, blank=True)
    next_of_kin_name = models.CharField(max_length=100, null=True, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, null=True, blank=True)
    next_of_kin_email = models.EmailField(null=True, blank=True)
    next_of_kin_address = models.TextField(null=True, blank=True)
    next_of_kin_relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, null=True, blank=True)
    guarantor_name = models.CharField(max_length=100, null=True, blank=True)
    guarantor_phone = models.CharField(max_length=20, null=True, blank=True)
    guarantor_email = models.EmailField(null=True, blank=True)
    is_public = models.BooleanField(default=False)
    public_slug = models.SlugField(max_length=140, unique=True, blank=True, null=True)
    public_qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    public_sections = models.JSONField(default=dict, blank=True, help_text="Per-section public visibility")
    bio = models.TextField(blank=True, null=True)

    STAFF_DEFAULT_SECTIONS = {
        'bio': True,
        'education': True,
        'experience': True,
        'achievements': True,
        'recommendations': True,
        'identity_documents': False,
        'emergency_contact': False,
        'next_of_kin': False,
        'guarantor': False,
        'account_info': False,
        'bank_info': False,
    }

    @property
    def get_public_sections(self):
        """Merge stored values with defaults so missing keys don't break."""
        merged = dict(self.STAFF_DEFAULT_SECTIONS)
        if self.public_sections:
            merged.update(self.public_sections)
        return merged

    def save(self, *args, **kwargs):
        """Auto generate slug when is_public is True"""
        if self.is_public and not self.public_slug:
            base = self.full_name or str(self.user)
            slug = slugify(base)[:130]
            original = slug
            counter = 1
            while StaffProfile.objects.filter(public_slug=slug).exclude(pk=self.pk).exists():
                slug = f"{original}-{counter}"
                counter += 1
            self.public_slug = slug
        super().save(*args, **kwargs)
    
    def get_formatted_bank_details(self):
        if all([self.bank_name, self.bank_account_number, self.bank_account_name]):
            return f"Bank: {self.bank_name}\nAccount Name: {self.bank_account_name}\nAccount Number: {self.bank_account_number}"
        return "Bank details not provided"


    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def has_complete_bank_details(self):
        """Check if all required bank fields are provided."""
        return all([
            self.bank_name,
            self.bank_account_number,
            self.bank_account_name,
            self.bank_code,
        ])
 

    @property
    def profile_completion(self):
        """Calculate profile completion percentage (0-100)."""
        checks = [
            bool(self.photo),
            bool(self.first_name),
            bool(self.last_name),
            bool(self.phone_number),
            bool(self.email),
            bool(self.date_of_birth),
            bool(self.home_address),
            bool(self.sex),
            bool(self.religion),
            bool(self.state_of_origin),
            bool(self.lga),
            bool(self.emergency_name),
            bool(self.emergency_phone),
            bool(self.next_of_kin_name),
            bool(self.guarantor_name),
            bool(self.bio),
            # Related records: at least one of each
            self.work_history.exists(),
            self.education_history.exists(),
            self.identity_documents.exists(),
            self.achievements.exists(),        ]
        filled = sum(checks)
        total = len(checks)
        return int((filled / total) * 100) if total else 0

    @property
    def current_department(self):
        """Get the current department from the latest promotion history."""
        latest_promotion = self.promotion_history.order_by('-start_date').first()
        return latest_promotion.department if latest_promotion else None

    @property
    def current_team(self):
        """Get the current team from the latest promotion history."""
        latest_promotion = self.promotion_history.order_by('-start_date').first()
        return latest_promotion.team if latest_promotion else None

    @property
    def current_designation(self):
        """Get the current designation from the latest promotion history."""
        latest_promotion = self.promotion_history.order_by('-start_date').first()
        return latest_promotion.designation if latest_promotion else None
    

def upload_to_user_profile_photos(instance, filename):
    username = instance.user.username if instance.user.username else instance.user.email
    return os.path.join('user_profile_photo', username, filename)
    
class UserProfile(models.Model):
    RELIGION_CHOICES = [
        ('islam', 'Islam'),
        ('christianity', 'Christianity'),
        ('other', 'Other'),
    ]
    SEX_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]
    EMERGENCY_RELATIONSHIP_CHOICES = [
        ('husband', 'Husband'),
        ('wife', 'Wife'),
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('brother', 'Brother'),
        ('sister', 'Sister'),
        ('son', 'Son'),
        ('daughter', 'Daughter'),
    ]
    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_profile")
    photo = models.ImageField(upload_to=upload_to_user_profile_photos, null=True, blank=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    home_address = models.CharField(max_length=255, null=True, blank=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, null=True, blank=True)
    religion = models.CharField(max_length=15, choices=RELIGION_CHOICES, null=True, blank=True)
    marital_status = models.CharField(max_length=255, choices=MARITAL_STATUS_CHOICES, null=True, blank=True)
    designation = models.CharField(max_length=100, null=True, blank=True)
    location = models.CharField(max_length=100, null=True, blank=True)
    bio = models.TextField(blank=True, null=True)

    # Bank details for remittance (ADD THESE FIELDS)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_account_name = models.CharField(max_length=255, blank=True, null=True)
    bank_code = models.CharField(max_length=20, blank=True, null=True)
    bank_verified = models.BooleanField(default=False)
    bank_verification_note = models.CharField(max_length=255, blank=True, null=True)
    bank_rejection_reason = models.CharField(max_length=255, blank=True, null=True)
    bank_verification_date = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=False)
    public_slug = models.SlugField(max_length=140, unique=True, blank=True, null=True)
    public_qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    public_sections = models.JSONField(default=dict, blank=True, help_text="Per-section public visibility")

    USER_DEFAULT_SECTIONS = {
        'bio': True,
        'education': True,
        'experience': True,
        'achievements': True,
        'recommendations': True,
        'identity_documents': False,
        'account_info': False,
        'bank_info': False,
    }

    @property
    def get_public_sections(self):
        """Merge stored values with defaults so missing keys don't break."""
        merged = dict(self.USER_DEFAULT_SECTIONS)
        if self.public_sections:
            merged.update(self.public_sections)
        return merged


    def __str__(self):
        return self.user.username
    
    def get_formatted_bank_details(self):
        if all([self.bank_name, self.bank_account_number, self.bank_account_name]):
            return f"Bank: {self.bank_name}\nAccount Name: {self.bank_account_name}\nAccount Number: {self.bank_account_number}"
        return "Bank details not provided"
    
    def has_complete_bank_details(self):
        """Check if all required bank details are provided"""
        return all([
            self.bank_name,
            self.bank_account_number, 
            self.bank_account_name,
            self.bank_code
        ])

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def profile_completion(self):
        """Calculate profile completion percentage (0-100)."""
        checks = [
            bool(self.photo),
            bool(self.first_name),
            bool(self.last_name),
            bool(self.phone_number),
            bool(self.email),
            bool(self.date_of_birth),
            bool(self.home_address),
            bool(self.sex),
            bool(self.religion),
            bool(self.designation),
            bool(self.location),
            bool(self.bio),
            # Related records: at least one of each
            self.work_history.exists(),
            self.education_history.exists(),
            self.identity_documents.exists(),
            self.achievements.exists(),
        ]
        filled = sum(checks)
        total = len(checks)
        return int((filled / total) * 100) if total else 0
        
    def save(self, *args, **kwargs):
        """Auto-generate slug when is_public=True"""
        if self.is_public and not self.public_slug:
            base = self.full_name or str(self.user)
            slug = slugify(base)[:130]
            original = slug
            counter = 1
            while UserProfile.objects.filter(public_slug=slug).exclude(pk=self.pk).exists():
                slug = f"{original}-{counter}"
                counter += 1
            self.public_slug = slug
        super().save(*args, **kwargs)

class Notification(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="notification", null=True, blank=True, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # today = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class NotificationType(models.TextChoices):
        NEWS = 'news', 'News'
        BIRTHDAY = 'birthday', 'Birthday'
        ALERT = 'alert', 'Alert'
        EVENT = 'event', 'Event'
        MEMO = 'memo', 'Memo'  # For memo notifications - bell icon only

    type = models.CharField(max_length=20, choices=NotificationType.choices, default=NotificationType.NEWS)
    
    # Generic relation to link notification to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Optional custom link (if not using generic relation)
    link = models.CharField(max_length=500, blank=True, null=True, help_text="Custom URL to redirect when notification is clicked")

    def is_visible(self):
        now = timezone.now()
        return self.is_active and (not self.expires_at or self.expires_at > now)
    
    def get_absolute_url(self):
        """Get the URL to redirect to when notification is clicked"""
        # Priority 1: Custom link
        if self.link:
            return self.link
        
        # Priority 2: Generic relation
        if self.content_object:
            # Try to get the absolute URL from the related object
            if hasattr(self.content_object, 'get_absolute_url'):
                try:
                    return self.content_object.get_absolute_url()
                except:
                    pass
            
            # Fallback: construct URL based on content type
            from django.urls import reverse, NoReverseMatch
            model_name = self.content_type.model
            
            # Map common models to their detail views
            # Format: 'model_name': ('url_name', 'param_name')
            url_mapping = {
                'task': ('task_detail', 'task_id'),
                'memo': ('memo:memo_detail', 'pk'),
                'event': ('edit_event', 'event_id'),  # Using edit as detail view
                'meeting': ('edit_event', 'event_id'),  # Meetings use same as events
                'staffprofile': ('view_staff_profile', 'staff_id'),
                'userkyc': ('kyc_status', None),  # No param needed
                'staffkyc': ('kyc_status', None),  # No param needed
                'companykyb': ('kyc_status', None),  # No param needed
            }
            
            if model_name in url_mapping:
                view_name, param_name = url_mapping[model_name]
                try:
                    # If param_name is None, reverse without kwargs
                    if param_name is None:
                        return reverse(view_name)
                    else:
                        return reverse(view_name, kwargs={param_name: self.object_id})
                except NoReverseMatch as e:
                    # Log the error for debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to reverse URL for {model_name} with id {self.object_id}: {e}")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error generating URL for notification {self.id}: {e}")
        
        # Default: return None (will redirect to notifications page)
        return None

    def __str__(self):
        return f"{self.get_type_display()}: {self.title}"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.expires_at and self.expires_at < timezone.now():
            self.is_active = False
    

class UserNotification(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="user_notification", null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    dismissed = models.BooleanField(default=False)
    seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'notification')


def upload_to_staff_documents(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    username = instance.staff_profile.user.username if instance.staff_profile.user else "anonymous"
    return os.path.join('staff_documents', tenant_name, username, filename)

class StaffDocument(models.Model):
    DOCUMENT_TYPES = [
        ('resume', 'Resume'),
        ('certificate', 'Certificate'),
        ('id_card', 'ID Card'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="staff_document")
    staff_profile = models.ForeignKey('StaffProfile', on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to=upload_to_staff_documents)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES, default='other')
    description = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_type} - {self.staff_profile.full_name} ({self.uploaded_at})"

def upload_to_public_folder(instance, filename):
    folder_name = instance.folder.name if instance.folder else "unassigned"
    return os.path.join('uploads/public', folder_name, filename)

def upload_to_company_photos(instance, filename):
    tenant_name = instance.tenant.name
    return os.path.join('company_photos', tenant_name, filename)

# class CompanyProfile(models.Model):
#     photo = models.ImageField(upload_to=upload_to_company_photos, null=True, blank=True)
#     tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="company_profile")
#     company_name = models.CharField(max_length=255)
#     description = models.TextField(blank=True, null=True)
#     date_founded = models.DateField(null=True, blank=True)
#     reg_number = models.CharField(max_length=255, null=True, blank=True)
#     address = models.TextField(blank=True, null=True)
#     email = models.EmailField(null=True, blank=True)
#     contact_details = models.TextField(null=True, blank=True)
#     website = models.URLField(null=True, blank=True)
#     num_staff = models.IntegerField(null=True, blank=True)
#     num_departments = models.IntegerField(null=True, blank=True)
#     num_teams = models.IntegerField(null=True, blank=True)

#     def __str__(self):
#         return self.tenant.name



class CompanyProfile(models.Model):
    photo = models.ImageField(upload_to=upload_to_company_photos, null=True, blank=True)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="company_profile")
    company_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    date_founded = models.DateField(null=True, blank=True)
    reg_number = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    email = models.EmailField(null=True, blank=True)
    contact_details = models.TextField(null=True, blank=True)
    website = models.URLField(null=True, blank=True)
    num_staff = models.IntegerField(null=True, blank=True)
    num_departments = models.IntegerField(null=True, blank=True)
    num_teams = models.IntegerField(null=True, blank=True)
    
    # Bank details for remittance (ADD THESE FIELDS)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=50, blank=True, null=True)
    bank_account_name = models.CharField(max_length=255, blank=True, null=True)
    bank_code = models.CharField(max_length=20, blank=True, null=True)
    bank_verified = models.BooleanField(default=False)
    bank_verification_note = models.CharField(max_length=255, blank=True, null=True)
    bank_rejection_reason = models.CharField(max_length=255, blank=True, null=True)
    bank_verification_date = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=False)
    public_slug = models.SlugField(max_length=140, unique=True, blank=True, null=True)
    public_qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    public_sections = models.JSONField(default=dict, blank=True, help_text="Per-section public visibility")

    COMPANY_DEFAULT_SECTIONS = {
        'description': True,
        'contact_details': True,
        'departments_teams': True,
        'bank_info': False,
        'documents': False,
    }

    @property
    def get_public_sections(self):
        """Merge stored values with defaults so missing keys don't break."""
        merged = dict(self.COMPANY_DEFAULT_SECTIONS)
        if self.public_sections:
            merged.update(self.public_sections)
        return merged

    def __str__(self):
        return self.tenant.name
    
    def get_formatted_bank_details(self):
        if all([self.bank_name, self.bank_account_number, self.bank_account_name]):
            return f"Bank: {self.bank_name}\nAccount Name: {self.bank_account_name}\nAccount Number: {self.bank_account_number}"
        return "Bank details not provided"
    
    def has_complete_bank_details(self):
        """Check if all required bank details are provided"""
        return all([
            self.bank_name,
            self.bank_account_number, 
            self.bank_account_name,
            self.bank_code
        ])

    def save(self, *args, **kwargs):
        """Auto-generate slug when is_public=True"""
        if self.is_public and not self.public_slug:
            base = self.tenant.name or str(self.tenant)
            slug = slugify(base)[:130]
            original = slug
            counter = 1
            while CompanyProfile.objects.filter(public_slug=slug).exclude(pk=self.pk).exists():
                slug = f"{original}-{counter}"
                counter += 1
            self.public_slug = slug
        super().save(*args, **kwargs)

class ContactTag(models.Model):
    """Tags for categorizing contacts"""
    name = models.CharField(max_length=50, unique=True)
    
    def __str__(self):
        return self.name


class Contact(models.Model):
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    
    LEAD_SOURCE_CHOICES = [
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('cold_call', 'Cold Call'),
        ('social_media', 'Social Media'),
        ('event', 'Event'),
        ('partner', 'Partner'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    organization = models.CharField(max_length=255, null=True, blank=True)
    designation = models.CharField(max_length=255, blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    department = models.ForeignKey('Department', null=True, blank=True, on_delete=models.SET_NULL, related_name='contact_lists')
    team = models.ForeignKey('Team', null=True, blank=True, on_delete=models.SET_NULL, related_name='contact_lists')
    
    # CRM fields
    title = models.CharField(max_length=100, blank=True, help_text="e.g., CTO, Manager, Director")
    lead_source = models.CharField(max_length=50, choices=LEAD_SOURCE_CHOICES, blank=True)
    is_primary_contact = models.BooleanField(default=False)
    tags = models.ManyToManyField(ContactTag, blank=True, related_name='contacts')
    linkedin_url = models.URLField(blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_contact_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='updated_contact_lists', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.email})"
    # class Meta:
    #     constraints = [
    #         models.CheckConstraint(
    #             check=Q(department__isnull=False) | Q(team__isnull=False),
    #             name='contact_list_department_or_team_required'
    #         )
    #     ]

class Email(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    to_emails = models.TextField()  # Store email addresses as JSON
    cc_emails = models.TextField(blank=True)  # Optional
    bcc_emails = models.TextField(blank=True)  # Optional
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sender_email')
    created_at = models.DateTimeField(auto_now_add=True)
    sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    def set_to_emails(self, emails):
        """Helper to store list of emails as JSON."""
        self.to_emails = json.dumps(emails)

    def get_to_emails(self):
        """Helper to retrieve list of emails."""
        return json.loads(self.to_emails) if self.to_emails else []

    def set_cc_emails(self, emails):
        self.cc_emails = json.dumps(emails)

    def get_cc_emails(self):
        return json.loads(self.cc_emails) if self.cc_emails else []

    def set_bcc_emails(self, emails):
        self.bcc_emails = json.dumps(emails)

    def get_bcc_emails(self):
        return json.loads(self.bcc_emails) if self.bcc_emails else []

    def __str__(self):
        return self.subject

def upload_to_email_attachments(instance, filename):
    tenant_name = instance.email.tenant.name if instance.email.tenant else "Personal"
    username = instance.email.sender.username if instance.email.sender.username else "anonymous"
    return os.path.join('email_attachments', tenant_name, username, filename)

class Attachment(models.Model):
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=upload_to_email_attachments)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name
    
class Payee(models.Model):
    PAYEE_TYPE_CHOICES = [
        ('employee', 'Employee'),  # Internal, linked to CustomUser
        ('contractor', 'Contractor'),  # External, freelance or temporary
        ('vendor', 'Vendor'),  # External, for suppliers or services
        ('other', 'Other'),  # Catch-all for miscellaneous
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payees', null=True, blank=True)
    user = models.OneToOneField(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='payee_profile')  # Link to internal user if applicable
    payee_type = models.CharField(max_length=20, choices=PAYEE_TYPE_CHOICES, default='employee')
    name = models.CharField(max_length=255)  # Full name or company name
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)  # For tax/compliance purposes
    tax_id = models.CharField(max_length=50, blank=True, null=True)  # e.g., SSN, EIN for US; adaptable for other countries
    account_number = models.CharField(max_length=100, blank=True, null=True)  # IBAN, account number, etc.
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_name = models.CharField(max_length=100, blank=True, null=True)
    routing_number = models.CharField(max_length=50, blank=True, null=True)  # For bank transfers
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.tenant is not None:
            return f"{self.name} ({self.payee_type}) for {self.tenant}"
        else:
            return f"{self.name} ({self.payee_type}) for {self.user}"

    def save(self, *args, **kwargs):
        if self.user:
            # Auto-populate from CustomUser if linked
            self.name = self.user.get_full_name() or self.user.username
            self.email = self.user.email
            self.payee_type = 'employee'
            if not self.user.is_personal:
                self.account_number = self.user.staff_profile.account_number
                self.bank_name = self.user.staff_profile.bank_name
                self.account_name = self.user.staff_profile.account_name
            else:
                self.account_number = self.user.user_profile.bank_account_number
                self.bank_name = self.user.user_profile.bank_name
                self.account_name = self.user.user_profile.bank_account_name
        super().save(*args, **kwargs)


class Payer(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payers', null=True, blank=True)
    user = models.OneToOneField(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='payer_profile')  # Optional: if they're a logged-in user
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True, null=True)
    organization = models.CharField(max_length=255, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    paystack_customer_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    # Add other payment provider IDs as needed
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.tenant:
            return f"{self.name} <{self.email}> - {self.tenant}"
        else:
            return f"{self.name} <{self.email}> - {self.user}"

    def save(self, *args, **kwargs):
        if self.user:
            self.name = self.user.staff_profile.get_full_name() or self.user.username
            self.email = self.user.email
        super().save(*args, **kwargs)

class Payroll(models.Model):
    """
    Refactored Payroll model for single-page Excel-like interface.
    Each payroll has a title (e.g., "March Salary") and PIN for security.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payrolls')
    title = models.CharField(max_length=255, default='Untitled Payroll', help_text="E.g., 'March Salary', 'April Salary'")
    
    # Security
    pin = models.CharField(max_length=255, null=True, blank=True, help_text="Encrypted PIN for payment authorization")
    
    # Status and totals
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    total_gross = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_net = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Metadata
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payrolls')
    
    # Payment tracking
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='paid_payrolls')
    
    # Read-only after payment
    is_locked = models.BooleanField(default=False, help_text="True after payment - becomes read-only")

    class Meta:
        ordering = ['-created_at']
        unique_together = ('tenant', 'title')

    def __str__(self):
        return f"{self.tenant.name} - {self.title} ({self.status})"
    
    def set_pin(self, raw_pin):
        """Encrypt and store PIN"""
        from django.contrib.auth.hashers import make_password
        self.pin = make_password(raw_pin)
    
    def check_pin(self, raw_pin):
        """Verify PIN"""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_pin, self.pin)
    
    def update_totals(self):
        """Recalculate total_gross and total_net from items"""
        from django.db.models import Sum
        totals = self.items.aggregate(
            gross=Sum('gross_amount'),
            net=Sum('net_amount')
        )
        self.total_gross = totals['gross'] or Decimal('0.00')
        self.total_net = totals['net'] or Decimal('0.00')
        self.save(update_fields=['total_gross', 'total_net', 'updated_at'])
    
    def duplicate(self, new_title, created_by):
        """Create a copy of this payroll with same structure"""
        new_payroll = Payroll.objects.create(
            tenant=self.tenant,
            title=new_title,
            created_by=created_by,
            notes=self.notes
        )
        
        # Copy custom columns
        for column in self.custom_columns.all():
            PayrollCustomColumn.objects.create(
                payroll=new_payroll,
                name=column.name,
                operation=column.operation,
                order=column.order
            )
        
        # Copy items (without amounts - admin will fill them)
        for item in self.items.all():
            PayrollItem.objects.create(
                payroll=new_payroll,
                staff=item.staff,
                staff_name=item.staff_name,
                gross_amount=Decimal('0.00'),
                net_amount=Decimal('0.00')
            )
        
        return new_payroll
    
    def can_user_approve(self, user):
        """Check if a user can approve this payroll"""
        # Admin (tenant owner/creator) can approve everything
        if user == self.tenant.admin or user == self.tenant.created_by:
            return True
        
        # Check if user has Admin role
        user_roles = [role.name for role in user.roles.all()]
        if 'Admin' in user_roles:
            return True
        
        # Check if user is in the approval workflow
        pending_approval = self.approvals.filter(
            approver=user,
            status='pending'
        ).first()
        
        if not pending_approval:
            return False
        
        # Check if it's their turn (all previous levels are approved)
        previous_levels = self.approvals.filter(level__lt=pending_approval.level)
        if previous_levels.exists():
            return all(approval.status == 'approved' for approval in previous_levels)
        
        return True
    
    def check_approval_status(self):
        """Check if all approvals are complete and update status"""
        all_approvals = self.approvals.all()
        if not all_approvals.exists():
            return
        
        # Check if all are approved
        if all_approvals.filter(status='approved').count() == all_approvals.count():
            self.status = 'approved'
            self.save()
            return
        
        # Check if all approved
        if all_approvals.filter(status='pending').exists():
            self.status = 'pending_approval'
        else:
            self.status = 'approved'
        
        self.save()
    
    def submit_for_approval(self):
        """Submit payroll for approval (changes status to pending_approval or approved if no approvers)"""
        if self.approvals.exists():
            self.status = 'pending_approval'
            self.save()
            return True
        else:
            # No approvers configured, auto-approve
            self.status = 'approved'
            self.save()
            return True


class PayrollCustomColumn(models.Model):
    """
    Dynamic columns for a specific payroll (Excel-like).
    Admin can add/remove columns and change their operation type.
    Examples: Tax, Bonus, Pension, Loan
    """
    OPERATION_CHOICES = [
        ('add', 'Add (+)'),
        ('subtract', 'Subtract (-)'),
    ]
    
    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name='custom_columns')
    name = models.CharField(max_length=100, help_text="Column name (e.g., 'Tax', 'Bonus')")
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES, default='add', help_text="Add or Subtract from Gross")
    order = models.IntegerField(default=0, help_text="Display order in table")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'name']
        unique_together = ('payroll', 'name')
        verbose_name = "Payroll Custom Column"
        verbose_name_plural = "Payroll Custom Columns"
    
    def __str__(self):
        return f"{self.payroll.title} - {self.name} ({self.get_operation_display()})"


class PayrollColumnTemplate(models.Model):
    """
    Saved column templates for quick reuse across payrolls.
    Admin can save frequently used column configurations.
    """
    OPERATION_CHOICES = [
        ('add', 'Add (+)'),
        ('subtract', 'Subtract (-)'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payroll_column_templates')
    name = models.CharField(max_length=100, help_text="Template column name")
    operation = models.CharField(max_length=20, choices=OPERATION_CHOICES, default='add')
    is_default = models.BooleanField(default=False, help_text="Auto-add to new payrolls")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_column_templates')
    
    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')
        verbose_name = "Column Template"
        verbose_name_plural = "Column Templates"
    
    def __str__(self):
        return f"{self.tenant.name} - {self.name} ({self.get_operation_display()})"


class PayrollItem(models.Model):
    """
    Individual row in the payroll table (Excel-like).
    Can be linked to a staff member OR manually entered (contractors).
    """
    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name='items')
    
    # Staff can be NULL for manual entries (contractors, one-time payments)
    staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_items')
    
    # Staff name - required (either from staff or manually entered)
    staff_name = models.CharField(max_length=255, help_text="Staff name (auto-filled or manual)")
    
    # Amounts
    gross_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Gross amount")
    net_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Net amount (auto-calculated)")
    
    # Custom column values stored as JSON
    # Example: {"Tax": 5000, "Bonus": 10000, "Pension": 3000}
    column_values = models.JSONField(default=dict, blank=True, help_text="Values for custom columns")
    
    # Row order for display
    order = models.IntegerField(default=0, help_text="Display order in table")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'staff_name']
        verbose_name = "Payroll Item"
        verbose_name_plural = "Payroll Items"
    
    def __str__(self):
        return f"{self.staff_name} - {self.payroll.title}"
    
    def calculate_net_amount(self):
        """
        Calculate net amount: Gross + Add columns - Subtract columns
        """
        net = Decimal(str(self.gross_amount))
        
        # Get custom columns for this payroll
        for column in self.payroll.custom_columns.all():
            value = Decimal(str(self.column_values.get(column.name, 0)))
            
            if column.operation == 'add':
                net += value
            elif column.operation == 'subtract':
                net -= value
        
        return net
    
    def save(self, *args, **kwargs):
        """Auto-calculate net_amount before saving"""
        if self.gross_amount is not None:
            self.net_amount = self.calculate_net_amount()
        super().save(*args, **kwargs)


class PayrollApproval(models.Model):
    """
    Multi-level approval system for payrolls.
    Each payroll can have multiple approvers in sequence.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    payroll = models.ForeignKey(Payroll, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payroll_approvals')
    
    # Approval order (1 = first approver, 2 = second, etc.)
    level = models.IntegerField(help_text="Approval level (1, 2, 3...)")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    comments = models.TextField(blank=True, null=True, help_text="Approver's comments")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    actioned_at = models.DateTimeField(null=True, blank=True, help_text="When approved/rejected")
    
    class Meta:
        ordering = ['level', 'created_at']
        unique_together = ('payroll', 'approver', 'level')
        verbose_name = "Payroll Approval"
        verbose_name_plural = "Payroll Approvals"
    
    def __str__(self):
        return f"{self.payroll.title} - Level {self.level} - {self.approver.get_full_name()} ({self.status})"
    
    def approve(self, comments=''):
        """Mark as approved"""
        self.status = 'approved'
        self.comments = comments
        self.actioned_at = timezone.now()
        self.save()
        
        # Check if all approvals are complete
        self.payroll.check_approval_status()
    
    def reject(self, comments=''):
        """Mark as rejected and reset payroll to draft"""
        self.status = 'rejected'
        self.comments = comments
        self.actioned_at = timezone.now()
        self.save()
        
        # Reset payroll to draft
        self.payroll.status = 'draft'
        self.payroll.save()


from decimal import Decimal
from django.db import models
from django.utils import timezone

class TenantBalance(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='wallet')
    owner = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet')
    total_earned = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    total_remitted = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Wallet Balance"
        verbose_name_plural = "Wallet Balances"

    def __str__(self):
        if self.tenant is not None:
            return f"{self.tenant.name} Wallet: {self.available_balance}"
        else:
            return f"{self.owner.username} Wallet: {self.available_balance}"
    
    def calculate_adjusted_amount(self, amount):
        """Calculate amount after deductions: minus 100, then minus 1/11 of the remainder"""
        # Ensure amount is Decimal
        amount_decimal = Decimal(str(amount))
        
        # Subtract 100 first
        amount_after_fixed = amount_decimal - Decimal('100.00')
        
        if amount_after_fixed <= 0:
            return Decimal('0.00')
        
        # Subtract 1/11 of the remaining amount
        deduction = Decimal(amount_after_fixed) / Decimal('11.00')
        final_amount = amount_after_fixed - deduction
        
        return final_amount.quantize(Decimal('0.01'))
    
    def get_detailed_calculation(self):
        """Get detailed breakdown of calculations for debugging"""
        from django.db.models import Sum
        # Determine which payment types this wallet owner earns.
        # Org wallet (tenant set)      → conference_fee + booking_fee
        # Pure personal user (owner)   → conference_fee + booking_fee
        # Staff member (owner)         → booking_fee only
        # Tenant admin personal (owner)→ booking_fee only  ← same rule as staff
        if self.tenant is not None:
            # Org wallet – conference + booking
            payments = Payment.objects.filter(
                tenant=self.tenant,
                direction='incoming',
                payment_type__in=['conference_fee', 'booking_fee'],
                status='success',
            )
        else:
            owner = self.owner
            # Both staff members AND tenant admins (acting on their personal wallet)
            # earn booking fees only. Pure personal users earn both.
            is_staff_or_admin_personal = (
                owner is not None and
                not owner.is_personal and
                owner.tenant is not None
            )
            if is_staff_or_admin_personal:
                payment_types = ['booking_fee']
            else:
                # Pure personal user: conference + booking
                payment_types = ['conference_fee', 'booking_fee']
    
            payments = Payment.objects.filter(
                owner=owner,
                direction='incoming',
                payment_type__in=payment_types,
                status='success',
            )

        
        breakdown = {
            'total_payments': payments.count(),
            'original_total': Decimal('0.00'),
            'adjusted_total': Decimal('0.00'),
            'deductions_total': Decimal('0.00'),
            'payment_details': []
        }
        
        for payment in payments:
            adjusted = self.calculate_adjusted_amount(payment.amount)
            deduction = Decimal(str(payment.amount)) - adjusted
            
            breakdown['original_total'] += Decimal(str(payment.amount))
            breakdown['adjusted_total'] += adjusted
            breakdown['deductions_total'] += deduction
            
            breakdown['payment_details'].append({
                'id': payment.id,
                'original': payment.amount,
                'adjusted': adjusted,
                'deduction': deduction,
                'date': payment.payment_date,
            })
        
        return breakdown
    
    def update_balance(self, force_update=False):
        """Update the balance with proper calculation"""
        from django.db.models import Sum
        from django.db import transaction
        from decimal import Decimal
        
        try:
            with transaction.atomic():
                # Get all successful incoming conference payments
                # Determine which payment types this wallet owner earns.
                # Org wallet (tenant set)      → conference_fee + booking_fee
                # Pure personal user (owner)   → conference_fee + booking_fee
                # Staff member (owner)         → booking_fee only
                # Tenant admin personal (owner)→ booking_fee only  ← same rule as staff
                if self.tenant is not None:
                    # Org wallet – conference + booking
                    payments = Payment.objects.filter(
                        tenant=self.tenant,
                        direction='incoming',
                        payment_type__in=['conference_fee', 'booking_fee'],
                        status='success',
                    )
                else:
                    owner = self.owner
                    # Both staff members AND tenant admins (acting on their personal wallet)
                    # earn booking fees only. Pure personal users earn both.
                    is_staff_or_admin_personal = (
                        owner is not None and
                        not owner.is_personal and
                        owner.tenant is not None
                    )
                    if is_staff_or_admin_personal:
                        payment_types = ['booking_fee']
                    else:
                        # Pure personal user: conference + booking
                        payment_types = ['conference_fee', 'booking_fee']
            
                    payments = Payment.objects.filter(
                        owner=owner,
                        direction='incoming',
                        payment_type__in=payment_types,
                        status='success',
                    )
                # Calculate total earned with deductions
                total_earned = Decimal('0.00')
                for payment in payments:
                    # Convert amount to Decimal if it's not already
                    if isinstance(payment.amount, float):
                        payment_amount = Decimal(str(payment.amount))
                    else:
                        payment_amount = payment.amount
                    
                    adjusted_amount = self.calculate_adjusted_amount(payment_amount)
                    total_earned += adjusted_amount
                
                # Sum all remitted amounts
                if self.tenant is not None:
                    total_remitted_result = Remittance.objects.filter(
                        tenant=self.tenant,
                        status='completed'
                    ).aggregate(Sum('amount'))
                else:
                    total_remitted_result = Remittance.objects.filter(
                        owner=self.owner,
                        status='completed'
                    ).aggregate(Sum('amount'))
                
                # total_remitted = total_remitted_result['amount__sum'] or Decimal('0.00')
                total_remitted_raw = total_remitted_result['amount__sum']

                if total_remitted_raw is None:
                    total_remitted = Decimal('0.00')
                else:
                    total_remitted = Decimal(str(total_remitted_raw))
                
                # Update the balance
                self.total_earned = total_earned
                self.total_remitted = total_remitted
                self.available_balance = total_earned - total_remitted
                self.save()
                
                return {
                    'total_earned': total_earned,
                    'total_remitted': total_remitted,
                    'available_balance': self.available_balance,
                    'payments_count': payments.count(),
                }
        except Exception as e:
            if self.tenant is not None:
                name = self.tenant.name
            else:
                name = self.owner.username
            print(f"❌ Error updating balance for {name}: {e}")
            return {
                'total_earned': self.total_earned,
                'total_remitted': self.total_remitted,
                'available_balance': self.available_balance,
                'payments_count': 0,
                'error': str(e)
            }
    
    def refresh_from_db_and_update(self):
        """Refresh from database and update balance"""
        self.refresh_from_db()
        return self.update_balance()
    
    @property
    def outstanding_balance(self):
        return self.available_balance
    
    @classmethod
    def get_or_create_for_tenant(cls, tenant, owner):
        """Get or create balance for tenant/owner and update it"""
        if tenant is not None:
            balance, created = cls.objects.get_or_create(tenant=tenant)
        else:
            # owner-keyed: covers both personal users AND staff members
            balance, created = cls.objects.get_or_create(owner=owner)
        if not created:
            balance.update_balance()
        return balance


class Remittance(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    CONFIRMATION_CHOICES = [
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('changed', 'Bank Details Changed'),
        ('rejected', 'Rejected'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='remittances')
    owner = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='remittances')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    bank_confirmation = models.CharField(max_length=20, choices=CONFIRMATION_CHOICES, default='pending')
    confirmation_requested_at = models.DateTimeField(null=True, blank=True)
    confirmation_responded_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_remittances')
    
    # Payment processing fields
    paystack_transfer_code = models.CharField(max_length=100, blank=True, null=True)
    paystack_recipient_code = models.CharField(max_length=100, blank=True, null=True)
    paystack_response = models.JSONField(null=True, blank=True)
    
    remittance_date = models.DateField(null=True, blank=True)
    completion_date = models.DateTimeField(null=True, blank=True)
    bank_reference = models.CharField(max_length=200, blank=True, null=True)
    
    # Link to payments being remitted
    payments = models.ManyToManyField('Payment', related_name='remittances', blank=True)
    
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='created_remittances')
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_remittances')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Remittance"
        verbose_name_plural = "Remittances"
    
    def __str__(self):
        if self.tenant is not None:
            name = self.tenant.name
        else:
            name = self.owner.username
        return f"Remittance {self.reference}: {self.amount} to {name}"
    
    def save(self, *args, **kwargs):
        if not self.reference:
            # Generate unique reference: REM-YYYYMMDD-XXXXXX
            date_part = timezone.now().strftime('%Y%m%d')
            random_part = str(uuid.uuid4().hex[:6]).upper()
            self.reference = f"REM-{date_part}-{random_part}"
        super().save(*args, **kwargs)
    
    @property
    def company_profile(self):
        """
        Get the profile that holds bank details for this remittance owner.
        Returns CompanyProfile (tenant), UserProfile (personal user), or
        StaffProfile (staff member OR tenant admin's personal wallet).
        """
        if self.tenant is not None:
            try:
                return self.tenant.company_profile
            except CompanyProfile.DoesNotExist:
                return None
 
        if self.owner is None:
            return None
 
        # Tenant admin personal wallet → StaffProfile
        # Staff member wallet         → StaffProfile
        # Pure personal user          → UserProfile
        owner = self.owner
        is_staff_or_admin = (
            not owner.is_personal and
            owner.tenant is not None
        )
        if is_staff_or_admin:
            try:
                return owner.staff_profile
            except Exception:
                return None
        else:
            try:
                return owner.user_profile
            except UserProfile.DoesNotExist:
                return None
    
    def get_bank_details(self):
        """Get bank details from company profile"""
        if self.company_profile:
            return {
                'bank_name': self.company_profile.bank_name,
                'bank_account_number': self.company_profile.bank_account_number,
                'bank_account_name': self.company_profile.bank_account_name,
                'bank_code': self.company_profile.bank_code,
            }
        return None
    
    def request_bank_confirmation(self, user=None):
        """Send email to tenant for bank details confirmation"""
        from django.template.loader import render_to_string
        
        if not self.company_profile or not self.company_profile.has_complete_bank_details():
            raise ValueError("Company profile not found or bank details incomplete")
        
        self.confirmation_requested_at = timezone.now()
        
        if user:
            self.updated_by = user
        
        self.save()
        
        # Send confirmation email
        subject = f"Bank Details Confirmation for Remittance {self.reference}"
        if self.tenant is not None:
            owner = self.tenant
        else:
            owner = self.owner
        context = {
            'remittance': self,
            'tenant': owner,
            'company_profile': self.company_profile,
            'amount': self.amount,
            'confirmation_url_correct': f"{settings.SITE_URL}/remittance/{self.id}/confirm?action=correct",
            'confirmation_url_incorrect': f"{settings.SITE_URL}/remittance/{self.id}/confirm?action=incorrect",
        }
        
        html_message = render_to_string('emails/bank_confirmation.html', context)
        plain_message = render_to_string('emails/bank_confirmation.txt', context)
        
        # Send to owner's email
        if self.tenant is not None:
            owner_email = self.company_profile.email or self.tenant.email
        else:
            owner_email = self.company_profile.email or self.owner.email
        
        if owner_email:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[owner_email],
                html_message=html_message,
            )
        
        return True
    
    def confirm_bank_details(self, user=None, is_correct=True):
        """Confirm or reject bank details"""
        if is_correct:
            self.bank_confirmation = 'confirmed'
            # Update company profile as verified
            self.company_profile.bank_verified = True
            self.company_profile.bank_verification_date = timezone.now()
            self.company_profile.save()
        else:
            self.bank_confirmation = 'rejected'
        
        self.confirmation_responded_at = timezone.now()
        if user:
            self.confirmed_by = user
        
        self.save()
        return self
    
    def update_company_bank_details(self, bank_name, account_number, account_name, bank_code, user=None):
        """Update bank details in company profile and mark as changed"""
        if not self.company_profile:
            raise ValueError("Company profile not found")
        
        # Update company profile
        self.company_profile.bank_name = bank_name
        self.company_profile.bank_account_number = account_number
        self.company_profile.bank_account_name = account_name
        self.company_profile.bank_code = bank_code
        self.company_profile.bank_verified = True
        self.company_profile.bank_verification_date = timezone.now()
        self.company_profile.save()
        
        # Update remittance status
        self.bank_confirmation = 'changed'
        self.confirmation_responded_at = timezone.now()
        
        if user:
            self.confirmed_by = user
        
        self.save()
        return self
    
    def can_process_payment(self):
        """Check if payment can be processed"""
        return (
            self.company_profile and 
            self.company_profile.has_complete_bank_details() and
            self.bank_confirmation in ['confirmed', 'changed'] and
            self.status in ['pending', 'failed']
        )
 

    
    def _get_amount_as_decimal(self):
        """Safely convert amount to Decimal"""
        from decimal import Decimal, InvalidOperation
        
        if self.amount is None:
            raise ValueError("Amount is None")
        
        # If it's already Decimal, return it
        if isinstance(self.amount, Decimal):
            return self.amount
        
        # If it's a float, convert via string
        elif isinstance(self.amount, float):
            return Decimal(str(self.amount))
        
        # If it's an integer
        elif isinstance(self.amount, int):
            return Decimal(str(self.amount))
        
        # If it's a string
        elif isinstance(self.amount, str):
            # Clean string - remove commas, currency symbols
            clean_str = self.amount.replace(',', '').replace('₦', '').replace('$', '').strip()
            if not clean_str:
                clean_str = '0'
            return Decimal(clean_str)
        
        # Try to convert whatever it is
        else:
            try:
                return Decimal(str(self.amount))
            except (InvalidOperation, TypeError, ValueError) as e:
                raise ValueError(f"Cannot convert amount {self.amount} (type: {type(self.amount)}) to Decimal: {e}")

    def _convert_to_kobo(self, amount_decimal):
        """Convert Decimal amount to kobo (multiply by 100)"""
        from decimal import Decimal
        
        try:
            # Method 1: Direct Decimal multiplication (preferred)
            if isinstance(amount_decimal, Decimal):
                # Multiply by 100
                amount_times_100 = amount_decimal * Decimal('100')
                # Convert to integer
                return int(amount_times_100.quantize(Decimal('1')))
            
            # Method 2: Fallback via string
            else:
                amount_float = float(str(amount_decimal))
                return int(amount_float * 100)
                
        except Exception as e:
            # Method 3: Emergency fallback
            try:
                # Try direct float conversion
                amount_float = float(amount_decimal)
                return int(amount_float * 100)
            except:
                raise ValueError(f"Cannot convert amount to kobo: {e}")

    def process_payment(self, user=None, is_retry=False):
        """Process payment via PayStack transfer API
        Args:
            is_retry (bool): If True, generate new reference for PayStack
        """
        import logging
        logger = logging.getLogger('documents')
        
        if not self.can_process_payment():
            raise ValueError("Cannot process payment. Check bank details and confirmation status.")
        
        try:
            # Get bank details from company profile
            bank_details = self.get_bank_details()
            if not bank_details:
                raise ValueError("Bank details not found")
            
            # Check if owner exists
            if not self.tenant and not self.owner:
                raise ValueError("Owner not found for this remittance")
            
            # Step 0: Create/update outgoing payment record
            from documents.models import Payment, Payee
            from decimal import Decimal
            
            # Ensure amount is Decimal
            amount_decimal = self._get_amount_as_decimal()
            
            # Minimal payee - just name and owner
            if self.tenant is not None:
                payee, created = Payee.objects.get_or_create(
                    tenant=self.tenant,
                    name=bank_details['bank_account_name'],
                )
            else:
                try:
                    # Try to get existing payee for this user
                    payee = Payee.objects.get(user=self.owner)
                    created = False
                    # Update existing payee with latest details
                    payee.name = bank_details['bank_account_name']
                    payee.account_number = bank_details.get('bank_account_number', payee.account_number)
                    payee.bank_name = bank_details.get('bank_name', payee.bank_name)
                    payee.email = bank_details.get('email', self.owner.email)
                    payee.save()
                    logger.info(f"Updated existing user payee {payee.id}")
                except Payee.DoesNotExist:
                    # Create new payee for this user
                    payee = Payee.objects.create(
                        user=self.owner,
                        name=bank_details['bank_account_name'],
                        email=bank_details.get('email', self.owner.email),
                        account_number=bank_details.get('bank_account_number', ''),
                        bank_name=bank_details.get('bank_name', ''),
                    )
                    created = True
                    logger.info(f"Created new user payee {payee.id}")
            
            # Find or create payment
            content_type = ContentType.objects.get_for_model(self)
            outgoing_payment = Payment.objects.filter(
                remittance=self,
                direction='outgoing',
                payment_type='remittance',
                content_type=content_type,
                object_id = self.id
            ).first()
            
            if not outgoing_payment:
                # Create new payment
                if self.tenant is not None:
                    outgoing_payment = Payment.objects.create(
                        tenant=self.tenant,
                        payee=payee,
                        payment_type='remittance',
                        direction='outgoing',
                        amount=amount_decimal,
                        description=f"Remittance {self.reference}",
                        reference_number=self.reference,
                        status='processing',
                        payment_method='bank_transfer',
                        created_by=user,
                        remittance=self,
                        content_object = self
                    )
                else:
                    outgoing_payment = Payment.objects.create(
                        owner=self.owner,
                        payee=payee,
                        payment_type='remittance',
                        direction='outgoing',
                        amount=amount_decimal,
                        description=f"Remittance {self.reference}",
                        reference_number=self.reference,
                        status='processing',
                        payment_method='bank_transfer',
                        created_by=user,
                        remittance=self,
                        content_object = self
                    )

            else:
                # Update existing payment
                outgoing_payment.status = 'processing'
                outgoing_payment.save()
            
            # Step 1: Create transfer recipient
            headers = {
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json"
            }
            
            # Check if recipient already exists
            if not self.paystack_recipient_code:
                # Create recipient
                recipient_payload = {
                    "type": "nuban",
                    "name": bank_details['bank_account_name'],
                    "account_number": bank_details['bank_account_number'],
                    "bank_code": bank_details['bank_code'],
                    "currency": "NGN"
                }
                
                recipient_response = requests.post(
                    "https://api.paystack.co/transferrecipient",
                    headers=headers,
                    json=recipient_payload,
                    timeout=30
                )
                
                recipient_data = recipient_response.json()
                
                if recipient_data['status']:
                    self.paystack_recipient_code = recipient_data['data']['recipient_code']
                    self.save()
                else:
                    # Update payment status to failed
                    outgoing_payment.status = 'failed'
                    outgoing_payment.save()
                    raise Exception(f"Recipient creation failed: {recipient_data.get('message')}")
            
            # Step 2: Initiate transfer
            # Convert Decimal amount to kobo
            amount_in_kobo = self._convert_to_kobo(amount_decimal)
            
            # Generate unique reference for PayStack (especially for retries)
            if is_retry:
                # For retries, use a new unique reference
                import uuid
                paystack_reference = f"{self.reference}-RETRY-{uuid.uuid4().hex[:8].upper()}"
            else:
                # For first attempt, use remittance reference
                paystack_reference = self.reference
            
            metadata = {
                "source": "balance",
                "source_id": str(self.id),
            }

            transfer_payload = {
                "source": "balance",
                "source_id": str(self.id),
                "amount": amount_in_kobo,
                "recipient": self.paystack_recipient_code,
                "reason": self.description or f"Remittance {self.reference}",
                "reference": paystack_reference,  # Use unique reference
                "metadata": metadata,
                "transfer_code": self.paystack_transfer_code,
            }
            
            logger.info(f"Sending transfer with reference: {paystack_reference}")
            
            transfer_response = requests.post(
                "https://api.paystack.co/transfer",
                headers=headers,
                json=transfer_payload,
                timeout=30
            )
            
            transfer_data = transfer_response.json()
            
            if transfer_data['status']:
                self.paystack_transfer_code = transfer_data['data']['transfer_code']
                self.paystack_response = transfer_data['data']
                self.status = 'processing'
                
                if user:
                    self.updated_by = user
                
                # Save payment transaction ID if available
                outgoing_payment.transaction_id = transfer_data['data'].get('transfer_code') or paystack_reference
                outgoing_payment.save()
                
                self.save()
                
                # Schedule a task to verify the transfer
                self.schedule_transfer_verification()
                
                return {
                    'success': True,
                    'message': 'Transfer initiated successfully',
                    'transfer_code': self.paystack_transfer_code,
                    'payment_id': outgoing_payment.id,
                    'reference': paystack_reference,
                    'data': transfer_data['data']
                }
            else:
                self.status = 'failed'
                self.paystack_response = transfer_data
                
                # Update payment status
                outgoing_payment.status = 'failed'
                outgoing_payment.save()
                
                self.save()
                
                error_msg = transfer_data.get('message', 'Unknown error')
                logger.error(f"Transfer failed: {error_msg}")
                
                return {
                    'success': False,
                    'message': f"Transfer failed: {error_msg}",
                    'payment_id': outgoing_payment.id,
                    'data': transfer_data
                }
                
        except Exception as e:
            self.status = 'failed'
            self.paystack_response = {'error': str(e)}
            self.save()
            
            # Update payment if it was created
            if 'outgoing_payment' in locals():
                outgoing_payment.status = 'failed'
                outgoing_payment.save()
            
            return {
                'success': False,
                'message': f"Error processing payment: {str(e)}"
            }

    def schedule_transfer_verification(self):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Transfer verification scheduled for remittance {self.reference}")
        pass


    @staticmethod
    def verify_remittance_transfer(remittance_id):
        """Background task to verify transfer status - webhook version"""
        # This will be called by PayStack webhook, not scheduled task
        from documents.viewfuncs.send_mails import send_remittance_success_email, send_remittance_failed_email, send_remittance_for_user_failed_email, send_remittance_success_for_user_email
        try:
            remittance = Remittance.objects.get(id=remittance_id)
            
            if not remittance.paystack_transfer_code:
                return
            
            headers = {
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"
            }
            
            response = requests.get(
                f"https://api.paystack.co/transfer/{remittance.paystack_transfer_code}",
                headers=headers,
                timeout=30
            )
            
            data = response.json()
            
            if data['status']:
                transfer_data = data['data']
                
                if transfer_data['status'] == 'success':
                    remittance.mark_as_completed(
                        bank_reference=transfer_data.get('reference'),
                        user=remittance.updated_by
                    )
                    
                    # Send success notification
                    if remittance.tenant is not None:
                        send_remittance_success_email(remittance)
                    else:
                        send_remittance_success_for_user_email(remittance)

                elif transfer_data['status'] == 'failed':
                    remittance.status = 'failed'
                    remittance.save()
                    
                    # Send failure notification
                    if remittance.tenant is not None:
                        send_remittance_failed_email(remittance, transfer_data.get('message'))
                    else:
                        send_remittance_for_user_failed_email(remittance, transfer_data.get('message'))
                    
                # If pending, do nothing - wait for webhook
                # No need to reschedule since we have webhooks
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error verifying transfer: {e}")
    
    def _check_transfer_status(self):
        """Check PayStack transfer status (can be called via webhook)"""
        from paystackapi.paystack import Paystack
        from paystackapi.transfer import Transfer
        try:  
            paystack_secret_key = settings.PAYSTACK_SECRET_KEY
            paystack = Paystack(secret_key=paystack_secret_key)
            
            if not self.paystack_transfer_code:
                return False
                
            status_response = Transfer.check(
                transfer_code=self.paystack_transfer_code
            )
            
            if status_response['status']:
                transfer_data = status_response['data']
                
                if transfer_data['status'] == 'success':
                    self.mark_as_completed(
                        bank_reference=transfer_data.get('reference'),
                        user=self.updated_by
                    )
                    return True
                elif transfer_data['status'] == 'failed':
                    self.status = 'failed'
                    self.save()
                    return False
                
            return False
        except Exception as e:
            print(f"Error checking transfer status: {e}")
            return False
    
    def mark_as_completed(self, bank_reference=None, user=None):
        """Mark remittance as completed and update owner balance"""
        self.status = 'completed'
        self.completion_date = timezone.now()
        
        if bank_reference:
            self.bank_reference = bank_reference
        
        if user:
            self.updated_by = user
        
        self.save()
        
        # Update payments
        self.payments.all().update(
            remittance_status='remitted',
            remittance=self
        )
        
        # Update owner balance
        if self.tenant is not None:
            tenant_balance, _ = TenantBalance.objects.get_or_create(tenant=self.tenant)
        else:
            tenant_balance, _ = TenantBalance.objects.get_or_create(owner=self.owner)
        tenant_balance.update_balance()

class Payment(models.Model):
    """Generic payment model – used for payroll, vendors, subscriptions, bonuses, etc."""
    PAYMENT_TYPE_CHOICES = [
        ('salary', 'Salary'),
        ('contractor', 'Contractor Fee'),
        ('vendor', 'Vendor Invoice'),
        ('subscription', 'Subscription'),
        ('conference_fee', 'Conference Fee'),
        ('booking_fee', 'Booking Fee'),
        ('bonus', 'Bonus'),
        ('reimbursement', 'Reimbursement'),
        ('refund', 'Refund'),
        ('subscription_adjustment', 'Subscription Adjustment'),
        ('setup_fee', 'Setup Fee'),
        ('credit', 'Credit'),
        ('abandoned', 'Abandoned'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('processing', 'Processing'),
        ('refunded', 'Refunded'),


    ]
    DIRECTION_CHOICES = [
        ('outgoing', 'Outgoing'),  # Platform → Payee (salary, vendor)
        ('incoming', 'Incoming'),  # Payer → Platform (conference fee, subscription)
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    payee = models.ForeignKey(Payee, on_delete=models.PROTECT, null=True, blank=True, related_name='received_payments')  # Who receives money (outgoing)
    payer = models.ForeignKey(Payer, on_delete=models.PROTECT, null=True, blank=True, related_name='made_payments')  # Who sends money (incoming)

    payment_type = models.CharField(max_length=30, choices=PAYMENT_TYPE_CHOICES, default='salary', blank=True, null=True)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default='outgoing')
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # Gross amount
    net_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  # After deductions
    tax_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    payroll = models.ForeignKey(Payroll, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')  # Link only for payroll batches

    # Recurring support (for subscriptions)
    is_recurring = models.BooleanField(default=False)
    recurrence_frequency = models.CharField(max_length=20, blank=True, null=True,
        choices=[
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ]
    )
    next_due_date = models.DateField(null=True, blank=True)

    description = models.TextField(blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)  # e.g., invoice #

    due_date = models.DateField(null=True, blank=True)  # When payment is expected
    payment_date = models.DateTimeField(null=True, blank=True)  # When actually paid

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)  # bank_transfer, card, etc.
    return_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payments')
    
    remittance_status = models.CharField(
        max_length=20,
        choices=[
            ('unremitted', 'Unremitted'),
            ('pending_remittance', 'Pending Remittance'),
            ('remitted', 'Remitted'),
        ],
        default='unremitted'
    )
    remitted_at = models.DateTimeField(null=True, blank=True)
    remittance = models.ForeignKey(Remittance, on_delete=models.SET_NULL, null=True, blank=True, related_name='remitted_payments')
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    metadata = models.JSONField(default=dict, blank=True, null=True)


    class Meta:
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['payment_type', 'status', 'payment_date']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        direction = "←" if self.direction == 'incoming' else "→"
        target = self.payer.name if self.payer else self.payee.name if self.payee else "Unknown"
        return f"{self.get_payment_type_display()} {self.amount} {direction} {target} ({self.status})"

    # def save(self, *args, **kwargs):
    #     # Auto-set net_amount if not provided
    #     if self.net_amount is None:
    #         self.net_amount = self.amount - self.tax_deductions - self.other_deductions
    #     super().save(*args, **kwargs)

    #     # If linked to a payroll, update its total
    #     if self.payroll:
    #         self.payroll.update_total()
    def save(self, *args, **kwargs):
        from decimal import Decimal
        
        # Auto-set net_amount if not provided
        if self.net_amount is None:
            # Convert all values to Decimal safely
            amount_decimal = self.amount if isinstance(self.amount, Decimal) else Decimal(str(self.amount))
            
            # Convert tax_deductions to Decimal (it might be float 0.00)
            tax_val = self.tax_deductions
            if tax_val is None:
                tax_decimal = Decimal('0.00')
            elif isinstance(tax_val, Decimal):
                tax_decimal = tax_val
            else:
                tax_decimal = Decimal(str(tax_val))
            
            # Convert other_deductions to Decimal
            other_val = self.other_deductions
            if other_val is None:
                other_decimal = Decimal('0.00')
            elif isinstance(other_val, Decimal):
                other_decimal = other_val
            else:
                other_decimal = Decimal(str(other_val))
            
            # Now do the subtraction with Decimals
            self.net_amount = amount_decimal - tax_decimal - other_decimal
        
        # Call the parent save method
        super().save(*args, **kwargs)

        # If linked to a payroll, update its total
        if self.payroll:
            self.payroll.update_total()

        
def upload_to_company_documents(instance, filename):
    tenant_name = instance.tenant.name
    return os.path.join('company_documents', tenant_name, filename)

class CompanyDocument(models.Model):
    DOCUMENT_TYPES = [
        ('certificate', 'Certificate'),
        ('contract', 'Contract'),
        ('license', 'License'),
        ('memorandum', 'Memorandum'),
        ('other', 'Other'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="company_document")
    company_profile = models.ForeignKey('CompanyProfile', on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to=upload_to_company_documents)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES, default='other')
    description = models.CharField(max_length=255, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_type} - {self.company_profile.full_name} ({self.uploaded_at})"


class VacancyTag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    def __str__(self):
        return self.name

class VacancySkill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    def __str__(self):
        return self.name

class Vacancy(models.Model):
    VACANCY_STATUS = [
        ('active', 'Active'),
        ('withdrawn', 'Withdrawn'),
        ('closed', 'Closed'),
    ]
    WORK_MODE = [
        ('remote', 'Remote'),
        ('onsite', 'On-Site'),
        ('hybrid', 'Hybrid'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="vacancy", null=True, blank=True)
    title = models.CharField(max_length=255, blank=False, null=False)
    description = models.TextField(blank=True, null=True)
    # skills = models.TextField(blank=True, null=True)
    skills = models.ManyToManyField(VacancySkill, blank=True)
    old_skills = models.TextField(blank=True, null=True)

    eligibility = models.TextField(blank=True, null=True)
    min_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=get_currency_choices(), null=True, blank=True)
    country = CountryField(blank=True, null=True)
    # old_city = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    # city = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Region/State")
    work_mode = models.CharField(max_length=20, choices=WORK_MODE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_vacancies')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_vacancies')
    status = models.CharField(max_length=20, choices=VACANCY_STATUS, default='active')
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_shared = models.BooleanField(default=False, help_text="Share/Post this vacancy.")
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='shared_vacancy')
    share_time = models.DateTimeField(null=True, blank=True)
    share_time_end = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField(VacancyTag, blank=True)
    
    def add_tags_from_text(self, tags_text):
        if tags_text:
            tag_names = [name.strip().lower() for name in tags_text.split(',') if name.strip()]
            for tag_name in tag_names:
                tag = VacancyTag.objects.get_or_create(name=tag_name)
                self.tags.add(tag)
    def add_skills_from_text(self, skills_text):
        if skills_text:
            skill_names = [name.strip().lower() for name in skills_text.split(',') if name.strip()]
            for skill_name in skill_names:
                skill = VacancySkill.objects.get_or_create(name=skill_name)
                self.skills.add(skill)

    def get_shareable_link(self):
        from django.urls import reverse
        return reverse('vacancy_post', kwargs={'token': str(self.share_token)})

    def __str__(self):
        if self.tenant is not None:
            return f"Vacancy position {self.title} by {self.tenant.name}"
        else:
            return f"Vacancy position {self.title} by {self.created_by.username}"

def upload_to_job_cvs(instance, filename):
    tenant_name = instance.vacancy.tenant.name if instance.vacancy.tenant else "Personal"
    title = instance.vacancy.title if instance.vacancy else "N/A"
    return os.path.join('vacancy_cvs', tenant_name, title, filename)

class VacancyApplication(models.Model):
    VACANCY_APPLICATION_STATUS = [
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]
    ONBOARDING_STATUS = [
        ("pending", "Pending"),
        ("onboarded", "Onboarded"),
        ("rejected", "Rejected"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="vacancy_application", null=True, blank=True)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="applications")
    first_name = models.CharField(max_length=255, blank=False, null=False)
    last_name = models.CharField(max_length=255, blank=False, null=False)
    middle_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=False, null=False)
    email = models.EmailField(blank=False, null=False)
    country = CountryField(blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    cv = models.FileField(upload_to=upload_to_job_cvs)
    cover_letter = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=VACANCY_APPLICATION_STATUS, blank=True, null=True)
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_vacancy_applications')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    onboarding_status = models.CharField(max_length=20, choices=ONBOARDING_STATUS, default="pending")
    onboarded_user = models.OneToOneField(CustomUser, null=True, blank=True, on_delete=models.SET_NULL)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

import pytz
ALL_TIMEZONES = [(tz, tz.replace('_', ' ')) for tz in pytz.common_timezones]
COMMON_FIRST = [
    'Africa/Lagos',
    'Africa/Johannesburg',
    'Europe/London',
    'Europe/Paris',
    'America/New_York',
    'America/Chicago',
    'America/Los_Angeles',
    'Asia/Dubai',
    'Asia/Singapore',
    'Asia/Tokyo',
]
class Interview(models.Model):
    INTERVIEW_STATUS = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('rescheduled', 'Rescheduled'),
        ('cancelled', 'Cancelled'),
    ]
    TIMEZONE_CHOICES = (
        [(tz, tz.replace('_', ' ').replace('/', ' → ')) for tz in COMMON_FIRST if tz in pytz.common_timezones] +
        [(tz, tz.replace('_', ' ').replace('/', ' → ')) for tz in pytz.common_timezones if tz not in COMMON_FIRST]
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="interviews", null=True, blank=True)
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name="interviews")
    applications = models.ManyToManyField(VacancyApplication, related_name="interviews")
    interviewers = models.ManyToManyField(CustomUser, blank=True, related_name='interviewer_interviews')
    scheduled_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='scheduled_interviews')

    schedule_start = models.DateTimeField()
    schedule_end = models.DateTimeField()

    timezone = models.CharField(
        max_length=100,
        choices=TIMEZONE_CHOICES,
        default='Africa/Lagos',
        help_text="Interview time zone (affects Google Meet & Calendar)"
    )

    is_virtual = models.BooleanField(default=True)
    google_meet = models.BooleanField(default=False, help_text="Use google meet")
    virtual_link = models.URLField(blank=True, null=True, help_text="Link for virtual interviews")
    physical_location = models.CharField(max_length=255, blank=True, null=True)

    google_meet_link = models.URLField(blank=True, null=True)
    google_event_id = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=20, choices=INTERVIEW_STATUS, default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'google_event_id')   # safety

    def clean(self):
        if not self.is_virtual and not self.physical_location:
            raise ValidationError("Physical location is required for non-virtual interviews.")
        if self.schedule_start < timezone.now():
            raise ValidationError("Start time must be in the future.")
        if self.schedule_start >= self.schedule_end:
            raise ValidationError("End time must be after start time.")
        
    def __str__(self):
        return f"{self.vacancy} – {self.schedule_start:%Y-%m-%d %H:%M}"
        
    # def save(self, *args, **kwargs):
    #     creating = self.pk is None
    #     super().save(*args, **kwargs)
    #     if creating and self.is_virtual and not self.google_event_id:
    #         from .viewfuncs.helper_funcs.google_meet_calendar import create_meet
    #         create_meet(self)


    
    # @property
    # def applicant_list(self):
    #     return ", ".join([f"{a.first_name} {a.last_name}" for a in self.applications.all()])

class InterviewParticipant(models.Model):
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE)
    application = models.ForeignKey(VacancyApplication, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("interview", "application")

def offer_letter_upload_path(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    title = instance.application.vacancy.title if instance.application.vacancy else "N/A"
    return os.path.join('offers', tenant_name, title, filename)
    # return f"tenants/{instance.tenant.id}/offers/{instance.application.id}/{filename}"

def signed_offer_letter_upload_path(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    title = instance.application.vacancy.title if instance.application.vacancy else "N/A"
    return os.path.join('signed offers', tenant_name, title, filename)

class JobOffer(models.Model):
    OFFER_STATUS = [
        ("sent", "Sent"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("expired", "Expired"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    application = models.OneToOneField(VacancyApplication, on_delete=models.CASCADE, related_name="offer")
    proposed_start_date = models.DateTimeField(null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    offer_letter = models.FileField(
        upload_to=offer_letter_upload_path,
        null=True,
        blank=True,
        help_text="Signed or official offer letter (PDF)"
    )
    signed_document = models.FileField(
        upload_to=signed_offer_letter_upload_path,
        null=True,
        blank=True,
        help_text="Signed offer letter (PDF)"
    )
    offer_token = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(max_length=20, choices=OFFER_STATUS, default="sent")
    sent_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)

class OnboardingLog(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    application = models.ForeignKey(VacancyApplication, on_delete=models.CASCADE)
    onboarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ConferenceTag(models.Model):
    """
    Tag for conferences. Optional tenant FK. Name is case-insensitive-unique per tenant.
    """
    name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
        ]


    def __str__(self):
        return self.name

    @classmethod
    def get_or_create_ci(cls, name):
        name = name.strip()
        tag = cls.objects.filter(name__iexact=name).first()
        if tag:
            return tag, False
        return cls.objects.create(name=name.title()), True

def upload_to_conference_banners(instance, filename):
    tenant_name = instance.tenant.name if instance.tenant else "Personal"
    username = instance.organizer.username if instance.organizer else "anonymous"
    return os.path.join('conference_banners', tenant_name, username, filename)

class Conference(models.Model):
    TYPE_CHOICES = [
        ('physical', 'In-Person'),
        ('virtual', 'Virtual'),
        ('hybrid', 'Hybrid'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255)
    theme = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    venue = models.CharField(max_length=255, blank=True)
    conference_type = models.CharField(max_length=10,  choices=TYPE_CHOICES,  default='physical')
    virtual_link = models.URLField(blank=True, null=True, help_text="Link for conferences held online, virtual or hybrid.")
    banner = models.ImageField(upload_to=upload_to_conference_banners, null=True, blank=True)
    registration_required = models.BooleanField(default=True)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    ticket_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, choices=get_currency_choices(), null=True, blank=True)
    tags = models.ManyToManyField(ConferenceTag, blank=True, related_name="conferences", help_text="Add tags to help people find this conference")
    # New advanced pricing fields
    early_bird_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Discounted price if registration is before early_bird_deadline.")
    early_bird_deadline = models.DateTimeField(null=True, blank=True, help_text="Deadline for early-bird pricing (must be before registration_deadline).") 
    late_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Higher price if registration is after late_deadline.")
    late_deadline = models.DateTimeField(null=True, blank=True, help_text="Start date for late pricing (must be before start_date).")
    free_first_n_participants = models.PositiveIntegerField(default=0, null=True, blank=True, help_text="Number of first registrants who get free tickets (overrides all other pricing).")
    platform_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Platform fee as percentage of ticket price (e.g., 10.00 = 10%).")
    platform_fee_fixed = models.DecimalField(max_digits=10, decimal_places=2, default=100.00, help_text="Fixed platform fee added to ticket price.")
    max_participants_physical = models.PositiveIntegerField(null=True, blank=True)
    max_participants_virtual = models.PositiveIntegerField(null=True, blank=True)
    organizer = models.ForeignKey('CustomUser', on_delete=models.SET_NULL, null=True, related_name='organized_conferences')
    about_host = models.TextField(blank=True, null=True, help_text="Short description of the host of the conference (company details)")
     # Reminder configuration fields
    reminder_count = models.PositiveIntegerField(default=0, help_text="How many reminders to send before the conference (use with reminder_offsets).")
    reminder_offsets = JSONField(default=list, blank=True, help_text="List of offsets (in days) before start_date to send reminders. Example: [7, 1, 0.5]")
    is_posted = models.BooleanField(default=False, help_text="Whether the conference is posted to the public feed.")
    time_posted = models.DateTimeField(null=True, blank=True)
    speakers = models.ManyToManyField('ConferenceSpeaker', blank=True, related_name='conferences', help_text="Speakers for this conference")
    upload_folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name='conference_uploads',
        help_text='Folder where participants can upload files (slides, posters, abstracts, etc.)')
    upload_instructions = models.TextField(blank=True, null=True, help_text='Custom instructions for participants when uploading files')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-start_date']

    # def clean(self):
    #     """Validate required fields based on conference type."""
    #     if self.conference_type in ('physical', 'hybrid') and not self.venue:
    #         raise ValidationError({'venue': 'Venue is required for physical or hybrid conferences.'})

    #     if self.conference_type in ('virtual', 'hybrid') and not self.virtual_link:
    #         raise ValidationError({'virtual_link': 'Virtual link is required for virtual or hybrid conferences.'})

    def __str__(self):
        if self.tenant is not None:
            return f"{self.title} ({self.tenant})"
        else:
            return f"{self.title} ({self.organizer.username})"
    
    # === Helper Methods ===
    def get_accepted_participant_count(self):
        """Count currently accepted participants (for free_first_n logic)."""
        return self.participants.filter(status='accepted').count()

    def get_current_price(self, registration_time=None, price_tier=None):
        """
        Calculate the applicable base price at a given time.

        Priority:
        1. Explicit price_tier (if the conference has tiers)
        2. free_first_n → early_bird → late → standard ticket_price
        """
        from django.utils import timezone
        now = registration_time or timezone.now()

        # ── Tier-based pricing ───────────────────────────────────────────────────
        if price_tier is not None:
            return price_tier.price

        # ── Legacy flat / time-based pricing ────────────────────────────────────
        accepted_count = self.get_accepted_participant_count()

        if (self.free_first_n_participants is not None and
                accepted_count < self.free_first_n_participants):
            return Decimal('0.00')

        if (self.early_bird_price is not None and
                self.early_bird_deadline and
                now <= self.early_bird_deadline):
            return self.early_bird_price

        if (self.late_price is not None and
                self.late_deadline and
                now >= self.late_deadline):
            return self.late_price

        return self.ticket_price or Decimal('0.00')

    def get_payable_amount(self, base_price):
        """
        Add platform fees to the base ticket price.
        """
        from decimal import Decimal
        if base_price <= 0:
            return Decimal('0.00')
        
        percent_fee = base_price * (self.platform_fee_percent / Decimal('100'))
        total = base_price + percent_fee + self.platform_fee_fixed
        return total.quantize(Decimal('0.01'))


class ConferenceParticipant(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("declined", "Declined"),
        ("cancelled", "Cancelled"),
    ]
    TITLE_CHOICES = [
        ("mr", "Mr."),
        ("ms", "Ms."),
        ("mrs", "Mrs."),
    ]
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
    ]
    AGE_CHOICES = [
        ("18-24", "18-24"),
        ("25-34", "25-34"),
        ("35-44", "35-44"),
        ("45-54", "45-54"),
        ("55-64", "55-64"),
        ("65+", "65+"),
    ]
    DISCOVERY_CHANNEL_CHOICES = [
        ("facebook", "Facebook"),
        ("twitter", "Twitter"),
        ("linkedin", "Linkedin"),
        ("google", "Google"),
        ("instagram", "Instagram"),
        ("whatsapp", "WhatsApp"),
        ("other", "Other"),
    ]
    ATTENDANCE_MODE_CHOICES = [
        ("physical", "Physical"),
        ("virtual", "Virtual"),
    ]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='participants')
    organization = models.CharField(max_length=255,null=True,blank=True)
    title = models.CharField(max_length=16, choices=TITLE_CHOICES, null=True, blank=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    age = models.CharField(max_length=16, choices=AGE_CHOICES, help_text="Age group", null=True, blank=True)
    gender = models.CharField(max_length=16, choices=GENDER_CHOICES, null=True, blank=True)
    phone_number=models.CharField(max_length=20,null=True,blank=True)
    email = models.EmailField()
    designation = models.CharField(max_length=255,null=True,blank=True)
    country = CountryField(blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    attendance_mode = models.CharField(max_length=16, choices=ATTENDANCE_MODE_CHOICES, null=True, blank=True)
    discovery_channel = models.CharField(max_length=16, choices=DISCOVERY_CHANNEL_CHOICES, null=True, blank=True, help_text="How did you find out about this conference?")
    unique_token = models.CharField(max_length=64, editable=False, unique=True, blank=True, help_text="Unique token for participant identification")
    registered_at = models.DateTimeField(default=timezone.now)
    ticket_paid =models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    is_confirmed = models.BooleanField(default=False)
    check_in_status= models.BooleanField(default=False)
    check_in_time   = models.DateTimeField(null=True, blank=True, verbose_name="Check-in Time")
    checked_in_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_performed")
    check_in_method = models.CharField(max_length=20,null=True,blank=True,
        choices=[
            ('qr_scan', 'QR Code Scan'),
            ('manual', 'Manual Check-in'),
            ('online', 'Online Verification')
        ]
    )

    reminder_sent=models.BooleanField(default=False)
    payment = models.OneToOneField('Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='conference_registration')
    payer = models.ForeignKey(Payer, on_delete=models.PROTECT, related_name='conference_registrations', null=True, blank=True)
    feedback = models.OneToOneField('Feedback', on_delete=models.SET_NULL, null=True, blank=True, related_name='conference_participant')
    # ── Tiered pricing ────────────────────────────────────────────────────────
    price_tier = models.ForeignKey('ConferencePriceTier', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='participants',
        help_text='The tier chosen by the participant at registration.',
    )
    

    class Meta:
        unique_together = ("conference", "email")
        ordering = ["conference", "-registered_at"]
    def save(self, *args, **kwargs):    
        if not self.unique_token:
            self.unique_token = uuid.uuid4()
        # Ensure reminders_sent is a list (defensive)
        if self.reminder_sent is None:
            try:
                self.reminder_sent = []
            except Exception:
                pass
        super().save(*args, **kwargs)

    def accept(self):
        self.status = "accepted"
        self.is_confirmed = True
        self.ticket_paid = True
        self.save(update_fields=['status', 'is_confirmed'])

    def decline(self):
        self.status = "declined"
        self.is_confirmed = False
        self.save(update_fields=['status', 'is_confirmed'])

    def unregister(self):
        self.status = "cancelled"
        self.is_confirmed = False
        self.save(update_fields=['status', 'is_confirmed'])

    def get_location(self):
        return f"{self.city}, {self.country}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email
    
    def __str__(self):
        return f"{self.full_name} ({self.email}) - {self.conference.title}"
    
# ─── NEW MODEL ────────────────────────────────────────────────────────────────
class ConferencePriceTier(models.Model):
    """
    A named pricing tier for a conference (e.g. "Student", "Professional", "VIP").
    Participants choose one tier when registering.
    If no tiers exist the conference falls back to ticket_price / early_bird_price etc.
    """
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='price_tiers',)
    name = models.CharField(max_length=100, help_text='e.g. "Student", "Professional", "VIP"')
    description = models.TextField(blank=True, help_text='Short description shown to participants during registration.',)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField(null=True, blank=True,
        help_text='Max registrations for this tier. Leave blank for unlimited.',
    )
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0, help_text='Display order — lower numbers appear first.',)

    class Meta:
        ordering = ['order', 'price']
        unique_together = ('conference', 'name')

    def __str__(self):
        return f"{self.name} – {self.price} ({self.conference.title})"

    def slots_remaining(self):
        """Returns None if unlimited, otherwise remaining capacity."""
        if self.capacity is None:
            return None
        used = ConferenceParticipant.objects.filter(
            price_tier=self,
            status__in=['pending', 'accepted'],
        ).count()
        return max(0, self.capacity - used)

    def is_available(self):
        remaining = self.slots_remaining()
        return self.is_active and (remaining is None or remaining > 0)

class GuestUser(models.Model):
    
    email = models.EmailField(unique=True)  # Normalized lowercase in practice
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    
    # Source tracking using GenericForeignKey
    source_content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='guest_user_sources',
        help_text="Type of entity this guest user originated from"
    )
    source_object_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="ID of the entity this guest user originated from"
    )
    source_content_object = GenericForeignKey('source_content_type', 'source_object_id')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    def update_access(self):
        self.last_accessed_at = timezone.now()
        self.save(update_fields=['last_accessed_at', 'updated_at'])
    
    def get_source_name(self):
        """Get a display name for the source entity."""
        if not self.source_content_object:
            return "Unknown Source"
        
        source = self.source_content_object
        if hasattr(source, 'title'):
            return source.title
        elif hasattr(source, 'name'):
            return source.name
        return str(source)
    
    def get_source_type(self):
        """Get the type of source entity."""
        if not self.source_content_type:
            return "Unknown"
        return self.source_content_type.model

    def __str__(self):
        return f"Guest: {self.email}"


class CustomerSupport(models.Model):
    """
    Tracks support/sales follow-up activity for various entities.
    """
    ENTITY_TYPE_CHOICES = [
        ('tenant', 'Tenant'),
        ('vacancy', 'Vacancy'),
        ('conference', 'Conference'),
        ('user', 'User'),
        ('guest', 'Guest User'),
    ]
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('follow_up', 'Follow-up Required'),
        ('converted', 'Converted'),
        ('inactive', 'Inactive'),
    ]
    
    # Generic reference to any entity type
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES)
    entity_id = models.PositiveIntegerField()
    
    # Source tracking using GenericForeignKey (where the entity came from)
    source_content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='customer_support_sources',
        help_text="Type of entity this support record originated from"
    )
    source_object_id = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="ID of the entity this support record originated from"
    )
    source_content_object = GenericForeignKey('source_content_type', 'source_object_id')
    
    # Support tracking fields
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    notes = models.TextField(
        blank=True, 
        null=True, 
        help_text="Internal notes about contact/follow-up for team collaboration"
    )
    
    # Contact tracking
    contacted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='support_contacts',
        help_text="Support staff member who contacted this entity"
    )
    contacted_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('entity_type', 'entity_id')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entity_type', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
        ]
        permissions = [
            ('view_support_dashboard', 'Can view Customer Support dashboard'),
            ('update_support_activity', 'Can update Customer Support activity'),
        ]
        verbose_name = 'Customer Support Record'
        verbose_name_plural = 'Customer Support Records'
    
    def __str__(self):
        return f"{self.get_entity_type_display()} #{self.entity_id} - {self.get_status_display()}"
    
    def mark_contacted(self, user, notes_text=None):
        """
        Mark this entity as contacted by a support staff member.
        
        Args:
            user: The CustomUser who made contact
            notes_text: Optional notes about the contact
        """
        self.status = 'contacted'
        self.contacted_by = user
        self.contacted_at = timezone.now()
        if notes_text:
            if self.notes:
                self.notes += f"\n\n[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {user.username}: {notes_text}"
            else:
                self.notes = f"[{timezone.now().strftime('%Y-%m-%d %H:%M')}] {user.username}: {notes_text}"
        self.save()
    
    def get_entity(self):
        """
        Retrieve the actual entity object (Tenant, Vacancy, Conference, User, or GuestUser).
        Returns None if entity doesn't exist or type is invalid.
        """
        try:
            if self.entity_type == 'tenant':
                return Tenant.objects.filter(id=self.entity_id).first()
            elif self.entity_type == 'vacancy':
                return Vacancy.objects.filter(id=self.entity_id).first()
            elif self.entity_type == 'conference':
                return Conference.objects.filter(id=self.entity_id).first()
            elif self.entity_type == 'user':
                return CustomUser.objects.filter(id=self.entity_id).first()
            elif self.entity_type == 'guest':
                return GuestUser.objects.filter(id=self.entity_id).first()
        except Exception as error:
            # Log error but don't crash - entity might have been deleted
            print(f"Error retrieving entity {self.entity_type} #{self.entity_id}: {error}")
        return None
    
    def get_entity_name(self):
        """
        Get a display name for the tracked entity.
        """
        entity = self.get_entity()
        if not entity:
            return f"Deleted {self.get_entity_type_display()}"
        
        if self.entity_type == 'tenant':
            return entity.name
        elif self.entity_type == 'vacancy':
            return entity.title
        elif self.entity_type == 'conference':
            return entity.title
        elif self.entity_type == 'user':
            return entity.get_full_name() or entity.username
        elif self.entity_type == 'guest':
            return entity.email
        return str(entity)
    
    def get_entity_created_date(self):
        """
        Get the creation date of the tracked entity.
        """
        entity = self.get_entity()
        if not entity:
            return self.created_at
        
        if hasattr(entity, 'created_at'):
            return entity.created_at
        elif hasattr(entity, 'date_joined'):
            return entity.date_joined
        return self.created_at
    
    def get_source_name(self):
        """Get a display name for the source entity."""
        if not self.source_content_object:
            return "Direct"
        
        source = self.source_content_object
        if hasattr(source, 'title'):
            return source.title
        elif hasattr(source, 'name'):
            return source.name
        return str(source)
    
    def get_source_type(self):
        """Get the type of source entity."""
        if not self.source_content_type:
            return None
        return self.source_content_type.model
    

class Feedback(models.Model):
    # The user who gave the feedback (can be anonymous if user is null)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedbacks'
    )
    guest_user = models.ForeignKey(
        GuestUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedbacks'
    )
    
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, null=True, blank=True)

    # Generic relation to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Rating: 1 to 5 stars (common standard)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        help_text="Rating from 1 to 5 stars"
    )

    # Optional topic/category (e.g., "Content Quality", "Speaker", "Organization")
    topic = models.CharField(max_length=100, blank=True, null=True)

    # Free-text feedback
    comment = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional: allow anonymous feedback with name/email
    anonymous_name = models.CharField(max_length=255, blank=True, null=True)
    anonymous_email = models.EmailField(blank=True, null=True)

    class Meta:
        constraints = [
            # Logged-in user: one feedback per user per target
            UniqueConstraint(
                fields=['content_type', 'object_id', 'user'],
                name='unique_feedback_per_user',
                condition=Q(user__isnull=False),
            ),
            # Guest user: one feedback per guest per target
            UniqueConstraint(
                fields=['content_type', 'object_id', 'guest_user'],
                name='unique_feedback_per_guest_user',
                condition=Q(guest_user__isnull=False),
            ),
            # Anonymous with email: one feedback per email per target
            UniqueConstraint(
                fields=['content_type', 'object_id', 'anonymous_email'],
                name='unique_feedback_per_anonymous_email',
                condition=Q(anonymous_email__isnull=False, user__isnull=True, guest_user__isnull=True),
            ),
        ]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['tenant']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        target = self.content_object or "Unknown Target"
        if self.user:
            submitter = str(self.user)  # or self.user.get_full_name()
        elif self.guest_user:
            submitter = str(self.guest_user)  # adjust based on GuestUser's __str__ or name field
        elif self.anonymous_name:
            submitter = self.anonymous_name
        elif self.anonymous_email:
            submitter = self.anonymous_email.split('@')[0]  # or just the email
        else:
            submitter = "Anonymous"
        rating = self.rating or "No rating"
        return f"Feedback by {submitter} on {target} ({rating})"
    
    def clean(self):
        submitters = [bool(self.user), bool(self.guest_user), bool(self.anonymous_email) or bool(self.anonymous_name)]
        if sum(submitters) > 1:
            raise ValidationError("Only one submitter type (user, guest_user, or anonymous) can be provided.")


class CustomQuestion(models.Model):
    """
    Custom registration questions created by conference organizers.

    """
    conference = models.ForeignKey(
        Conference, 
        on_delete=models.CASCADE, 
        related_name='custom_questions'
    )
    question = models.CharField(
        max_length=200,
        help_text="The question text displayed to participants"
    )
    required = models.BooleanField(
        default=True,
        help_text="Whether this question must be answered"
    )
    order = models.IntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Custom Question'
        verbose_name_plural = 'Custom Questions'
    
    def __str__(self):
        return f"{self.conference.title} - Q{self.order}: {self.question[:50]}"


class CustomAnswer(models.Model):
    """
    Answers to custom questions provided during conference registration.
    Links participant's registration to their answers.
    """
    participant = models.ForeignKey(
        ConferenceParticipant,  # ← Changed from Registration to ConferenceParticipant
        on_delete=models.CASCADE,
        related_name='custom_answers'
    )
    question = models.ForeignKey(
        CustomQuestion,
        on_delete=models.CASCADE
    )
    answer = models.TextField(
        max_length=500,
        help_text="Participant's answer to the custom question"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['question__order']
        unique_together = ['participant', 'question']
        verbose_name = 'Custom Answer'
        verbose_name_plural = 'Custom Answers'
    
    def __str__(self):
        return f"{self.participant.full_name} - {self.question.question[:30]}: {self.answer[:30]}"
    
# def upload_to_conference_speakers(instance, filename):
#     tenant_name = instance.conferences.tenant.name if instance.conferences.tenant else f"Personal-{instance.conferences.organized_by}"
#     title = instance.conferences.title if instance.conferences else "N/A"
#     return os.path.join('conference_speakers', tenant_name, title, filename)

def upload_to_conference_speakers(instance, filename):
    ext = filename.split('.')[-1]
    # Use tenant directly from speaker (safe)
    if instance.tenant:
        tenant_part = f"tenant-{instance.tenant.id}"
    else:
        tenant_part = "personal"
    name_part = f"{instance.first_name}_{instance.last_name}".lower()
    return f"conference_speakers/{tenant_part}/{name_part}_{uuid4().hex}.{ext}"


class ConferenceSpeaker(models.Model):
    TITLE_CHOICES = [
        ('mr', 'Mr.'),
        ('mrs', 'Mrs.'),
        ('ms', 'Ms.'),
        ('dr', 'Dr.'),
        ('prof', 'Prof.'),
    ]
    """
    Speaker model for conferences.
    Speakers can be reused across multiple conferences.
    """
    # Tenant relationship
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='conference_speakers',
        help_text="Tenant this speaker belongs to. Null for personal/global speakers."
    )    
    # Personal Information
    photo = models.ImageField(upload_to=upload_to_conference_speakers, null=True, blank=True, help_text="Speaker's photo (recommended: 300x300px)")
    title = models.CharField(max_length=16, choices=TITLE_CHOICES, null=True, blank=True)
    first_name = models.CharField(max_length=100, help_text="Speaker's first name")
    middle_name = models.CharField(max_length=100, null=True, blank=True, help_text="Speaker's middle name or initial")
    last_name = models.CharField(max_length=100, help_text="Speaker's last name")
    # Professional Information
    company = models.CharField(max_length=255, null=True, blank=True, help_text="Company or organization")    
    designation = models.CharField(max_length=255, null=True, blank=True, help_text="Job title or position")
    # Bio/Description (optional - adding for better speaker profiles)
    bio = models.TextField(null=True, blank=True, help_text="Brief biography or description")    
    # Contact (optional - useful for coordination)
    email = models.EmailField(null=True, blank=True, help_text="Speaker's email address")
    phone = models.CharField(max_length=20, null=True, blank=True, help_text="Speaker's phone number")
    # Social Media (optional - for speaker promotion)
    linkedin_url = models.URLField(max_length=255, null=True, blank=True, help_text="LinkedIn profile URL")
    twitter_handle = models.CharField(max_length=100, null=True, blank=True, help_text="Twitter handle (without @)")
    # Audit Fields
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_speakers')    
    created_at = models.DateTimeField(auto_now_add=True)    
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_speakers')    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Conference Speaker'
        verbose_name_plural = 'Conference Speakers'
        indexes = [
            models.Index(fields=['tenant', 'last_name']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        """String representation of the speaker."""
        parts = []
        if self.title:
            parts.append(self.get_title_display())
        parts.append(self.first_name)
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        
        name = ' '.join(parts)
        
        if self.designation and self.company:
            return f"{name} - {self.designation}, {self.company}"
        elif self.designation:
            return f"{name} - {self.designation}"
        elif self.company:
            return f"{name} - {self.company}"
        else:
            return name
    
    @property
    def full_name(self):
        """Get full name without title."""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return ' '.join(parts)
    
    @property
    def full_name_with_title(self):
        """Get full name with title."""
        parts = []
        if self.title:
            parts.append(self.get_title_display())
        parts.append(self.full_name)
        return ' '.join(parts)
    
    @property
    def initials(self):
        """Get initials (e.g., JD for John Doe)."""
        initials = [self.first_name[0].upper() if self.first_name else '']
        if self.middle_name:
            initials.append(self.middle_name[0].upper())
        if self.last_name:
            initials.append(self.last_name[0].upper())
        return ''.join(initials)

class Event(models.Model):
    PAYMENT_STATUS_CHOICES = [('not_required','Free'),('pending','Pending'),('success','Paid'),('failed','Failed')]
    STATUS_CHOICES = [('available', 'Available'),('pending', 'Pending confirmation'),('confirmed','Confirmed'),('cancelled','Cancelled'),('no_show','No-show')]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='events')
    created_at = models.DateTimeField(auto_now_add=True)
    event_link = models.URLField(blank=True, null=True)

    is_booking = models.BooleanField(default=False)
    booking_type = models.ForeignKey('BookingType', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Booker (can be registered user or guest)
    attendee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='booked_events')
    attendee_email = models.EmailField(blank=True)
    attendee_name  = models.CharField(max_length=150, blank=True)
    attendee_phone = models.CharField(max_length=30, blank=True)

    # Payment integration (incoming only)
    payment = models.OneToOneField('Payment', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='booking_event')
    payment_status = models.CharField(max_length=20, default='not_required', choices=PAYMENT_STATUS_CHOICES)

    booking_uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    status = models.CharField(max_length=20, default='pending', choices=STATUS_CHOICES)

    @property
    def attendee_count(self):
        return self.bookings.filter(status__in=['pending', 'confirmed']).count()

    # @property
    # def is_full(self):
    #     if not self.booking_type or not self.booking_type.max_capacity:
    #         return self.attendee_count >= 1  # Default to individual
    #     return self.attendee_count >= self.booking_type.max_capacity
    
    @property
    def current_bookings(self):
        return self.bookings.filter(status__in=['pending', 'confirmed']).count()

    @property
    def is_full(self):
        cap = self.booking_type.effective_max_capacity
        return cap is not None and self.current_bookings >= cap

    @property
    def spots_left(self):
        cap = self.booking_type.effective_max_capacity
        if cap is None:
            return None   # unlimited
        return max(0, cap - self.current_bookings)

    def __str__(self):
        return f"{self.title} ({self.start_time} - {self.end_time})"
    
    def get_absolute_url(self):
        """Return the URL to view/edit this event."""
        from django.urls import reverse
        return reverse('edit_event', kwargs={'event_id': self.id})

class EventParticipant(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, )
    response = models.CharField(max_length=10, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')], default='pending')
    invited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')

class ExternalParticipant(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='external_participants')
    email = models.EmailField()
    # name = models.CharField(max_length=150, blank=True)
    response = models.CharField(max_length=10,
        choices=[('pending','Pending'),('accepted','Accepted'),('declined','Declined')],
        default='pending'
    )
    token      = models.UUIDField(default=uuid.uuid4, editable=False,
                                  help_text="For email RSVP links — no login required")
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = ('event', 'email')

    def __str__(self):
        return f"{self.email} → {self.event.title}"

TIMEZONE_CHOICES = (
    [(tz, tz.replace('_', ' ').replace('/', ' → ')) for tz in COMMON_FIRST if tz in pytz.common_timezones] +
    [(tz, tz.replace('_', ' ').replace('/', ' → ')) for tz in pytz.common_timezones if tz not in COMMON_FIRST]
)
class BookingType(models.Model):
    """
    What can be booked: duration, price, name, schedule, etc.
    Availability windows are now defined inline via BookingTypeSchedule children.
    """
    BOOKING_FOR_CHOICES = [
        ('personal', 'Personal (user)'),
        ('organization', 'Organization-wide'),
    ]
 
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(
        'CustomUser', on_delete=models.CASCADE,
        related_name='created_booking_types', null=True, blank=True
    )
    booking_for = models.CharField(
        max_length=20, choices=BOOKING_FOR_CHOICES, default='personal',
        help_text="Create booking for personal or organization-wide?"
    )
    host_user = models.ForeignKey(
        'CustomUser', on_delete=models.CASCADE,
        related_name='hosted_booking_types', null=True, blank=True,
        help_text="The primary user whose calendar/availability this booking service uses."
    )
    managers = models.ManyToManyField(
        'CustomUser', related_name='managed_booking_types', blank=True,
        help_text="Users who can view and manage (accept/decline) bookings for this type."
    )
 
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
 
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, null=True, blank=True)   # use your get_currency_choices()
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False, help_text="Visible on public booking page")
    shareable_link = models.CharField(max_length=300, blank=True, editable=False)
    color = models.CharField(max_length=7, default='#3788d8')
 
    max_bookings_per_day = models.PositiveSmallIntegerField(null=True, blank=True)
    is_multiple = models.BooleanField(default=False, help_text="Multiple bookings per slot allowed.")
    max_capacity = models.PositiveIntegerField(
        default=1, null=True, blank=True,
        help_text="Maximum number of attendees per event slot (null/1 for individual bookings only)."
    )
    booking_deadline_hours  = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Hours before start time when bookings close (null = no deadline)."
    )
    is_hybrid    = models.BooleanField(default=False, help_text="Hybrid events only.")
    location     = models.CharField(max_length=255, blank=True)
    virtual_link = models.URLField(max_length=255, blank=True)
 
    start_date = models.DateField(null=True, blank=True,
        help_text="Earliest date this meeting type accepts bookings (blank = immediately).")
    end_date   = models.DateField(null=True, blank=True,
        help_text="Latest date this meeting type accepts bookings (blank = no expiry).")
 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    def save(self, *args, **kwargs):
        if not self.host_user:
            self.host_user = self.created_by
        if self.is_public and not self.shareable_link:
            from django.conf import settings as django_settings
            base_url = "http://localhost:8000" if django_settings.DEBUG else "https://teammanager.ng"
            self.shareable_link = f"{base_url}/bookings/book/{self.uuid}/"
        super().save(*args, **kwargs)
        if self.created_by and self.created_by not in self.managers.all():
            self.managers.add(self.created_by)
        if self.host_user and self.host_user not in self.managers.all():
            self.managers.add(self.host_user)
 
    @property
    def public_url(self):
        return self.shareable_link if self.is_public else None
 
    @property
    def effective_max_capacity(self):
        if not self.is_multiple:
            return 1
        return self.max_capacity  # None → unlimited
 
    def get_shareable_link(self):
        if self.is_public and not self.shareable_link:
            from django.conf import settings as django_settings
            base_url = "http://localhost:8000" if django_settings.DEBUG else "https://teammanager.ng"
            self.shareable_link = f"{base_url}/bookings/book/{self.uuid}/"
        return self.shareable_link
 
    def is_personal(self):
        return self.created_by is not None and self.tenant is None
 
    def clean(self):
        if not self.is_multiple and self.max_capacity and self.max_capacity > 1:
            raise ValidationError({
                "max_capacity": "Maximum capacity > 1 only makes sense when multiple bookings are allowed."
            })
        if self.is_multiple and self.max_capacity == 1:
            self.is_multiple = False
 
    def __str__(self):
        owner = self.created_by.username if self.created_by else f"Org {self.tenant}"
        return f"{self.name} ({self.duration_minutes} min) – {owner}"
 
 
# ─────────────────────────────────────────────────────────────────────────────
# BookingTypeSchedule  (NEW — replaces AvailabilityRule)
# ─────────────────────────────────────────────────────────────────────────────
class BookingTypeSchedule(models.Model):
    """
    One recurring weekly time window for a BookingType.
 
    Multiple rows per BookingType are allowed, and multiple rows for the
    same weekday are allowed (e.g. Mon 09:00–12:00 AND Mon 14:00–17:00).
 
    buffer_before_minutes / buffer_after_minutes shrink the bookable window
    inside this slot (same semantics as the old AvailabilityRule).
    """
 
    WEEKDAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]
 
    booking_type = models.ForeignKey(
        BookingType, on_delete=models.CASCADE, related_name='schedules'
    )
    weekday    = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField(help_text="Local time (interpreted in the timezone below)")
    end_time   = models.TimeField()
    timezone   = models.CharField(
        max_length=100, default='Africa/Lagos', choices=TIMEZONE_CHOICES,
        help_text="IANA timezone for this window"
    )
 
    buffer_before_minutes = models.PositiveSmallIntegerField(
        default=0, help_text="Minutes blocked before each bookable slot in this window"
    )
    buffer_after_minutes = models.PositiveSmallIntegerField(
        default=0, help_text="Minutes blocked after each bookable slot in this window"
    )
    is_active = models.BooleanField(default=True)
 
    class Meta:
        ordering = ['weekday', 'start_time']
        # Allow the same day to have multiple windows, but not exact duplicates
        constraints = [
            models.UniqueConstraint(
                fields=['booking_type', 'weekday', 'start_time', 'end_time'],
                name='unique_schedule_window_per_booking_type',
            )
        ]
 
    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("Start time must be before end time.")
        total_buffer = self.buffer_before_minutes + self.buffer_after_minutes
        from datetime import datetime, date
        if self.start_time and self.end_time:
            window_minutes = (
                datetime.combine(date.today(), self.end_time) -
                datetime.combine(date.today(), self.start_time)
            ).seconds // 60
            if total_buffer >= window_minutes:
                raise ValidationError(
                    "Combined buffers must be smaller than the window duration."
                )
 
    def __str__(self):
        return (
            f"{self.booking_type.name} — "
            f"{self.get_weekday_display()} "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M} "
            f"({self.timezone})"
        )

class Booking(models.Model):
    """
    Represents an individual booking/attendee for an Event.
    - Supports registered users or guests.
    - One Event can have multiple Bookings (up to BookingType.max_capacity).
    """
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('pending', 'Pending confirmation'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No-show'),
    ]

    ATTENDANCE_MODE_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='bookings')
    booking_type = models.ForeignKey('BookingType', on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='my_bookings')
    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    attendance_mode = models.CharField(max_length=20, default='online', choices=ATTENDANCE_MODE_CHOICES)

    payment = models.OneToOneField('Payment', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='booking_payment')
    amount_paid   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, default='not_required',
                                      choices=Event.PAYMENT_STATUS_CHOICES)  # Reuse from Event if possible

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [
            ('event', 'user'),
            ('event', 'email')
        ]  # Prevent duplicate bookings by same user (if registered)

    def __str__(self):
        attendee = self.user.username if self.user else self.email or self.name
        return f"Booking for {attendee} in {self.event.title}"

class WorkHistory(models.Model):
    """Represents an individual's work history"""
    MODE_CHOICES = [
        ('full_time', 'Full Time'),
        ("remote", "Remote"),
        ("contract", "Contract"),
        ("other", "Other"),
    ]
    staff_profile = models.ForeignKey("StaffProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="work_history")
    user_profile  = models.ForeignKey("UserProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="work_history")
    organization_name = models.CharField(max_length=200)
    designation       = models.CharField(max_length=120)
    start_date        = models.DateField()
    end_date          = models.DateField(null=True, blank=True)
    mode              = models.CharField(max_length=40, choices=MODE_CHOICES)
    description       = models.TextField(blank=True)

    class Meta: ordering = ["-start_date"]

    def __str__(self):
        return f"{self.designation} at {self.organization_name}"

class PromotionHistory(models.Model):
    """Represents an individual's promotion history"""
    staff_profile = models.ForeignKey("StaffProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="promotion_history")
    organization_name = models.CharField(max_length=200)
    designation       = models.CharField(max_length=120)
    start_date        = models.DateField()
    end_date          = models.DateField(null=True, blank=True)
    description       = models.TextField(blank=True)
    promotion_letter = models.FileField(upload_to="promotion_letters/", null=True, blank=True)
    department = models.ForeignKey("Department", on_delete=models.SET_NULL, null=True, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    team = models.ForeignKey("Team", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta: ordering = ["-start_date"]

    def __str__(self):
        return f"{self.designation} at {self.organization_name}"

class EducationHistory(models.Model):
    """Represents an individual's education history"""
    staff_profile = models.ForeignKey("StaffProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="education_history")
    user_profile  = models.ForeignKey("UserProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="education_history")
    school_name = models.CharField(max_length=200)
    course = models.CharField(max_length=200)
    degree           = models.CharField(max_length=120)
    start_date       = models.DateField()
    end_date         = models.DateField(null=True, blank=True)
    certificate = models.FileField(upload_to="certificates/", null=True, blank=True)

    class Meta: ordering = ["-start_date"]

    def __str__(self):
        return f"{self.degree} at {self.school_name}"


class IdentityDocument(models.Model):
    """Represents an individual's identity document"""
    DOCUMENT_TYPES = [
        ("nin", "NIN"),
        ("passport", "International Passport"),
        ("drivers", "Driver's License"),
        ("voters", "Voter's Card"),
        ("other", "Other"),
    ]
    staff_profile = models.ForeignKey("StaffProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="identity_documents")
    user_profile  = models.ForeignKey("UserProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="identity_documents")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    number = models.CharField(max_length=200)
    file = models.FileField(upload_to="identity_documents/", null=True, blank=True)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    
    class Meta: ordering = ["-issue_date"]
    
    def __str__(self):
        return f"{self.document_type} - {self.number}"


class Achievement(models.Model):
    """Represents an individual's achievement"""
    CATEGORIES = [
        ("award", "Award"),
        ("testimonial", "Testimonial"),
        ("publication", "Publication"),
        ("license", "License"),
        ("certification", "Certification"),
        ("other", "Other"),
    ]
    staff_profile = models.ForeignKey("StaffProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="achievements")
    user_profile  = models.ForeignKey("UserProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="achievements")
    company_profile = models.ForeignKey("CompanyProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="achievements")
    category = models.CharField(max_length=40, choices=CATEGORIES)
    title = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField()
    file = models.FileField(upload_to="achievements/", null=True, blank=True)
    url = models.URLField(blank=True)
    
    class Meta: ordering = ["-date"]
    
    def __str__(self):
        return f"{self.category} - {self.title}"

class Recommendation(models.Model):
    """A recommendation/reference written by one user about another user or staff member."""

    # Subject of the recommendation (one of these must be set)
    staff_profile = models.ForeignKey(
        "StaffProfile", null=True, blank=True, on_delete=models.CASCADE,
        related_name="recommendations"
    )
    user_profile = models.ForeignKey(
        "UserProfile", null=True, blank=True, on_delete=models.CASCADE,
        related_name="recommendations"
    )

    # Optional: link the recommendation to a specific work or education entry
    work_history = models.ForeignKey(
        "WorkHistory", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recommendations"
    )
    education_history = models.ForeignKey(
        "EducationHistory", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recommendations"
    )

    # The person writing the recommendation
    recommender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="given_recommendations"
    )

    # Content
    relationship = models.CharField(
        max_length=100,
        help_text="e.g. 'Direct Manager', 'Colleague', 'Professor'"
    )
    body = models.TextField(help_text="The recommendation text")
    created_at = models.DateTimeField(auto_now_add=True)
    is_visible = models.BooleanField(
        default=True,
        help_text="Subject can hide a recommendation from their profile"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.staff_profile or self.user_profile
        return f"Rec by {self.recommender} for {target}"


class CompanyProductService(models.Model):

    """Represents a company's product or service"""
    company_profile = models.ForeignKey("CompanyProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="products_services")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount_offered = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_sold = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    icon = models.ImageField(upload_to="products_services_icons/", null=True, blank=True)
    is_top = models.BooleanField(default=False)
    
    

class CompanyTeamHighlight(models.Model):
    """Represents a company's team highlight"""
    company_profile = models.ForeignKey("CompanyProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="team_highlights")
    staff_profile = models.ForeignKey("StaffProfile",
         null=True, blank=True, on_delete=models.CASCADE,
         related_name="team_highlights")
    display_order = models.PositiveIntegerField(default=0)
    custom_title = models.CharField(max_length=200, blank=True)
    
    class Meta:
        ordering = ["display_order"]
        unique_together = [("company_profile", "staff_profile")]
    
    def __str__(self):
        return f"{self.staff_profile.user_profile.first_name} {self.staff_profile.user_profile.last_name} - {self.company_profile.company_name}"