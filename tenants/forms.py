# tenants/forms.py
from django import forms
from .models import TenantApplication, Tenant, CompanyGroup, Subscription, SubscriptionType, Credit, Promo
from documents.models import CustomUser
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal



class TenantApplicationForm(forms.ModelForm):
    first_name = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    phone_number = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = TenantApplication
        fields = ['email', 'password', 'confirm_password', 'organization_name', 'slug']

    # def clean_username(self):
    #     username = self.cleaned_data['username']
    #     if CustomUser.objects.filter(username=username).exists():
    #         raise forms.ValidationError("This username is already taken.")
    #     return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean_organization_name(self):
        name = self.cleaned_data['organization_name']
        if TenantApplication.objects.filter(organization_name=name).exists() or Tenant.objects.filter(name=name).exists():
            raise forms.ValidationError("This organization name is already in use.")
        return name

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if TenantApplication.objects.filter(slug=slug).exists() or Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("This slug is already in use.")
        if "_" in slug:
            raise forms.ValidationError("Slug cannot contain underscores. Use hyphens instead.")
        if slug.isnumeric():
            raise forms.ValidationError("Slug cannot be numeric. Start with a letter.")
        if len(slug) > 20:
            raise forms.ValidationError("Slug must be under 20 characters.")
        return slug.lower()

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        self.phone_number = cleaned_data['phone_number']
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        if not self.phone_number:
            raise forms.ValidationError("Please Enter Phone Number")
        return cleaned_data
    

class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['name', 'slug', 'admin']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'admin': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['admin'].queryset = CustomUser.objects.filter(roles__name='Admin')




class GroupOwnerTenantCreationForm(forms.Form):
    organization_name = forms.CharField(
        max_length=255, 
        label="Company Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter company name'})
    )
    slug = forms.SlugField(
        max_length=50, 
        label="URL Slug",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'company-name'})
    )
    email = forms.EmailField(
        label="Admin Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'admin@company.com'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter password'}),
        label="Admin Password"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'}),
        label="Confirm Password"
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean_organization_name(self):
        name = self.cleaned_data.get('organization_name')
        # Check both TenantApplication and Tenant tables
        from tenants.models import TenantApplication, Tenant
        if TenantApplication.objects.filter(organization_name=name).exists():
            raise forms.ValidationError("An application with this organization name already exists.")
        if Tenant.objects.filter(name=name).exists():
            raise forms.ValidationError("A company with this name already exists.")
        return name

    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        # Check both TenantApplication and Tenant tables
        from tenants.models import TenantApplication, Tenant
        if TenantApplication.objects.filter(slug=slug).exists():
            raise forms.ValidationError("An application with this slug already exists.")
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A company with this slug already exists.")
        if "_" in slug:
            raise forms.ValidationError("Slug cannot contain underscores. Use hyphens instead.")
        if slug.isnumeric():
            raise forms.ValidationError("Slug cannot be numeric. Start with a letter.")
        if len(slug) > 20:
            raise forms.ValidationError("Slug must be under 20 characters.")
        return slug.lower()

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

# class CompanyGroupForm(forms.ModelForm):
#     class Meta:
#         model = CompanyGroup
#         fields = ['name', 'slug']

class CompanyGroupForm(forms.ModelForm):
    class Meta:
        model = CompanyGroup
        fields = ['name', 'slug']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter group name',
                'required': True
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Auto-generated or custom slug'
            }),
        }
        labels = {
            'name': 'Group Name',
            'slug': 'URL Slug',
        }
        help_texts = {
            'name': 'Enter a descriptive name for this oversight group',
            'slug': 'Used in URLs. Will be auto-generated if left blank.',
        }
    
    def clean_slug(self):
        slug = self.cleaned_data.get('slug')
        name = self.cleaned_data.get('name')
        
        # If slug is empty, generate from name
        if not slug and name:
            slug = slugify(name)
        
        # Ensure slug is unique
        if CompanyGroup.objects.filter(slug=slug).exists():
            if not self.instance.pk:  # Only check for new objects
                raise forms.ValidationError(f"A group with slug '{slug}' already exists.")
        
        return slug
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Auto-generate slug if not set
        if not instance.slug and instance.name:
            instance.slug = slugify(instance.name)
            
        if commit:
            instance.save()
            self.save_m2m()
            
        return instance


class CompanyGroupAdminForm(forms.ModelForm):
    class Meta:
        model = CompanyGroup
        fields = ['name', 'slug', 'owner', 'members', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'owner': forms.Select(attrs={'class': 'form-control'}),
            'members': forms.SelectMultiple(attrs={'class': 'form-control', 'disabled': 'disabled'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show all users for owner selection
        self.fields['owner'].queryset = CustomUser.objects.all()
        # Show all tenants for member selection (but disabled)
        self.fields['members'].queryset = Tenant.objects.all().order_by('name')
        self.fields['members'].required = False
        
    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            # Don't save the members field - we handle it separately
            if 'members' in self.cleaned_data:
                # We'll handle members through the add/remove forms
                pass
        return instance
    
class AddCompanyGroupMemberForm(forms.Form):
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.none(),  # Will be set in __init__
        label="Select Tenant",
        help_text="Choose a tenant to add to the group",
        widget=forms.Select(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Search for a tenant...'
        })
    )
    
    
    def __init__(self, *args, **kwargs):
        self.company_group = kwargs.pop('company_group', None)
        super().__init__(*args, **kwargs)
        
        # Filter tenants that are NOT already members
        if self.company_group:
            existing_member_ids = self.company_group.members.values_list('id', flat=True)
            self.fields['tenant'].queryset = Tenant.objects.exclude(
                id__in=existing_member_ids
            ).filter(is_active=True).order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        tenant = cleaned_data.get('tenant')
        
        if self.company_group and tenant:
            if self.company_group.members.filter(id=tenant.id).exists():
                raise ValidationError(f"{tenant.name} is already a member of this group.")
        
        return cleaned_data
    
    def save(self, commit=True):
        tenant = self.cleaned_data['tenant']
        
        if not self.company_group:
            raise ValueError("Company group must be provided")
        
        self.company_group.members.add(tenant)
        

class EditCompanyGroupMemberForm(forms.Form):
    is_active = forms.BooleanField(
        required=False,
        label="Active in Group",
        help_text="Is this tenant active in the group?",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        self.company_group = kwargs.pop('company_group', None)
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
    
    def save(self, commit=True):
        if not (self.company_group and self.tenant):
            raise ValueError("Company group and tenant must be provided")

class RemoveCompanyGroupMemberForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="I confirm I want to remove this member",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def __init__(self, *args, **kwargs):
        self.company_group = kwargs.pop('company_group', None)
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        confirm = cleaned_data.get('confirm')
        
        if not confirm:
            raise ValidationError("You must confirm removal.")
        
        return cleaned_data
    
    def save(self, commit=True):
        if not (self.company_group and self.tenant):
            raise ValueError("Company group and tenant must be provided")
        
        if commit:
            self.company_group.members.remove(self.tenant)
        
        return True

class BulkAddCompanyGroupMemberForm(forms.Form):
    tenants = forms.ModelMultipleChoiceField(
        queryset=Tenant.objects.none(),
        label="Select Tenants",
        help_text="Hold Ctrl/Cmd to select multiple tenants",
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select multiple tenants...',
            'style': 'height: 200px;'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.company_group = kwargs.pop('company_group', None)
        super().__init__(*args, **kwargs)
        
        # Filter tenants that are NOT already members
        if self.company_group:
            existing_member_ids = self.company_group.members.values_list('id', flat=True)
            self.fields['tenants'].queryset = Tenant.objects.exclude(
                id__in=existing_member_ids
            ).filter(is_active=True).order_by('name')
    
    def save(self, commit=True):
        tenants = self.cleaned_data['tenants']
        role = self.cleaned_data.get('role', '')
        
        if not self.company_group:
            raise ValueError("Company group must be provided")
        
        added_count = 0
        for tenant in tenants:
            self.company_group.members.add(tenant)
            added_count += 1
            
            try:
                through_model = self.company_group.members.through
                membership = through_model.objects.get(
                    companygroup=self.company_group,
                    tenant=tenant
                )
                
                if role and hasattr(membership, 'role'):
                    membership.role = role
                    membership.save()
                    
            except (AttributeError, through_model.DoesNotExist):
                continue
        
        return added_count


# Search form for filtering members
class MemberSearchForm(forms.Form):
    """
    Form for searching/filtering members in a company group.
    """
    search = forms.CharField(
        required=False,
        max_length=100,
        label="Search",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by tenant name...'
        })
    )
    
    is_active = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'All Status'),
            ('true', 'Active Only'),
            ('false', 'Inactive Only')
        ],
        label="Status",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    role = forms.CharField(
        required=False,
        max_length=50,
        label="Role",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by role...'
        })
    )
    
    def filter_queryset(self, queryset):
        """Apply filters to the queryset."""
        if not self.is_valid():
            return queryset
        
        search = self.cleaned_data.get('search')
        is_active = self.cleaned_data.get('is_active')
        role = self.cleaned_data.get('role')
        
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        if is_active:
            queryset = queryset.filter(is_active=(is_active == 'true'))
        
        return queryset
    

class SubscriptionTypeForm(forms.ModelForm):
    """Form for creating/editing subscription plans"""
    
    class Meta:
        model = SubscriptionType
        fields = ['name', 'price', 'duration', 'discount_percentage', 'is_active', 'description', 'max_users']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'discount_percentage': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'duration': forms.NumberInput(attrs={'min': '1'}),
            'max_users': forms.NumberInput(attrs={'min': '1'}),
        }
    
    def clean_discount_percentage(self):
        discount = self.cleaned_data.get('discount_percentage')
        if discount < 0 or discount > 100:
            raise forms.ValidationError("Discount percentage must be between 0 and 100")
        return discount
    
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price <= 0:
            raise forms.ValidationError("Price must be greater than 0")
        return price


class SubscriptionForm(forms.ModelForm):
    """Form for creating/editing subscriptions"""
    
    promo_code = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'placeholder': 'Enter promo code'}))
    
    # Add duration months field
    duration_months = forms.ChoiceField(
        choices=[(i, f"{i} month{'s' if i > 1 else ''}") for i in range(1, 25)],
        initial=1,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Subscription Duration"
    )
    
    # New field for user selection
    selected_users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
        label="Select Users"
    )
    
    class Meta:
        model = Subscription
        fields = ['tenant', 'user', 'plan', 'duration_months', 'user_scope',
                  'promo_code', 'auto_renew', 'selected_users']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'user_scope': forms.RadioSelect(choices=Subscription.USER_SCOPE_CHOICES),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        # Only show active plans
        self.fields['plan'].queryset = SubscriptionType.objects.filter(is_active=True)

        if 'duration_months' in self.fields:
            # If it's a ChoiceField, set the choices
            if isinstance(self.fields['duration_months'], forms.ChoiceField):
                self.fields['duration_months'].choices = [(i, f"{i} month{'s' if i > 1 else ''}") for i in range(1, 25)]
            
        # Add price display for different durations
        if self.fields['plan'].queryset.exists():
            self.fields['duration_months'].help_text = self._get_duration_help_text()
        
        # Configure user selection queryset
        if self.request:
            if self.request.user.is_superuser:
                self.fields['selected_users'].queryset = CustomUser.objects.filter(is_superuser=False)
            elif hasattr(self.request.user, 'tenant') and self.request.user.tenant:
                self.fields['selected_users'].queryset = CustomUser.objects.filter(
                    tenant=self.request.user.tenant,
                    is_superuser=False
                )
                self.fields['tenant'].queryset = Tenant.objects.filter(id=self.request.user.tenant.id)
                self.fields['tenant'].initial = self.request.user.tenant
                self.fields['tenant'].disabled = True
                self.fields['user'].widget = forms.HiddenInput()
            else:
                self.fields['user'].initial = self.request.user
                self.fields['user'].disabled = True
                self.fields['tenant'].widget = forms.HiddenInput()
        
        # Set initial selected users if editing OR if we have POST data
        if self.data and 'selected_users' in self.data:
            # If we have POST data, get the selected user IDs from the POST data
            selected_ids = self.data.getlist('selected_users')
            if selected_ids and selected_ids[0]:
                # Handle comma-separated values
                if len(selected_ids) == 1 and ',' in selected_ids[0]:
                    selected_ids = selected_ids[0].split(',')
                # Filter out empty strings and convert to int
                selected_ids = [int(uid) for uid in selected_ids if uid and uid.isdigit()]
                if selected_ids:
                    self.fields['selected_users'].initial = CustomUser.objects.filter(id__in=selected_ids)
        elif self.instance and self.instance.pk and self.instance.user_scope == 'selected':
            self.fields['selected_users'].initial = self.instance.covered_users.all()
    
    def _get_duration_help_text(self):
        """Generate help text showing prices for different durations"""
        plan = self.fields['plan'].queryset.first()
        if plan:
            monthly_price = plan.get_effective_price()
            return f"Monthly price: ₦{monthly_price:,.2f}. Save with longer durations!"
        return "Select subscription duration"
    
    def clean(self):
        cleaned_data = super().clean()
        tenant = cleaned_data.get('tenant')
        user = cleaned_data.get('user')
        plan = cleaned_data.get('plan')
        promo = cleaned_data.get('promo_code')
        user_scope = cleaned_data.get('user_scope')
        duration_months = cleaned_data.get('duration_months', 1)

        if duration_months:
            try:
                duration_months = int(duration_months)
            except (ValueError, TypeError):
                duration_months = 1
        else:
            duration_months = 1
        
        # Get selected_users from POST data
        selected_users_ids = self.data.getlist('selected_users')
        
        # If we got a single value with commas, split it
        if selected_users_ids and len(selected_users_ids) == 1 and ',' in selected_users_ids[0]:
            selected_users_ids = selected_users_ids[0].split(',')
        
        # Filter out empty strings and convert to integers
        selected_users_ids = [uid for uid in selected_users_ids if uid and uid.strip()]
        
        # Get actual user objects if we have IDs
        selected_users = []
        if selected_users_ids:
            try:
                # Convert to integers
                int_ids = []
                for uid in selected_users_ids:
                    if uid.strip().isdigit():
                        int_ids.append(int(uid))
                if int_ids:
                    selected_users = CustomUser.objects.filter(id__in=int_ids)
            except (ValueError, TypeError):
                pass
        
        # Validate tenant/user
        if not tenant and not user:
            raise forms.ValidationError("Either tenant or user must be selected")
        duration_months = cleaned_data.get('duration_months', 1)
        try:
            duration_months = int(duration_months)
            if duration_months < 1 or duration_months > 24:
                raise forms.ValidationError("Duration must be between 1 and 24 months")
            cleaned_data['duration_months'] = duration_months
        except (ValueError, TypeError):
            raise forms.ValidationError("Duration must be a valid number")
        # # Validate duration
        # if duration_months and (duration_months < 1 or duration_months > 24):
        #     raise forms.ValidationError("Duration must be between 1 and 24 months")
        
        # Validate user scope for tenant subscriptions
        if tenant and user_scope == 'selected':
            if not selected_users:
                raise forms.ValidationError("Please select at least one user when choosing 'Selected Users'")
            
            # Check if selected users belong to the tenant
            for selected_user in selected_users:
                if selected_user.tenant != tenant:
                    raise forms.ValidationError(f"User {selected_user.email} does not belong to this tenant")
            
            # Check plan user limits for new subscriptions
            if plan and plan.max_users and selected_users.count() > plan.max_users:
                raise forms.ValidationError(
                    f"Selected users count ({selected_users.count()}) exceeds plan maximum ({plan.max_users})"
                )
            
            # Store selected users in cleaned_data for use in save
            cleaned_data['selected_users_objects'] = selected_users
        
        # Store promo in cleaned_data for use in save
        if promo and hasattr(promo, 'code'):
            cleaned_data['validated_promo'] = promo
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set start_date to today if not provided
        if not instance.start_date:
            instance.start_date = timezone.now().date()
        
        # Set duration_months from form
        # instance.duration_months = self.cleaned_data.get('duration_months', 1)
        duration_months = self.cleaned_data.get('duration_months', 1)
        try:
            instance.duration_months = int(duration_months)
        except (ValueError, TypeError):
            instance.duration_months = 1
        
        # Calculate end date based on duration_months
        if instance.start_date and instance.duration_months:
            instance.end_date = instance.start_date + timedelta(days=30 * instance.duration_months)
        
        # Set created_by if user is authenticated
        if self.request and self.request.user.is_authenticated:
            instance.created_by = self.request.user
        
        # Handle promo code
        promo = self.cleaned_data.get('validated_promo')
        if promo:
            instance.promo = promo
            instance.promo_code = promo.code
            
            if promo.discount_type == 'percentage':
                instance.promo_code_discount = promo.discount_value
            elif promo.discount_type == 'full':
                instance.promo_code_discount = 100
            
            promo.increment_usage()
        
        if commit:
            # Save the subscription first
            instance.save()
            
            # Then add the selected users (for new subscriptions)
            if instance.tenant and instance.user_scope == 'selected':
                selected_users = self.cleaned_data.get('selected_users_objects', [])
                if selected_users:
                    instance.covered_users.set(selected_users)
            elif instance.tenant and instance.user_scope == 'all':
                instance.covered_users.clear()
        
        return instance

class SubscriptionAdjustmentForm(forms.Form):
    """Form for manually adjusting subscription user counts"""
    
    ACTION_CHOICES = [
        ('add', 'Add Users'),
        ('remove', 'Remove Users'),
    ]
    
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    user_count = forms.IntegerField(min_value=1, help_text="New total user count")
    reason = forms.CharField(widget=forms.Textarea, required=False)
    
    def clean_user_count(self):
        count = self.cleaned_data['user_count']
        if count < 1:
            raise forms.ValidationError("User count must be at least 1")
        return count

class CreditApplyForm(forms.Form):
    """Form for applying credits to subscription"""
    
    credit = forms.ModelChoiceField(queryset=None, empty_label="Select credit to apply")
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    
    def __init__(self, *args, **kwargs):
        subscription = kwargs.pop('subscription')
        super().__init__(*args, **kwargs)
        
        # Only show available credits for this tenant
        self.fields['credit'].queryset = Credit.objects.filter(
            tenant=subscription.tenant,
            remaining_amount__gt=0
        )
    
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        credit = self.cleaned_data.get('credit')
        
        if credit and amount > credit.remaining_amount:
            raise forms.ValidationError(f"Amount cannot exceed remaining credit (${credit.remaining_amount})")
        
        return amount



class PromoForm(forms.ModelForm):
    """Form for creating/editing promo codes"""
    
    class Meta:
        model = Promo
        fields = [
            'code', 'discount_type', 'discount_value', 
            'start_date', 'end_date', 'duration_days',
            'max_uses', 'is_active', 'description',
            'applicable_plans', 'applicable_tenants', 'applicable_users'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'applicable_plans': forms.SelectMultiple(attrs={'class': 'select2'}),
            'applicable_tenants': forms.SelectMultiple(attrs={'class': 'select2'}),
            'applicable_users': forms.SelectMultiple(attrs={'class': 'select2'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['applicable_plans'].queryset = SubscriptionType.objects.all()
        self.fields['applicable_tenants'].queryset = Tenant.objects.all()
        self.fields['applicable_users'].queryset = CustomUser.objects.all()
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date must be after start date")
        
        return cleaned_data
    
    def clean_code(self):
        code = self.cleaned_data['code'].upper().strip()
        if Promo.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A promo code with this name already exists")
        return code

class PromoApplyForm(forms.Form):
    """Form for applying promo code during subscription"""
    promo_code = forms.CharField(max_length=50, required=False)
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.tenant = kwargs.pop('tenant', None)
        self.plan = kwargs.pop('plan', None)
        super().__init__(*args, **kwargs)
    
    def clean_promo_code(self):
        code = self.cleaned_data.get('promo_code')
        if not code:
            return None
        
        try:
            promo = Promo.objects.get(code__iexact=code, is_active=True)
        except Promo.DoesNotExist:
            raise forms.ValidationError("Invalid promo code")
        
        # Validate promo
        is_valid, message = promo.is_valid(
            user=self.user,
            tenant=self.tenant,
            plan=self.plan
        )
        
        if not is_valid:
            raise forms.ValidationError(message)
        
        return promo