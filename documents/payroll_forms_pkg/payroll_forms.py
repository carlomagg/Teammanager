"""
Forms for payroll management.
Includes forms for payroll creation, custom field management, and password verification.
"""
from django import forms
from django.core.exceptions import ValidationError
from documents.models import Payroll, PayrollItem, PayrollCustomColumn, PayrollColumnTemplate
from documents.utils.payroll_helpers import verify_payroll_password
from datetime import date


class PayrollCustomFieldForm(forms.ModelForm):
    """
    Form for Admin/HR to define custom payroll columns.
    Examples: Tax, Pension, Loan, Insurance, Bonus
    """
    
    class Meta:
        model = PayrollCustomColumn
        fields = ['name', 'operation', 'order']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Tax, Bonus, Pension'
            }),
            'operation': forms.Select(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0'
            }),
        }
        help_texts = {
            'name': 'Column name (e.g., Tax, Bonus)',
            'operation': 'Add (+) or Subtract (-) from Gross',
            'order': 'Display order (lower numbers appear first)',
        }
    
    def clean_name(self):
        """Ensure name is valid"""
        name = self.cleaned_data.get('name', '').strip()
        
        if not name:
            raise ValidationError("Column name is required")
        
        return name


class PayrollForm(forms.ModelForm):
    """
    Main form for creating/editing payroll batches.
    """
    pin = forms.CharField(
        max_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter 4-6 digit PIN'
        }),
        help_text='PIN for payment authorization',
        required=True
    )
    
    class Meta:
        model = Payroll
        fields = ['title', 'notes']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., March Salary, April Salary'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional notes about this payroll...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        
        # PIN not required when editing
        if self.instance.pk:
            self.fields['pin'].required = False
            self.fields['pin'].help_text = 'Leave blank to keep current PIN'
    
    def clean(self):
        cleaned_data = super().clean()
        title = cleaned_data.get('title')
        pin = cleaned_data.get('pin')
        
        # Validate PIN format
        if pin and not pin.isdigit():
            raise ValidationError("PIN must contain only digits")
        
        if pin and (len(pin) < 4 or len(pin) > 6):
            raise ValidationError("PIN must be 4-6 digits")
        
        return cleaned_data


class PayrollItemForm(forms.ModelForm):
    """
    Form for individual staff payroll item.
    Simplified for Excel-like interface.
    """
    
    class Meta:
        model = PayrollItem
        fields = ['staff', 'staff_name', 'gross_amount', 'column_values']
        widgets = {
            'staff': forms.Select(attrs={
                'class': 'form-control',
                'placeholder': 'Select staff (optional)'
            }),
            'staff_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Staff name or contractor'
            }),
            'gross_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'column_values': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        self.custom_fields = kwargs.pop('custom_fields', None)
        super().__init__(*args, **kwargs)
        
        # Filter staff by tenant
        if self.tenant:
            from documents.models import CustomUser
            self.fields['staff'].queryset = CustomUser.objects.filter(
                tenant=self.tenant,
                is_active=True,
                staff_profile__isnull=False
            ).select_related('staff_profile').order_by('first_name', 'last_name')
        
        # Add dynamic custom fields
        if self.custom_fields:
            for field in self.custom_fields:
                field_name = f'custom_{field.name}'
                self.fields[field_name] = forms.DecimalField(
                    label=field.label,
                    required=False,
                    initial=0,
                    widget=forms.NumberInput(attrs={
                        'class': 'form-control custom-field',
                        'step': '0.01',
                        'min': '0',
                        'placeholder': '0.00',
                        'data-operation': field.operation
                    })
                )
                
                # Pre-fill from custom_field_values if editing
                if self.instance.pk and self.instance.custom_field_values:
                    self.fields[field_name].initial = self.instance.custom_field_values.get(field.name, 0)
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Collect custom field values
        custom_values = {}
        if self.custom_fields:
            for field in self.custom_fields:
                field_name = f'custom_{field.name}'
                value = cleaned_data.get(field_name, 0)
                custom_values[field.name] = float(value) if value else 0
        
        cleaned_data['custom_field_values'] = custom_values
        
        return cleaned_data


class PayrollPasswordForm(forms.Form):
    """
    Form for verifying payroll password before payment execution.
    """
    password = forms.CharField(
        label='Payroll Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter payroll password',
            'autocomplete': 'off'
        }),
        help_text='Enter the payroll password to authorize payment'
    )
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        
        if not self.tenant:
            raise ValidationError("Tenant not specified")
        
        if not verify_payroll_password(self.tenant, password):
            raise ValidationError("Incorrect payroll password")
        
        return password


class SetPayrollPasswordForm(forms.Form):
    """
    Form for Admin to set/change payroll password.
    """
    new_password = forms.CharField(
        label='New Payroll Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password'
        }),
        min_length=6,
        help_text='Minimum 6 characters'
    )
    
    confirm_password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm password',
            'autocomplete': 'new-password'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password:
            if new_password != confirm_password:
                raise ValidationError("Passwords do not match")
        
        return cleaned_data


class PayrollApprovalForm(forms.Form):
    """
    Form for approving/rejecting payroll.
    """
    ACTION_CHOICES = [
        ('approved', 'Approve'),
        ('rejected', 'Reject'),
        ('returned', 'Return for Revision'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='approved'
    )
    
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional comments...'
        }),
        help_text='Add comments about your decision (optional)'
    )
