from django import forms
from .models import MemoCategory, Memo, MemoStep, MemoComment, MemoSetting
from documents.models import CustomUser
from ckeditor_uploader.widgets import CKEditorUploadingWidget


class MemoCategoryForm(forms.ModelForm):
    class Meta:
        model = MemoCategory
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Procurement, Leave Request'}),
        }


class MemoCreateForm(forms.ModelForm):
    forward_to = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select recipients',
            'data-allow-clear': 'true',
            'data-close-on-select': 'false'
        }),
        help_text="Click to select multiple recipients - each appears as a removable tag"
    )
    cc_users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select CC recipients',
            'data-allow-clear': 'true',
            'data-close-on-select': 'false'
        }),
        label="CC",
        help_text="Click to select multiple users - each appears as a removable tag"
    )
    bcc_users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select BCC recipients',
            'data-allow-clear': 'true',
            'data-close-on-select': 'false'
        }),
        label="BCC",
        help_text="Select hidden recipients - each appears as a removable tag"
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Add a note for the recipient...'}),
    )
    attachments = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        help_text="You can attach multiple files"
    )

    class Meta:
        model = Memo
        fields = ['title', 'description', 'category', 'priority', 'document_type', 'scanned_file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Memo subject/title'}),
            'description': CKEditorUploadingWidget(config_name='custom_toolbar'),
            'category': forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select category'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'document_type': forms.Select(attrs={'class': 'form-control', 'id': 'id_document_type'}),
            'scanned_file': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request:
            tenant = self.request.effective_tenant
            user = self.request.effective_user

            if tenant:
                self.fields['forward_to'].queryset = CustomUser.objects.filter(tenant=tenant).exclude(id=user.id)
                self.fields['cc_users'].queryset = CustomUser.objects.filter(tenant=tenant).exclude(id=user.id)
                self.fields['bcc_users'].queryset = CustomUser.objects.filter(tenant=tenant).exclude(id=user.id)
                self.fields['category'].queryset = MemoCategory.objects.filter(tenant=tenant)
            else:
                self.fields['forward_to'].queryset = CustomUser.objects.filter(id=user.id)
                self.fields['cc_users'].queryset = CustomUser.objects.filter(id=user.id)
                self.fields['bcc_users'].queryset = CustomUser.objects.filter(id=user.id)
                self.fields['category'].queryset = MemoCategory.objects.filter(tenant=None, created_by=user)


class MemoForwardForm(forms.Form):
    """Form for forwarding / routing a memo to the next person."""
    ACTION_CHOICES = [
        ('forwarded', 'Minute'),
        ('approved', 'Approve'),
        ('rejected', 'Reject'),
        ('escalated', 'Escalate'),
        ('returned', 'Return to Sender'),
    ]

    to_users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=True,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select recipients',
            'data-allow-clear': 'true',
            'data-close-on-select': 'false'
        }),
        label="Route To"
    )
    cc_users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select CC recipients',
            'data-allow-clear': 'true',
            'data-close-on-select': 'false'
        }),
        label="CC",
        help_text="Click to select multiple users - each appears as a removable tag"
    )
    bcc_users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Select BCC recipients',
            'data-allow-clear': 'true',
            'data-close-on-select': 'false'
        }),
        label="BCC",
        help_text="Select hidden recipients - each appears as a removable tag"
    )
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Action"
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Add a note...'}),
    )
    is_private_note = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label="Private note (only you and recipient can see)",
    )
    attachments = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        help_text="You can attach multiple files"
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.memo = kwargs.pop('memo', None)
        super().__init__(*args, **kwargs)

        if self.request:
            tenant = self.request.effective_tenant
            user = self.request.effective_user

            if tenant:
                self.fields['to_users'].queryset = CustomUser.objects.filter(tenant=tenant)
                self.fields['cc_users'].queryset = CustomUser.objects.filter(tenant=tenant)
                self.fields['bcc_users'].queryset = CustomUser.objects.filter(tenant=tenant)
            else:
                self.fields['to_users'].queryset = CustomUser.objects.filter(id=user.id)
                self.fields['cc_users'].queryset = CustomUser.objects.filter(id=user.id)
                self.fields['bcc_users'].queryset = CustomUser.objects.filter(id=user.id)


class MemoCommentForm(forms.ModelForm):
    class Meta:
        model = MemoComment
        fields = ['content', 'is_private']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Add a comment...'}),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_private': 'Private comment (only you and current holder can see)',
        }


class MemoExternalSubmissionForm(forms.Form):
    """Public form for external memo submission."""
    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject of your request'}),
    )
    description = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6, 'class': 'form-control', 'placeholder': 'Describe your request in detail...'}),
    )
    category = forms.ModelChoiceField(
        queryset=MemoCategory.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select a category (optional)",
    )
    staff_suggestion = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Optional: select a staff member'}),
        label="Known staff member (optional)",
        help_text="If you know someone in the organization, select them here or send to receptionist"
    )
    submitter_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full name'}),
        label="Your Name"
    )
    submitter_email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'your@email.com'}),
        label="Your Email"
    )
    submitter_phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number (optional)'}),
        label="Your Phone"
    )
    attachments = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        help_text="You can attach multiple files"
    )

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)

        if self.tenant:
            self.fields['category'].queryset = MemoCategory.objects.filter(tenant=self.tenant)
            # Show staff members as suggestions (only active, non-superuser)
            self.fields['staff_suggestion'].queryset = CustomUser.objects.filter(
                tenant=self.tenant, is_active=True, is_superuser=False
            )


class MemoSettingForm(forms.ModelForm):
    class Meta:
        model = MemoSetting
        fields = ['notify_external_on_move', 'allow_external_escalation', 'allow_external_completion']
        widgets = {
            'notify_external_on_move': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_external_escalation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_external_completion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
