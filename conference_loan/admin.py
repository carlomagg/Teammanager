from django.contrib import admin
from django.utils.html import format_html
from .models import ConferenceLoan, LoanDocument, LoanRepayment, LoanComment


class LoanDocumentInline(admin.TabularInline):
    model = LoanDocument
    extra = 0
    readonly_fields = ('uploaded_at', 'uploaded_by', 'original_name')
    fields = ('document_type', 'file', 'description', 'uploaded_at', 'uploaded_by')


class LoanRepaymentInline(admin.TabularInline):
    model = LoanRepayment
    extra = 0
    readonly_fields = ('payment_date', 'created_at')
    fields = ('amount', 'payment_reference', 'status', 'payment_method', 'payment_date')


class LoanCommentInline(admin.TabularInline):
    model = LoanComment
    extra = 0
    readonly_fields = ('created_at', 'author')
    fields = ('author', 'content', 'is_internal', 'created_at')


@admin.register(ConferenceLoan)
class ConferenceLoanAdmin(admin.ModelAdmin):
    list_display = (
        'reference_number', 'conference', 'applicant', 'amount_display',
        'status_badge', 'kyc_status', 'created_at', 'submitted_at'
    )
    list_filter = (
        'status', 'kyc_verified', 'currency', 'created_at', 'submitted_at'
    )
    search_fields = (
        'reference_number', 'conference__title', 'applicant__username',
        'applicant__email', 'reason'
    )
    readonly_fields = (
        'reference_number', 'created_at', 'updated_at', 'submitted_at',
        'kyc_verification_date', 'reviewed_at', 'disbursement_date',
        'outstanding_balance', 'is_fully_repaid'
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'reference_number', 'tenant', 'conference', 'applicant', 'status'
            )
        }),
        ('Loan Details', {
            'fields': (
                'amount', 'currency', 'reason', 'expected_date',
                'conference_description', 'expected_revenue', 'expected_expenses'
            )
        }),
        ('Guarantor Information', {
            'fields': (
                'guarantor_name', 'guarantor_phone', 'guarantor_email',
                'guarantor_address', 'guarantor_relationship', 'guarantor_occupation'
            )
        }),
        ('KYC Verification', {
            'fields': (
                'kyc_verified', 'kyc_verification_date'
            )
        }),
        ('Approval/Rejection', {
            'fields': (
                'approved_amount', 'interest_rate', 'repayment_period_months',
                'rejection_reason', 'reviewed_by', 'reviewed_at'
            )
        }),
        ('Disbursement', {
            'fields': (
                'disbursement_date', 'disbursement_reference'
            )
        }),
        ('Repayment Tracking', {
            'fields': (
                'total_repaid', 'outstanding_balance', 'is_fully_repaid',
                'next_payment_date', 'next_payment_amount'
            )
        }),
        ('Transave Integration', {
            'fields': (
                'transave_loan_id', 'transave_response'
            ),
            'classes': ('collapse',)
        }),
        ('Internal', {
            'fields': (
                'internal_notes', 'created_at', 'updated_at', 'submitted_at'
            )
        }),
    )
    
    inlines = [LoanDocumentInline, LoanRepaymentInline, LoanCommentInline]
    
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    
    def status_badge(self, obj):
        colors = {
            'draft': 'gray',
            'pending': 'orange',
            'submitted_to_transave': 'blue',
            'under_review': 'blue',
            'approved': 'green',
            'rejected': 'red',
            'disbursed': 'purple',
            'repaying': 'teal',
            'completed': 'darkgreen',
            'defaulted': 'darkred',
            'cancelled': 'gray',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def kyc_status(self, obj):
        if obj.kyc_verified:
            return format_html(
                '<span style="color: green;">✓ Verified</span>'
            )
        return format_html(
            '<span style="color: red;">✗ Not Verified</span>'
        )
    kyc_status.short_description = 'KYC Status'
    
    actions = ['mark_as_submitted', 'mark_as_under_review']
    
    def mark_as_submitted(self, request, queryset):
        count = queryset.filter(status='pending').update(status='submitted_to_transave')
        self.message_user(request, f'{count} loan(s) marked as submitted to Transave')
    mark_as_submitted.short_description = 'Mark as submitted to Transave'
    
    def mark_as_under_review(self, request, queryset):
        count = queryset.filter(status='submitted_to_transave').update(status='under_review')
        self.message_user(request, f'{count} loan(s) marked as under review')
    mark_as_under_review.short_description = 'Mark as under review'


@admin.register(LoanDocument)
class LoanDocumentAdmin(admin.ModelAdmin):
    list_display = (
        'loan', 'document_type', 'original_name', 'uploaded_by', 'uploaded_at'
    )
    list_filter = ('document_type', 'uploaded_at')
    search_fields = ('loan__reference_number', 'original_name', 'description')
    readonly_fields = ('uploaded_at', 'original_name')


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = (
        'loan', 'amount', 'payment_reference', 'status', 'payment_date'
    )
    list_filter = ('status', 'payment_date')
    search_fields = ('loan__reference_number', 'payment_reference')
    readonly_fields = ('payment_date', 'created_at', 'updated_at')


@admin.register(LoanComment)
class LoanCommentAdmin(admin.ModelAdmin):
    list_display = (
        'loan', 'author', 'content_preview', 'is_internal', 'created_at'
    )
    list_filter = ('is_internal', 'created_at')
    search_fields = ('loan__reference_number', 'content', 'author__username')
    readonly_fields = ('created_at',)
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
