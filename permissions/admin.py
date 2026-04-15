from django.contrib import admin
from .models import PermissionCategory, Permission, PermissionStep, PermissionAttachment, PermissionComment, PermissionSetting


@admin.register(PermissionCategory)
class PermissionCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'created_by', 'created_at']
    list_filter = ['tenant', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


class PermissionStepInline(admin.TabularInline):
    model = PermissionStep
    extra = 0
    readonly_fields = ['step_number', 'from_user', 'to_user', 'action', 'created_at']


class PermissionAttachmentInline(admin.TabularInline):
    model = PermissionAttachment
    extra = 0
    readonly_fields = ['uploaded_at']


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = [
        'reference_number', 'title', 'status', 'priority',
        'start_date', 'end_date',
        'current_holder', 'tenant', 'created_by', 'created_at'
    ]
    list_filter = ['tenant', 'status', 'priority', 'created_at', 'start_date']
    search_fields = ['reference_number', 'title', 'description']
    readonly_fields = ['reference_number', 'created_at', 'updated_at', 'closed_at', 'completed_at']
    inlines = [PermissionStepInline, PermissionAttachmentInline]


@admin.register(PermissionStep)
class PermissionStepAdmin(admin.ModelAdmin):
    list_display = ['permissions', 'step_number', 'from_user', 'to_user', 'action', 'is_private_note', 'created_at']
    list_filter = ['action', 'is_private_note', 'created_at']
    search_fields = ['memo__reference_number', 'note']
    readonly_fields = ['created_at']


@admin.register(PermissionAttachment)
class PermissionAttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_name', 'permissions', 'step', 'uploaded_by', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['original_name', 'memo__reference_number']
    readonly_fields = ['uploaded_at']


@admin.register(PermissionComment)
class PermissionCommentAdmin(admin.ModelAdmin):
    list_display = ['permissions', 'author', 'external_author_name', 'is_private', 'created_at']
    list_filter = ['is_private', 'created_at']
    search_fields = ['content', 'memo__reference_number']
    readonly_fields = ['created_at']


@admin.register(PermissionSetting)
class PermissionSettingAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'notify_external_on_move', 'allow_external_escalation', 'allow_external_completion']
    list_filter = ['notify_external_on_move', 'allow_external_escalation']
