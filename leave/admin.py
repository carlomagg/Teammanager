from django.contrib import admin
from .models import LeaveCategory, Leave, LeaveStep, LeaveAttachment, LeaveComment, LeaveSetting


@admin.register(LeaveCategory)
class LeaveCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'created_by', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


class LeaveStepInline(admin.TabularInline):
    model = LeaveStep
    extra = 0
    readonly_fields = ['step_number', 'from_user', 'to_user', 'action', 'created_at']


class LeaveAttachmentInline(admin.TabularInline):
    model = LeaveAttachment
    extra = 0
    readonly_fields = ['uploaded_at']


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = [
        'reference_number', 'title', 'status', 'priority',
        'start_date', 'end_date', 'days_requested',
        'current_holder', 'tenant', 'created_by', 'created_at'
    ]
    list_filter = ['tenant', 'status', 'priority', 'created_at', 'start_date']
    search_fields = ['reference_number', 'title', 'description']
    readonly_fields = ['reference_number', 'created_at', 'updated_at', 'closed_at', 'completed_at']
    inlines = [LeaveStepInline, LeaveAttachmentInline]


@admin.register(LeaveStep)
class LeaveStepAdmin(admin.ModelAdmin):
    list_display = ['leave', 'step_number', 'from_user', 'to_user', 'action', 'is_private_note', 'created_at']
    list_filter = ['action', 'is_private_note', 'created_at']
    search_fields = ['memo__reference_number', 'note']
    readonly_fields = ['created_at']


@admin.register(LeaveAttachment)
class LeaveAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_name', 'leave', 'step', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['original_name', 'memo__reference_number']
    readonly_fields = ['uploaded_at']


@admin.register(LeaveComment)
class LeaveCommentAdmin(admin.ModelAdmin):
    list_display = ['leave', 'author', 'external_author_name', 'is_private', 'created_at']
    list_filter = ['is_private', 'created_at']
    search_fields = ['content', 'memo__reference_number']
    readonly_fields = ['created_at']


@admin.register(LeaveSetting)
class LeaveSettingAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'notify_external_on_move', 'allow_external_escalation', 'allow_external_completion']
    list_filter = ['notify_external_on_move', 'allow_external_escalation']
