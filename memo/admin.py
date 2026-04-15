from django.contrib import admin
from .models import MemoCategory, Memo, MemoStep, MemoAttachment, MemoComment, MemoSetting


@admin.register(MemoCategory)
class MemoCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'created_by', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


class MemoStepInline(admin.TabularInline):
    model = MemoStep
    extra = 0
    readonly_fields = ['step_number', 'from_user', 'to_user', 'action', 'created_at']


class MemoAttachmentInline(admin.TabularInline):
    model = MemoAttachment
    extra = 0
    readonly_fields = ['uploaded_at']


@admin.register(Memo)
class MemoAdmin(admin.ModelAdmin):
    list_display = [
        'reference_number', 'title', 'status', 'priority',
        'current_holder', 'is_external', 'tenant', 'created_by', 'created_at'
    ]
    list_filter = ['tenant', 'status', 'priority', 'is_external', 'created_at']
    search_fields = ['reference_number', 'title', 'description', 'external_name', 'external_email']
    readonly_fields = ['reference_number', 'external_token', 'created_at', 'updated_at', 'closed_at', 'completed_at']
    inlines = [MemoStepInline, MemoAttachmentInline]


@admin.register(MemoStep)
class MemoStepAdmin(admin.ModelAdmin):
    list_display = ['memo', 'step_number', 'from_user', 'to_user', 'action', 'is_private_note', 'created_at']
    list_filter = ['action', 'is_private_note', 'created_at']
    search_fields = ['memo__reference_number', 'note']
    readonly_fields = ['created_at']


@admin.register(MemoAttachment)
class MemoAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_name', 'memo', 'step', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['original_name', 'memo__reference_number']
    readonly_fields = ['uploaded_at']


@admin.register(MemoComment)
class MemoCommentAdmin(admin.ModelAdmin):
    list_display = ['memo', 'author', 'external_author_name', 'is_private', 'created_at']
    list_filter = ['is_private', 'created_at']
    search_fields = ['content', 'memo__reference_number']
    readonly_fields = ['created_at']


@admin.register(MemoSetting)
class MemoSettingAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'notify_external_on_move', 'allow_external_escalation', 'allow_external_completion']
    list_filter = ['notify_external_on_move', 'allow_external_escalation']
