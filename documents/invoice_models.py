
       

import uuid
from django.db import models
from django.utils import timezone
from django.db import transaction
# from documents.models import CustomUser, Department
from raadaa import settings
from tenants.models import Tenant
# CustomUser and Contact already exist in documents/models.py — no re-import needed


# ─── Invoice ──────────────────────────────────────────────────────────────────

class Invoice(models.Model):

    DIRECTION = [
        ('out', 'Sent (we issue)'),
        ('in',  'Received (we pay)'),
    ]
    STATUS = [
        ('draft',     'Draft'),
        ('sent',      'Sent / Issued'),
        ('viewed',    'Viewed by recipient'),
        ('partial',   'Partially paid'),
        ('paid',      'Fully paid'),
        ('overdue',   'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    # ── Core ──────────────────────────────────────────────────────────────────
    tenant    = models.ForeignKey(Tenant, on_delete=models.CASCADE,
                                  related_name='invoices')
    direction = models.CharField(max_length=3, choices=DIRECTION, default='out')
    status    = models.CharField(max_length=12, choices=STATUS, default='draft')

    # ── Parties ───────────────────────────────────────────────────────────────
    # For outgoing: the client/customer we are billing
    # For incoming: the supplier/vendor who billed us
    contact   = models.ForeignKey('Contact', on_delete=models.PROTECT,
                                  null=True, blank=True,
                                  related_name='invoices',
                                  help_text="Recipient (sent) or Sender (received)")

    # Free-text fallback when no Contact record exists yet
    payer_name    = models.CharField(max_length=255, blank=True,
                                     help_text="Name of the party paying (incoming invoices)")
    payer_email   = models.EmailField(blank=True)
    payee_name    = models.CharField(max_length=255, blank=True,
                                     help_text="Name of the party being paid (outgoing invoices)")
    payee_email   = models.EmailField(blank=True)

    # ── Numbering ─────────────────────────────────────────────────────────────
    invoice_number = models.CharField(max_length=40, db_index=True)
    issue_date     = models.DateField(default=timezone.now)
    due_date       = models.DateField()
    currency       = models.CharField(max_length=3, default='NGN')

    # ── Line items ────────────────────────────────────────────────────────────
    # Stored as JSON list of dicts:
    # [{"product_id": 123, "name": "...", "quantity": 2,
    #   "unit_price": 1500.00, "subtotal": 3000.00}, ...]
    items        = models.JSONField(default=list)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount   = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                       help_text="Total tax component (informational)")
    discount     = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                       help_text="Discount applied before total")
    notes        = models.TextField(blank=True,
                                    help_text="Footer notes / terms visible on invoice")

    # ── Payment instructions ───────────────────────────────────────────────────
    payment_link       = models.URLField(blank=True,
                                         help_text="Paystack / Flutterwave payment link")
    bank_account_name  = models.CharField(max_length=160, blank=True)
    bank_account_number= models.CharField(max_length=20, blank=True)
    bank_name          = models.CharField(max_length=100, blank=True)
    bank_code          = models.CharField(max_length=20, blank=True,
                                          help_text="Sort code / SWIFT / routing number")

    # ── Recurring (phase 1 ) ──────────────────────────────────────────
    is_recurring     = models.BooleanField(default=False)
    recurrence_rule  = models.CharField(max_length=20, blank=True,
                                        help_text="e.g. monthly, quarterly, annually")
    next_recurrence  = models.DateField(null=True, blank=True)

    # ── Tracking & files ──────────────────────────────────────────────────────
    share_token  = models.UUIDField(default=uuid.uuid4, unique=True, editable=False,
                                    help_text="UUID used for public shareable link")
    attachment   = models.FileField(upload_to='invoices/attachments/',
                                    null=True, blank=True,
                                    help_text="Scanned PDF or supporting doc")

    # ── Audit ─────────────────────────────────────────────────────────────────
    # Invoice model — change created_by to allow null for external submissions
    created_by = models.ForeignKey('CustomUser',on_delete=models.PROTECT,related_name='created_invoices',null=True,blank=True)   

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at    = models.DateTimeField(null=True, blank=True)
    viewed_at  = models.DateTimeField(null=True, blank=True,
                                      help_text="First time the public link was accessed")
    sent_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('tenant', 'invoice_number')
        ordering = ['-issue_date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'due_date']),
            models.Index(fields=['tenant', 'direction']),
        ]

    def __str__(self):
        return f"{self.invoice_number} – {self.total_amount} {self.currency}"

    def get_absolute_url(self):
        return f"/invoices/track/{self.share_token}/"

    # ── Computed properties ────────────────────────────────────────────────────

    @property
    def is_overdue(self):
        return (self.due_date < timezone.now().date()
                and self.status not in ('paid', 'cancelled'))

    @property
    def party_display(self):
        """Human-readable counterparty name."""
        if self.contact:
            return str(self.contact)
        if self.direction == 'out':
            return self.payee_name or self.payee_email or '—'
        return self.payer_name or self.payer_email or '—'

    @property
    def party_email(self):
        if self.contact and self.contact.email:
            return self.contact.email
        return self.payee_email if self.direction == 'out' else self.payer_email

    def recalculate_total(self):
        """Recompute total_amount from items JSONField and save."""
        total = sum(
            float(item.get('subtotal', 0)) for item in (self.items or [])
        )
        self.total_amount = round(total - float(self.discount or 0), 2)

    # ── Auto invoice number ────────────────────────────────────────────────────

    @classmethod
    def generate_invoice_number(cls, tenant, direction='out') -> str:
        """
        Format: INV-{YEAR}-{NNNN} for outgoing, BILL-{YEAR}-{NNNN} for incoming.
        Sequential per tenant per year.
        """
        from django.db import transaction
        with transaction.atomic():
            year   = timezone.now().year
            prefix = 'INV' if direction == 'out' else 'BILL'
            stub   = f"{prefix}-{year}-"
            last   = cls.objects.select_for_update().filter(
                tenant=tenant,
                invoice_number__startswith=stub,
            ).order_by('-invoice_number').first()
            seq = 1
            if last:
                try:
                    seq = int(last.invoice_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            return f"{stub}{seq:04d}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = Invoice.generate_invoice_number(
                self.tenant, self.direction)
        super().save(*args, **kwargs)

# Add/replace in documents/models.py

import uuid
from django.utils import timezone


class InvoiceSendSchedule(models.Model):
    """
    Defines when/how often an invoice is sent.
    Linked OneToOne to Invoice.
    """
    FREQUENCY_CHOICES = [
        ('once',    'One-time'),
        ('daily',   'Daily'),
        ('weekly',  'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly',  'Yearly'),
    ]

    invoice       = models.OneToOneField('Invoice', on_delete=models.CASCADE,
                                         related_name='send_schedule')
    frequency     = models.CharField(max_length=10, choices=FREQUENCY_CHOICES,
                                     default='once')
    send_now      = models.BooleanField(default=False,
                                        help_text="Send immediately on save (one-time only)")
    send_date     = models.DateField(null=True, blank=True,
                                     help_text="Scheduled send date (one-time)")
    send_time     = models.TimeField(null=True, blank=True,
                                     help_text="Time of day to send")

    # Recurrence
    interval      = models.PositiveSmallIntegerField(default=1,
                    help_text="Every N days/weeks/months/years")
    days_of_week  = models.JSONField(default=list, blank=True,
                    help_text="[0=Mon … 6=Sun] for weekly recurrence")
    days_of_month = models.JSONField(default=list, blank=True,
                    help_text="[1..31] for monthly recurrence")
    month_day     = models.PositiveSmallIntegerField(null=True, blank=True,
                    help_text="Day of month for yearly recurrence")
    month_month   = models.PositiveSmallIntegerField(null=True, blank=True,
                    help_text="Month (1-12) for yearly recurrence")

    # Tracking
    last_sent_at  = models.DateTimeField(null=True, blank=True)
    next_send_at  = models.DateTimeField(null=True, blank=True)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Invoice Send Schedule'

    def __str__(self):
        return f"{self.get_frequency_display()} schedule for {self.invoice.invoice_number}"


class Receipt(models.Model):
    """
    Receipt for a paid invoice OR standalone receipt created from scratch.
    receipt_number is unique per tenant: REC-{YEAR}-{NNNN}
    """
    # Link to invoice (optional — standalone receipts have no invoice)
    invoice        = models.OneToOneField('Invoice', on_delete=models.SET_NULL,
                                          related_name='receipt',
                                          null=True, blank=True)
    
   
    tenant = models.ForeignKey('tenants.Tenant',on_delete=models.CASCADE,related_name='receipts',null=True,blank=True)
    receipt_number = models.CharField(max_length=40)

    # Payer info (auto-filled from invoice if linked, otherwise entered manually)
    payer_name     = models.CharField(max_length=255, blank=True)
    payer_email    = models.EmailField(blank=True)
    contact        = models.ForeignKey('Contact', on_delete=models.SET_NULL,
                                       null=True, blank=True,
                                       related_name='receipts')

    # Items (copied from invoice or entered manually)
    items          = models.JSONField(default=list,
                     help_text='Same format as Invoice.items')
    currency       = models.CharField(max_length=3, default='NGN')
    amount_paid    = models.DecimalField(max_digits=14, decimal_places=2)
    discount       = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    paid_at        = models.DateTimeField()
    notes          = models.TextField(blank=True)
    pdf_file       = models.FileField(upload_to='receipts/', null=True, blank=True)
    issued_by      = models.ForeignKey('CustomUser', on_delete=models.PROTECT,
                                       related_name='issued_receipts')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'receipt_number')
        ordering = ['-created_at']

    def __str__(self):
        return f"Receipt {self.receipt_number}"

    @property
    def party_display(self):
        if self.contact:
            return str(self.contact)
        return self.payer_name or self.payer_email or '—'

    @classmethod
    def generate_receipt_number(cls, tenant) -> str:
        from django.db import transaction
        with transaction.atomic():
            year = timezone.now().year
            stub = f"REC-{year}-"
            last = cls.objects.select_for_update().filter(
                tenant=tenant,
                receipt_number__startswith=stub,
            ).order_by('-receipt_number').first()
            seq = 1
            if last:
                try:
                    seq = int(last.receipt_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            return f"{stub}{seq:04d}"

    @classmethod
    def create_from_invoice(cls, invoice, issued_by) -> 'Receipt':
        """Auto-create a receipt from a paid invoice."""
        receipt_number = cls.generate_receipt_number(invoice.tenant)
        return cls.objects.create(
            invoice=invoice,
            tenant=invoice.tenant,
            receipt_number=receipt_number,
            payer_name=invoice.payer_name or invoice.payee_name,
            payer_email=invoice.payer_email or invoice.payee_email,
            contact=invoice.contact,
            items=invoice.items,
            currency=invoice.currency,
            amount_paid=invoice.total_amount,
            discount=invoice.discount,
            paid_at=invoice.paid_at or timezone.now(),
            issued_by=issued_by,
        )


class TicketCategory(models.Model):
    """
    Category defined per tenant, tied to a department/division.
    Format: {DEPT_ABBREV}-{NNN}  e.g. HR-001, TECH-003, FIN-002

    Special slug 'other' is reserved for the free-text "Other" option.
    """
    tenant      = models.ForeignKey(Tenant, on_delete=models.CASCADE,
                                    related_name='ticket_categories')
    # Optional link to department — used to derive prefix if set
    department  = models.ForeignKey(
        'Department',                       # or your existing dept model
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ticket_categories',
        help_text="Link to department/division this category belongs to",
    )
    name         = models.CharField(max_length=100)
    # slug = department abbreviation + sequential number, e.g. HR-001
    slug         = models.CharField(max_length=20,
                                    help_text="Auto-generated code e.g. HR-001, TECH-003")
    description  = models.TextField(blank=True, null=True)
    department = models.ForeignKey("documents.Department", on_delete=models.CASCADE, blank=True, null=True)
    icon         = models.CharField(max_length=60, blank=True, null=True,
                                    help_text="FontAwesome class e.g. fas fa-users")
    # Queue prefix derived from slug prefix (the part before the dash)
    queue_prefix = models.CharField(max_length=10, blank=True, null=True,
                                    help_text="Overrides prefix; defaults to department abbreviation")
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'slug')
        ordering = ('slug',)

    def __str__(self):
        return f"[{self.slug}] {self.name}"

    def get_prefix(self):
        """Return the queue prefix — department abbreviation or override."""
        if self.queue_prefix:
            return self.queue_prefix.upper()
        # Derive from slug: 'HR-001' → 'HR'
        if '-' in self.slug:
            return self.slug.split('-')[0].upper()
        return self.slug[:3].upper()

    @classmethod
    def get_or_create_other(cls, tenant):
        """Return the reserved 'Other' catch-all category for a tenant."""
        obj, _ = cls.objects.get_or_create(
            tenant=tenant, slug='OTHER',
            defaults={'name': 'Other', 'queue_prefix': 'OTH', 'is_active': True},
        )
        return obj

    @classmethod
    def generate_slug(cls, tenant, department) -> str:
        """
        Auto-generate the next slug for a department.
        e.g. department.abbreviation='HR' → HR-001, HR-002, …
        """
        prefix = department.abbreviation.upper()
        last = cls.objects.filter(
            tenant=tenant,
            slug__startswith=f"{prefix}-"
        ).order_by('-slug').first()
        if last:
            try:
                seq = int(last.slug.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f"{prefix}-{seq:03d}"


class TicketPriority(models.Model):
    """
    Three standard priority levels: Low, Medium, High.
    Global (tenant=None) or per-tenant.
    """
    LEVEL_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
    ]
    BADGE_CHOICES = [
        ('bg-secondary',          'Grey  (Low)'),
        ('bg-warning text-dark',  'Amber (Medium)'),
        ('bg-danger',             'Red   (High)'),
    ]

    name        = models.CharField(max_length=20)
    level       = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES)
    badge_class = models.CharField(max_length=40, choices=BADGE_CHOICES,
                                   default='bg-secondary')
    tenant      = models.ForeignKey(Tenant, on_delete=models.CASCADE,
                                    null=True, blank=True,
                                    related_name='ticket_priorities',
                                    help_text="Null = global, available to all tenants")

    class Meta:
        ordering = ('level',)
        verbose_name_plural = 'Ticket Priorities'
        unique_together = ('tenant', 'level')

    def __str__(self):
        return self.name

    @classmethod
    def seed_defaults(cls):
        """Create Low/Medium/High globally if they don't exist."""
        defaults = [
            ('Low',    1, 'bg-secondary'),
            ('Medium', 2, 'bg-warning text-dark'),
            ('High',   3, 'bg-danger'),
        ]
        for name, level, badge in defaults:
            cls.objects.get_or_create(
                name=name, level=level, tenant=None,
                defaults={'badge_class': badge},
            )

    @classmethod
    def for_tenant(cls, tenant):
        """Return priorities available to a tenant (own + global)."""
        from django.db.models import Q
        return cls.objects.filter(
            Q(tenant=tenant) | Q(tenant__isnull=True)
        ).order_by('level')
# ─── Ticket ───────────────────────────────────────────────────────────────────

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('new',          'New'),
        ('assigned',     'Assigned'),
        ('in_progress',  'In Progress'),
        ('pending_info', 'Pending Info'),
        ('pending',      'Pending'),
        ('escalated',    'Escalated'),
        ('reassigned',   'Reassigned'),
        ('resolved',     'Resolved'),
        ('closed',       'Closed'),
        ('reopen',       'Reopened'),
    ]
    SOURCE_CHOICES = [
        ('online',   'Online / Self-Service'),
        ('walkin',   'Walk-in / Front Desk'),
        ('phone',    'Phone'),
        ('email',    'Email'),
    ]

    # ── Identity ──────────────────────────────────────────────────────────────
    tenant        = models.ForeignKey(Tenant, on_delete=models.CASCADE,
                                      related_name='tickets')
    ticket_number = models.CharField(max_length=30, db_index=True,
                                     help_text="Auto-generated unique ticket number per tenant")
    # ── Classification ────────────────────────────────────────────────────────
    category      = models.ForeignKey(TicketCategory, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='tickets')
    priority      = models.ForeignKey(TicketPriority, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='tickets')
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                     default='new')
    source        = models.CharField(max_length=10, choices=SOURCE_CHOICES,
                                     default='online')
    # ── Content ───────────────────────────────────────────────────────────────
    title         = models.CharField(max_length=255)
    description   = models.TextField()
    # ── Parties ───────────────────────────────────────────────────────────────
    # Logged-in creator (null for guest submissions)
    created_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      related_name='tickets_created')
    # Guest details for unauthenticated submissions
    guest_name    = models.CharField(max_length=255, blank=True, null=True)
    guest_email   = models.EmailField(blank=True, null=True)
    guest_phone   = models.CharField(max_length=20, blank=True, null=True)
    # Staff assigned to handle this ticket
    assigned_to   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      related_name='tickets_assigned')
    assigned_at   = models.DateTimeField(null=True, blank=True)

    # ── Token for guest status lookup ─────────────────────────────────────────
    access_token  = models.UUIDField(default=uuid.uuid4, unique=True, editable=False,
                                     help_text="Used to let guests check ticket status without logging in")
    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    resolved_at   = models.DateTimeField(null=True, blank=True)
    closed_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('tenant', 'ticket_number')
        ordering = ('-created_at',)

    def __str__(self):
        return f"[{self.ticket_number}] {self.title}"

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def short_id(self):
        return self.ticket_number

    @property
    def submitter_display(self):
        if self.created_by:
            return self.created_by.get_full_name() or self.created_by.username
        return self.guest_name or 'Anonymous'

    @property
    def is_open(self):
        return self.status not in ('closed', 'resolved')

    # ── Auto ticket number generation ─────────────────────────────────────────

    @classmethod
    def generate_ticket_number(cls, tenant) -> str:
        """
        Generates a unique, sequential ticket number per tenant.
        Format: TKT-{YEAR}-{NNNNNN}  e.g. TKT-2026-000001
        Uses select_for_update to prevent duplicates under concurrency.
        """
        with transaction.atomic():
            year   = timezone.now().year
            prefix = f"TKT-{year}-"
            last   = cls.objects.select_for_update().filter(
                tenant=tenant,
                ticket_number__startswith=prefix
            ).order_by('-ticket_number').first()

            if last:
                try:
                    seq = int(last.ticket_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1

            return f"{prefix}{seq:06d}"

    def save(self, *args, **kwargs):
        # Auto-assign ticket number on first save
        if not self.ticket_number:
            self.ticket_number = Ticket.generate_ticket_number(self.tenant)
        # Track resolved / closed timestamps
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        if self.status == 'closed' and not self.closed_at:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)


# ─── Ticket Comment ───────────────────────────────────────────────────────────

class TicketComment(models.Model):
    """
    Public and internal notes on a ticket.
    is_internal=True comments are staff-only and hidden from the submitter.
    """
    ticket      = models.ForeignKey(Ticket, on_delete=models.CASCADE,
                                    related_name='comments')
    # Logged-in author
    author      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name='ticket_comments')
    # Guest author details
    author_name  = models.CharField(max_length=255, blank=True, null=True)
    author_email = models.EmailField(blank=True, null=True)

    content     = models.TextField()
    is_internal = models.BooleanField(default=False,
                                      help_text="Internal notes visible only to staff")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('created_at',)

    def __str__(self):
        prefix = '[INTERNAL] ' if self.is_internal else ''
        label  = self.author.username if self.author else (self.author_name or 'Guest')
        return f"{prefix}{label} on {self.ticket.ticket_number}"

    @property
    def author_display(self):
        if self.author:
            return self.author.get_full_name() or self.author.username
        return self.author_name or 'Anonymous'


# ─── Queue Entry ─────────────────────────────────────────────────────────────

class QueueEntry(models.Model):
    """
    Daily queue token.
    Queue numbers reset every day and are sequential per category per tenant.
    Format: {prefix}-{NNN}  e.g.  F-001, HR-042, IT-007
    """
    STATUS_CHOICES = [
        ('waiting',   'Waiting'),
        ('serving',   'Being Served'),
        ('completed', 'Completed'),
        ('no_show',   'No Show'),
        ('skipped',   'Skipped'),
    ]
    SOURCE_CHOICES = [
        ('online',  'Online / Self-Service'),
        ('walkin',  'Walk-in / Front Desk'),
    ]

    # ── Identity ──────────────────────────────────────────────────────────────
    tenant        = models.ForeignKey(Tenant, on_delete=models.CASCADE,
                                      related_name='queue_entries')
    queue_number  = models.CharField(max_length=20,
                                     help_text="e.g. F-001, HR-042")
    category      = models.ForeignKey(TicketCategory, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='queue_entries')
    department    = models.CharField(max_length=100, blank=True, null=True)

    # ── Status ────────────────────────────────────────────────────────────────
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                     default='waiting')
    source        = models.CharField(max_length=10, choices=SOURCE_CHOICES,
                                     default='walkin')

    # ── Customer ──────────────────────────────────────────────────────────────
    customer_name  = models.CharField(max_length=255, blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    # If the customer is a registered user
    customer_user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True,
                                       related_name='queue_entries')

    # ── Linked ticket ─────────────────────────────────────────────────────────
    # FK (not OneToOne) because the same ticket can have multiple queue entries
    # across different days (returning customer spec).
    ticket        = models.ForeignKey(Ticket, on_delete=models.SET_NULL,
                                      null=True, blank=True,
                                      related_name='queue_entries',
                                      help_text="Ticket linked to this queue entry (optional)")

    # ── Timestamps ────────────────────────────────────────────────────────────
    issued_at    = models.DateTimeField(default=timezone.now)
    called_at    = models.DateTimeField(null=True, blank=True,
                                        help_text="When the number was called/served")
    completed_at = models.DateTimeField(null=True, blank=True)

    # ── Staff who served ──────────────────────────────────────────────────────
    served_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name='served_queue_entries')
    notes        = models.TextField(blank=True, null=True)

    class Meta:
        # queue_number unique per tenant per day
        unique_together = ('tenant', 'queue_number', 'issued_at')
        ordering = ('issued_at',)
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'issued_at']),
        ]

    def __str__(self):
        return f"{self.queue_number} — {self.get_status_display()} ({self.tenant.name})"

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def display_number(self):
        return self.queue_number

    @property
    def customer_display(self):
        if self.customer_user:
            return self.customer_user.get_full_name() or self.customer_user.username
        return self.customer_name or 'Walk-in'

    @property
    def wait_time(self):
        """Minutes from issuance to being called."""
        if self.called_at and self.issued_at:
            delta = self.called_at - self.issued_at
            return int(delta.total_seconds() // 60)
        return None

    @property
    def service_time(self):
        """Minutes from being called to completion."""
        if self.called_at and self.completed_at:
            delta = self.completed_at - self.called_at
            return int(delta.total_seconds() // 60)
        return None

    # ── Queue number generation ────────────────────────────────────────────────

    @classmethod
    def generate_queue_number(cls, tenant, category) -> str:
        """
        Atomically generates the next sequential queue number for today.
        Format: {PREFIX}-{NNN}  e.g. F-001, HR-042
        Resets to 001 every new day.
        """
        with transaction.atomic():
            today  = timezone.localdate()
            prefix = category.get_prefix() if category else 'Q'

            last = cls.objects.select_for_update().filter(
                tenant=tenant,
                category=category,
                issued_at__date=today,
            ).order_by('-issued_at').first()

            if last:
                try:
                    seq = int(last.queue_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1

            return f"{prefix}-{seq:03d}"

    def mark_called(self, staff_user=None):
        self.status    = 'serving'
        self.called_at = timezone.now()
        if staff_user:
            self.served_by = staff_user
        self.save(update_fields=['status', 'called_at', 'served_by'])

    def mark_completed(self):
        self.status       = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])

    def mark_no_show(self):
        self.status = 'no_show'
        self.save(update_fields=['status'])


# ─── Ticket Status History ────────────────────────────────────────────────────

class TicketStatusHistory(models.Model):
    """
    Immutable audit log of every status change on a ticket.
    """
    ticket     = models.ForeignKey(Ticket, on_delete=models.CASCADE,
                                   related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True, null=True)
    to_status   = models.CharField(max_length=20)
    changed_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True)
    note        = models.TextField(blank=True, null=True,
                                   help_text="Optional reason for the status change")
    changed_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('changed_at',)
        verbose_name_plural = 'Ticket Status Histories'

    def __str__(self):
        return f"{self.ticket.ticket_number}: {self.from_status} → {self.to_status}"
