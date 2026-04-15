from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count

from .models import (
    WorkSchedule,
    StaffCheckIn,
    StaffPIN,
    StaffQRToken,
    BiometricCredential,
    Visitor,
    VisitorLog,
    VisitorTagCounter,
)


# ─── Work Schedule ─

@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display    = ('tenant', 'work_start_time', 'work_end_time', 'late_after',
                       'created_by', 'updated_at')
    list_filter     = ('tenant',)
    search_fields   = ('tenant__name',)
    ordering        = ('tenant__name',)
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields   = ('created_by',)

    fieldsets = (
        ('Tenant', {'fields': ('tenant',)}),
        ('Hours',  {'fields': ('work_start_time', 'work_end_time', 'late_after')}),
        ('Meta',   {'fields': ('created_by', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


# ─── Staff Check-In 

class LateFilter(admin.SimpleListFilter):
    title          = 'Punctuality'
    parameter_name = 'punctuality'

    def lookups(self, request, model_admin):
        return (('on_time', 'On Time'), ('late', 'Late'))

    def queryset(self, request, queryset):
        if self.value() == 'late':    return queryset.filter(is_late=True)
        if self.value() == 'on_time': return queryset.filter(is_late=False)
        return queryset


@admin.register(StaffCheckIn)
class StaffCheckInAdmin(admin.ModelAdmin):
    list_display    = ('staff', 'tenant', 'date', 'check_in_time', 'check_out_time',
                       'method_badge', 'status_badge', 'is_late', 'duration_display')
    list_filter     = ('tenant', 'status', 'method', LateFilter, 'date')
    search_fields   = ('staff__username', 'staff__first_name', 'staff__last_name')
    ordering        = ('-date', '-check_in_time')
    date_hierarchy  = 'date'
    readonly_fields = ('created_at', 'duration_display')
    raw_id_fields   = ('staff', 'checked_in_by')

    fieldsets = (
        ('Staff & Tenant',  {'fields': ('tenant', 'staff')}),
        ('Attendance',      {'fields': ('date', 'check_in_time', 'check_out_time',
                                        'method', 'status', 'is_late')}),
        ('Additional',      {'fields': ('checked_in_by', 'notes', 'created_at'),
                             'classes': ('collapse',)}),
    )

    def method_badge(self, obj):
        colours = {'fingerprint': '#198754', 'faceid': '#0dcaf0',
                   'qrcode': '#0d6efd', 'pin': '#6610f2', 'manual': '#6c757d'}
        colour = colours.get(obj.method, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:.8rem;">{}</span>',
            colour, obj.get_method_display())
    method_badge.short_description = 'Method'
    method_badge.admin_order_field = 'method'

    def status_badge(self, obj):
        colours = {'present': '#198754', 'late': '#fd7e14', 'absent': '#dc3545'}
        colour = colours.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:.8rem;">{}</span>',
            colour, obj.get_status_display())
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'

    def duration_display(self, obj):
        if obj.check_in_time and obj.check_out_time:
            delta = obj.check_out_time - obj.check_in_time
            h, rem = divmod(int(delta.total_seconds()), 3600)
            return f'{h}h {rem // 60}m'
        return '—'
    duration_display.short_description = 'Duration'


# ─── Staff PIN ──

@admin.register(StaffPIN)
class StaffPINAdmin(admin.ModelAdmin):
    list_display    = ('user', 'created_at', 'updated_at')
    search_fields   = ('user__username', 'user__first_name', 'user__last_name')
    ordering        = ('user__username',)
    readonly_fields = ('pin_hash', 'created_at', 'updated_at')
    raw_id_fields   = ('user',)

    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Credential (read-only)', {
            'fields': ('pin_hash', 'created_at', 'updated_at'),
            'classes': ('collapse',),
            'description': 'PIN hash — never edit directly.',
        }),
    )

    def has_add_permission(self, request):
        return False  # PINs must be set via set_staff_pin view to ensure hashing


# ─── Staff QR Token ─

@admin.register(StaffQRToken)
class StaffQRTokenAdmin(admin.ModelAdmin):
    list_display    = ('user', 'token_partial', 'created_at')
    search_fields   = ('user__username', 'user__first_name', 'user__last_name')
    ordering        = ('user__username',)
    readonly_fields = ('token', 'created_at')
    raw_id_fields   = ('user',)

    def token_partial(self, obj):
        t = str(obj.token)
        return f'{t[:8]}…{t[-4:]}' if t else '—'
    token_partial.short_description = 'Token (partial)'

    def has_add_permission(self, request):
        return False  # auto-created via get_or_create in the view


# ─── Biometric Credential 

@admin.register(BiometricCredential)
class BiometricCredentialAdmin(admin.ModelAdmin):
    list_display    = ('user', 'type_badge', 'credential_id_partial',
                       'sign_count', 'last_used_at', 'created_at')
    list_filter     = ('authenticator_type',)
    search_fields   = ('user__username', 'user__first_name', 'user__last_name')
    ordering        = ('-last_used_at',)
    readonly_fields = ('credential_id', 'public_key', 'sign_count',
                       'last_used_at', 'created_at')
    raw_id_fields   = ('user',)

    fieldsets = (
        ('User',   {'fields': ('user', 'authenticator_type')}),
        ('Credential (read-only)', {
            'fields': ('credential_id', 'public_key', 'sign_count'),
            'classes': ('collapse',),
            'description': 'Raw WebAuthn credential data — do not edit manually.',
        }),
        ('Usage',  {'fields': ('last_used_at', 'created_at')}),
    )

    def type_badge(self, obj):
        colours = {'fingerprint': '#198754', 'faceid': '#0dcaf0'}
        colour = colours.get(obj.authenticator_type, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:.8rem;">{}</span>',
            colour, obj.get_authenticator_type_display())
    type_badge.short_description = 'Type'

    def credential_id_partial(self, obj):
        cid = str(obj.credential_id)
        return f'{cid[:16]}…' if len(cid) > 16 else cid
    credential_id_partial.short_description = 'Credential ID'

    def has_add_permission(self, request):
        return False  # credentials registered via WebAuthn flow only


# ─── Visitor 

@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display    = ('name', 'phone_number', 'email', 'tenant',
                       'visit_count', 'created_at', 'updated_at')
    list_filter     = ('tenant',)
    search_fields   = ('name', 'phone_number', 'email')
    ordering        = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'visit_count')

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_visit_count=Count('logs'))

    def visit_count(self, obj):
        return getattr(obj, '_visit_count', obj.logs.count())
    visit_count.short_description = 'Total Visits'
    visit_count.admin_order_field = '_visit_count'


# ─── Visitor Log ─

class CheckedOutFilter(admin.SimpleListFilter):
    title          = 'Status'
    parameter_name = 'checked_out'

    def lookups(self, request, model_admin):
        return (('inside', 'Currently Inside'), ('out', 'Checked Out'))

    def queryset(self, request, queryset):
        if self.value() == 'inside': return queryset.filter(time_out__isnull=True)
        if self.value() == 'out':    return queryset.filter(time_out__isnull=False)
        return queryset


@admin.register(VisitorLog)
class VisitorLogAdmin(admin.ModelAdmin):
    list_display    = ('visitor_tag_badge', 'visitor_name', 'visitor_phone',
                       'purpose', 'visitee', 'time_in', 'time_out',
                       'status_badge', 'on_appointment', 'has_document',
                       'tenant', 'checked_in_by')
    list_filter     = ('tenant', CheckedOutFilter, 'purpose', 'on_appointment',
                       'has_document', 'id_type')
    search_fields   = ('visitor__name', 'visitor__phone_number', 'visitor_tag',
                       'visitee__first_name', 'visitee__last_name', 'notes')
    ordering        = ('-date', '-time_in')
    date_hierarchy  = 'date'
    readonly_fields = ('visitor_tag', 'time_in', 'time_out', 'date',
                       'checked_in_by', 'checked_out_by',
                       'created_at', 'document_preview', 'duration_display')
    raw_id_fields   = ('visitor', 'visitee', 'checked_in_by', 'checked_out_by')

    fieldsets = (
        ('Visitor & Tenant',   {'fields': ('tenant', 'visitor', 'visitor_tag', 'date')}),
        ('Visit Details',      {'fields': ('purpose', 'purpose_detail', 'visitee',
                                           'on_appointment', 'notes')}),
        ('Identification',     {'fields': ('id_type', 'id_number'), 'classes': ('collapse',)}),
        ('Document',           {'fields': ('has_document', 'document_scan', 'document_preview'),
                                'classes': ('collapse',)}),
        ('Timestamps & Staff', {'fields': ('time_in', 'time_out', 'duration_display',
                                           'checked_in_by', 'checked_out_by', 'created_at')}),
    )

    def visitor_tag_badge(self, obj):
        return format_html(
            '<span style="background:#0d6efd;color:#fff;padding:2px 10px;'
            'border-radius:4px;font-weight:600;letter-spacing:.05em;">{}</span>',
            obj.visitor_tag)
    visitor_tag_badge.short_description = 'Tag'
    visitor_tag_badge.admin_order_field = 'visitor_tag'

    def visitor_name(self, obj):
        return obj.visitor.name if obj.visitor else '—'
    visitor_name.short_description = 'Visitor'
    visitor_name.admin_order_field = 'visitor__name'

    def visitor_phone(self, obj):
        return obj.visitor.phone_number if obj.visitor else '—'
    visitor_phone.short_description = 'Phone'

    def status_badge(self, obj):
        if obj.is_checked_out:
            return format_html(
                '<span style="background:#6c757d;color:#fff;padding:2px 8px;'
                'border-radius:4px;font-size:.8rem;">Out</span>')
        return format_html(
            '<span style="background:#198754;color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:.8rem;">Inside</span>')
    status_badge.short_description = 'Status'

    def duration_display(self, obj):
        return obj.duration
    duration_display.short_description = 'Duration'

    def document_preview(self, obj):
        if not obj.document_scan:
            return '—'
        url  = obj.document_scan.url
        name = obj.document_scan.name.lower()
        if name.endswith('.pdf'):
            return format_html(
                '<a href="{}" target="_blank" style="color:#dc3545;font-weight:600;">'
                '📄 View PDF</a>', url)
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-width:220px;max-height:160px;'
            'border-radius:6px;border:1px solid #dee2e6;"></a>',
            url, url)
    document_preview.short_description = 'Document Preview'


# ─── Visitor Tag Counter 

@admin.register(VisitorTagCounter)
class VisitorTagCounterAdmin(admin.ModelAdmin):
    list_display    = ('tenant', 'date', 'last_number')
    list_filter     = ('tenant',)
    ordering        = ('-date',)
    readonly_fields = ('tenant', 'date', 'last_number')

    def has_add_permission(self, request):
        return False  # auto-created by VisitorTagCounter.get_next_tag()

    def has_change_permission(self, request, obj=None):
        return False  # counter must never be manually edited


# ─── Admin site branding ──

admin.site.site_header = 'TeamManager Administration'
admin.site.site_title  = 'TeamManager Admin'
admin.site.index_title = 'TeamManager App Management'