

# tickets/forms.py
import json
from django import forms
from .invoice_models import Ticket, TicketComment, TicketCategory, TicketPriority, QueueEntry, Invoice, Receipt, InvoiceSendSchedule
from documents.models import CustomUser, Department, Contact
from django.db.models import Q
from django.utils import timezone
from crm.models import Product

try:
    from crm.models import Product
    HAS_PRODUCT = True
except ImportError:
    HAS_PRODUCT = False


class TenantScopedMixin:
    """Scope all FK querysets to the current tenant."""
    def  __init__(self, *args, tenant=None, user=None, **kwargs):
        self.tenant = tenant
        self.user = user
        super().__init__(*args, **kwargs)
        if tenant:
            self._scope_to_tenant()
    
    def _scope_to_tenant(self):
        if 'contact' in self.fields:
            self.fields['contact'].queryset = Contact.objects.filter(tenant=self.tenant).order_by('name')

# ─── Ticket Status Update ─────────────────────────────────────────────────────

class TicketStatusForm(forms.ModelForm):
    """Staff-only: change ticket status + optional reason note."""
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Reason for status change (optional)',
        }),
        help_text='This note will be saved to the audit history.',
    )

    class Meta:
        model  = Ticket
        fields = ('status',)
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


# ─── Ticket Assignment ────────────────────────────────────────────────────────

class TicketAssignForm(forms.ModelForm):
    """Staff-only: assign or reassign a ticket to a staff member."""
    class Meta:
        model  = Ticket
        fields = ('assigned_to', 'priority')
        widgets = {
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'priority':    forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                tenant=tenant, is_active=True
            ).order_by('first_name', 'last_name')
        self.fields['priority'].queryset    = TicketPriority.objects.order_by('level')
        self.fields['assigned_to'].required = False


# ─── Ticket Comment ───────────────────────────────────────────────────────────

class TicketCommentForm(forms.ModelForm):
    """
    Add a comment to a ticket.
    Staff see the is_internal toggle; public/guest form hides it.
    """
    class Meta:
        model  = TicketComment
        fields = ('content', 'is_internal')
        widgets = {
            'content':     forms.Textarea(attrs={
                               'class': 'form-control', 'rows': 3,
                               'placeholder': 'Write your comment…'}),
            'is_internal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_internal': 'Internal note (staff-only, not visible to submitter)',
        }

    def __init__(self, *args, is_staff=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_staff:
            # Hide internal toggle from public/guest users
            self.fields.pop('is_internal')


# ─── Guest Ticket Lookup ──────────────────────────────────────────────────────

class TicketLookupForm(forms.Form):
    """
    Lets guests check their ticket status using ticket number + email/phone.
    """
    ticket_number = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. TKT-2026-000001'}),
    )
    email_or_phone = forms.CharField(
        label='Email or Phone',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address or phone number used when submitting'}),
    )






from django.db.models import Q


# ─── Category Management Form (for admin/HR to create categories) ─────────────

class TicketCategoryForm(forms.ModelForm):
    """
    HR / Admin creates a category tied to a department.
    Slug is auto-generated from department abbreviation + sequence.
    """
    class Meta:
        model  = TicketCategory
        fields = ('department', 'name', 'description', 'icon',
                  'queue_prefix', 'is_active')
        widgets = {
            'department':   forms.Select(attrs={'class': 'form-select select2'}),
            'name':         forms.TextInput(attrs={'class': 'form-control',
                            'placeholder': 'e.g. Human Resource Enquiries'}),
            'description':  forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'icon':         forms.TextInput(attrs={'class': 'form-control',
                            'placeholder': 'fas fa-users (optional)'}),
            'queue_prefix': forms.TextInput(attrs={'class': 'form-control',
                            'placeholder': 'Auto-derived from department if blank'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant:
            self.fields['department'].queryset = Department.objects.filter(
                tenant=tenant).order_by('name')
        self.fields['department'].required = False
        self.fields['queue_prefix'].required = False

    def save(self, commit=True):
        cat = super().save(commit=False)
        cat.tenant = self.tenant
        # Auto-generate slug if not already set
        if not cat.slug:
            if cat.department:
                cat.slug = TicketCategory.generate_slug(self.tenant, cat.department)
            else:
                # No department — use queue_prefix or name initials
                prefix = (cat.queue_prefix or cat.name[:3]).upper().replace(' ', '')
                last = TicketCategory.objects.filter(
                    tenant=self.tenant,
                    slug__startswith=f"{prefix}-"
                ).order_by('-slug').first()
                seq = 1
                if last:
                    try:
                        seq = int(last.slug.split('-')[-1]) + 1
                    except ValueError:
                        seq = 1
                cat.slug = f"{prefix}-{seq:03d}"
        if commit:
            cat.save()
        return cat


# ───  Public Ticket Form ────────────────────────────────────────────────

class TicketCreatePublicForm(forms.ModelForm):
    """
    Public ticket submission.
    Category includes all active tenant categories + an 'Other' option
    with a free-text field for custom specification.
    """
    # Free-text field shown when "Other" is selected
    other_category = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Please specify your category / department',
            'id': 'id_other_category',
        }),
        label='Specify category',
    )

    class Meta:
        model  = Ticket
        fields = ('category', 'priority', 'title', 'description',
                  'guest_name', 'guest_email', 'guest_phone')
        widgets = {
            'category':    forms.Select(attrs={
                               'class': 'form-select',
                               'id': 'id_category',
                               'onchange': 'toggleOtherCategory(this)'}),
            'priority':    forms.Select(attrs={'class': 'form-select'}),
            'title':       forms.TextInput(attrs={
                               'class': 'form-control',
                               'placeholder': 'Brief summary of your issue'}),
            'description': forms.Textarea(attrs={
                               'class': 'form-control', 'rows': 5,
                               'placeholder': 'Describe your issue in detail'}),
            'guest_name':  forms.TextInput(attrs={
                               'class': 'form-control', 'placeholder': 'Full name'}),
            'guest_email': forms.EmailInput(attrs={
                               'class': 'form-control', 'placeholder': 'Email address'}),
            'guest_phone': forms.TextInput(attrs={
                               'class': 'form-control', 'placeholder': 'Phone number'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant:
            # Active categories + Other sentinel
            cats = list(TicketCategory.objects.filter(
                tenant=tenant, is_active=True).exclude(slug='OTHER').order_by('slug'))
            other = TicketCategory.get_or_create_other(tenant)
            # Build choices manually so Other is always last
            choices = [('', '— Select category —')]
            for c in cats:
                choices.append((c.pk, f"[{c.slug}] {c.name}"))
            choices.append((other.pk, 'Other (please specify)'))
            self.fields['category'].choices = choices
            self.fields['category'].queryset = TicketCategory.objects.filter(
                tenant=tenant, is_active=True)

        self.fields['priority'].queryset = TicketPriority.for_tenant(tenant)
        self.fields['guest_name'].required  = True
        self.fields['guest_email'].required = True

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        other_text = cleaned.get('other_category', '').strip()
        if category and category.slug == 'OTHER' and not other_text:
            self.add_error('other_category',
                'Please specify your category when selecting "Other".')
        return cleaned

    def save(self, commit=True):
        ticket = super().save(commit=False)
        # Store other_category text in notes if Other was selected
        category = self.cleaned_data.get('category')
        other_text = self.cleaned_data.get('other_category', '').strip()
        if category and category.slug == 'OTHER' and other_text:
            prefix = f"[Category: {other_text}]\n"
            ticket.description = prefix + (ticket.description or '')
        if commit:
            ticket.save()
        return ticket


# ───  Staff Ticket Form ────────────────────────────────────────────────

class TicketCreateStaffForm(forms.ModelForm):
    """Staff walk-in ticket form with Other category support."""
    other_category = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Specify category / department',
            'id': 'id_other_category',
        }),
        label='Specify category',
    )

    class Meta:
        model  = Ticket
        fields = ('category', 'priority', 'title', 'description',
                  'guest_name', 'guest_email', 'guest_phone',
                  'created_by', 'assigned_to', 'source')
        widgets = {
            'category':    forms.Select(attrs={
                               'class': 'form-select',
                               'onchange': 'toggleOtherCategory(this)'}),
            'priority':    forms.Select(attrs={'class': 'form-select'}),
            'source':      forms.Select(attrs={'class': 'form-select'}),
            'title':       forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'guest_name':  forms.TextInput(attrs={'class': 'form-control'}),
            'guest_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'guest_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'created_by':  forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant:
            staff_qs = CustomUser.objects.filter(tenant=tenant, is_active=True)
            cats = list(TicketCategory.objects.filter(
                tenant=tenant, is_active=True).exclude(slug='OTHER').order_by('slug'))
            other = TicketCategory.get_or_create_other(tenant)
            choices = [('', '— Select category —')]
            for c in cats:
                choices.append((c.pk, f"[{c.slug}] {c.name}"))
            choices.append((other.pk, 'Other (please specify)'))
            self.fields['category'].choices = choices
            self.fields['category'].queryset = TicketCategory.objects.filter(
                tenant=tenant, is_active=True)
            self.fields['created_by'].queryset  = staff_qs.order_by('first_name')
            self.fields['assigned_to'].queryset = staff_qs.order_by('first_name')
        self.fields['priority'].queryset    = TicketPriority.for_tenant(tenant)
        self.fields['created_by'].required  = False
        self.fields['assigned_to'].required = False


# ───  Queue Issue Form ─

class QueueIssueForm(forms.Form):
    """
    Front-desk queue number issuance.
    Now supports:
      - Attach existing ticket by ticket number + verification
      - Or create a new ticket inline
    """
    category = forms.ModelChoiceField(
        queryset=TicketCategory.objects.none(),
        empty_label='— Select category —',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_queue_category'}),
    )
    other_category = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Specify category / department',
            'id': 'id_queue_other',
        }),
        label='Specify category',
    )
    customer_name  = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Customer name (optional)'}),
    )
    customer_phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': 'Phone number'}),
    )
    customer_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control', 'placeholder': 'Email (optional)'}),
    )
    source = forms.ChoiceField(
        choices=[('walkin', 'Walk-in'), ('online', 'Online')],
        initial='walkin',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    # ── Ticket attachment mode ─────────────────────────────────────────────────
    TICKET_MODE_CHOICES = [
        ('none',     'No ticket — queue only'),
        ('existing', 'Attach existing ticket'),
        ('new',      'Create new ticket'),
    ]
    ticket_mode = forms.ChoiceField(
        choices=TICKET_MODE_CHOICES,
        initial='none',
        widget=forms.RadioSelect(attrs={'class': 'ticket-mode-radio'}),
        label='Ticket',
    )

    # ── Existing ticket fields ─────────────────────────────────────────────────
    existing_ticket_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. TKT-2026-000042',
            'id': 'id_existing_ticket_number',
        }),
        label='Ticket Number',
    )
    verify_email_or_phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email or phone used when ticket was submitted',
        }),
        label='Verify with email or phone',
    )

    # ── New ticket fields ──────────────────────────────────────────────────────
    ticket_title = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Brief issue title (required if creating ticket)',
        }),
    )
    ticket_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Issue description (optional)',
        }),
    )
    ticket_priority = forms.ModelChoiceField(
        queryset=TicketPriority.objects.none(),
        required=False,
        empty_label='— Priority —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant:
            cats = list(TicketCategory.objects.filter(
                tenant=tenant, is_active=True).exclude(slug='OTHER').order_by('slug'))
            other = TicketCategory.get_or_create_other(tenant)
            choices = [('', '— Select category —')]
            for c in cats:
                choices.append((c.pk, f"[{c.slug}] {c.name}"))
            choices.append((other.pk, 'Other (please specify)'))
            self.fields['category'].choices = choices
            self.fields['category'].queryset = TicketCategory.objects.filter(
                tenant=tenant, is_active=True)
            self.fields['ticket_priority'].queryset = TicketPriority.for_tenant(tenant)

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('ticket_mode', 'none')
        category = cleaned.get('category')

        # Other category validation
        if category and category.slug == 'OTHER':
            if not cleaned.get('other_category', '').strip():
                self.add_error('other_category',
                    'Please specify the category.')

        if mode == 'existing':
            ticket_num = cleaned.get('existing_ticket_number', '').strip()
            verify     = cleaned.get('verify_email_or_phone', '').strip()
            if not ticket_num:
                self.add_error('existing_ticket_number',
                    'Please enter a ticket number.')
            elif not verify:
                self.add_error('verify_email_or_phone',
                    'Please enter an email or phone to verify the ticket.')
            else:
                # Verify ticket exists and belongs to this tenant
                try:
                    ticket = Ticket.objects.get(
                        tenant=self.tenant,
                        ticket_number__iexact=ticket_num,
                    )
                    # Verify customer details
                    if not (
                        (ticket.guest_email and
                         ticket.guest_email.lower() == verify.lower()) or
                        (ticket.guest_phone and ticket.guest_phone == verify) or
                        (ticket.created_by and
                         ticket.created_by.email.lower() == verify.lower())
                    ):
                        self.add_error('verify_email_or_phone',
                            'Details do not match the ticket. '
                            'Check the email or phone number.')
                    else:
                        cleaned['_verified_ticket'] = ticket
                except Ticket.DoesNotExist:
                    self.add_error('existing_ticket_number',
                        f'Ticket "{ticket_num}" not found.')

        elif mode == 'new':
            if not cleaned.get('ticket_title', '').strip():
                self.add_error('ticket_title',
                    'Please provide a title for the new ticket.')

        return cleaned






#invoice forms

class InvoiceSendForm(TenantScopedMixin, forms.ModelForm):
    """
    Creates an outgoing invoice (direction='out').
    Line items are submitted as a JSON string from the JS-managed table.
    """
    # Hidden field — JS serialises line items into this before submit
    items_json = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )

    class Meta:
        model  = Invoice
        fields = (
            'contact', 'payee_name', 'payee_email',
            'due_date', 'currency',
            'payment_link', 'bank_account_name', 'bank_account_number',
            'bank_name', 'bank_code',
            'discount', 'notes', 'attachment',
            'is_recurring', 'recurrence_rule',
        )
        widgets = {
            'contact':             forms.Select(attrs={'class': 'form-select select2'}),
            'payee_name':          forms.TextInput(attrs={'class': 'form-control',
                                   'placeholder': 'Or enter recipient name manually'}),
            'payee_email':         forms.EmailInput(attrs={'class': 'form-control',
                                   'placeholder': 'Recipient email'}),
            'due_date':            forms.DateInput(attrs={'class': 'form-control',
                                   'type': 'date'}),
            'currency':            forms.TextInput(attrs={'class': 'form-control',
                                   'placeholder': 'NGN'}),
            'payment_link':        forms.URLInput(attrs={'class': 'form-control',
                                   'placeholder': 'https://paystack.com/pay/...'}),
            'bank_account_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name':           forms.TextInput(attrs={'class': 'form-control'}),
            'bank_code':           forms.TextInput(attrs={'class': 'form-control'}),
            'discount':            forms.NumberInput(attrs={'class': 'form-control',
                                   'step': '0.01', 'min': '0'}),
            'notes':               forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                   'placeholder': 'Payment terms, thank-you note, etc.'}),
            'attachment':          forms.FileInput(attrs={'class': 'form-control'}),
            'recurrence_rule':     forms.Select(attrs={'class': 'form-select'},
                                   choices=[('', '—'), ('monthly', 'Monthly'),
                                            ('quarterly', 'Quarterly'), ('annually', 'Annually')]),
        }

    def clean(self):
        cleaned = super().clean()

        # Parse items from hidden JSON field
        raw = self.data.get('items_json', '[]')
        try:
            items = json.loads(raw) if raw else []
        except (json.JSONDecodeError, ValueError):
            items = []

        # Validate + enrich each line item against Product if available
        validated_items = []
        for item in items:
            if not item.get('name') and not item.get('product_id'):
                continue  # skip empty rows
            quantity   = float(item.get('quantity', 1) or 1)
            unit_price = float(item.get('unit_price', 0) or 0)
            subtotal   = round(quantity * unit_price, 2)

            row = {
                'name':       item.get('name', ''),
                'quantity':   quantity,
                'unit_price': unit_price,
                'subtotal':   subtotal,
            }
            product_id = item.get('product_id')
            if product_id and HAS_PRODUCT:
                try:
                    product = Product.objects.get(
                        id=product_id, tenant=self.tenant)
                    row['product_id']  = product.pk
                    row['name']        = row['name'] or product.name
                    row['unit_price']  = row['unit_price'] or float(product.unit_price)
                    row['subtotal']    = round(row['quantity'] * row['unit_price'], 2)
                except Product.DoesNotExist:
                    pass
            validated_items.append(row)

        if not validated_items:
            raise forms.ValidationError(
                "Please add at least one line item to the invoice.")

        cleaned['items'] = validated_items
        # Calculate total
        discount = float(cleaned.get('discount') or 0)
        cleaned['total_amount'] = max(
            round(sum(i['subtotal'] for i in validated_items) - discount, 2), 0)
        return cleaned

    def save(self, commit=True):
        invoice = super().save(commit=False)
        invoice.direction    = 'out'
        invoice.items        = self.cleaned_data['items']
        invoice.total_amount = self.cleaned_data['total_amount']
        if self.user:
            invoice.created_by = self.user
        if commit:
            invoice.save()
        return invoice


# ─── Incoming Invoice (Receive) ───────────────────────────────────────────────

class InvoiceReceiveForm(TenantScopedMixin, forms.ModelForm):
    """
    Records an invoice received from a supplier/vendor (direction='in').
    """
    items_json = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model  = Invoice
        fields = (
            'contact', 'payer_name', 'payer_email',
            'due_date', 'currency', 'discount',
            'notes', 'attachment',
        )
        widgets = {
            'contact':    forms.Select(attrs={'class': 'form-select select2'}),
            'payer_name': forms.TextInput(attrs={'class': 'form-control',
                          'placeholder': 'Supplier / vendor name'}),
            'payer_email':forms.EmailInput(attrs={'class': 'form-control'}),
            'due_date':   forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'currency':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'NGN'}),
            'discount':   forms.NumberInput(attrs={'class': 'form-control',
                          'step': '0.01', 'min': '0'}),
            'notes':      forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        # Reuse same item parsing logic as InvoiceSendForm
        cleaned = super().clean()
        raw = self.data.get('items_json', '[]')
        try:
            items = json.loads(raw) if raw else []
        except (json.JSONDecodeError, ValueError):
            items = []

        validated_items = []
        for item in items:
            if not item.get('name'):
                continue
            quantity   = float(item.get('quantity', 1) or 1)
            unit_price = float(item.get('unit_price', 0) or 0)
            validated_items.append({
                'name':       item['name'],
                'quantity':   quantity,
                'unit_price': unit_price,
                'subtotal':   round(quantity * unit_price, 2),
            })

        discount = float(cleaned.get('discount') or 0)
        cleaned['items']        = validated_items
        cleaned['total_amount'] = max(
            round(sum(i['subtotal'] for i in validated_items) - discount, 2), 0)
        return cleaned

    def save(self, commit=True):
        invoice = super().save(commit=False)
        invoice.direction    = 'in'
        invoice.items        = self.cleaned_data['items']
        invoice.total_amount = self.cleaned_data['total_amount']
        if self.user:
            invoice.created_by = self.user
        if commit:
            invoice.save()
        return invoice


# ─── Mark Paid ────────────────────────────────────────────────────────────────

class MarkPaidForm(forms.Form):
    """
    Staff manually marks an invoice as paid.
    Creates a Payment and generates a Receipt.
    """
    amount_paid = forms.DecimalField(
        max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
    )
    paid_at = forms.DateTimeField(
        initial=timezone.now,
        widget=forms.DateTimeInput(attrs={
            'class': 'form-control', 'type': 'datetime-local'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Payment reference, bank transfer ID, etc.'}),
    )

    def clean_amount_paid(self):
        amount = self.cleaned_data['amount_paid']
        if amount <= 0:
            raise forms.ValidationError("Amount paid must be greater than zero.")
        return amount
    

class InvoiceExternalSubmitForm(forms.ModelForm):
    """
    Public form for external vendors/suppliers to submit invoices.
    No login required. Collects submitter contact details + line items.
    """
    items_json = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model  = Invoice
        fields = (
            # Submitter (the vendor)
            'payer_name', 'payer_email',
            # Invoice meta
            'invoice_number', 'issue_date', 'due_date', 'currency',
            # Payment details the vendor expects
            'bank_account_name', 'bank_account_number', 'bank_name', 'bank_code',
            'payment_link',
            # Extras
            'discount', 'notes', 'attachment',
        )
        widgets = {
            'payer_name':          forms.TextInput(attrs={
                                   'class': 'form-control',
                                   'placeholder': 'Your company / full name'}),
            'payer_email':         forms.EmailInput(attrs={
                                   'class': 'form-control',
                                   'placeholder': 'Your email address'}),
            'invoice_number':      forms.TextInput(attrs={
                                   'class': 'form-control',
                                   'placeholder': 'Your internal invoice reference'}),
            'issue_date':          forms.DateInput(attrs={
                                   'class': 'form-control', 'type': 'date'}),
            'due_date':            forms.DateInput(attrs={
                                   'class': 'form-control', 'type': 'date'}),
            'currency':            forms.TextInput(attrs={
                                   'class': 'form-control', 'placeholder': 'NGN'}),
            'bank_account_name':   forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name':           forms.TextInput(attrs={'class': 'form-control'}),
            'bank_code':           forms.TextInput(attrs={
                                   'class': 'form-control',
                                   'placeholder': 'Sort code / SWIFT (optional)'}),
            'payment_link':        forms.URLInput(attrs={
                                   'class': 'form-control',
                                   'placeholder': 'https://... (optional)'}),
            'discount':            forms.NumberInput(attrs={
                                   'class': 'form-control',
                                   'step': '0.01', 'min': '0'}),
            'notes':               forms.Textarea(attrs={
                                   'class': 'form-control', 'rows': 3,
                                   'placeholder': 'Payment terms, notes, references…'}),
            'attachment':          forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'payer_name':  'Your Name / Company',
            'payer_email': 'Your Email Address',
        }

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        self.fields['payer_name'].required  = True
        self.fields['payer_email'].required = True
        self.fields['due_date'].required    = True
        self.fields['invoice_number'].required = False  # we'll auto-assign if blank
        self.fields['issue_date'].required  = False

    def clean(self):
        cleaned = super().clean()
        # Parse line items
        raw = self.data.get('items_json', '[]')
        try:
            items = json.loads(raw) if raw else []
        except (json.JSONDecodeError, ValueError):
            items = []

        validated = []
        for item in items:
            if not item.get('name'):
                continue
            qty   = float(item.get('quantity', 1) or 1)
            price = float(item.get('unit_price', 0) or 0)
            validated.append({
                'name':       item['name'],
                'quantity':   qty,
                'unit_price': price,
                'subtotal':   round(qty * price, 2),
            })

        if not validated:
            raise forms.ValidationError(
                "Please add at least one line item to your invoice.")

        discount = float(cleaned.get('discount') or 0)
        cleaned['items']        = validated
        cleaned['total_amount'] = max(
            round(sum(i['subtotal'] for i in validated) - discount, 2), 0)
        return cleaned
# documents/forms/invoice_forms.py — add these forms

class ReceiptStandaloneForm(TenantScopedMixin, forms.ModelForm):
    """
    Create a receipt from scratch (no linked invoice).
    """
    items_json = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model  = Receipt
        fields = ('contact', 'payer_name', 'payer_email',
                  'currency', 'discount', 'paid_at', 'notes')
        widgets = {
            'contact':    forms.Select(attrs={'class': 'form-select select2',
                          'id': 'id_receipt_contact'}),
            'payer_name': forms.TextInput(attrs={'class': 'form-control',
                          'placeholder': 'Or enter payer name manually'}),
            'payer_email':forms.EmailInput(attrs={'class': 'form-control'}),
            'currency':   forms.TextInput(attrs={'class': 'form-control',
                          'placeholder': 'NGN'}),
            'discount':   forms.NumberInput(attrs={'class': 'form-control',
                          'step': '0.01', 'min': '0'}),
            'paid_at':    forms.DateTimeInput(attrs={'class': 'form-control',
                          'type': 'datetime-local'}),
            'notes':      forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()
        raw = self.data.get('items_json', '[]')
        try:
            items = json.loads(raw) if raw else []
        except (json.JSONDecodeError, ValueError):
            items = []

        validated = []
        for item in items:
            if not item.get('name'):
                continue
            qty   = float(item.get('quantity', 1) or 1)
            price = float(item.get('unit_price', 0) or 0)
            validated.append({
                'name':       item['name'],
                'quantity':   qty,
                'unit_price': price,
                'subtotal':   round(qty * price, 2),
            })

        if not validated:
            raise forms.ValidationError("Please add at least one line item.")

        discount = float(cleaned.get('discount') or 0)
        cleaned['items']        = validated
        cleaned['amount_paid']  = max(
            round(sum(i['subtotal'] for i in validated) - discount, 2), 0)
        return cleaned

    def save(self, commit=True):
        receipt = super().save(commit=False)
        receipt.items       = self.cleaned_data['items']
        receipt.amount_paid = self.cleaned_data['amount_paid']
        receipt.receipt_number = Receipt.generate_receipt_number(self.tenant)
        if self.user:
            receipt.issued_by = self.user
        if commit:
            receipt.save()
        return receipt


class InvoiceSendScheduleForm(forms.ModelForm):
    """
    Embedded in the invoice form — controls when/how often the invoice is sent.
    """
    WEEKDAY_CHOICES = [
        (0, 'Mon'), (1, 'Tue'), (2, 'Wed'),
        (3, 'Thu'), (4, 'Fri'), (5, 'Sat'), (6, 'Sun'),
    ]
    MONTH_DAY_CHOICES = [(d, str(d)) for d in range(1, 32)]

    days_of_week_field  = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Days of week',
    )
    days_of_month_field = forms.MultipleChoiceField(
        choices=MONTH_DAY_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Days of month',
    )

    class Meta:
        model  = InvoiceSendSchedule
        fields = ('frequency', 'send_now', 'send_date', 'send_time',
                  'interval', 'month_day', 'month_month')
        widgets = {
            'frequency':   forms.Select(attrs={
                           'class': 'form-select', 'id': 'id_freq',
                           'onchange': 'onFreqChange(this)'}),
            'send_now':    forms.CheckboxInput(attrs={'class': 'form-check-input',
                           'id': 'id_send_now',
                           'onchange': 'onSendNowChange(this)'}),
            'send_date':   forms.DateInput(attrs={'class': 'form-control',
                           'type': 'date', 'id': 'id_send_date'}),
            'send_time':   forms.TimeInput(attrs={'class': 'form-control',
                           'type': 'time', 'id': 'id_send_time'}),
            'interval':    forms.NumberInput(attrs={'class': 'form-control',
                           'min': '1', 'id': 'id_interval'}),
            'month_day':   forms.NumberInput(attrs={'class': 'form-control',
                           'min': '1', 'max': '31'}),
            'month_month': forms.Select(attrs={'class': 'form-select'},
                           choices=[
                               (1,'January'),(2,'February'),(3,'March'),
                               (4,'April'),(5,'May'),(6,'June'),
                               (7,'July'),(8,'August'),(9,'September'),
                               (10,'October'),(11,'November'),(12,'December'),
                           ]),
        }

    def clean(self):
        cleaned = super().clean()
        # Merge multi-choice fields into JSONField lists
        cleaned['days_of_week']  = [int(d) for d in
                                     cleaned.get('days_of_week_field', [])]
        cleaned['days_of_month'] = [int(d) for d in
                                     cleaned.get('days_of_month_field', [])]
        return cleaned

    def save(self, commit=True):
        schedule = super().save(commit=False)
        schedule.days_of_week  = self.cleaned_data.get('days_of_week', [])
        schedule.days_of_month = self.cleaned_data.get('days_of_month', [])
        if commit:
            schedule.save()
        return schedule
