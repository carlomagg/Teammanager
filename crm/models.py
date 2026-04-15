from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from tenants.models import Tenant
from django_countries.fields import CountryField
from decimal import Decimal


class CRMQuerySet(models.QuerySet):
    def get_assigned_or_all(self, user, tenant):
        """
        Filter CRM objects based on user context.
        - Tenant users: see all company data
        - Personal users: see only their created data
        """
        if tenant:
            return self.filter(tenant=tenant)
        return self.filter(tenant=None, created_by=user)


class CRMManager(models.Manager):
    def get_queryset(self):
        return CRMQuerySet(self.model, using=self._db)
    
    def get_assigned_or_all(self, user, tenant):
        return self.get_queryset().get_assigned_or_all(user, tenant)


class Product(models.Model):
    """
    Products or services offered by the company.
    Can be linked to opportunities.
    """
    CATEGORY_CHOICES = [
        ('software', 'Software'),
        ('hardware', 'Hardware'),
        ('service', 'Service'),
        ('consulting', 'Consulting'),
        ('training', 'Training'),
        ('support', 'Support'),
        ('other', 'Other'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, blank=True)
    unit_price = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)]
    )
    is_active = models.BooleanField(default=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='created_products'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_products'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = CRMManager()
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['tenant', 'category']),
        ]
    
    def __str__(self):
        return self.name


class Pipeline(models.Model):
    """
    Named pipeline container for stages.
    Tenants can have multiple pipelines (e.g., "New Business", "Renewals").
    Personal users can create their own pipelines.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Null for personal/user-owned pipelines"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_pipelines'
    )
    name = models.CharField(max_length=150)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = CRMManager()

    class Meta:
        constraints = [
            # Company pipelines: unique name within the same tenant
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                condition=models.Q(tenant__isnull=False),
                name='unique_pipeline_name_per_tenant'
            ),
            # Personal pipelines: unique name per user (when tenant is null)
            models.UniqueConstraint(
                fields=['created_by', 'name'],
                condition=models.Q(tenant__isnull=True),
                name='unique_personal_pipeline_name'
            ),
            # Only one default pipeline per tenant
            models.UniqueConstraint(
                fields=['tenant'],
                condition=models.Q(is_default=True, tenant__isnull=False),
                name='unique_default_pipeline_per_tenant'
            ),
            # Only one default pipeline per personal user
            models.UniqueConstraint(
                fields=['created_by'],
                condition=models.Q(is_default=True, tenant__isnull=True),
                name='unique_default_pipeline_per_user'
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'name']),
            models.Index(fields=['created_by', 'name']),
            models.Index(fields=['tenant', 'is_default']),
            models.Index(fields=['created_by', 'is_default']),
        ]
        ordering = ['name']

    def __str__(self):
        if self.tenant:
            return f"{self.name} (Tenant: {self.tenant})"
        return f"{self.name} (Personal: {self.created_by})"

    def clean(self):
        if self.tenant and self.created_by:
            if self.created_by.tenant != self.tenant:
                raise ValidationError("Pipeline creator must belong to the selected tenant.")
        if not self.tenant:
            if not self.created_by or not self.created_by.is_personal:
                raise ValidationError("Personal pipelines can only be created by is_personal=True users.")


class PipelineStageQuerySet(models.QuerySet):
    def get_assigned_or_all(self, user, tenant):
        """
        Filter pipeline stages based on user context through pipeline relationship.
        - Tenant users: see all stages from tenant pipelines
        - Personal users: see only stages from their created pipelines
        """
        if tenant:
            return self.filter(pipeline__tenant=tenant)
        return self.filter(pipeline__tenant=None, pipeline__created_by=user)


class PipelineStageManager(models.Manager):
    def get_queryset(self):
        return PipelineStageQuerySet(self.model, using=self._db)
    
    def get_assigned_or_all(self, user, tenant):
        return self.get_queryset().get_assigned_or_all(user, tenant)


class PipelineStage(models.Model):
    """
    Pipeline stages categorized by opportunity type.
    Each category (Lead, Deal, Customer) has its own set of stages.
    """
    CATEGORY_CHOICES = [
        ('Lead', 'Lead'),
        ('Deal', 'Deal'),
        ('Customer', 'Customer'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField()
    is_terminal = models.BooleanField(
        default=False,
        help_text="Terminal stages like Closed Won, Closed Lost, Lost Customer"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='created_pipeline_stages'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_pipeline_stages'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = PipelineStageManager()
    
    class Meta:
        ordering = ['category', 'order']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'category', 'order'],
                name='unique_stage_order_per_category'
            ),
            models.UniqueConstraint(
                fields=['tenant', 'category', 'name'],
                name='unique_stage_name_per_category'
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'category', 'order']),
        ]
    
    def __str__(self):
        return f"{self.category} - {self.name}"


class Opportunity(models.Model):
    """
    Central CRM entity representing leads, deals, and customers.
    Replaces the old Account, Lead, and Deal models.
    """
    CATEGORY_CHOICES = [
        ('Lead', 'Lead'),
        ('Deal', 'Deal'),
        ('Customer', 'Customer'),
    ]
    
    COMPANY_TYPE_CHOICES = [
        ('Private', 'Private'),
        ('NGO', 'NGO'),
        ('Government/Public', 'Government/Public'),
    ]
    
    DEAL_TYPE_CHOICES = [
        ('New Deal', 'New Deal'),
        ('Expansion', 'Expansion'),
        ('Renewal', 'Renewal'),
    ]
    
    INDUSTRY_CHOICES = [
        ('technology', 'Technology'),
        ('finance', 'Finance'),
        ('healthcare', 'Healthcare'),
        ('education', 'Education'),
        ('manufacturing', 'Manufacturing'),
        ('retail', 'Retail'),
        ('consulting', 'Consulting'),
        ('agriculture', 'Agriculture'),
        ('energy', 'Energy'),
        ('telecommunications', 'Telecommunications'),
        ('other', 'Other'),
    ]
    
    DELIVERY_METHOD_CHOICES = [
        ('By Company', 'By Company'),
        ('Through Consultant', 'Through Consultant'),
        ('Through Partner', 'Through Partner / 3rd Party'),
    ]
    
    RECURRING_REVENUE_CHOICES = [
        ('None', 'None'),
        ('Monthly', 'Monthly'),
        ('Yearly', 'Yearly'),
    ]
    
    SOURCE_CHOICES = [
        ('Customer Call', 'Customer Call'),
        ('Event', 'Event'),
        ('Direct Outreach', 'Direct Outreach'),
        ('Referral', 'Referral'),
        ('Other', 'Other'),
    ]
    
    DEAL_SIZE_CHOICES = [
        ('Small', 'Small'),
        ('Medium', 'Medium'),
        ('Large', 'Large'),
    ]
    
    COMPANY_SIZE_CHOICES = [
        ('Startup', 'Startup'),
        ('SMB', 'SMB'),
        ('SMB Large', 'SMB Large'),
        ('Enterprise', 'Enterprise'),
        ('Large Enterprise', 'Large Enterprise'),
    ]
    
    # Core
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Company Information
    company_name = models.CharField(max_length=255, blank=True)
    company_type = models.CharField(max_length=50, choices=COMPANY_TYPE_CHOICES, blank=True)
    company_size = models.CharField(max_length=20, choices=COMPANY_SIZE_CHOICES, blank=True)
    company_website = models.URLField(blank=True)
    industry = models.CharField(max_length=50, choices=INDUSTRY_CHOICES, blank=True)
    
    # Company Address
    country = CountryField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    
    # Customer Contact Person
    contact = models.ForeignKey(
        'documents.Contact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='opportunities'
    )
    contact_first_name = models.CharField(max_length=100, blank=True)
    contact_last_name = models.CharField(max_length=100, blank=True)
    contact_title = models.CharField(max_length=100, blank=True, help_text="e.g., CTO, Manager")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    
    # Deal Classification
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Lead')
    deal_type = models.CharField(max_length=20, choices=DEAL_TYPE_CHOICES, blank=True)
    
    # Products/Services
    products = models.ManyToManyField(Product, blank=True, related_name='opportunities')
    product_details = models.TextField(
        blank=True,
        help_text="Explanation of services to be delivered"
    )
    
    # Method of Delivery
    delivery_method = models.CharField(max_length=50, choices=DELIVERY_METHOD_CHOICES, blank=True)
    partner_contact = models.ForeignKey(
        'documents.Contact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='partner_opportunities'
    )
    partner_org_name = models.CharField(max_length=255, blank=True)
    partner_contact_name = models.CharField(max_length=255, blank=True)
    partner_phone = models.CharField(max_length=20, blank=True)
    partner_email = models.EmailField(blank=True)
    partner_address = models.TextField(blank=True)
    
    # Contractor Information (similar to partner)
    contractor_contact = models.ForeignKey(
        'documents.Contact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contractor_opportunities'
    )
    contractor_org_name = models.CharField(max_length=255, blank=True)
    contractor_contact_name = models.CharField(max_length=255, blank=True)
    contractor_phone = models.CharField(max_length=20, blank=True)
    contractor_email = models.EmailField(blank=True)
    contractor_address = models.TextField(blank=True)
    
    # Deal Value
    deal_size = models.CharField(
        max_length=10, 
        choices=DEAL_SIZE_CHOICES, 
        blank=True,
        editable=False,
        help_text="Auto-calculated based on estimated amount"
    )
    estimated_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    actual_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)]
    )
    
    # Recurring Revenue
    recurring_revenue = models.CharField(
        max_length=20, 
        choices=RECURRING_REVENUE_CHOICES, 
        default='None',
        blank=True
    )
    
    # Timeline
    expected_close_date = models.DateField(null=True, blank=True)
    contract_expiry_date = models.DateField(
        null=True, 
        blank=True,
        help_text="Contract/subscription expiry date for renewal tracking"
    )
    
    # Deal Source
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, blank=True)
    referrer_name = models.CharField(max_length=255, blank=True)
    referrer_phone = models.CharField(max_length=20, blank=True)
    referrer_email = models.EmailField(blank=True)
    referrer_address = models.TextField(blank=True)
    
    # Competition
    is_competitive = models.BooleanField(default=False)
    competitor_names = models.TextField(
        blank=True,
        help_text="List competitor names, separated by commas"
    )
    
    # Assignment & Stage
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_opportunities'
    )
    stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='opportunities'
    )
    
    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='created_opportunities'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_opportunities'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = CRMManager()
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Opportunities'
        indexes = [
            models.Index(fields=['tenant', 'category']),
            models.Index(fields=['tenant', 'stage']),
            models.Index(fields=['tenant', 'assigned_to']),
            models.Index(fields=['tenant', 'expected_close_date']),
            models.Index(fields=['tenant', 'company_name']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.company_name or 'No Company'}"
    
    def clean(self):
        """Validate partner fields when delivery method is Through Partner"""
        if self.delivery_method == 'Through Partner':
            if not self.partner_contact and not (
                self.partner_org_name and self.partner_contact_name and 
                self.partner_email and self.partner_phone
            ):
                raise ValidationError(
                    "Partner information is required when delivery method is 'Through Partner'. "
                    "Either select an existing partner contact or fill in all partner details."
                )


class Activity(models.Model):
    """
    Tracks activities (tasks, calls, emails, meetings) linked to CRM objects.
    Uses GenericForeignKey to link to any CRM entity (primarily Opportunity).
    """
    ACTIVITY_TYPE_CHOICES = [
        ('task', 'Task'),
        ('call', 'Call'),
        ('email', 'Email'),
        ('meeting', 'Meeting'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPE_CHOICES)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_activities'
    )
    
    # GenericForeignKey to link to Opportunity or Contact
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='created_activities'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_activities'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = CRMManager()
    
    class Meta:
        ordering = ['due_date']
        verbose_name_plural = 'Activities'
        indexes = [
            models.Index(fields=['tenant', 'assigned_to', 'completed']),
            models.Index(fields=['tenant', 'due_date']),
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"{self.get_activity_type_display()}: {self.subject}"
    
    def mark_complete(self):
        """Mark activity as completed"""
        self.completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['completed', 'completed_at', 'updated_at'])
