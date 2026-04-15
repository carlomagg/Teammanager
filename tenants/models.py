from decimal import Decimal
from functools import cached_property
from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.apps import apps
import logging

logger = logging.getLogger(__name__)


# class SuperUser(AbstractUser):
#     pass

class TenantApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    username = models.CharField(max_length=150, unique=True, help_text="Required. Letters, digits and @/./+/-/_ only.")
    email = models.EmailField(unique=True, help_text="Enter a valid email address.")
    password = models.CharField(max_length=255)
    organization_name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, help_text="Short name used in the URL. Can only contain lowercase letters, numbers and hyphens.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization_name} ({self.status})"

class Tenant(models.Model):
    SUB_STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'documents.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tenants'
    )
    admin = models.ForeignKey(
        'documents.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_tenants'
    )
    is_verified = models.BooleanField(default=False)
    num_users = models.PositiveIntegerField(default=0)
    subscription_plan = models.ForeignKey("tenants.SubscriptionType", on_delete=models.SET_NULL, null=True, blank=True, default=None)
    subscription_status = models.CharField(max_length=20, choices=SUB_STATUS_CHOICES, default='inactive')
    
    # Payroll security
    payroll_password_hash = models.CharField(max_length=128, blank=True, null=True, help_text="Hashed password for payroll payment actions")

    def __str__(self):
        return self.name
    
    @cached_property
    def has_unremitted_remittance(self):
        """Check if tenant has any pending remittances"""
        # Use the string reference to avoid circular import
        from documents.models import Remittance
        return Remittance.objects.filter(
            tenant=self,
            status__in=['pending', 'processing', 'failed']
        ).exists()
    
    @cached_property
    def pending_remittances(self):
        """Get pending remittances for this tenant"""
        # Use the string reference to avoid circular import
        from documents.models import Remittance
        return Remittance.objects.filter(
            tenant=self,
            status__in=['pending', 'processing', 'failed']
        )
    

    @property
    def company_name(self):
        """Get company name from profile or fall back to tenant name"""
        profile = self.company_profile
        if profile and profile.company_name:
            return profile.company_name
        return self.name
    
    @property
    def has_public_bookings(self):
        """Check if tenant has any public organization booking services"""
        return self.bookingtype_set.filter(booking_for='organization', is_public=True).exists()
    
    @property
    def bank_details_provided(self):
        """Check if bank details are provided"""
        profile = self.company_profile
        if not profile:
            return False
        return all([
            profile.bank_name,
            profile.bank_account_name,
            profile.bank_account_number
        ])
    
    def get_active_subscription(self):
        """Get active subscription for this tenant"""
        return self.subscriptions.filter(status='active').first()
    
    def get_user_count(self):
        """Get current user count for this tenant"""
        from documents.models import CustomUser
        return CustomUser.objects.filter(tenant=self).count()
        
    
    
class SubscriptionType(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.PositiveIntegerField()
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    max_users = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum users allowed (null = unlimited)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        discount_text = f" ({self.discount_percentage}% off)" if self.discount_percentage > 0 else ""
        return f"{self.name} - N{self.price} for {self.duration} days{discount_text}"
    
    
    def get_effective_price(self):
        """
        Get price after applying any discounts
        """
        price = self.price
        if self.discount_percentage > 0:
            price = price * (1 - self.discount_percentage / 100)
        return price



class Subscription(models.Model):
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'), 
        ('cancelled', 'Cancelled'),  
        ('pending', 'Pending'),
        ('suspended', 'Suspended'),
        ('revoked', 'Revoked'),
    ]

    BILLING_CYCLE_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom'),
    ]
    
    # New field to track which users are covered by this subscription
    USER_SCOPE_CHOICES = [
        ('selected', 'Selected Users'),
        ('all', 'All Users'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='subscriptions')
    user = models.ForeignKey('documents.CustomUser', on_delete=models.CASCADE, null=True, blank=True, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionType, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(choices=STATUS_CHOICES, default='pending', max_length=50)
    billing_cycle = models.CharField(choices=BILLING_CYCLE_CHOICES, default='monthly', max_length=50)

    duration_months = models.PositiveIntegerField(
        default=1,
        help_text="Number of months for this subscription (1-24)"
    )
    
    # New fields for user scope
    user_scope = models.CharField(max_length=20, choices=USER_SCOPE_CHOICES, default='all')
    covered_users = models.ManyToManyField('documents.CustomUser', blank=True, related_name='covered_subscriptions')
    
    trial_end_date = models.DateField(null=True, blank=True)
    discount_applied = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True)
    promo = models.ForeignKey('tenants.Promo', on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    promo_code = models.CharField(max_length=50, null=True, blank=True)
    promo_code_discount = models.DecimalField(max_digits=5, decimal_places=2, default=0, null=True, blank=True)
    
    start_date = models.DateField()
    end_date = models.DateField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Updated user count fields to reflect covered users
    current_user_count = models.PositiveIntegerField(default=1)
    next_billing_user_count = models.PositiveIntegerField(default=1)
    last_user_count_updated_at = models.DateTimeField(null=True, blank=True)
    
    auto_renew = models.BooleanField(default=False)
    grace_period_end = models.DateField(null=True, blank=True)
    is_free = models.BooleanField(default=False, help_text="Mark as free subscription (no payment required)")
    free_reason = models.CharField(max_length=100, blank=True, null=True, 
                                   help_text="Reason for free subscription (e.g., beta tester, staff, promotional)")
    free_approved_by = models.ForeignKey('documents.CustomUser', on_delete=models.SET_NULL, 
                                         null=True, blank=True, related_name='approved_free_subscriptions')
    free_approved_at = models.DateTimeField(null=True, blank=True)
    free_expires_at = models.DateField(null=True, blank=True, 
                                       help_text="When the free access expires (null = never)")
    
    is_exempt = models.BooleanField(default=False, 
                                   help_text="Completely exempt from subscription requirements")
    exempt_reason = models.CharField(max_length=100, blank=True, null=True)

    created_by = models.ForeignKey('documents.CustomUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_subscriptions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        ordering = ['-created_at']


    def __str__(self):
        if self.user_scope == 'all':
            subscriber = self.tenant or self.user
            return f"{subscriber}'s subscription: {self.plan.name} (All Users)"
        else:
            return f"{self.tenant}'s subscription: {self.plan.name} ({self.covered_users.count()} users)"

    def get_covered_users(self):
        """Get all users covered by this subscription"""
        # Get the CustomUser model dynamically to avoid circular imports
        CustomUser = apps.get_model('documents', 'CustomUser')
        
        if self.user_scope == 'all' and self.tenant:
            # Return all non-superuser users in the tenant
            return CustomUser.objects.filter(tenant=self.tenant, is_superuser=False)
        elif self.user_scope == 'selected':
            return self.covered_users.all()
        elif self.user:
            return CustomUser.objects.filter(id=self.user.id)
        return CustomUser.objects.none()
    
    def get_covered_user_count_safe(self):
        """Safely get covered user count without causing recursion"""
        try:
            if self.user_scope == 'all' and self.tenant:
                from django.apps import apps
                CustomUser = apps.get_model('documents', 'CustomUser')
                return CustomUser.objects.filter(tenant=self.tenant, is_superuser=False).count()
            elif self.user_scope == 'selected':
                return self.covered_users.count()
            elif self.user:
                return 1
            return 0
        except Exception as e:
            logger.error(f"Error in get_covered_user_count_safe for subscription {self.id}: {e}")
            return 0
        
    def get_total_price(self):
        """Get total price for the entire subscription duration"""
        monthly_price = self.plan.get_effective_price()
        user_count = self.get_covered_user_count()
        total = monthly_price * user_count * (self.duration_months or 1)
        
        # Apply discounts
        if self.promo:
            total = self.promo.apply_discount(total)
        
        return total

    def get_monthly_equivalent(self):
        """Get monthly equivalent price (total / months)"""
        total = self.get_total_price()
        months = self.duration_months or 1
        return total / months

    def get_savings_percentage(self):
        """Calculate savings percentage compared to monthly billing"""
        if self.duration_months <= 1:
            return 0
        
        monthly_total = self.plan.get_effective_price() * self.get_covered_user_count()
        current_monthly_equivalent = self.get_monthly_equivalent()
        
        if monthly_total > 0:
            savings = ((monthly_total - current_monthly_equivalent) / monthly_total) * 100
            return round(savings, 1)
        return 0    
    
    def update_covered_user_status(self):
        """Update subscription status for all covered users"""
        covered_users = self.get_covered_users()
        
        if self.status == 'active':
            user_status = 'active'
            end_date = self.end_date
        else:
            user_status = 'inactive'
            end_date = None
        
        updated_count = covered_users.update(
            subscription_status=user_status,
            subscription_end_date=end_date,
            subscription_plan=self.plan if self.status == 'active' else None
        )
        
        # logger.info(f"Updated {updated_count} users for subscription {self.id} to {user_status}")
        return updated_count
    
    
    def clean(self):
        """Validate the subscription"""
        from django.core.exceptions import ValidationError
        from django.apps import apps
        
        # Ensure either tenant or user is set (but not both)
        if not self.tenant and not self.user:
            raise ValidationError("Either tenant or user must be set for a subscription")
        if self.tenant and self.user:
            raise ValidationError("Subscription cannot have both tenant and user")
        
        if self.tenant:
            
            if self.plan and self.plan.max_users and self.pk:
                user_count = self.get_covered_user_count_safe()
                if user_count > self.plan.max_users:
                    raise ValidationError(f"Selected users count ({user_count}) exceeds plan maximum ({self.plan.max_users})")
    def get_current_monthly_rate(self):
        """
        Get current monthly rate based on user count
        """
        base_rate = self.plan.get_effective_price() if hasattr(self.plan, 'get_effective_price') else self.plan.price
        
        if self.tenant:
            return base_rate * self.current_user_count
        return base_rate
    
    def get_next_monthly_rate(self):
        """
        Get next month's rate based on projected user count
        """
        base_rate = self.plan.get_effective_price() if hasattr(self.plan, 'get_effective_price') else self.plan.price
        
        if self.tenant:
            return base_rate * self.next_billing_user_count
        return base_rate
    
    def get_covered_user_count(self):
        """Get count of covered users - alias for backward compatibility"""
        return self.get_covered_user_count_safe()
    
    
    def save(self, *args, **kwargs):

        from decimal import Decimal
        from django.utils import timezone
        from calendar import monthrange
        from datetime import date
        
        # Check if this is a new instance
        is_new = self.pk is None

        if self.duration_months:
            try:
                self.duration_months = int(self.duration_months)
            except (ValueError, TypeError):
                self.duration_months = 1

        
        if self.trial_end_date and self.trial_end_date < timezone.now().date():
            self.trial_end_date = None
            
        if not self.start_date:
            self.start_date = timezone.now().date()

        # Calculate end date based on duration_months if not already set
        if not self.end_date and self.start_date:
            if self.promo and self.promo.duration_days:
                self.end_date = self.start_date + timedelta(days=self.promo.duration_days)
            elif self.duration_months:
                duration_months = int(self.duration_months)
                # Calculate end date by adding months manually
                year = self.start_date.year
                month = self.start_date.month + duration_months
                day = self.start_date.day
                
                # Handle year overflow
                while month > 12:
                    month -= 12
                    year += 1
                
                # Handle invalid days (e.g., Jan 31 + 1 month = Feb 31 -> Feb 28/29)
                last_day = monthrange(year, month)[1]
                if day > last_day:
                    day = last_day
                
                self.end_date = date(year, month, day)
            elif self.plan:
                # Fallback to plan duration (backward compatibility)
                self.end_date = self.start_date + timedelta(days=self.plan.duration)

        
        if not self.discount_applied and self.plan and self.plan.discount_percentage > 0:
            self.discount_applied = self.plan.discount_percentage
        
        # Update user counts - only for existing subscriptions
        if self.tenant and not is_new:
            self.current_user_count = self.get_covered_user_count()
            self.next_billing_user_count = self.current_user_count
        
        if self.end_date and self.end_date < timezone.now().date():
            if self.status == 'active':
                self.status = 'expired'
        
        if self.is_free and self.status == 'pending':
            self.status = 'active'
        
        # Call clean - but for new subscriptions with selected scope, we skip certain validations
        self.clean()
        
        # Save the instance
        super().save(*args, **kwargs)
        
        # Update covered users status after save
        if self.tenant and self.status == 'active':
            self.update_covered_user_status()
    
    def calculate_prorated_amount(self, old_user_count, new_user_count):
        """Calculate prorated amount for user count changes"""
        if old_user_count >= new_user_count:
            return 0
        
        additional_users = new_user_count - old_user_count
        
        days_in_period = (self.end_date - self.start_date).days
        if days_in_period <= 0:
            return 0
        
        daily_rate = self.plan.price / Decimal(days_in_period)
        
        today = timezone.now().date()
        remaining_days = (self.end_date - today).days
        if remaining_days <= 0:
            return 0
        
        total_discount = self.discount_applied + self.promo_code_discount
        discounted_daily_rate = daily_rate * (1 - total_discount/100)
        
        prorated_amount = (discounted_daily_rate * remaining_days) * additional_users
        
        return round(prorated_amount, 2)

    def calculate_prorated_credit(self, old_user_count, new_user_count):
        """Calculate credit for user count decreases"""
        if old_user_count <= new_user_count:
            return 0
        
        removed_users = old_user_count - new_user_count
        
        days_in_period = (self.end_date - self.start_date).days
        if days_in_period <= 0:
            return 0
        
        today = timezone.now().date()
        remaining_days = (self.end_date - today).days
        if remaining_days <= 0:
            return 0
        
        daily_rate = self.plan.price / Decimal(days_in_period)
        total_discount = self.discount_applied + self.promo_code_discount
        discounted_daily_rate = daily_rate * (1 - total_discount/100)
        
        credit_amount = (discounted_daily_rate * remaining_days) * removed_users
        
        return round(credit_amount, 2)
    
    def add_user(self, user):
        """Add a user to this subscription"""
        if self.user_scope == 'selected':
            self.covered_users.add(user)
            self.current_user_count = self.get_covered_user_count()
            self.next_billing_user_count = self.current_user_count
            self.save(update_fields=['current_user_count', 'next_billing_user_count'])
            self.update_covered_user_status()
        elif self.user_scope == 'all':
            # For all users, we don't need to add individually
            # But we should update the user's status if they're now covered
            if self.tenant and user.tenant == self.tenant:
                self.update_covered_user_status()

    def get_duration_display(self):
        """Return human readable duration"""
        if self.duration_months:
            months = self.duration_months
            if months >= 12:
                years = months // 12
                remaining_months = months % 12
                if remaining_months > 0:
                    return f"{years} year{'s' if years > 1 else ''} and {remaining_months} month{'s' if remaining_months > 1 else ''}"
                return f"{years} year{'s' if years > 1 else ''}"
            return f"{months} month{'s' if months > 1 else ''}"
        return "Custom duration"
    
    def remove_user(self, user):
        """Remove a user from this subscription"""
        if self.user_scope == 'selected':
            self.covered_users.remove(user)
            self.current_user_count = self.get_covered_user_count()
            self.next_billing_user_count = self.current_user_count
            self.save(update_fields=['current_user_count', 'next_billing_user_count'])
            self.update_covered_user_status()
    

class Credit(models.Model):
    """Credit model for future billing"""
    # from documents.models import Subscription
    
    CREDIT_TYPE_CHOICES = [
        ('user_removal', 'User Removal Credit'),
        ('plan_downgrade', 'Plan Downgrade Credit'),
        ('promo', 'Promotional Credit'),
        ('refund', 'Refund Credit'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='credits')
    subscription = models.ForeignKey('tenants.Subscription', on_delete=models.CASCADE, related_name='credits')
    credit_type = models.CharField(max_length=30, choices=CREDIT_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    expires_at = models.DateField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'subscription']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"Credit for {self.tenant}: ${self.amount} ({self.credit_type})"
    
    def apply_credit(self, amount):
        """Apply credit to a payment"""
        if amount > self.remaining_amount:
            amount = self.remaining_amount
        
        self.remaining_amount -= amount
        if self.remaining_amount == 0:
            self.applied_at = timezone.now()
        self.save()
        return amount

# class Payment(models.Model):
#     STATUS_CHOICES = [
#         ('pending', 'Pending'),
#         ('success', 'Success'),
#         ('failed', 'Failed'),
#         ('refunded', 'Refunded'),
#     ]

#     tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payments')
#     subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='payments')
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     payment_date = models.DateTimeField(auto_now_add=True)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
#     transaction_id = models.CharField(max_length=100, blank=True, null=True)  # From payment gateway
#     payment_method = models.CharField(max_length=50, blank=True, null=True)  # e.g., 'credit_card', 'paypal'
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

    # def __str__(self):
    #     return f"Payment of {self.amount} for {self.tenant} on {self.payment_date}"


class CompanyGroup(models.Model):
    # User = get_user_model()
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=100, unique=True, help_text="Used in URLs, e.g. lagos-state-2025")
    
    # The 100 (or more) companies under oversight
    members = models.ManyToManyField(
        'tenants.Tenant',
        related_name='company_groups',
        help_text="Tenants that belong to this government oversight group",
        blank=True,
    )

    owner = models.ForeignKey('documents.CustomUser', on_delete=models.SET_NULL, limit_choices_to={'is_personal': True},null=True,blank=True,related_name='owns_company_group')
    
    created_by = models.ForeignKey(
        'documents.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_groups_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Company Oversight Group"
        verbose_name_plural = "Company Oversight Groups"

    def save(self, *args, **kwargs):
        grp_tenant = Tenant.objects.get(slug="group")
        self.tenant = grp_tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.members.count()} companies)"


class Promo(models.Model):
    """Promotional codes for discounts on subscriptions"""
    
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
        ('full', 'Full Access (100% off)'),
    ]
    
    code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Percentage or fixed amount")
    
    # Validity period
    start_date = models.DateField()
    end_date = models.DateField()
    duration_days = models.PositiveIntegerField(
        default=30, 
        help_text="Number of days the subscription lasts when using this promo"
    )
    
    # Usage limits
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum number of times this promo can be used")
    uses = models.PositiveIntegerField(default=0, help_text="Current number of times used")
    
    # Restrictions
    is_active = models.BooleanField(default=True)
    applicable_plans = models.ManyToManyField(
        SubscriptionType, 
        blank=True,
        help_text="Leave empty to apply to all plans"
    )
    applicable_tenants = models.ManyToManyField(
        Tenant, 
        blank=True,
        help_text="Leave empty to apply to all tenants"
    )
    applicable_users = models.ManyToManyField(
        'documents.CustomUser', 
        blank=True,
        help_text="Leave empty to apply to all users"
    )
    
    # Metadata
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('documents.CustomUser', on_delete=models.SET_NULL, null=True, related_name='created_promos')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['code', 'is_active']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        if self.discount_type == 'percentage':
            discount_display = f"{self.discount_value}% off"
        elif self.discount_type == 'fixed':
            discount_display = f"${self.discount_value} off"
        else:
            discount_display = "Full Access"
        return f"{self.code} - {discount_display}"
    
    def is_valid(self, user=None, tenant=None, plan=None):
        """Check if promo is valid for given user/tenant/plan"""
        from django.utils import timezone
        today = timezone.now().date()
        
        # Basic validity checks
        if not self.is_active:
            return False, "Promo code is not active"
        
        if today < self.start_date:
            return False, f"Promo code starts on {self.start_date}"
        
        if today > self.end_date:
            return False, "Promo code has expired"
        
        if self.max_uses and self.uses >= self.max_uses:
            return False, "Promo code usage limit reached"
        
        # Check plan restrictions
        if plan and self.applicable_plans.exists():
            if not self.applicable_plans.filter(id=plan.id).exists():
                return False, "This promo code is not valid for the selected plan"
        
        # Check tenant restrictions
        if tenant and self.applicable_tenants.exists():
            if not self.applicable_tenants.filter(id=tenant.id).exists():
                return False, "This promo code is not valid for your organization"
        
        # Check user restrictions
        if user and self.applicable_users.exists():
            if not self.applicable_users.filter(id=user.id).exists():
                return False, "This promo code is not valid for your account"
        
        return True, "Promo code is valid"
    
    def apply_discount(self, original_price):
        """Calculate discounted price based on promo type"""
        from decimal import Decimal
        
        if self.discount_type == 'percentage':
            discount_amount = original_price * (self.discount_value / Decimal('100'))
            return original_price - discount_amount
        
        elif self.discount_type == 'fixed':
            return max(Decimal('0'), original_price - self.discount_value)
        
        elif self.discount_type == 'full':
            return Decimal('0')
        
        return original_price
    
    def increment_usage(self):
        """Increment the usage count"""
        self.uses += 1
        self.save(update_fields=['uses'])

    
    


class ExternalServiceLink(models.Model):
    """
    External service links that visitors can access without login
    based on the organization's URL
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='external_services',
        help_text="Organization this service belongs to"
    )
    
    name = models.CharField(
        max_length=200,
        help_text="Service name (e.g., 'Book a Meeting', 'Pay Invoice', 'Submit Application')"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Brief description of what this service does"
    )
    
    external_url = models.URLField(
        max_length=500,
        help_text="Full URL to the external service"
    )
    
    icon = models.CharField(
        max_length=100,
        blank=True,
        default='fa-link',
        help_text="Font Awesome icon class (e.g., 'fa-calendar', 'fa-credit-card')"
    )
    
    icon_color = models.CharField(
        max_length=50,
        default='#319795',
        help_text="Hex color code for the icon"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this service is currently available"
    )
    
    open_in_new_tab = models.BooleanField(
        default=True,
        help_text="Open link in a new browser tab"
    )
    
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in which services are displayed (lower numbers first)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'documents.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_external_services'
    )
    
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = 'External Service Link'
        verbose_name_plural = 'External Service Links'
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.tenant.name} - {self.name}"
    
    def get_icon_class(self):
        """Return the full Font Awesome icon class"""
        if self.icon:
            return f"fas {self.icon}"
        return "fas fa-link"
