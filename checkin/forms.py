from django import forms
from .models import WorkSchedule, VisitorLog
from documents.models import CustomUser


from .models import StaffCheckIn, VisitorLog, VisitorTagCounter
from documents.models import CustomUser

class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model  = WorkSchedule
        fields = ['work_start_time', 'work_end_time', 'late_after']
        widgets = {
            'work_start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'work_end_time':   forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'late_after':      forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }
        labels = {
            'work_start_time': 'Work Start Time',
            'work_end_time':   'Work End Time',
            'late_after':      'Mark Late After',
        }
        help_texts = {
            'late_after': 'Staff arriving after this time will be marked Late (e.g. 08:15).',
        }


class VisitorCheckInForm(forms.Form):
    # ── Required 
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Full name', 'autofocus': True,
        }),
    )
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Phone number',
            'id': 'id_phone_number',
        }),
    )

    # ── personal ─
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email (optional)'}),
    )

    # ── Visit details ──
    PURPOSE_CHOICES = [('', '— Purpose (optional) —')] + VisitorLog.PURPOSE_CHOICES
    purpose = forms.ChoiceField(
        choices=PURPOSE_CHOICES, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    purpose_detail = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Additional details (optional)',
        }),
    )
    visitee = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        empty_label="— Who are you visiting? (optional) —",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    on_appointment = forms.BooleanField(
        required=False,
        label="On appointment",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    # ── ID ─
    ID_TYPE_CHOICES = [('', '— Form of ID (optional) —')] + VisitorLog.ID_TYPE_CHOICES
    id_type   = forms.ChoiceField(
        choices=ID_TYPE_CHOICES, required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    id_number = forms.CharField(
        required=False, max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'ID number (optional)',
        }),
    )

    # ── Document 
    has_document  = forms.BooleanField(
        required=False, label="Has document to scan?",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input', 'id': 'hasDocCheck',
            'onchange': 'toggleDocUpload(this)',
        }),
    )
    document_scan = forms.FileField(
    required=False, label="Scan document",
    widget=forms.FileInput(attrs={
        'class': 'form-control',
        'accept': 'image/*,application/pdf,.pdf',
        'capture': 'environment',
        'id': 'id_document_scan',   # docScanInput'
          }),
)

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2, 'placeholder': 'Notes (optional)',
        }),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['visitee'].queryset = CustomUser.objects.filter(
                tenant=tenant, is_active=True
            ).order_by('first_name', 'last_name')
   
    
    def clean_document_scan(self):
        f = self.cleaned_data.get('document_scan')
        if f:
            allowed = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf']
            mime = getattr(f, 'content_type', '')
            if mime and mime not in allowed:
                raise forms.ValidationError("Only images and PDF files are accepted.")
        return f
    
    

class VisitorCheckOutForm(forms.Form):
    visitor_tag = forms.CharField(
        max_length=4,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-center fw-bold',
            'placeholder': '0001', 'maxlength': '4', 'autofocus': True,
            'inputmode': 'numeric', 'style': 'letter-spacing:.3rem;font-size:2rem;',
        }),
        label="Enter Visitor Tag",
    )


class StaffPINSetupForm(forms.Form):
    pin = forms.CharField(
        min_length=4, max_length=6,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'placeholder': '4–6 digit PIN',
            'inputmode': 'numeric',
        }),
        label="New PIN",
    )
    confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'placeholder': 'Confirm PIN',
            'inputmode': 'numeric',
        }),
        label="Confirm PIN",
    )

    def clean(self):
        d = super().clean()
        pin     = d.get('pin', '')
        confirm = d.get('confirm', '')
        if pin != confirm:
            raise forms.ValidationError("PINs do not match.")
        if not pin.isdigit():
            raise forms.ValidationError("PIN must contain digits only.")
        return d

# ─── Manual Staff Check-in Form 

class ManualCheckInForm(forms.Form):
    """
    Used on the dashboard to manually check in a staff member.
    Staff dropdown is scoped to the current tenant.
    """
    staff = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(),
        empty_label="— Select staff member —",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id':    'id_manual_staff',
        }),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class':       'form-control',
            'rows':        2,
            'placeholder': 'Notes (optional)',
        }),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            # Only show active staff belonging to this tenant
            self.fields['staff'].queryset = CustomUser.objects.filter(
                tenant=tenant, is_active=True
            ).order_by('first_name', 'last_name')


# ─── Visitor Quick Checkout Form 

class VisitorCheckoutForm(forms.Form):
    """
    Used on the dashboard and visitor log for signing out a visitor by tag number.
    """
    visitor_tag = forms.CharField(
        max_length=10,
        label="Visitor Tag",
        widget=forms.TextInput(attrs={
            'class':       'form-control',
            'placeholder': 'e.g. 0001',
            'inputmode':   'numeric',
            'pattern':     '[0-9]*',
            'id':          'id_visitor_tag',
            'autocomplete': 'off',
        }),
    )

    def clean_visitor_tag(self):
        tag = self.cleaned_data.get('visitor_tag', '').strip()
        if not tag:
            raise forms.ValidationError("Please enter a visitor tag number.")
        # Zero-pad to 4 digits to match stored format e.g. "0001"
        tag = tag.zfill(4)
        return tag
    




class StaffManualCheckInForm(forms.Form):
    """Receptionist manually selects a staff member."""
    staff = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(),
        empty_label="— Select staff member —",
        widget=forms.Select(attrs={'class': 'form-select form-select-lg'}),
        label="Staff Member",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['staff'].queryset = CustomUser.objects.filter(
                tenant=tenant, is_active=True
            ).order_by('first_name', 'last_name')
