from django import forms
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from .models import ConferenceLoan, LoanDocument, LoanComment
from documents.models import Conference
from documents.kyc_field_approval_models import FieldApprovalStatus


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
        """Send notification to admins when a new loan is submitted"""
        from documents.models import Notification, UserNotification, CustomUser
        from django.urls import reverse
        
        try:
            # Create notification
            notification = Notification.objects.create(
                tenant=instance.tenant,
                title=f"New Loan Application: {instance.reference_number}",
                message=f"A new loan application by {instance.applicant.get_full_name()} for {instance.conference.title} requires your review.",
                type=Notification.NotificationType.INFO,
                is_active=True,
                link=reverse('conference_loan:loan_review', kwargs={'pk': instance.pk})
            )
            
            # Notify tenant admins
            admins = CustomUser.objects.filter(
                tenant=instance.tenant,
                roles__name='Admin',
                is_active=True
            )
            
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=instance.tenant,
                    notification=notification,
                    dismissed=False
                )
        except Exception as e:
            print(f"Failed to send new loan submission notification: {e}")
    
    def notify_admins_of_resubmission(self, instance):
        """Send notification to admins when loan fields are resubmitted"""
        from documents.models import Notification, UserNotification, CustomUser
        from django.urls import reverse
        
        try:
            # Create notification
            notification = Notification.objects.create(
                tenant=instance.tenant,
                title=f"Loan Resubmitted: {instance.reference_number}",
                message=f"Loan application by {instance.applicant.get_full_name()} has been updated. Rejected fields have been resubmitted for review.",
                type=Notification.NotificationType.INFO,
                is_active=True,
                link=reverse('conference_loan:loan_review', kwargs={'pk': instance.pk})
            )
            
            # Notify tenant admins
            admins = CustomUser.objects.filter(
                tenant=instance.tenant,
                roles__name='Admin',
                is_active=True
            )
            
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=instance.tenant,
                    notification=notification,
                    dismissed=False
                )
        except Exception as e:
            print(f"Failed to send loan resubmission notification: {e}")


class ConferenceLoanForm(PartialResubmissionMixin, forms.ModelForm):
    """Form for creating/editing conference loan applications"""
    
    class Meta:
        model = ConferenceLoan
        fields = [
            'conference', 'amount', 'currency', 'reason', 'expected_date',
            'conference_description', 'expected_revenue', 'expected_expenses',
            'guarantor_name', 'guarantor_phone', 'guarantor_email',
            'guarantor_address', 'guarantor_relationship', 'guarantor_occupation',
            'guarantor_id', 'guarantor_signature'
        ]
        widgets = {
            'conference': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter loan amount',
                'step': '0.01',
                'min': '0'
            }),
            'currency': forms.Select(attrs={
                'class': 'form-control'
            }, choices=[
                ('NGN', 'NGN - Nigerian Naira'),
                ('USD', 'USD - US Dollar'),
                ('GBP', 'GBP - British Pound'),
                ('EUR', 'EUR - Euro'),
            ]),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Explain why you need this loan'
            }),
            'expected_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'conference_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the conference, target audience, expected attendance, etc.'
            }),
            'expected_revenue': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Expected revenue from conference (optional)',
                'step': '0.01',
                'min': '0'
            }),
            'expected_expenses': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Expected total expenses (optional)',
                'step': '0.01',
                'min': '0'
            }),
            'guarantor_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name of guarantor'
            }),
            'guarantor_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+234...'
            }),
            'guarantor_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'guarantor@example.com'
            }),
            'guarantor_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Guarantor residential address'
            }),
            'guarantor_relationship': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Business Partner, Family Member, etc.'
            }),
            'guarantor_occupation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Guarantor occupation'
            }),
            'guarantor_id': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'guarantor_signature': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        
        # Filter conferences to only show tenant's conferences
        if self.tenant:
            self.fields['conference'].queryset = Conference.objects.filter(
                tenant=self.tenant
            ).order_by('-start_date')
        else:
            # If no tenant, show empty queryset
            self.fields['conference'].queryset = Conference.objects.none()
        
        # Add help text
        self.fields['conference'].help_text = "Select the conference you're requesting financing for"
        self.fields['amount'].help_text = "Amount in selected currency"
        self.fields['expected_date'].help_text = "When do you need the funds?"

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise ValidationError("Loan amount must be greater than zero")
        return amount

    def clean_expected_date(self):
        expected_date = self.cleaned_data.get('expected_date')
        conference = self.cleaned_data.get('conference')
        
        if expected_date and conference:
            if expected_date > conference.start_date.date():
                raise ValidationError(
                    "Expected date must be before the conference start date"
                )
        
        return expected_date

    def clean(self):
        cleaned_data = super().clean()
        conference = cleaned_data.get('conference')
        
        # Verify conference belongs to tenant
        # Use self.tenant (passed to form) rather than instance.tenant (not set yet during creation)
        if conference and self.tenant and conference.tenant != self.tenant:
            raise ValidationError({
                'conference': "You can only request loans for your organization's conferences"
            })
        
        return cleaned_data


class LoanDocumentForm(forms.ModelForm):
    """Form for uploading loan documents"""
    
    class Meta:
        model = LoanDocument
        fields = ['document_type', 'file', 'description']
        widgets = {
            'document_type': forms.Select(attrs={
                'class': 'form-control'
            }, choices=[
                ('', 'Select type...'),
                ('conference_proposal', 'Conference Proposal'),
                ('budget', 'Budget/Financial Plan'),
                ('business_plan', 'Business Plan'),
                ('cac', 'CAC Document'),
                ('memart', 'MEMART Document'),
                ('other', 'Other'),
            ]),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optional description'
            }),
        }


class LoanCommentForm(forms.ModelForm):
    """Form for adding comments to loan applications"""
    
    class Meta:
        model = LoanComment
        fields = ['content', 'is_internal']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add a comment...'
            }),
            'is_internal': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }


class LoanReviewForm(forms.Form):
    """Form for reviewing and approving/rejecting loans"""
    action = forms.ChoiceField(
        choices=[('approve', 'Approve'), ('reject', 'Reject')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    approved_amount = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Approved amount',
            'step': '0.01'
        })
    )
    interest_rate = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Interest rate %',
            'step': '0.01'
        })
    )
    repayment_period_months = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Repayment period (months)'
        })
    )
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for rejection'
        })
    )
    internal_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Internal notes (optional)'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        
        if action == 'approve':
            if not cleaned_data.get('approved_amount'):
                raise ValidationError({'approved_amount': 'Approved amount is required'})
            if not cleaned_data.get('interest_rate'):
                raise ValidationError({'interest_rate': 'Interest rate is required'})
            if not cleaned_data.get('repayment_period_months'):
                raise ValidationError({'repayment_period_months': 'Repayment period is required'})
        
        elif action == 'reject':
            if not cleaned_data.get('rejection_reason'):
                raise ValidationError({'rejection_reason': 'Rejection reason is required'})
        
        return cleaned_data


# Import timezone for date validation
from django.utils import timezone
