from django.contrib import admin
from .models import FundRequestCategory, FundRequestType, FundRequest, FundRequestStep, FundRequestAttachment, FundRequestComment, FundRequestSetting


@admin.register(FundRequestCategory)
class FundRequestCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'created_by', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


@admin.register(FundRequestType)
class FundRequestTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'created_by', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


class FundRequestStepInline(admin.TabularInline):
    model = FundRequestStep
    extra = 0
    readonly_fields = ['step_number', 'from_user', 'to_user', 'action', 'created_at']


class FundRequestAttachmentInline(admin.TabularInline):
    model = FundRequestAttachment
    extra = 0
    readonly_fields = ['uploaded_at']


@admin.register(FundRequest)
class FundRequestAdmin(admin.ModelAdmin):
    list_display = [
        'reference_number', 'title', 'status', 'priority',
        'amount', 'currency', 'request_type',
        'current_holder', 'tenant', 'created_by', 'created_at'
    ]
    list_filter = ['tenant', 'status', 'priority', 'request_type', 'created_at']
    search_fields = ['reference_number', 'title', 'description']
    readonly_fields = ['reference_number', 'created_at', 'updated_at', 'closed_at', 'completed_at']
    inlines = [FundRequestStepInline, FundRequestAttachmentInline]


@admin.register(FundRequestStep)
class FundRequestStepAdmin(admin.ModelAdmin):
    list_display = ['fund_request', 'step_number', 'from_user', 'to_user', 'action', 'is_private_note', 'created_at']
    list_filter = ['action', 'is_private_note', 'created_at']
    search_fields = ['memo__reference_number', 'note']
    readonly_fields = ['created_at']


@admin.register(FundRequestAttachment)
class FundRequestAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_name', 'fund_request', 'step', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['original_name', 'memo__reference_number']
    readonly_fields = ['uploaded_at']


@admin.register(FundRequestComment)
class FundRequestCommentAdmin(admin.ModelAdmin):
    list_display = ['fund_request', 'author', 'external_author_name', 'is_private', 'created_at']
    list_filter = ['is_private', 'created_at']
    search_fields = ['content', 'memo__reference_number']
    readonly_fields = ['created_at']


@admin.register(FundRequestSetting)
class FundRequestSettingAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'notify_external_on_move', 'allow_external_escalation', 'allow_external_completion']
    list_filter = ['notify_external_on_move', 'allow_external_escalation']
