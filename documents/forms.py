# documents/forms.py
from django import forms
from django.forms import modelformset_factory
from .models import Document, User, CustomUser, Folder, File, Task, StaffProfile, StaffDocument, Department, Team, Role, Event, EventParticipant, Notification, UserNotification, CompanyProfile, Contact, Email, Attachment, CompanyDocument, UserProfile, VacancySkill, VacancyTag
from .models import Conference,ConferenceParticipant, ConferenceTag, JobOffer, ConferenceSpeaker, BookingType, BookingTypeSchedule, ConferencePriceTier
from .models import WorkHistory, EducationHistory, PromotionHistory, IdentityDocument, Achievement, CompanyProductService, CompanyTeamHighlight, Recommendation
from .viewfuncs.mail_connection import get_email_smtp_connection
from tenants.models import Tenant
from ckeditor.widgets import CKEditorWidget
from ckeditor_uploader.widgets import CKEditorUploadingWidget
from crm.models import Opportunity, Product
from django.contrib.auth import get_user_model
import json
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.core.exceptions import ValidationError
from django.core.mail import send_mail, get_connection
from django_countries.fields import CountryField
from django.urls import reverse
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from cities_light.models import Region
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db.models import Q
from django.forms import inlineformset_factory
from .invoice_forms import *

User = get_user_model()

class TenantAwareModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

def filter_by_tenant(queryset, user):
    tenant = getattr(user, 'tenant', None)
    if tenant:
        return queryset.filter(tenant=tenant)
    return queryset.none()

ConferencePriceTierFormSet = inlineformset_factory(
    Conference,
    ConferencePriceTier,
    fields=['name', 'description', 'price', 'capacity', 'is_active', 'order'],
    extra=1,
    can_delete=True,
    widgets={
        'name':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Student'}),
        'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional short description'}),
        'price':       forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
        'capacity':    forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Blank = unlimited'}),
        'order':       forms.NumberInput(attrs={'class': 'form-control'}),
        'is_active':   forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    },
)

class DocumentForm(forms.ModelForm):
    creation_method = forms.ChoiceField(
        choices=[('template', 'Use Template'), ('upload', 'Upload Document')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    uploaded_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.docx,.pdf'}),
        help_text='Upload a .docx or .pdf file (required if using Upload Document option)'
    )
    document_type = forms.ChoiceField(
        choices=[('approval', 'Approval Letter'), ('sla', 'SLA Document')],
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False  # Not required for uploaded documents
    )

    class Meta:
        model = Document
        fields = [
            'creation_method',
            'uploaded_file',
            'document_type',
            'company_name',
            'company_address',
            'contact_person_name',
            'contact_person_email',
            'contact_person_designation',
            'sales_rep'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'company_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'contact_person_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_person_designation': forms.TextInput(attrs={'class': 'form-control'}),
            'sales_rep': forms.TextInput(attrs={'class': 'form-control sales-rep-field'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        creation_method = cleaned_data.get('creation_method')
        uploaded_file = cleaned_data.get('uploaded_file')
        document_type = cleaned_data.get('document_type')

        if creation_method == 'upload':
            if not uploaded_file:
                raise forms.ValidationError('You must upload a .docx or .pdf file when using the Upload Document option.')
            if not uploaded_file.name.lower().endswith(('.docx', '.pdf')):
                raise forms.ValidationError('Only .docx or .pdf files are allowed.')
            # if document_type:
            #     self.add_error('document_type', 'Document type should not be selected when uploading a document.')
            # Set document_type to 'Uploaded' for uploads
            cleaned_data['document_type'] = 'Uploaded'
        else:
            if not document_type:
                raise forms.ValidationError('Document type is required when using a template.')
            if uploaded_file:
                self.add_error('uploaded_file', 'Do not upload a file when using a template.')

        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Ensure document_type is set to 'Uploaded' for upload method
        if self.cleaned_data['creation_method'] == 'upload':
            instance.document_type = 'Uploaded'
        if commit:
            instance.save()
        return instance

class CreateDocumentForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Document Title'})
    )
    content = forms.CharField(
        widget=CKEditorUploadingWidget(config_name='custom_toolbar'),
        required=True
    )
    
class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
    password_confirm = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
    phone_number = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "password"]

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        first_name = cleaned_data.get("first_name")
        last_name = cleaned_data.get("last_name")
        email = cleaned_data['email']
        self.phone_number = cleaned_data['phone_number']
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords do not match")
        if not first_name:
            raise forms.ValidationError("Please Enter First Name")
        if not last_name:
            raise forms.ValidationError("Please Enter Last Name")
        if not self.phone_number:
            raise forms.ValidationError("Please Enter Phone Number")
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return cleaned_data


class CustomLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Username or Email",
        widget=forms.TextInput(attrs={
            'autofocus': True,
            'placeholder': 'Enter your username or email'
        })
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        'invalid_login': _(
            "Please enter a correct email address and password. "
            "Note that both fields may be case-sensitive."
        ),
        'inactive': _(
            "Your account has been successfully registered but is currently pending approval "
            "by an administrator. You will receive an email once your account is approved "
            "and you can log in. If you have questions, contact your administrator."
        ),
    }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            raise ValidationError("Please enter your username or email.")
        return username

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            # Normalize the input (strip whitespace, convert to lowercase if emails are case-insensitive)
            username = username.strip()
            
            # Determine if the input is an email
            is_email = '@' in username

            user_obj = None

            if is_email:
                user_obj = User.objects.filter(email__iexact=username).first()
            else:
                user_obj = User.objects.filter(username__iexact=username).first()

            # 🔴 USER EXISTS BUT IS INACTIVE
            if user_obj and not user_obj.is_active:
                raise ValidationError(
                    self.error_messages['inactive'],
                    code='inactive'
                )
            
            # Authenticate ONLY if active
            if user_obj:
                self.user_cache = authenticate(
                    self.request,
                    username=user_obj.username,
                    password=password
                )
            else:
                self.user_cache = None

            if self.user_cache is None:
                raise self.get_invalid_login_error()

            self.confirm_login_allowed(self.user_cache)
            return self.cleaned_data

class UserForm(forms.ModelForm):
    # password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
    # password_confirm = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 
                  'is_active', 'roles', 'phone_number', 
                  'department', 'teams']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'roles': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'teams': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
            self.fields['teams'].queryset = Team.objects.filter(tenant=tenant)
        else:
            self.fields['department'].queryset = Department.objects.none()
            self.fields['teams'].queryset = Team.objects.none()

class EditUserForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False  # Set to True if selection is mandatory
    )
    class Meta:
        model = CustomUser
        fields = ['username', 'first_name', 'last_name', 'email', 
                  'is_active', 'roles', 'phone_number', 
                  'department', 'teams']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            # 'roles': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'teams': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
            self.fields['teams'].queryset = Team.objects.filter(tenant=tenant)
        else:
            self.fields['department'].queryset = Department.objects.none()
            self.fields['teams'].queryset = Team.objects.none()

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(label='Email', max_length=254)

    def clean_email(self):
        email = self.cleaned_data['email']
        if not CustomUser.objects.filter(email=email, is_active=True).exists():
            raise ValidationError("No active user found with this email address.")
        return email

    # def save(self, request):
        # email = self.cleaned_data['email']
        # user = CustomUser.objects.get(email=email)
        # # Generate token and UID
        # token = default_token_generator.make_token(user)
        # uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        # # Build reset URL
        # reset_url = request.build_absolute_uri(
        #     reverse('reset_password', kwargs={'uidb64': uidb64, 'token': token})
        # )
        # superuser = CustomUser.objects.get(is_superuser=True)
        # sender_email = superuser.email_address
        # sender_password = superuser.get_smtp_password()
        # if sender_email and sender_password:
        #     connection, error_message = get_email_smtp_connection(superuser.email_provider, sender_email, sender_password)
        #     # Send email (customize content as needed)
        #     subject = 'TeamManager Password Reset Request'
        #     message = f"""
        #     Hello {user.username},

        #     You requested a password reset. Click the link below to set a new password:

        #     {reset_url}

        #     If you didn’t request this, ignore this email.

        #     Thanks,
        #     The TeamManager Team
        #     """
        #     send_mail(subject, message, sender_email, [user.email], connection=connection)

class ResetPasswordForm(SetPasswordForm):
    # Inherits new_password1 and new_password2 fields with validation
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(user, *args, **kwargs)

class FolderForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ['name', 'parent', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.HiddenInput(),
            # 'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            # 'parent': forms.ModelChoiceField(queryset=Folder.objects.all(), required=False, widget=forms.HiddenInput),
        }

class FileUploadForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ['folder', 'file']
        widgets = {
            'folder': forms.HiddenInput(),
        }

class FileUploadAnonForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ['folder', 'file', 'anon_name', 'anon_email', 'anon_phone']
        widgets = {
            'folder': forms.HiddenInput(),
            'anon_name': forms.TextInput(attrs={'class':'form-control'}),
            'anon_email': forms.TextInput(attrs={'class':'form-control'}),
            'anon_phone': forms.TextInput(attrs={'class':'form-control'}),
        }

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)
        self.widget.attrs.update({'multiple': 'multiple', 'class': 'form-control'})

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class TaskForm(forms.ModelForm):
    uploaded_files = MultipleFileField(
        required=False,
        label="Upload New Files"
    )

    class Meta:
        model = Task
        fields = ['title', 'description', 'documents', 'assigned_to', 'opportunity', 'product', 'due_date', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'documents': forms.SelectMultiple(attrs={
                'class': 'form-control select2', 
                'data-placeholder': 'Select existing documents',
                'id': 'id_documents'
            }),
            'assigned_to': forms.SelectMultiple(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Select staff members',
                'id': 'id_assigned_to'
            }),
            'opportunity': forms.Select(attrs={'class': 'form-control select2', 'id': 'id_opportunity'}),
            'product': forms.Select(attrs={'class': 'form-control select2', 'id': 'id_product'}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                self.fields['assigned_to'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
                self.fields['documents'].queryset = File.objects.filter(tenant=tenant)
                self.fields['opportunity'].queryset = Opportunity.objects.filter(tenant=tenant)
                self.fields['product'].queryset = Product.objects.filter(tenant=tenant)
            else:
                self.fields['assigned_to'].queryset = CustomUser.objects.none()
                self.fields['assigned_to'].widget = forms.HiddenInput()
                self.fields['documents'].queryset = File.objects.none()
                self.fields['opportunity'].queryset = Opportunity.objects.none()
                self.fields['product'].queryset = Product.objects.none()

class ReassignTaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['assigned_to', 'due_date']
        widgets = {
            'assigned_to': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'},)
        }
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                self.fields['assigned_to'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
            else:
                self.fields['assigned_to'].queryset = CustomUser.objects.none()

class StaffProfileForm(forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = [
            "photo",
            "first_name", "last_name", "middle_name", "email", "phone_number", "sex", "date_of_birth", "home_address",
            "state_of_origin", "lga", "religion",
            "next_of_kin_name", "next_of_kin_phone", "next_of_kin_relationship", "next_of_kin_email", "next_of_kin_address",
            "guarantor_name", "guarantor_phone", "guarantor_email", 
            "bank_account_number", "bank_name", "bank_account_name", "bank_code", "bank_verification_note",
            "emergency_name", "emergency_relationship", "emergency_phone",
            "emergency_address", "emergency_email", "bio",
            "department", "team", "designation", "official_email", "employment_date",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "employment_date": forms.DateInput(attrs={"type": "date"}),
            "home_address": forms.Textarea(attrs={"rows": 2}),
            "emergency_address": forms.Textarea(attrs={"rows": 2}),
            "next_of_kin_address": forms.Textarea(attrs={"rows": 2}),
            "team": forms.Select(attrs={"class": "form-control"}),
            "department": forms.Select(attrs={"class": "form-control"}),
            "designation": forms.TextInput(attrs={"class": "form-control"}),
            "official_email": forms.EmailInput(attrs={"class": "form-control"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 3}),         
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
                self.fields['team'].queryset = Team.objects.filter(tenant=tenant)
            else:
                self.fields['department'].queryset = Department.objects.none()
                self.fields['team'].queryset = Team.objects.none
        
class StaffDocumentForm(forms.ModelForm):
    class Meta:
        model = StaffDocument
        fields = ['file', 'document_type', 'description']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file and file.size > 5 * 1024 * 1024:  # 5MB limit
            raise forms.ValidationError("File size must be under 5MB.")
        return file
    
class EmailConfigForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['email_provider', 'email_address', 'email_password' ]
        widgets = {
            'email_provider': forms.Select(attrs={'class': 'form-control'}),
            'email_address': forms.EmailInput(attrs={'class': 'form-control'}),
            'email_password': forms.PasswordInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
            instance = super().save(commit=False)
            instance.set_smtp_password(self.cleaned_data['email_password'])
            if commit:
                instance.save()
            return instance

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'hod']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'hod': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # tenant = getattr(user, 'tenant', None)
            tenant = user.tenant
            if tenant:
                self.fields['hod'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
            else:
                self.fields['hod'].queryset = CustomUser.objects.none()

class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'department', 'team_leader']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-control'}),
            'team_leader': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
                self.fields['team_leader'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
            else:
                self.fields['department'].queryset = Department.objects.none()
                self.fields['team_leader'].queryset = CustomUser.objects.none()

class AssignUsersToDepartmentForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2',
            'data-placeholder': 'Select users',
            'data-tags': 'true',
            'data-token-separators': '[",", " "]'}),
        label="Select Users",
        required=False
    )

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['users'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)

class AssignTeamsToUsersForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2',
            'data-placeholder': 'Select users',
            'data-tags': 'true',
            'data-token-separators': '[",", " "]'}),
        label="Select Users",
        required=False
    )
    # teams = forms.ModelMultipleChoiceField(
    #     queryset=Team.objects.all(),
    #     widget=forms.CheckboxSelectMultiple,
    #     label="Select Teams"
    # )

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['users'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
            # self.fields['teams'].queryset = Team.objects.filter(tenant=tenant)

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'start_time', 'end_time', 'event_link']
        widgets = {
            "start_time": forms.DateInput(attrs={'type': 'date', 'class': 'form-control'},),
            "end_time": forms.DateInput(attrs={'type': 'date', 'class': 'form-control'},),
            "description": forms.Textarea(attrs={"rows": 2}),
            "link": forms.URLInput(attrs={"class": 'form-control'}),
        }

class EventParticipantForm(forms.ModelForm):
    
    class Meta:
        model = EventParticipant
        fields = ['event', 'user', 'response']
        widgets = {
            'event': forms.Select(attrs={'class': 'form-control'}),
            'user': forms.Select(attrs={'class': 'form-control'}),
            'response': forms.Select(attrs={'class': 'form-control'}, choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined')]),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if not user.is_personal:
            tenant = getattr(user, 'tenant', None)
            if tenant is not None:
                self.fields['event'].queryset = Event.objects.filter(tenant=tenant)
                self.fields['user'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
            else:
                self.fields['event'].queryset = Event.objects.none()
                self.fields['user'].queryset = CustomUser.objects.none()
                self.fields['department'].queryset = CustomUser.objects.none()
                self.fields['team'].queryset = Department.objects.none

class NotificationForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = ['title', 'message', 'type', 'expires_at', 'is_active']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-control'}, choices=Notification.NotificationType),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class UserNotificationForm(forms.ModelForm):
    class Meta:
        model = UserNotification
        fields = ['user', 'notification']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'notification': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            tenant = getattr(user, 'tenant', None)
            if tenant:
                self.fields['user'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)
                self.fields['notification'].queryset = Notification.objects.filter(tenant=tenant)
            else:
                self.fields['user'].queryset = CustomUser.objects.none()
                self.fields['notification'].queryset = Notification.objects.none()

class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ['photo', 'company_name',  'description', 'date_founded', 'reg_number', 
                  'address', 'email', 'contact_details', 'website',
                  'bank_name', 'bank_account_number', 'bank_account_name', 'bank_code', 'bank_verification_note']
        widgets = {
            'description' : forms.TextInput(attrs={'rows': 5, 'class': 'form-control'}),
            'date_founded': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'contact_details': forms.TextInput(attrs={'rows': 4, 'class': 'form-control'}),
            'bank_verification_note': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Put in a note and date of verification',
                'required': 'Please put in the latest date of confirmation without which we cannot proceed with remittance'
            }),
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['photo', 'first_name',  'last_name', 'middle_name', 'phone_number', 'designation', 'location', 'home_address', 'date_of_birth',
                   'email', 'sex', 'religion', 'marital_status', 'bio', 'bank_name', 'bank_account_number', 
                  'bank_account_name', 'bank_code', 'bank_verification_note']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'bank_verification_note': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Put in a note and date of verification',
                'required': 'Please put in the latest date of confirmation without which we cannot proceed with remittance'
            }),
        }

# New form specifically for bank verification
class BankVerificationForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ['bank_name', 'bank_account_number', 'bank_account_name', 'bank_code', 'bank_verification_note']
        widgets = {
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., GTBank, First Bank, etc.',
                'required': 'required'
            }),
            'bank_account_number': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '0123456789',
                'required': 'required'
            }),
            'bank_account_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Your Company Name Ltd.',
                'required': 'required'
            }),
            'bank_code': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '058 (for GTBank), 011 (for First Bank)',
                'required': 'required'
            }),
            'bank_verification_note': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Put in a note and date of verification',
                'required': 'Please put in the latest date of confirmation without which we cannot proceed with remittance'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields required
        self.fields['bank_name'].required = True
        self.fields['bank_account_number'].required = True
        self.fields['bank_account_name'].required = True
        self.fields['bank_code'].required = True
    
    def clean_bank_account_number(self):
        """Validate bank account number"""
        account_number = self.cleaned_data.get('bank_account_number')
        if account_number and not account_number.isdigit():
            raise forms.ValidationError("Account number must contain only digits.")
        if account_number and len(account_number) != 10:
            raise forms.ValidationError("Account number must be 10 digits.")
        return account_number
    
    def clean_bank_code(self):
        """Validate bank code"""
        bank_code = self.cleaned_data.get('bank_code')
        if bank_code and not bank_code.isdigit():
            raise forms.ValidationError("Bank code must contain only digits.")
        if bank_code and len(bank_code) != 3:
            raise forms.ValidationError("Bank code must be 3 digits.")
        return bank_code
    
class UserBankVerificationForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bank_name', 'bank_account_number', 'bank_account_name', 'bank_code', 'bank_verification_note']
        widgets = {
            'bank_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'e.g., GTBank, First Bank, etc.',
                'required': 'required'
            }),
            'bank_account_number': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '0123456789',
                'required': 'required'
            }),
            'bank_account_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Your Company Name Ltd.',
                'required': 'required'
            }),
            'bank_code': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '058 (for GTBank), 011 (for First Bank)',
                'required': 'required'
            }),
            'bank_verification_note': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Put in a note and date of verification',
                'required': 'Please put in the latest date of confirmation without which we cannot proceed with remittance'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields required
        self.fields['bank_name'].required = True
        self.fields['bank_account_number'].required = True
        self.fields['bank_account_name'].required = True
        self.fields['bank_code'].required = True
    
    def clean_bank_account_number(self):
        """Validate bank account number"""
        account_number = self.cleaned_data.get('bank_account_number')
        if account_number and not account_number.isdigit():
            raise forms.ValidationError("Account number must contain only digits.")
        if account_number and len(account_number) != 10:
            raise forms.ValidationError("Account number must be 10 digits.")
        return account_number
    
    def clean_bank_code(self):
        """Validate bank code"""
        bank_code = self.cleaned_data.get('bank_code')
        if bank_code and not bank_code.isdigit():
            raise forms.ValidationError("Bank code must contain only digits.")
        if bank_code and len(bank_code) != 3:
            raise forms.ValidationError("Bank code must be 3 digits.")
        return bank_code

# Optional: Form for tenants to confirm their bank details
class BankConfirmationForm(forms.Form):
    is_correct = forms.BooleanField(
        required=True,
        label="I confirm that these bank details are correct",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    agree_to_terms = forms.BooleanField(
        required=True,
        label="I agree that incorrect bank details may delay payment processing",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

class CompanyDocumentForm(forms.ModelForm):
    class Meta:
        model = CompanyDocument
        fields = ['file', 'document_type', 'description']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file and file.size > 10 * 1024 * 1024:  # 10MB limit
            raise forms.ValidationError("File size must be under 10MB.")
        return file

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            'name', 'email', 'phone', 'organization', 'designation', 'priority', 'is_public',
            'title', 'lead_source', 'is_primary_contact', 'tags', 'linkedin_url'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'organization': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., CTO, Manager'}),
            'lead_source': forms.Select(attrs={'class': 'form-control'}),
            'is_primary_contact': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tags': forms.CheckboxSelectMultiple(),
            'linkedin_url': forms.URLInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if request:
            tenant = request.effective_tenant
            user = request.effective_user
            
            # Filter account by tenant context
            if tenant:
                from crm.models import Account
                self.fields['account'].queryset = Account.objects.filter(tenant=tenant)
            elif user:
                from crm.models import Account
                self.fields['account'].queryset = Account.objects.filter(tenant=None, created_by=user)

# class EmailForm(forms.ModelForm):
#     class Meta:
#         model = Email
#         fields = ['subject', 'body', 'to', 'cc', 'bcc']
#         widgets = {
#             'subject': forms.TextInput(attrs={'class': 'form-control'}),
#             'body': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
#             'to': forms.SelectMultiple(attrs={'class': 'form-control select2', 'multiple': 'multiple'}),
#             'cc': forms.SelectMultiple(attrs={'class': 'form-control select2', 'multiple': 'multiple'}),
#             'bcc': forms.SelectMultiple(attrs={'class': 'form-control select2', 'multiple': 'multiple'}),
#         }

#     def __init__(self, *args, **kwargs):
#         user = kwargs.pop('user', None)
#         super().__init__(*args, **kwargs)
#         if user:
#             tenant = getattr(user, 'tenant', None)
#             if tenant:
#                 self.fields['to'].queryset = Contact.objects.filter(tenant=tenant, department=user.department)
#                 self.fields['cc'].queryset = Contact.objects.filter(tenant=tenant, department=user.department)
#                 self.fields['bcc'].queryset = Contact.objects.filter(tenant=tenant, department=user.department)
#             else:
#                 self.fields['to'].queryset = Contact.objects.none()
#                 self.fields['cc'].queryset = Contact.objects.none()
#                 self.fields['bcc'].queryset = Contact.objects.none()

class EmailForm(forms.ModelForm):
    to_emails = forms.CharField(
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Enter emails or select contacts',
            'data-tags': 'true',
            'data-token-separators': '[",", " "]'
        }),
        help_text="Enter email addresses or select contacts, separated by commas or spaces.",
        required=True
    )
    cc_emails = forms.CharField(
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Enter CC emails or select contacts',
            'data-tags': 'true',
            'data-token-separators': '[",", " "]'
        }),
        help_text="Enter CC email addresses or select contacts, separated by commas or spaces.",
        required=False
    )
    bcc_emails = forms.CharField(
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Enter BCC emails or select contacts',
            'data-tags': 'true',
            'data-token-separators': '[",", " "]'
        }),
        help_text="Enter BCC email addresses or select contacts, separated by commas or spaces.",
        required=False
    )
    attachments = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control'
        }),
        required=False
    )

    class Meta:
        model = Email
        fields = ['subject', 'body', 'to_emails', 'cc_emails', 'bcc_emails']

    def clean_to_emails(self):
        """Validate and process to_emails field."""
        emails = self.cleaned_data['to_emails']
        print(f"To Emails: {emails}")
        email_list = []
        if isinstance(emails, str):
            try:
                # Handle stringified list (e.g., "['email1','email2']")
                parsed_emails = json.loads(emails.replace("'", '"'))
                email_list = [email.strip() for email in parsed_emails if email.strip()]
                print(f"To Emails string instance: {email_list}")
            except (json.JSONDecodeError, TypeError):
                # Handle comma-separated string
                email_list = [email.strip() for email in emails.split(',') if email.strip()]
        else:
            # Handle list input from SelectMultiple
            email_list = [email.strip() for email in emails if email.strip()]
            print(f"To Emails list instance: {email_list}")
        if not email_list:
            raise forms.ValidationError("At least one recipient email is required.")
        for email in email_list:
            if not self._is_valid_email(email):
                raise forms.ValidationError(f"Invalid email address: {email}")
        return email_list

    def clean_cc_emails(self):
        """Validate and process cc_emails field."""
        emails = self.cleaned_data['cc_emails']
        email_list = []
        if isinstance(emails, str):
            try:
                parsed_emails = json.loads(emails.replace("'", '"'))
                email_list = [email.strip() for email in parsed_emails if email.strip()]
            except (json.JSONDecodeError, TypeError):
                email_list = [email.strip() for email in emails.split(',') if email.strip()]
        else:
            email_list = [email.strip() for email in emails if email.strip()]
        for email in email_list:
            if not self._is_valid_email(email):
                raise forms.ValidationError(f"Invalid email address: {email}")
        return email_list

    def clean_bcc_emails(self):
        """Validate and process bcc_emails field."""
        emails = self.cleaned_data['bcc_emails']
        email_list = []
        if isinstance(emails, str):
            try:
                parsed_emails = json.loads(emails.replace("'", '"'))
                email_list = [email.strip() for email in parsed_emails if email.strip()]
            except (json.JSONDecodeError, TypeError):
                email_list = [email.strip() for email in emails.split(',') if email.strip()]
        else:
            email_list = [email.strip() for email in emails if email.strip()]
        for email in email_list:
            if not self._is_valid_email(email):
                raise forms.ValidationError(f"Invalid email address: {email}")
        return email_list
    
    def clean_attachments(self):
        """Validate multiple file attachments."""
        files = self.files.getlist('attachments')
        if not files:
            return None
        for f in files:
            if f.size > 10 * 1024 * 1024:  # 10MB limit
                raise forms.ValidationError(f"File {f.name} is too large (max 10MB).")
        return files

    def _is_valid_email(self, email):
        """Validate email format."""
        from django.core.validators import validate_email
        try:
            validate_email(email)
            return True
        except forms.ValidationError:
            return False

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.set_to_emails(self.cleaned_data['to_emails'])
        instance.set_cc_emails(self.cleaned_data['cc_emails'])
        instance.set_bcc_emails(self.cleaned_data['bcc_emails'])
        if commit:
            instance.save()
            files = self.cleaned_data.get('attachments')
            if files:
                for f in files:
                    Attachment.objects.create(email=instance, file=f)
        return instance

    
# Formset for attachments
# AttachmentFormSet = modelformset_factory(
#     Attachment,
#     fields=('file',),
#     extra=3,  # Allow up to 3 additional attachments
#     can_delete=True,
#     widgets={'file': forms.FileInput(attrs={'class': 'form-control'})}
# )

class SupportForm(forms.Form):
    subject = forms.CharField(max_length=255, required=True)
    message = forms.CharField(widget=forms.Textarea, required=True)
    attachments = forms.FileField(
        widget=forms.FileInput(attrs={'class':'form-control'}),
        required=False
    )

    def clean_attachments(self):
        files = self.files.getlist('attachments')
        print("Cleaning attachments: %s", [(f.name, f.size, f.content_type) for f in files])
        if not files:
            print("No attachments provided")
            return None
        for f in files:
            if f.size > 10 * 1024 * 1024:  # 10MB limit
                raise forms.ValidationError(f"File {f.name} is too large (max 10MB).")
            if f.content_type not in ['image/jpeg', 'image/png']:
                raise forms.ValidationError(f"File {f.name} is not a valid JPG/PNG file.")
        return files

from .models import Vacancy, VacancyApplication
# class VacancyForm(forms.ModelForm):
#     class Meta:
#         model = Vacancy
#         fields = ['title', 'description', 'country', 'city', 'work_mode', 'skills', 'tags','eligibility', 'min_salary', 'max_salary', 'status']
#         widgets = {
#             'title': forms.TextInput(attrs={'class': 'form-control'}),
#             'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
#             'country': forms.Select(attrs={'class': 'form-control'}),
#             'city': forms.TextInput(attrs={'class': 'form-control'}),
#             'work_mode': forms.Select(attrs={'class': 'form-control'}),
#             'skills': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
#             'eligibility': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
#             'min_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
#             'max_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
#             'status': forms.Select(attrs={'class': 'form-control'}),
#         }
#         tags = forms.ModelMultipleChoiceField(
#             queryset=VacancyTag.objects.all(),
#             required=False,
#             widget=forms.SelectMultiple(attrs={'class': 'form-control select2', 'data-placeholder': 'Select tags'})
#         )

#         skills = forms.ModelMultipleChoiceField(
#             queryset=VacancySkill.objects.all(),
#             required=False,
#             widget=forms.SelectMultiple(attrs={'class': 'form-control select2', 'data-placeholder': 'Select skills'})
#         )


#     def clean(self):
#         cleaned_data = super().clean()
#         # Handle new tags
#         new_tags = self.data.get('new_tags', '')
#         if new_tags:
#             tag_names = [tag.strip() for tag in new_tags.split(',') if tag.strip()]
#             for tag_name in tag_names:
#                 tag, created = VacancyTag.objects.get_or_create(name=tag_name.lower())
#                 if self.instance.pk:
#                     self.instance.tags.add(tag)
        
#         # Handle new skills
#         new_skills = self.data.get('new_skills', '')
#         if new_skills:
#             skill_names = [skill.strip() for skill in new_skills.split(',') if skill.strip()]
#             for skill_name in skill_names:
#                 skill, created = VacancySkill.objects.get_or_create(name=skill_name.lower())
#                 if self.instance.pk:
#                     self.instance.skills.add(skill)
#         min_salary = cleaned_data.get('min_salary')
#         max_salary = cleaned_data.get('max_salary')
#         if min_salary and max_salary and min_salary > max_salary:
#             raise forms.ValidationError("Minimum salary cannot be greater than maximum salary.")
#         return cleaned_data


class VacancyForm(forms.ModelForm):
    tags = forms.ModelMultipleChoiceField(
        queryset=VacancyTag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2', 'data-placeholder': 'Select tags'})
    )

    skills = forms.ModelMultipleChoiceField(
        queryset=VacancySkill.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2', 'data-placeholder': 'Select skills'})
    )

    city = forms.ModelChoiceField(
        queryset=Region.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control select2', 
            'data-placeholder': 'Select Region/State',
            'id': 'id_city'
        })
    )

    class Meta:
        model = Vacancy
        fields = ['title', 'description', 'country', 'city', 'work_mode', 'skills', 'tags', 'eligibility', 'min_salary', 'max_salary', 'currency', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'country': forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select country'}),
            # 'city': forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select region/state'}),
            'work_mode': forms.Select(attrs={'class': 'form-control'}),
            'skills': forms.SelectMultiple(attrs={'class': 'form-control select2', 'data-placeholder': 'Select skills', 'multiple': 'multiple', 'id': 'id_skills'}),
            'tags': forms.SelectMultiple(attrs={'class': 'form-control select2', 'data-placeholder': 'Select tags', 'multiple': 'multiple', 'id': 'id_tags'}),
            'eligibility': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'min_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'currency': forms.Select(attrs={'class': 'form-control select2'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk:
            self.fields['skills'].initial = self.instance.skills.all()
            self.fields['tags'].initial = self.instance.tags.all()

    def clean(self):
        cleaned_data = super().clean()
        
        new_tags = self.data.get('new_tags', '')
        if new_tags:
            tag_names = [tag.strip() for tag in new_tags.split(',') if tag.strip()]
            for tag_name in tag_names:
                tag, created = VacancyTag.objects.get_or_create(name=tag_name.lower())
                if self.instance:
                    self.instance.tags.add(tag)
        
        new_skills = self.data.get('new_skills', '')
        if new_skills:
            skill_names = [skill.strip() for skill in new_skills.split(',') if skill.strip()]
            for skill_name in skill_names:
                existing_skill = VacancySkill.objects.filter(
                    name__iexact=skill_name.lower()
                ).first()
                
                if existing_skill:
                    skill = existing_skill
                else:
                    skill, created = VacancySkill.objects.get_or_create(name=skill_name.lower())
                
                if self.instance:
                    self.instance.skills.add(skill)
        
        min_salary = cleaned_data.get('min_salary')
        max_salary = cleaned_data.get('max_salary')
        if min_salary and max_salary and min_salary > max_salary:
            raise forms.ValidationError("Minimum salary cannot be greater than maximum salary.")
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if commit:
            instance.save()
            self.save_m2m()
            
            if hasattr(self, '_new_tags'):
                for tag in self._new_tags:
                    instance.tags.add(tag)
            if hasattr(self, '_new_skills'):
                for skill in self._new_skills:
                    instance.skills.add(skill)
        
        return instance
    
class VacancyApplicationForm(forms.ModelForm):
    
    class Meta:
        model = VacancyApplication
        fields = ['first_name', 'last_name', 'middle_name', 'phone', 'email', 'country', 'city', 'cv', 'cover_letter']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.Select(attrs={'class': 'form-control'}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'cv': forms.FileInput(attrs={'class':'form-control'}),
            'cover_letter': forms.Textarea(attrs={'class':'form-control'}),
        }

        def clean_attachments(self):
            cvs = self.cv.getlist('attachments')
            print("Cleaning attachments: %s", [(cv.name, cv.size, cv.content_type) for cv in cvs])
            if not cvs:
                print("No attachments provided")
                return None
            for cv in cvs:
                if cv.size > 5 * 1024 * 1024:  # 5MB limit
                    raise forms.ValidationError(f"File {cv.name} is too large (max 5MB).")
            return cvs

from documents.models import Interview, InterviewParticipant

class InterviewForm(forms.ModelForm):
    class Meta:
        model = Interview
        fields = [
            "vacancy",
            "applications",
            "interviewers",
            "is_virtual",
            "google_meet",
            "virtual_link",
            "physical_location",
            "schedule_start",
            "schedule_end",
            "timezone"
        ]
        widgets = {
            "applications": forms.CheckboxSelectMultiple(),
            "interviewers": forms.SelectMultiple(attrs={"class": "form-control select2"}),
            "schedule_start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "schedule_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "physical_location": forms.TextInput(attrs={"placeholder": "Enter physical venue (if applicable)"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_virtual = cleaned_data.get("is_virtual")
        google_meet = cleaned_data.get("google_meet")
        virtual_link = cleaned_data.get("virtual_link")
        location = cleaned_data.get("physical_location")

        if not is_virtual and not location:
            raise forms.ValidationError("Please specify a physical location for an in-person interview.")
        if is_virtual and not (google_meet or virtual_link):
            raise forms.ValidationError("Please specify either a Google Meet link or a virtual link for a virtual interview.")
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if not user or not hasattr(user, 'tenant') or not user.tenant:
            qs = VacancyApplication.objects.none()
            self.fields['vacancy'].queryset = Vacancy.objects.none()
            self.fields['applications'].queryset = qs
            self.fields['interviewers'].queryset = CustomUser.objects.none()
            return

        tenant = user.tenant

        # Always restrict vacancies & interviewers
        self.fields['vacancy'].queryset = Vacancy.objects.filter(tenant=tenant, status__in=['active',  'withdrawn'])
        self.fields['interviewers'].queryset = CustomUser.objects.filter(tenant=tenant, is_active=True)

        # DEFAULT: empty (will be filled by AJAX on frontend)
        applications_qs = VacancyApplication.objects.none()

        # CASE 1: Editing existing interview
        if self.instance.pk and self.instance.vacancy:
            applications_qs = VacancyApplication.objects.filter(
                vacancy=self.instance.vacancy,
                tenant=tenant,
                status='accepted'
            )

        # CASE 2: Form was submitted (even if invalid) → use selected vacancy from POST data
        elif self.data:
            vacancy_id = self.data.get('vacancy')

            if vacancy_id:
                try:
                    vacancy = Vacancy.objects.get(id=vacancy_id, tenant=tenant)
                    applications_qs = VacancyApplication.objects.filter(
                        vacancy=vacancy,
                        tenant=tenant,
                        status='accepted'
                    )
                except Vacancy.DoesNotExist:
                    applications_qs = VacancyApplication.objects.none()

        # THIS IS THE KEY LINE — always apply the correct queryset
        self.fields['applications'].queryset = applications_qs

        # Optional: Debug
        print(f"[FORM INIT] Applications queryset count: {applications_qs.count()}")

    def clean(self):
        cleaned = super().clean()
        s, e = cleaned.get("schedule_start"), cleaned.get("schedule_end")
        if s and e and s >= e:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned

    def clean_application(self):
        application_id = self.cleaned_data.get('application')
        if not application_id:
            return None

        # Re-fetch the application using the same logic as AJAX
        vacancy_id = self.data.get('vacancy') or (self.instance.vacancy_id if self.instance.pk else None)
        
        if not vacancy_id:
            raise forms.ValidationError("Please select a vacancy first.")
        
        try:
            application = VacancyApplication.objects.get(
                id=application_id,
                vacancy_id=vacancy_id,
                vacancy__tenant=self.user.tenant,
                status='accepted'
            )
            return application
        except VacancyApplication.DoesNotExist:
            raise forms.ValidationError("Selected application is not valid for this vacancy.")

class SelectedInterviewForm(forms.ModelForm):
    applications = forms.ModelMultipleChoiceField(
        queryset=VacancyApplication.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    class Meta:
        model = Interview
        fields = [
            "interviewers",
            "schedule_start",
            "schedule_end",
            "timezone",
            "is_virtual",
            "google_meet",
            "virtual_link",
            "physical_location",
        ]
        widgets = {
            "interviewers": forms.SelectMultiple(attrs={"class": "form-control select2"}),
            "schedule_start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "schedule_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "physical_location": forms.TextInput(attrs={"placeholder": "Enter physical venue (if applicable)"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        vacancy = kwargs.pop('vacancy', None)
        # This is key: allow pre-selected applications via initial
        self.selected_applications = kwargs.pop('applications', None)  # queryset or None

        super().__init__(*args, **kwargs)

        tenant = getattr(user, 'tenant', None) if user else None

        # Set interviewers
        if tenant:
            self.fields['interviewers'].queryset = CustomUser.objects.filter(
                tenant=tenant, is_active=True
            )
        else:
            self.fields['interviewers'].queryset = CustomUser.objects.none()

        # Set applications queryset — use passed ones or fall back to vacancy's
        if self.selected_applications is not None:
            self.fields['applications'].queryset = self.selected_applications
            # Pre-select them if coming from initial data
            if self.data:  # POST with POST
                pass  # let form handle it
            else:  # GET — use initial to pre-check
                self.fields['applications'].initial = self.selected_applications.values_list('id', flat=True)
        else:
            # Fallback: all applications for this vacancy
            if vacancy:
                self.fields['applications'].queryset = vacancy.applications.all()
            
    def clean(self):
        if not self.is_bound:
            return self.cleaned_data
        
        cleaned = super().clean()
        s, e = cleaned.get("schedule_start"), cleaned.get("schedule_end")
        if s and e and s >= e:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned

class InterviewRescheduleForm(forms.ModelForm):
    interviewers = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select"})
    )

    class Meta:
        model = Interview
        fields = [
            "schedule_start",
            "schedule_end",
            "is_virtual",
            "virtual_link",
            "physical_location",
            "interviewers",
        ]
        widgets = {
            "schedule_start": forms.DateTimeInput(attrs={
                "type": "datetime-local", "class": "form-control"
            }),
            "schedule_end": forms.DateTimeInput(attrs={
                "type": "datetime-local", "class": "form-control"
            }),
            "is_virtual": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "virtual_link": forms.URLInput(attrs={"class": "form-control"}),
            "physical_location": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields["interviewers"].queryset = CustomUser.objects.filter(
                tenant=tenant, is_active=True
            )
        else:
            self.fields["interviewers"].queryset = CustomUser.objects.none()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("schedule_start")
        end = cleaned.get("schedule_end")

        if start and start < timezone.now():
            raise forms.ValidationError("Start time must be in the future.")
        if start and end and start >= end:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned
    
class JobOfferForm(forms.ModelForm):
    class Meta:
        model = JobOffer
        fields = ["proposed_start_date", "department", "offer_letter"]
        widgets = {
            "proposed_start_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "department": forms.Select(attrs={"class": "form-select"}),
            "offer_letter": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": ".pdf,.doc,.docx"
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(tenant=tenant)


class ConferenceForm(forms.ModelForm):
    tags = forms.CharField(
        # queryset=ConferenceTag.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            "class": "form-control select2-tags",
            "data-placeholder": "Add tags"
        })
    )
    create_new_folder = forms.BooleanField(
        required=False,
        initial=False,
        label='Create new upload folder for participants',
        help_text='Automatically create a folder where participants can upload their files',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    custom_folder_name = forms.CharField(
        required=False,
        max_length=255,
        label='Custom folder name (optional)',
        help_text='Leave blank to use: "Uploads - [Conference Title]"',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Uploads - Your Conference Title'
        })
    )

    class Meta:
        model = Conference
        fields = [
            'title', 'theme', 'description', 'banner', 'start_date', 'end_date', 'conference_type', 'venue', 'virtual_link',
            'registration_required', 'registration_deadline','ticket_price', 'currency', 'early_bird_price', 'about_host',
            'early_bird_deadline', 'late_price', 'late_deadline', 'free_first_n_participants', 'max_participants_physical', 
            'max_participants_virtual', 'reminder_offsets', 'reminder_count', 'upload_folder',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'theme': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'banner': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class':'form-control'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class':'form-control'}),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'conference_type': forms.RadioSelect(),
            'venue': forms.TextInput(attrs={'class': 'form-control'}),
            'virtual_link': forms.URLInput(attrs={'class': 'form-control'}),
            'registration_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'ticket_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'currency': forms.Select(attrs={'class': 'form-control select2'}),
            'early_bird_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'late_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'free_first_n_participants': forms.NumberInput(attrs={'class': 'form-control'}),
            'about_host': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'early_bird_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'late_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'max_participants_physical': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_participants_virtual': forms.NumberInput(attrs={'class': 'form-control'}),
            'reminder_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'upload_folder': forms.Select(attrs={'class': 'form-select', 'id': 'id_upload_folder'}),
        }

    reminder_offsets = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': 'e.g. [30, 7, 3, 1]',
            'class': 'form-control'
        }),
        required=False,
        help_text="Enter a list of numbers (days before the conference) when reminders should be sent. Example: [30, 7, 3, 1]"
    )

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     if self.instance.pk:
    #         self.initial["tags"] = [str(tag.pk) for tag in self.instance.tags.all()]

    def __init__(self, *args, **kwargs):

        # Pop user/tenant from kwargs to scope folder/speaker choices
        user = kwargs.pop("user", None)
        tenant = kwargs.pop("tenant", None) or (getattr(user, "tenant", None) if user.tenant else None)

        super().__init__(*args, **kwargs)

        # Determine effective user and tenant (consider instance for editing)
        if self.instance and self.instance.pk:
            effective_user = self.instance.organizer or user
            effective_tenant = self.instance.tenant or tenant
        else:
            effective_user = user
            effective_tenant = tenant

        # ══════════════════════════════════════════════════════════════
        # 1. POPULATE upload_folder QUERYSET
        # ══════════════════════════════════════════════════════════════
        if effective_user:
            from django.db.models import Q
        
            if effective_tenant:
                # Tenant mode: show tenant folders OR user's personal folders
                folder_queryset = Folder.objects.filter(
                    Q(tenant=effective_tenant) | Q(tenant__isnull=True, created_by=effective_user)
                ).order_by('name')
            else:
                # Personal mode: only user's personal folders
                folder_queryset = Folder.objects.filter(
                tenant__isnull=True,
                created_by=effective_user
            ).order_by('name')
        
            self.fields['upload_folder'].queryset = folder_queryset
        else:
            self.fields['upload_folder'].queryset = Folder.objects.none()
    
            # Configure upload_folder field
            self.fields['upload_folder'].required = False
            self.fields['upload_folder'].empty_label = "— No upload folder yet —"
            self.fields['upload_folder'].help_text = ('Select an existing folder where participants can upload files')

        # ══════════════════════════════════════════════════════════════
        # 2. POPULATE speakers QUERYSET
        # ══════════════════════════════════════════════════════════════
        try:
            if effective_tenant:
                self.fields['speakers'].queryset = ConferenceSpeaker.objects.filter(tenant=effective_tenant).order_by('last_name', 'first_name')
            else:
                self.fields['speakers'].queryset = ConferenceSpeaker.objects.filter(tenant__isnull=True).order_by('last_name', 'first_name')
            self.fields['speakers'].required = False
        except KeyError:
            pass
        # ══════════════════════════════════════════════════════════════
        # 3. PRE-FILL TAGS (if editing existing conference)
        # ══════════════════════════════════════════════════════════════
        if self.instance.pk:
            self.initial["tags"] = [str(tag.pk) for tag in self.instance.tags.all()]
    


    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        ticket_price = cleaned.get('ticket_price')
        max_participants_physical = cleaned.get('max_participants_physical')
        max_participants_virtual = cleaned.get('max_participants_virtual')

        if start and end and start >= end:
            raise ValidationError("Start date must be before end date.")

        if ticket_price is not None and ticket_price < 0:
            raise ValidationError("Ticket price cannot be negative.")

        if max_participants_physical is not None and max_participants_physical <= 0:
            raise ValidationError("Max participants must be a positive integer or blank.")

        if max_participants_virtual is not None and max_participants_virtual <= 0:
            raise ValidationError("Max participants must be a positive integer or blank.")

        return cleaned

    def clean_reminder_offsets(self):
        data = self.cleaned_data['reminder_offsets'].strip()
        if not data:
            return []  # empty list → no reminders

        try:
            # Allow simple input like "[7, 3, 1]" or "7,3,1"
            if data.startswith('['):
                offsets = eval(data)  # safe because it's our own admin form
            else:
                offsets = [float(x.strip()) for x in data.split(',') if x.strip()]
            # Validate they are positive numbers
            if any(o < 0 for o in offsets):
                raise forms.ValidationError("Offsets must be positive numbers.")
            return offsets
        except Exception:
            raise forms.ValidationError("Invalid format. Use a comma-separated list or Python list like [7, 3, 1].")
        
    def clean_tags(self):
        """
        Convert any string values from Select2 into real ConferenceTag objects
        """
        raw_tags = self.data.getlist("tags")
        tags = []

        for item in raw_tags:
            if item.isdigit():
                tags.append(ConferenceTag.objects.get(pk=item))
            else:
                tag, _ = ConferenceTag.get_or_create_ci(item)
                tags.append(tag)

        return tags
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self.save_m2m()

        return instance

class ConferenceParticipantForm(forms.ModelForm):
    class Meta:
        model = ConferenceParticipant
        fields = [
            'title', 'first_name', 'last_name', 'age', 'gender',
            'email', 'phone_number', 'city', 'country',
            'organization', 'designation',
            'attendance_mode', 'discovery_channel',
            'price_tier',                          # ← NEW
        ]
        widgets = {
            'title':            forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select title'}),
            'first_name':       forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':        forms.TextInput(attrs={'class': 'form-control'}),
            'age':              forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select age'}),
            'gender':           forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select gender'}),
            'email':            forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number':     forms.TextInput(attrs={'class': 'form-control'}),
            'country':          forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select country'}),
            'city':             forms.TextInput(attrs={'class': 'form-control'}),
            'organization':     forms.TextInput(attrs={'class': 'form-control'}),
            'designation':      forms.TextInput(attrs={'class': 'form-control'}),
            'attendance_mode':  forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select attendance mode'}),
            'discovery_channel':forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'Select discovery channel'}),
            'price_tier':       forms.RadioSelect(),   # rendered as cards in template
        }

    def __init__(self, *args, **kwargs):
        self.conference = kwargs.pop('conference', None)
        super().__init__(*args, **kwargs)

        # ── Scope price_tier choices to this conference ───────────────────
        if self.conference:
            active_tiers = self.conference.price_tiers.filter(is_active=True).order_by('order', 'price')
            if active_tiers.exists():
                self.fields['price_tier'].queryset = active_tiers
                self.fields['price_tier'].required = True
                self.fields['price_tier'].empty_label = None
            else:
                # No tiers configured → hide field entirely
                self.fields['price_tier'].queryset = ConferencePriceTier.objects.none()
                self.fields['price_tier'].required = False
                self.fields['price_tier'].widget = forms.HiddenInput()
        else:
            self.fields['price_tier'].queryset = ConferencePriceTier.objects.none()
            self.fields['price_tier'].required = False

    def clean(self):
        super().clean()
        if self.conference and self.conference.conference_type == 'hybrid':
            if not self.cleaned_data.get('attendance_mode'):
                raise ValidationError({'attendance_mode': "Required for hybrid conferences."})

        # ── Tier capacity guard ───────────────────────────────────────────
        tier = self.cleaned_data.get('price_tier')
        if tier and not tier.is_available():
            raise ValidationError({'price_tier': f'The "{tier.name}" tier is fully booked. Please choose another.'})

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not self.conference:
            return email
        if ConferenceParticipant.objects.filter(conference=self.conference, email__iexact=email).exists():
            raise forms.ValidationError("This email is already registered for this conference.")
        return email

    def save(self, commit=True):
        self.full_clean()
        instance = super().save(commit=False)
        if self.conference:
            instance.conference = self.conference
        if commit:
            instance.save()
        return instance

class ConferenceSpeakerForm(forms.ModelForm):
    """Form for creating/editing conference speakers."""
    
    class Meta:
        model = ConferenceSpeaker
        fields = [
            'photo', 'title', 'first_name', 'middle_name', 'last_name',
            'company', 'designation', 'bio', 'email', 'phone',
            'linkedin_url', 'twitter_handle'
        ]
        
        widgets = {
            'title': forms.Select(attrs={'class': 'form-select',}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name', 'required': True,}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Middle name (optional)',}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name', 'required': True,}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company or organization',}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Job title or position',}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Brief biography or description',}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com',}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1 234 567 8900',}),
            'linkedin_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://linkedin.com/in/username',}),
            'twitter_handle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'username (without @)',}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*',}),
        }
        
        labels = {
            'title':'Title',
            'first_name': 'First Name',
            'middle_name': 'Middle Name',
            'last_name': 'Last Name',
            'company': 'Company/Organization',
            'designation': 'Job Title',
            'bio': 'Biography',
            'email': 'Email Address',
            'phone': 'Phone Number',
            'linkedin_url': 'LinkedIn Profile',
            'twitter_handle': 'Twitter Handle',
            'photo': 'Speaker Photo',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make first_name and last_name required
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        
        # Add asterisks to required fields
        for field_name, field in self.fields.items():
            if field.required:
                field.label = f"{field.label} *"
    
    def clean_twitter_handle(self):
        """Remove @ symbol if user includes it."""
        twitter = self.cleaned_data.get('twitter_handle', '')
        if twitter and twitter.startswith('@'):
            twitter = twitter[1:]
        return twitter

class BookingTypeScheduleForm(forms.ModelForm):
    class Meta:
        model  = BookingTypeSchedule
        fields = [
            'weekday', 'start_time', 'end_time', 'timezone',
            'buffer_before_minutes', 'buffer_after_minutes', 'is_active',
        ]
        widgets = {
            'weekday':    forms.Select(attrs={
                'class': 'form-select form-select-sm schedule-weekday',
            }),
            'start_time': forms.TimeInput(attrs={
                'type': 'time', 'class': 'form-control form-control-sm schedule-start',
            }),
            'end_time': forms.TimeInput(attrs={
                'type': 'time', 'class': 'form-control form-control-sm schedule-end',
            }),
            'timezone': forms.Select(attrs={
                'class': 'form-select form-select-sm schedule-tz',
            }),
            'buffer_before_minutes': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': 0, 'placeholder': '0',
            }),
            'buffer_after_minutes': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm', 'min': 0, 'placeholder': '0',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
 
    def clean(self):
        cleaned = super().clean()
        start  = cleaned.get('start_time')
        end    = cleaned.get('end_time')
        buf_b  = cleaned.get('buffer_before_minutes', 0)
        buf_a  = cleaned.get('buffer_after_minutes', 0)
 
        if start and end:
            if start >= end:
                raise forms.ValidationError("Start time must be before end time.")
            from datetime import datetime, date
            window_minutes = (
                datetime.combine(date.today(), end) -
                datetime.combine(date.today(), start)
            ).seconds // 60
            if (buf_b + buf_a) >= window_minutes:
                raise forms.ValidationError(
                    "Combined buffer minutes must be less than the window duration."
                )
        return cleaned
 
 
# Inline formset: zero or more schedule rows attached to one BookingType
BookingTypeScheduleFormSet = inlineformset_factory(
    parent_model = BookingType,
    model        = BookingTypeSchedule,
    form         = BookingTypeScheduleForm,
    extra        = 1,       # one blank row shown by default
    can_delete   = True,    # renders DELETE checkbox per row
    min_num      = 0,
    validate_min = False,
)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# BookingTypeForm  (main booking-type fields, no availability_rules)
# ─────────────────────────────────────────────────────────────────────────────
class BookingTypeForm(forms.ModelForm):
    class Meta:
        model  = BookingType
        fields = [
            'name', 'booking_for', 'host_user', 'managers',
            'duration_minutes', 'price', 'currency', 'description',
            'is_public', 'color',
            'max_bookings_per_day', 'is_multiple', 'max_capacity',
            'booking_deadline_hours', 'is_hybrid', 'location', 'virtual_link',
            'start_date', 'end_date',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. 30-min Strategy Call',
            }),
            'booking_for': forms.Select(attrs={'class': 'form-control'}),
            'host_user':   forms.Select(attrs={'class': 'form-control'}),
            'managers':    forms.SelectMultiple(attrs={'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Duration in minutes',
            }),
            'price':    forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Price'}),
            'currency': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control'}),
            'max_bookings_per_day': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Max bookings per day',
            }),
            'is_multiple': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_capacity': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Max capacity',
            }),
            'booking_deadline_hours': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': 'Hours before start',
            }),
            'is_hybrid':    forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'location':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'virtual_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Zoom / Meet link'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
            'end_date':   forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}, format='%Y-%m-%d'),
        }
 
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
 
        self.fields['start_date'].input_formats = ['%Y-%m-%d']
        self.fields['end_date'].input_formats   = ['%Y-%m-%d']
 
        if self.user and self.user.is_personal:
            # Personal-only users: hide org-level fields
            self.fields['booking_for'].required = False
            self.fields['host_user'].widget  = forms.HiddenInput()
            self.fields['managers'].widget   = forms.HiddenInput()
 
        if self.user and self.user.tenant:
            tenant_users = CustomUser.objects.filter(tenant=self.user.tenant)
            self.fields['host_user'].queryset = tenant_users
            self.fields['managers'].queryset  = tenant_users
 
    def clean(self):
        cleaned_data = super().clean()
        booking_for  = cleaned_data.get('booking_for')
 
        if booking_for == 'personal':
            cleaned_data['host_user'] = self.user
        elif booking_for == 'organization':
            if not self.user.tenant:
                raise forms.ValidationError(
                    "Organization booking services require an organization context."
                )
            host_user = cleaned_data.get('host_user')
            if not host_user:
                raise forms.ValidationError("Host user is required for organization booking services.")
            if host_user.tenant != self.user.tenant:
                raise forms.ValidationError("Host user must belong to the same organization.")
 
        start_date = cleaned_data.get('start_date')
        end_date   = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError({"end_date": "End date cannot be before start date."})
 
        return cleaned_data

class WorkHistoryForm(forms.ModelForm):
    class Meta:
        model = WorkHistory
        fields = ["organization_name", "designation", "start_date", "end_date", "mode", "description"]
        widgets = {
            'organization_name': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'mode': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }


class EducationHistoryForm(forms.ModelForm):
    class Meta:
        model = EducationHistory
        fields = ["school_name", "course", "degree", "start_date", "end_date", "certificate"]
        widgets = {
            'school_name': forms.TextInput(attrs={'class': 'form-control'}),
            'course': forms.TextInput(attrs={'class': 'form-control'}),
            'degree': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'certificate': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class PromotionHistoryForm(forms.ModelForm):
    class Meta:
        model = PromotionHistory
        fields = [
            "organization_name", "designation", "start_date", "end_date",
            "description", "promotion_letter", "salary", "department", "team",
        ]
        widgets = {
            'organization_name': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'promotion_letter': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'salary': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'team': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['department'].queryset = Department.objects.filter(tenant=tenant)
            self.fields['team'].queryset = Team.objects.filter(tenant=tenant)
        else:
            self.fields['department'].queryset = Department.objects.none()
            self.fields['team'].queryset = Team.objects.none()


class IdentityDocumentForm(forms.ModelForm):
    class Meta:
        model = IdentityDocument
        fields = ["document_type", "number", "file", "issue_date", "expiry_date"]
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'number': forms.TextInput(attrs={'class': 'form-control'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }


class AchievementForm(forms.ModelForm):
    class Meta:
        model = Achievement
        fields = ["category", "title", "issuer", "description", "date", "file", "url"]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'issuer': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'url': forms.URLInput(attrs={'class': 'form-control'}),
        }


class CompanyProductServiceForm(forms.ModelForm):
    class Meta:
        model = CompanyProductService
        fields = ["name", "description", "amount_offered", "amount_sold", "icon", "is_top"]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'amount_offered': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'amount_sold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'icon': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'is_top': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CompanyTeamHighlightForm(forms.ModelForm):
    class Meta:
        model = CompanyTeamHighlight
        fields = ["staff_profile", "display_order", "custom_title"]
        widgets = {
            'staff_profile': forms.Select(attrs={'class': 'form-control'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
            'custom_title': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['staff_profile'].queryset = StaffProfile.objects.filter(tenant=tenant)
        else:
            self.fields['staff_profile'].queryset = StaffProfile.objects.none()


class RecommendationForm(forms.ModelForm):
    """Form for writing a recommendation about another user's profile."""

    class Meta:
        model = Recommendation
        fields = ['relationship', 'body', 'work_history', 'education_history']
        widgets = {
            'relationship': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Direct Manager, Colleague, Professor'
            }),
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Write your recommendation...'
            }),
            'work_history': forms.Select(attrs={'class': 'form-control'}),
            'education_history': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'work_history': 'Link to Work Experience (optional)',
            'education_history': 'Link to Education (optional)',
        }

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['work_history'].required = False
        self.fields['education_history'].required = False
        self.fields['work_history'].empty_label = '— Not linked to a specific role —'
        self.fields['education_history'].empty_label = '— Not linked to a specific education —'
        if profile is not None:
            self.fields['work_history'].queryset = profile.work_history.all()
            self.fields['education_history'].queryset = profile.education_history.all()
        else:
            self.fields['work_history'].queryset = WorkHistory.objects.none()
            self.fields['education_history'].queryset = EducationHistory.objects.none()
