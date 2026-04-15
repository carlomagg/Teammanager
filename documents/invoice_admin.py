from django.contrib import admin, messages
from .models import Ticket, TicketComment, TicketStatusHistory, QueueEntry, TicketCategory, TicketPriority
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Invoice, InvoiceSendSchedule, Receipt


class TicketCommentInline(admin.TabularInline):
    model         = TicketComment
    extra         = 1
    fields        = ('author', 'author_name', 'content', 'is_internal', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


class TicketStatusHistoryInline(admin.TabularInline):
    model         = TicketStatusHistory
    extra         = 0
    fields        = ('from_status', 'to_status', 'changed_by', 'note', 'changed_at')
    readonly_fields = ('from_status', 'to_status', 'changed_by', 'note', 'changed_at')
    can_delete    = False

    def has_add_permission(self, request, obj=None):
        return False


# ─── Ticket ───────────────────────────────────────────────────────────────────

class StatusFilter(admin.SimpleListFilter):
    title          = 'Status Group'
    parameter_name = 'status_group'

    def lookups(self, request, model_admin):
        return (
            ('open',     'Open (all active)'),
            ('closed',   'Closed / Resolved'),
            ('escalated', 'Escalated'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'open':
            return queryset.exclude(status__in=('closed', 'resolved'))
        if self.value() == 'closed':
            return queryset.filter(status__in=('closed', 'resolved'))
        if self.value() == 'escalated':
            return queryset.filter(status='escalated')
        return queryset


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display  = ('ticket_number', 'title', 'status_badge', 'priority_badge',
                     'category', 'source', 'submitter_display', 'assigned_to',
                     'tenant', 'created_at', 'updated_at')
    list_filter   = ('tenant', StatusFilter, 'priority', 'category', 'source')
    search_fields = ('ticket_number', 'title', 'guest_name', 'guest_email',
                     'created_by__username', 'assigned_to__username')
    ordering      = ('-created_at',)
    date_hierarchy = 'created_at'
    readonly_fields = ('ticket_number', 'access_token', 'created_at', 'updated_at',
                       'resolved_at', 'closed_at', 'assigned_at')
    raw_id_fields   = ('created_by', 'assigned_to')
    inlines         = [TicketCommentInline, TicketStatusHistoryInline]

    fieldsets = (
        ('Identity', {
            'fields': ('tenant', 'ticket_number', 'access_token'),
        }),
        ('Content', {
            'fields': ('title', 'description', 'category', 'priority', 'status', 'source'),
        }),
        ('Submitter', {
            'fields': ('created_by', 'guest_name', 'guest_email', 'guest_phone'),
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'assigned_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'resolved_at', 'closed_at'),
            'classes': ('collapse',),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'new':          '#0d6efd',
            'assigned':     '#6610f2',
            'in_progress':  '#198754',
            'pending_info': '#fd7e14',
            'pending':      '#fd7e14',
            'escalated':    '#dc3545',
            'reassigned':   '#6c757d',
            'resolved':     '#20c997',
            'closed':       '#adb5bd',
            'reopen':       '#ffc107',
        }
        colour = colours.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:.8rem;">{}</span>',
            colour, obj.get_status_display())
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def priority_badge(self, obj):
        if not obj.priority:
            return '—'
        return format_html(
            '<span class="badge {}">{}</span>',
            obj.priority.badge_class, obj.priority.name)
    priority_badge.short_description = 'Priority'


# ─── Ticket Comment ───────────────────────────────────────────────────────────

@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display  = ('ticket', 'author_display', 'is_internal', 'created_at',
                     'content_preview')
    list_filter   = ('is_internal', 'ticket__tenant')
    search_fields = ('ticket__ticket_number', 'content', 'author__username', 'author_name')
    ordering      = ('-created_at',)
    raw_id_fields = ('ticket', 'author')

    def content_preview(self, obj):
        return obj.content[:80] + '…' if len(obj.content) > 80 else obj.content
    content_preview.short_description = 'Content'

    def author_display(self, obj):
        return obj.author_display
    author_display.short_description = 'Author'


# ─── Queue Entry ──────────────────────────────────────────────────────────────

class QueueStatusFilter(admin.SimpleListFilter):
    title          = 'Queue Status'
    parameter_name = 'queue_status'

    def lookups(self, request, model_admin):
        return (
            ('active',    'Active (Waiting + Serving)'),
            ('waiting',   'Waiting'),
            ('serving',   'Being Served'),
            ('completed', 'Completed'),
            ('no_show',   'No Show'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(status__in=('waiting', 'serving'))
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


@admin.register(QueueEntry)
class QueueEntryAdmin(admin.ModelAdmin):
    list_display  = ('queue_number_badge', 'category', 'customer_display_col',
                     'status_badge', 'source', 'ticket_link',
                     'issued_at', 'called_at', 'completed_at',
                     'wait_time_col', 'tenant')
    list_filter   = ('tenant', QueueStatusFilter, 'category', 'source')
    search_fields = ('queue_number', 'customer_name', 'customer_phone',
                     'customer_email', 'ticket__ticket_number')
    ordering      = ('-issued_at',)
    date_hierarchy = 'issued_at'
    readonly_fields = ('queue_number', 'issued_at', 'wait_time_col', 'service_time_col')
    raw_id_fields   = ('ticket', 'customer_user', 'served_by')

    fieldsets = (
        ('Queue', {
            'fields': ('tenant', 'queue_number', 'category', 'department', 'source'),
        }),
        ('Customer', {
            'fields': ('customer_user', 'customer_name', 'customer_phone', 'customer_email'),
        }),
        ('Status & Times', {
            'fields': ('status', 'issued_at', 'called_at', 'completed_at',
                       'served_by', 'notes'),
        }),
        ('Linked Ticket', {
            'fields': ('ticket',),
        }),
    )

    def queue_number_badge(self, obj):
        colour = '#0d6efd' if obj.status == 'waiting' else \
                 '#198754' if obj.status == 'serving' else \
                 '#6c757d'
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:4px;font-weight:700;">{}</span>',
            colour, obj.queue_number)
    queue_number_badge.short_description = 'Queue #'
    queue_number_badge.admin_order_field = 'queue_number'

    def status_badge(self, obj):
        colours = {
            'waiting':   '#fd7e14',
            'serving':   '#198754',
            'completed': '#6c757d',
            'no_show':   '#dc3545',
            'skipped':   '#adb5bd',
        }
        colour = colours.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:.8rem;">{}</span>',
            colour, obj.get_status_display())
    status_badge.short_description = 'Status'

    def customer_display_col(self, obj):
        return obj.customer_display
    customer_display_col.short_description = 'Customer'

    def ticket_link(self, obj):
        if obj.ticket:
            return format_html(
                '<a href="/admin/tickets/ticket/{}/change/">{}</a>',
                obj.ticket.pk, obj.ticket.ticket_number)
        return '—'
    ticket_link.short_description = 'Ticket'

    def wait_time_col(self, obj):
        wt = obj.wait_time
        return f'{wt} min' if wt is not None else '—'
    wait_time_col.short_description = 'Wait'

    def service_time_col(self, obj):
        st = obj.service_time
        return f'{st} min' if st is not None else '—'
    service_time_col.short_description = 'Service'


# ─── Status History ───────────────────────────────────────────────────────────

@admin.register(TicketStatusHistory)
class TicketStatusHistoryAdmin(admin.ModelAdmin):
    list_display  = ('ticket', 'from_status', 'to_status', 'changed_by', 'changed_at')
    list_filter   = ('ticket__tenant', 'to_status')
    search_fields = ('ticket__ticket_number', 'changed_by__username')
    ordering      = ('-changed_at',)
    readonly_fields = ('ticket', 'from_status', 'to_status',
                       'changed_by', 'note', 'changed_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ─── Admin branding ───────────────────────────────────────────────────────────

admin.site.site_header = 'Ticket & Queue Administration'
admin.site.site_title  = 'Tickets Admin'
admin.site.index_title = 'Ticket & Queue Management'





# Add/replace in documents/admin.py — Department + TicketCategory admin

# @admin.register(Department)
# class DepartmentAdmin(admin.ModelAdmin):
#     list_display  = ('name', 'abbreviation', 'tenant')
#     list_filter   = ('tenant',)
#     search_fields = ('name', 'abbreviation', 'tenant__name')
#     ordering      = ('tenant', 'name')





@admin.register(TicketCategory)
class TicketCategoryAdmin(admin.ModelAdmin):
    list_display  = ('slug', 'name', 'department', 'queue_prefix',
                     'tenant', 'is_active')
    list_filter   = ('tenant', 'is_active', 'department')
    search_fields = ('name', 'slug', 'tenant__name')
    ordering      = ('tenant', 'slug')
    readonly_fields = ('slug',)   # auto-generated on save


@admin.register(TicketPriority)
class TicketPriorityAdmin(admin.ModelAdmin):
    list_display  = ('name', 'level', 'badge_preview', 'tenant')
    list_filter   = ('tenant',)
    ordering      = ('level',)

    def badge_preview(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<span class="badge {}">{}</span>', obj.badge_class, obj.name)
    badge_preview.short_description = 'Badge'


# Inline for Receipt (one-to-one) shown on Invoice admin
class ReceiptInline(admin.StackedInline):
    model = Receipt
    can_delete = False
    verbose_name = "Linked receipt"
    verbose_name_plural = "Receipt"
    readonly_fields = (
        "receipt_number",
        "tenant",
        "amount_paid",
        "paid_at",
        "issued_by",
        "pdf_file",
        "created_at",
    )
    fields = readonly_fields
    max_num = 1
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "tenant",
        "party_display",
        "total_amount",
        "currency",
        "status",
        "direction",
        "issue_date",
        "due_date",
        "created_by",
    )
    search_fields = (
        "invoice_number",
        "payer_name",
        "payee_name",
        "contact__name",
        "contact__email",
        "created_by__username",
    )
    list_filter = ("status", "direction", "currency", "issue_date", "due_date")
    readonly_fields = ("invoice_number", "created_at", "updated_at", "share_token")
    fields = (
        ("tenant", "direction", "status"),
        ("contact",),
        ("payer_name", "payer_email"),
        ("payee_name", "payee_email"),
        ("invoice_number", "issue_date", "due_date", "currency"),
        ("total_amount", "tax_amount", "discount"),
        "items",
        "notes",
        ("payment_link",),
        ("bank_name", "bank_account_name", "bank_account_number", "bank_code"),
        ("share_token",),
        ("created_by", "created_at", "updated_at", "sent_at", "viewed_at", "paid_at"),
    )
    inlines = [ReceiptInline]

    actions = ["action_mark_sent", "action_mark_paid_create_receipt", "action_send_invoice_email"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("contact", "created_by", "tenant")

    def invoice_link(self, obj):
        return format_html('<a href="{}">{}</a>', obj.get_absolute_url(), obj.invoice_number)

    # ----- Admin actions -----
    def action_mark_sent(self, request, queryset):
        updated = queryset.update(status="sent", sent_at=timezone.now())
        self.message_user(request, f"{updated} invoice(s) marked as sent.", level=messages.SUCCESS)
    action_mark_sent.short_description = "Mark selected invoices as Sent"

    def action_mark_paid_create_receipt(self, request, queryset):
        """
        Mark selected invoices as paid and create receipts (one per invoice) where missing.
        Uses Receipt.create_from_invoice (tenant-aware) if available.
        """
        created = 0
        skipped = 0
        errors = 0
        for inv in queryset.select_related("tenant"):
            try:
                if inv.status == "paid":
                    skipped += 1
                    continue
                # mark invoice as paid
                inv.status = "paid"
                inv.paid_at = timezone.now()
                inv.save(update_fields=["status", "paid_at", "updated_at"])

                # create receipt if none exists
                if not hasattr(inv, "receipt") or inv.receipt is None:
                    Receipt.create_from_invoice(inv, issued_by=request.user)
                    created += 1
                else:
                    skipped += 1
            except Exception as exc:
                errors += 1
                self.message_user(request, f"Error processing {inv.invoice_number}: {exc}", level=messages.ERROR)

        msg = []
        if created:
            msg.append(f"{created} receipt(s) created")
        if skipped:
            msg.append(f"{skipped} invoice(s) skipped (already paid/receipt exists)")
        if errors:
            msg.append(f"{errors} errors")
        level = messages.SUCCESS if errors == 0 else messages.WARNING
        self.message_user(request, "; ".join(msg), level=level)
    action_mark_paid_create_receipt.short_description = "Mark paid and create receipts for selected invoices"

    def action_send_invoice_email(self, request, queryset):
        """
        Attempt to send invoice email for selected invoices.
        This action calls a send helper if present; otherwise it records a message.
        Replace or integrate with your project's email helper.
        """
        sent = 0
        missing = 0
        for inv in queryset:
            try:
               
                inv.sent_at = timezone.now()
                inv.status = "sent"
                inv.save(update_fields=["sent_at", "status", "updated_at"])
                sent += 1
            except Exception:
                missing += 1
        self.message_user(request, f"Emails processed: {sent}. Failures: {missing}", level=messages.INFO)
    action_send_invoice_email.short_description = "Send invoice email (mark as sent) for selected invoices"

    # show a small preview of items in change list 
    def short_items(self, obj):
        try:
            if not obj.items:
                return "-"
            parts = []
            for it in (obj.items or [])[:3]:
                parts.append(f"{it.get('name') or it.get('product', '')} x{it.get('quantity', 1)}")
            more = "…" if len(obj.items or []) > 3 else ""
            return ", ".join(parts) + more
        except Exception:
            return "-"
    short_items.short_description = "Items"


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "tenant", "invoice_link", "amount_paid", "currency", "paid_at", "issued_by", "created_at")
    search_fields = ("receipt_number", "payer_name", "payer_email", "invoice__invoice_number", "payment_id")
    list_filter = ("paid_at", "issued_by")
    readonly_fields = ("receipt_number", "tenant", "created_at")
    fields = (
        ("tenant", "receipt_number"),
        ("invoice", "amount_paid", "currency"),
        ("paid_at", "issued_by"),
        "items",
        "notes",
        "pdf_file",
    )

    def invoice_link(self, obj):
        if obj.invoice:
            url = reverse("documents:invoice_detail", kwargs={"invoice_id": obj.invoice.id})
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
        return "-"
    invoice_link.short_description = "Invoice"

    actions = ["action_download_pdf"]

    def action_download_pdf(self, request, queryset):
        """
        Placeholder action; you can implement mass-download as a zip of PDFs.
        """
        count = 0
        for r in queryset:
            if r.pdf_file:
                count += 1
        self.message_user(request, f"{count} receipts have attached PDFs.", level=messages.INFO)
    action_download_pdf.short_description = "Count attached PDF receipts"


@admin.register(InvoiceSendSchedule)
class InvoiceSendScheduleAdmin(admin.ModelAdmin):
    list_display = ("invoice", "frequency", "interval", "is_active", "last_sent_at", "next_send_at")
    search_fields = ("invoice__invoice_number",)
    readonly_fields = ("last_sent_at", "next_send_at", "created_at")