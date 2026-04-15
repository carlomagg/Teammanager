# documents/kyc_forms.py
from django import forms
from django.contrib.contenttypes.models import ContentType
from .kyc_models import UserKYC, StaffKYC, CompanyKYB, CompanyDirector
from .kyc_field_approval_models import FieldApprovalStatus
from .models import UserProfile, StaffProfile, CompanyProfile, Department


class PartialResubmissionMixin:
    """Mixin to handle partial resubmission - only enable rejected fields"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If this is an existing instance, check for rejected fields
        if self.instance and self.instance.pk:
            self.setup_partial_resubmission()
    
    def setup_partial_resubmission(self):
        """Disable all fields except rejected ones"""
        content_type = ContentType.objects.get_for_model(self.instance)
        
        # Get all field approvals for this instance
        field_approvals = FieldApprovalStatus.objects.filter(
            content_type=content_type,
            object_id=self.instance.pk
        )
        
        # Create a dict of field statuses
        field_statuses = {fa.field_name: fa.status for fa in field_approvals}
        
        # Disable approved fields, enable rejected/resubmitted fields
        for field_name, field in self.fields.items():
            status = field_statuses.get(field_name, 'pending')
            
            if status == 'approved':
                # Disable approved fields
                field.disabled = True
                field.widget.attrs['readonly'] = True
                field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' bg-light'
                field.help_text = '✓ This field has been approved and cannot be edited.'
            elif status == 'rejected':
                # Highlight rejected fields that need resubmission
                field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' border-danger'
                field.help_text = f'⚠️ This field was rejected. Please update and resubmit. {field.help_text or ""}'
            elif status == 'resubmitted':
                # Highlight resubmitted fields
                field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' border-info'
                field.help_text = f'↻ This field has been resubmitted and is awaiting review. {field.help_text or ""}'
    
    def save(self, commit=True):
        """Mark rejected fields as resubmitted when saved"""
        instance = super().save(commit=False)
        
        # Check if this is a new submission
        is_new_submission = not instance.pk
        
        if commit:
            instance.save()
            
            # Track if any fields were resubmitted
            has_resubmissions = False
            
            # Mark changed rejected fields as resubmitted
            if instance.pk and not is_new_submission:
                content_type = ContentType.objects.get_for_model(instance)
                
                for field_name in self.changed_data:
                    try:
                        field_approval = FieldApprovalStatus.objects.get(
                            content_type=content_type,
                            object_id=instance.pk,
                            field_name=field_name
                        )
                        
                        # If field was rejected and now changed, mark as resubmitted
                        if field_approval.status == 'rejected':
                            field_approval.mark_resubmitted()
                            has_resubmissions = True
                    except FieldApprovalStatus.DoesNotExist:
                        pass
                
                # Send notification to admins if there were resubmissions
                if has_resubmissions:
                    self.notify_admins_of_resubmission(instance)
            
            # Send notification for new submissions
            if is_new_submission:
                self.notify_admins_of_new_submission(instance)
        
        return instance
    
    def notify_admins_of_new_submission(self, instance):
        """Send notification to admins when a new KYC/KYB is submitted"""
        from documents.models import Notification, UserNotification, CustomUser
        from django.urls import reverse
        
        # Determine notification details based on instance type
        model_name = instance.__class__.__name__
        tenant = None
        review_link = None
        
        if model_name == 'UserKYC':
            notification_title = f"New User KYC Submitted: {instance.user_profile.get_full_name()}"
            review_link = reverse('review_user_kyc', kwargs={'kyc_id': instance.pk})
            # Personal KYC - notify superusers
        elif model_name == 'StaffKYC':
            notification_title = f"New Staff KYC Submitted: {instance.staff_profile.get_full_name()}"
            tenant = instance.staff_profile.tenant
            review_link = reverse('review_staff_kyc', kwargs={'kyc_id': instance.pk})
        elif model_name == 'CompanyKYB':
            notification_title = f"New Company KYB Submitted: {instance.company_profile.company_name}"
            tenant = instance.company_profile.tenant
            review_link = reverse('review_company_kyb', kwargs={'kyb_id': instance.pk})
        else:
            return
        
        try:
            # Create notification
            notification = Notification.objects.create(
                tenant=tenant,
                title=notification_title,
                message=f"A new {model_name.replace('KYC', 'KYC').replace('KYB', 'KYB')} submission requires your review and approval.",
                type=Notification.NotificationType.INFO,
                is_active=True,
                link=review_link
            )
            
            # Notify admins
            if tenant:
                # Notify tenant admins
                admins = CustomUser.objects.filter(
                    tenant=tenant,
                    roles__name='Admin',
                    is_active=True
                )
            else:
                # Notify superusers for personal KYC
                admins = CustomUser.objects.filter(is_superuser=True, is_active=True)
            
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=tenant,
                    notification=notification,
                    dismissed=False
                )
        except Exception as e:
            print(f"Failed to send new submission notification: {e}")
    
    def notify_admins_of_resubmission(self, instance):
        """Send notification to admins when fields are resubmitted"""
        from documents.models import Notification, UserNotification, CustomUser
        from django.urls import reverse
        
        # Determine notification details based on instance type
        model_name = instance.__class__.__name__
        tenant = None
        review_link = None
        
        if model_name == 'UserKYC':
            notification_title = f"User KYC Resubmitted: {instance.user_profile.get_full_name()}"
            review_link = reverse('review_user_kyc', kwargs={'kyc_id': instance.pk})
            # Personal KYC - notify superusers
        elif model_name == 'StaffKYC':
            notification_title = f"Staff KYC Resubmitted: {instance.staff_profile.get_full_name()}"
            tenant = instance.staff_profile.tenant
            review_link = reverse('review_staff_kyc', kwargs={'kyc_id': instance.pk})
        elif model_name == 'CompanyKYB':
            notification_title = f"Company KYB Resubmitted: {instance.company_profile.company_name}"
            tenant = instance.company_profile.tenant
            review_link = reverse('review_company_kyb', kwargs={'kyb_id': instance.pk})
        else:
            return
        
        try:
            # Create notification
            notification = Notification.objects.create(
                tenant=tenant,
                title=notification_title,
                message=f"Rejected fields have been updated and resubmitted. Please review the changes.",
                type=Notification.NotificationType.INFO,
                is_active=True,
                link=review_link
            )
            
            # Notify admins
            if tenant:
                # Notify tenant admins
                admins = CustomUser.objects.filter(
                    tenant=tenant,
                    roles__name='Admin',
                    is_active=True
                )
            else:
                # Notify superusers for personal KYC
                admins = CustomUser.objects.filter(is_superuser=True, is_active=True)
            
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=tenant,
                    notification=notification,
                    dismissed=False
                )
        except Exception as e:
            print(f"Failed to send resubmission notification: {e}")


class UserProfileUpdateForm(forms.ModelForm):
    """Embedded form for updating missing UserProfile fields"""
    
    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'phone_number', 'date_of_birth', 'home_address', 'designation']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'home_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Address'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Designation/Title'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show fields that are missing
        if self.instance and self.instance.pk:
            for field_name in self.fields:
                field_value = getattr(self.instance, field_name, None)
                if field_value:
                    # Hide field if already filled
                    self.fields[field_name].widget = forms.HiddenInput()
                    self.fields[field_name].required = False


class UserKYCForm(PartialResubmissionMixin, forms.ModelForm):
    """Form for individual KYC completion"""
    
    # Profile update fields (prefixed to avoid conflicts)
    profile_first_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    profile_last_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))
    profile_phone_number = forms.CharField(max_length=15, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}))
    profile_date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    profile_home_address = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Address'}))
    profile_designation = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Designation/Title'}))
    
    class Meta:
        model = UserKYC
        fields = [
            'nin', 'bvn', 'id_type', 'id_number',
            'id_front_file', 'id_back_file', 'utility_bill_file',
            'next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'next_of_kin_address'
        ]
        widgets = {
            'nin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901', 'maxlength': '11'}),
            'bvn': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901', 'maxlength': '11'}),
            'id_type': forms.Select(attrs={'class': 'form-control'}),
            'id_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter ID number'}),
            'id_front_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'id_back_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'utility_bill_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'next_of_kin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'next_of_kin_relationship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spouse, Sibling, Parent'}),
            'next_of_kin_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}),
            'next_of_kin_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Next of Kin Address'}),
        }
        help_texts = {
            'nin': 'Enter your 11-digit National Identification Number',
            'bvn': 'Enter your 11-digit Bank Verification Number',
            'id_front_file': 'Upload front of your ID (Max 5MB)',
            'id_back_file': 'Upload back of your ID if applicable (Max 5MB)',
            'utility_bill_file': 'Upload recent utility bill or bank statement not older than 3 months (Max 5MB)',
        }
    
    def __init__(self, *args, **kwargs):
        self.user_profile = kwargs.pop('user_profile', None)
        super().__init__(*args, **kwargs)
        
        # Pre-populate and hide profile fields that are already filled
        if self.user_profile:
            profile_fields = {
                'profile_first_name': 'first_name',
                'profile_last_name': 'last_name',
                'profile_phone_number': 'phone_number',
                'profile_date_of_birth': 'date_of_birth',
                'profile_home_address': 'home_address',
                'profile_designation': 'designation',
            }
            
            for form_field, profile_field in profile_fields.items():
                value = getattr(self.user_profile, profile_field, None)
                if value:
                    self.fields[form_field].widget = forms.HiddenInput()
                    self.fields[form_field].initial = value
                else:
                    self.fields[form_field].initial = value
    
    def get_missing_profile_fields(self):
        """Return list of missing profile fields for display"""
        if not self.user_profile:
            return []
        
        missing = []
        field_labels = {
            'first_name': 'Full Name',
            'last_name': 'Last Name',
            'phone_number': 'Phone',
            'date_of_birth': 'Date of Birth',
            'home_address': 'Address',
            'designation': 'Designation',
        }
        
        for field, label in field_labels.items():
            if not getattr(self.user_profile, field, None):
                missing.append(label)
        
        return missing
    
    def clean_nin(self):
        nin = self.cleaned_data.get('nin')
        if nin and len(nin) != 11:
            raise forms.ValidationError("NIN must be exactly 11 digits")
        if nin and not nin.isdigit():
            raise forms.ValidationError("NIN must contain only digits")
        return nin
    
    def clean_bvn(self):
        bvn = self.cleaned_data.get('bvn')
        if bvn and len(bvn) != 11:
            raise forms.ValidationError("BVN must be exactly 11 digits")
        if bvn and not bvn.isdigit():
            raise forms.ValidationError("BVN must contain only digits")
        return bvn
    
    def clean(self):
        cleaned_data = super().clean()
        nin = cleaned_data.get('nin')
        bvn = cleaned_data.get('bvn')
        
        if not nin and not bvn:
            raise forms.ValidationError("Please provide at least NIN or BVN")
        
        # File size validation
        for field_name in ['id_front_file', 'id_back_file', 'utility_bill_file']:
            file = cleaned_data.get(field_name)
            if file and file.size > 5 * 1024 * 1024:  # 5MB
                self.add_error(field_name, "File size must be under 5MB")
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save KYC and update profile if needed"""
        # First, update the profile before saving KYC
        if self.user_profile:
            profile_updated = False
            profile_fields = {
                'profile_first_name': 'first_name',
                'profile_last_name': 'last_name',
                'profile_phone_number': 'phone_number',
                'profile_date_of_birth': 'date_of_birth',
                'profile_home_address': 'home_address',
                'profile_designation': 'designation',
            }
            
            for form_field, profile_field in profile_fields.items():
                value = self.cleaned_data.get(form_field)
                current_value = getattr(self.user_profile, profile_field, None)
                
                # Update if value provided and field is currently empty
                if value and not current_value:
                    setattr(self.user_profile, profile_field, value)
                    profile_updated = True
                    print(f"Updating {profile_field}: {value}")  # Debug log
            
            if profile_updated:
                self.user_profile.save()
                print(f"Profile updated successfully for user: {self.user_profile.user.username}")  # Debug log
            else:
                print("No profile fields to update")  # Debug log
        
        # Now save the KYC instance through the mixin
        instance = super().save(commit=commit)
        return instance


class StaffKYCForm(PartialResubmissionMixin, forms.ModelForm):
    """Form for staff KYC completion"""
    
    # Profile update fields (prefixed to avoid conflicts)
    profile_first_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    profile_last_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))
    profile_phone_number = forms.CharField(max_length=15, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}))
    profile_date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    profile_home_address = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Address'}))
    profile_department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    profile_designation = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Designation/Title'}))
    
    class Meta:
        model = StaffKYC
        fields = [
            'nin', 'bvn', 'id_type', 'id_number',
            'id_front_file', 'id_back_file', 'utility_bill_file',
            'next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'next_of_kin_address'
        ]
        widgets = {
            'nin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901', 'maxlength': '11'}),
            'bvn': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901', 'maxlength': '11'}),
            'id_type': forms.Select(attrs={'class': 'form-control'}),
            'id_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter ID number'}),
            'id_front_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'id_back_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'utility_bill_file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'next_of_kin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'next_of_kin_relationship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spouse, Sibling, Parent'}),
            'next_of_kin_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}),
            'next_of_kin_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Next of Kin Address'}),
        }
        help_texts = {
            'nin': 'Enter your 11-digit National Identification Number',
            'bvn': 'Enter your 11-digit Bank Verification Number',
            'id_front_file': 'Upload front of your ID (Max 5MB)',
            'id_back_file': 'Upload back of your ID if applicable (Max 5MB)',
            'utility_bill_file': 'Upload recent utility bill or bank statement not older than 3 months (Max 5MB)',
        }
    
    def __init__(self, *args, **kwargs):
        self.staff_profile = kwargs.pop('staff_profile', None)
        super().__init__(*args, **kwargs)
        
        # Set department queryset based on tenant
        if self.staff_profile and self.staff_profile.tenant:
            self.fields['profile_department'].queryset = Department.objects.filter(tenant=self.staff_profile.tenant)
        
        # Pre-populate and hide profile fields that are already filled
        if self.staff_profile:
            profile_fields = {
                'profile_first_name': 'first_name',
                'profile_last_name': 'last_name',
                'profile_phone_number': 'phone_number',
                'profile_date_of_birth': 'date_of_birth',
                'profile_home_address': 'home_address',
                'profile_department': 'department',
                'profile_designation': 'designation',
            }
            
            for form_field, profile_field in profile_fields.items():
                value = getattr(self.staff_profile, profile_field, None)
                if value:
                    self.fields[form_field].widget = forms.HiddenInput()
                    self.fields[form_field].initial = value
                else:
                    self.fields[form_field].initial = value
    
    def get_missing_profile_fields(self):
        """Return list of missing profile fields for display"""
        if not self.staff_profile:
            return []
        
        missing = []
        field_labels = {
            'first_name': 'Full Name',
            'last_name': 'Last Name',
            'phone_number': 'Phone',
            'date_of_birth': 'Date of Birth',
            'home_address': 'Address',
            'department': 'Department',
            'designation': 'Designation',
        }
        
        for field, label in field_labels.items():
            if not getattr(self.staff_profile, field, None):
                missing.append(label)
        
        return missing
    
    def clean_nin(self):
        nin = self.cleaned_data.get('nin')
        if nin and len(nin) != 11:
            raise forms.ValidationError("NIN must be exactly 11 digits")
        if nin and not nin.isdigit():
            raise forms.ValidationError("NIN must contain only digits")
        return nin
    
    def clean_bvn(self):
        bvn = self.cleaned_data.get('bvn')
        if bvn and len(bvn) != 11:
            raise forms.ValidationError("BVN must be exactly 11 digits")
        if bvn and not bvn.isdigit():
            raise forms.ValidationError("BVN must contain only digits")
        return bvn
    
    def clean(self):
        cleaned_data = super().clean()
        nin = cleaned_data.get('nin')
        bvn = cleaned_data.get('bvn')
        
        if not nin and not bvn:
            raise forms.ValidationError("Please provide at least NIN or BVN")
        
        # File size validation
        for field_name in ['id_front_file', 'id_back_file', 'utility_bill_file']:
            file = cleaned_data.get(field_name)
            if file and file.size > 5 * 1024 * 1024:  # 5MB
                self.add_error(field_name, "File size must be under 5MB")
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save KYC and update profile if needed"""
        # First, update the profile before saving KYC
        if self.staff_profile:
            profile_updated = False
            profile_fields = {
                'profile_first_name': 'first_name',
                'profile_last_name': 'last_name',
                'profile_phone_number': 'phone_number',
                'profile_date_of_birth': 'date_of_birth',
                'profile_home_address': 'home_address',
                'profile_department': 'department',
                'profile_designation': 'designation',
            }
            
            for form_field, profile_field in profile_fields.items():
                value = self.cleaned_data.get(form_field)
                current_value = getattr(self.staff_profile, profile_field, None)
                
                # Update if value provided and field is currently empty
                if value and not current_value:
                    setattr(self.staff_profile, profile_field, value)
                    profile_updated = True
                    print(f"Updating {profile_field}: {value}")  # Debug log
            
            if profile_updated:
                self.staff_profile.save()
                print(f"Profile updated successfully for staff: {self.staff_profile.user.username}")  # Debug log
            else:
                print("No profile fields to update")  # Debug log
        
        # Now save the KYC instance through the mixin
        instance = super().save(commit=commit)
        return instance


class CompanyKYBForm(PartialResubmissionMixin, forms.ModelForm):
    """Form for company KYB completion"""
    
    # Profile update fields (prefixed to avoid conflicts)
    profile_company_name = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company Name'}))
    profile_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'company@example.com'}))
    profile_address = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Company Address'}))
    profile_contact_details = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Phone, Email, etc.'}))
    
    class Meta:
        model = CompanyKYB
        fields = [
            'rc_number', 'tin', 'cac_certificate_file', 'memart_file',
            'status_report_file', 'scuml_certificate_file', 'utility_bill_file'
        ]
        widgets = {
            'rc_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter RC Number'}),
            'tin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter TIN'}),
            'cac_certificate_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'memart_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'status_report_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'scuml_certificate_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
            'utility_bill_file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,image/*'}),
        }
        help_texts = {
            'rc_number': 'Business Registration Number (RC Number)',
            'tin': 'Tax Identification Number',
            'cac_certificate_file': 'CAC Certificate of Incorporation (Max 10MB)',
            'memart_file': 'Memorandum & Articles of Association (Max 10MB)',
            'status_report_file': 'CAC Status Report / Form CAC 1.1 (Max 10MB)',
            'scuml_certificate_file': 'SCUML Certificate if applicable (Max 10MB)',
            'utility_bill_file': 'Utility bill or bank statement not older than 3 months (Max 10MB)',
        }
    
    def __init__(self, *args, **kwargs):
        self.company_profile = kwargs.pop('company_profile', None)
        super().__init__(*args, **kwargs)
        
        # Pre-populate and hide profile fields that are already filled
        if self.company_profile:
            profile_fields = {
                'profile_company_name': 'company_name',
                'profile_email': 'email',
                'profile_address': 'address',
                'profile_contact_details': 'contact_details',
            }
            
            for form_field, profile_field in profile_fields.items():
                value = getattr(self.company_profile, profile_field, None)
                if value:
                    self.fields[form_field].widget = forms.HiddenInput()
                    self.fields[form_field].initial = value
                else:
                    self.fields[form_field].initial = value
    
    def get_missing_profile_fields(self):
        """Return list of missing profile fields for display"""
        if not self.company_profile:
            return []
        
        missing = []
        field_labels = {
            'company_name': 'Company Name',
            'email': 'Email',
            'address': 'Address',
            'contact_details': 'Contact Details',
        }
        
        for field, label in field_labels.items():
            if not getattr(self.company_profile, field, None):
                missing.append(label)
        
        return missing
    
    def clean(self):
        cleaned_data = super().clean()
        
        # File size validation (10MB for business documents)
        for field_name in ['cac_certificate_file', 'memart_file', 'status_report_file', 
                          'scuml_certificate_file', 'utility_bill_file']:
            file = cleaned_data.get(field_name)
            if file and file.size > 10 * 1024 * 1024:  # 10MB
                self.add_error(field_name, "File size must be under 10MB")
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save KYB and update profile if needed"""
        # First, update the profile before saving KYB
        if self.company_profile:
            profile_updated = False
            profile_fields = {
                'profile_company_name': 'company_name',
                'profile_email': 'email',
                'profile_address': 'address',
                'profile_contact_details': 'contact_details',
            }
            
            for form_field, profile_field in profile_fields.items():
                value = self.cleaned_data.get(form_field)
                current_value = getattr(self.company_profile, profile_field, None)
                
                # Update if value provided and field is currently empty
                if value and not current_value:
                    setattr(self.company_profile, profile_field, value)
                    profile_updated = True
                    print(f"Updating {profile_field}: {value}")  # Debug log
            
            if profile_updated:
                self.company_profile.save()
                print(f"Profile updated successfully for company: {self.company_profile.company_name}")  # Debug log
            else:
                print("No profile fields to update")  # Debug log
        
        # Now save the KYB instance through the mixin
        instance = super().save(commit=commit)
        return instance


class CompanyDirectorForm(forms.ModelForm):
    """Form for adding company directors"""
    
    class Meta:
        model = CompanyDirector
        fields = [
            'first_name', 'last_name', 'email', 'phone', 'address',
            'designation', 'nin', 'bvn', 'id_type', 'id_front',
            'id_back', 'photo', 'percentage_ownership',
            'next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'next_of_kin_address'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Residential Address'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Director, CEO, Proprietor'}),
            'nin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901', 'maxlength': '11'}),
            'bvn': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678901', 'maxlength': '11'}),
            'id_type': forms.Select(attrs={'class': 'form-control'}),
            'id_front': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'id_back': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'percentage_ownership': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01', 'min': '0', 'max': '100'}),
            'next_of_kin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'next_of_kin_relationship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Spouse, Sibling, Parent'}),
            'next_of_kin_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234...'}),
            'next_of_kin_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Next of Kin Address'}),
        }
        help_texts = {
            'nin': 'Enter 11-digit National Identification Number',
            'bvn': 'Enter 11-digit Bank Verification Number',
            'percentage_ownership': 'Percentage ownership (for beneficial owners)',
        }
    
    def clean_nin(self):
        nin = self.cleaned_data.get('nin')
        if nin and len(nin) != 11:
            raise forms.ValidationError("NIN must be exactly 11 digits")
        if nin and not nin.isdigit():
            raise forms.ValidationError("NIN must contain only digits")
        return nin
    
    def clean_bvn(self):
        bvn = self.cleaned_data.get('bvn')
        if bvn and len(bvn) != 11:
            raise forms.ValidationError("BVN must be exactly 11 digits")
        if bvn and not bvn.isdigit():
            raise forms.ValidationError("BVN must contain only digits")
        return bvn
    
    def clean_percentage_ownership(self):
        percentage = self.cleaned_data.get('percentage_ownership')
        if percentage and (percentage < 0 or percentage > 100):
            raise forms.ValidationError("Percentage must be between 0 and 100")
        return percentage
    
    def clean(self):
        cleaned_data = super().clean()
        nin = cleaned_data.get('nin')
        bvn = cleaned_data.get('bvn')
        
        if not nin and not bvn:
            raise forms.ValidationError("Please provide at least NIN or BVN for the director")
        
        # File size validation
        for field_name in ['id_front', 'id_back', 'photo']:
            file = cleaned_data.get(field_name)
            if file and file.size > 5 * 1024 * 1024:  # 5MB
                self.add_error(field_name, "File size must be under 5MB")
        
        return cleaned_data


# Formset for multiple directors
from django.forms import formset_factory

CompanyDirectorFormSet = formset_factory(CompanyDirectorForm, extra=1, max_num=10, can_delete=True)
