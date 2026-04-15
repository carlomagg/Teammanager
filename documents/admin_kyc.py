# documents/admin_kyc.py
from django.contrib import admin
from .kyc_models import UserKYC, StaffKYC, CompanyKYB, CompanyDirector


@admin.register(UserKYC)
class UserKYCAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'kyc_status', 'nin', 'bvn', 'created_at', 'kyc_verified_at']
    list_filter = ['kyc_status', 'created_at', 'kyc_verified_at']
    search_fields = ['user_profile__user__username', 'user_profile__user__email', 'nin', 'bvn']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user_profile',)
        }),
        ('Identity Information', {
            'fields': ('nin', 'bvn', 'id_type', 'id_number')
        }),
        ('Documents', {
            'fields': ('id_front_file', 'id_back_file', 'utility_bill_file')
        }),
        ('Next of Kin Information', {
            'fields': ('next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'next_of_kin_address')
        }),
        ('Verification Status', {
            'fields': ('kyc_status', 'kyc_verified_at', 'kyc_rejection_reason', 'verified_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(StaffKYC)
class StaffKYCAdmin(admin.ModelAdmin):
    list_display = ['staff_profile', 'kyc_status', 'nin', 'bvn', 'created_at', 'kyc_verified_at']
    list_filter = ['kyc_status', 'created_at', 'kyc_verified_at']
    search_fields = ['staff_profile__user__username', 'staff_profile__user__email', 'nin', 'bvn']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Staff Information', {
            'fields': ('staff_profile',)
        }),
        ('Identity Information', {
            'fields': ('nin', 'bvn', 'id_type', 'id_number')
        }),
        ('Documents', {
            'fields': ('id_front_file', 'id_back_file', 'utility_bill_file')
        }),
        ('Next of Kin Information', {
            'fields': ('next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'next_of_kin_address')
        }),
        ('Verification Status', {
            'fields': ('kyc_status', 'kyc_verified_at', 'kyc_rejection_reason', 'verified_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CompanyKYB)
class CompanyKYBAdmin(admin.ModelAdmin):
    list_display = ['company_profile', 'kyb_status', 'rc_number', 'tin', 'created_at', 'kyb_verified_at']
    list_filter = ['kyb_status', 'created_at', 'kyb_verified_at']
    search_fields = ['company_profile__company_name', 'rc_number', 'tin']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Company Information', {
            'fields': ('company_profile',)
        }),
        ('Tax & Registration', {
            'fields': ('rc_number', 'tin')
        }),
        ('Legal Documents', {
            'fields': ('cac_certificate_file', 'memart_file', 'status_report_file', 'scuml_certificate_file')
        }),
        ('Proof of Address', {
            'fields': ('utility_bill_file',)
        }),
        ('Verification Status', {
            'fields': ('kyb_status', 'kyb_verified_at', 'kyb_rejection_reason', 'verified_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CompanyDirector)
class CompanyDirectorAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'company_profile', 'designation', 'nin', 'bvn', 'created_at']
    list_filter = ['created_at', 'designation']
    search_fields = ['first_name', 'last_name', 'email', 'nin', 'bvn', 'company_profile__company_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Company', {
            'fields': ('company_profile', 'user')
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email', 'phone', 'address', 'designation')
        }),
        ('Identity Information', {
            'fields': ('nin', 'bvn', 'id_type')
        }),
        ('Documents', {
            'fields': ('id_front', 'id_back', 'photo')
        }),
        ('Ownership', {
            'fields': ('percentage_ownership',)
        }),
        ('Next of Kin Information', {
            'fields': ('next_of_kin_name', 'next_of_kin_relationship', 'next_of_kin_phone', 'next_of_kin_address')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# Register field approval models
from .kyc_field_approval_models import FieldApprovalStatus, FieldApprovalGroup


@admin.register(FieldApprovalStatus)
class FieldApprovalStatusAdmin(admin.ModelAdmin):
    list_display = ['field_label', 'content_object_display', 'status', 'reviewed_by', 'reviewed_at']
    list_filter = ['status', 'field_type', 'reviewed_at', 'created_at']
    search_fields = ['field_name', 'field_label', 'rejection_reason']
    readonly_fields = ['created_at', 'updated_at', 'reviewed_at']
    
    fieldsets = (
        ('Field Information', {
            'fields': ('content_type', 'object_id', 'field_name', 'field_label', 'field_type')
        }),
        ('Approval Status', {
            'fields': ('status', 'rejection_reason', 'reviewed_by', 'reviewed_at')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def content_object_display(self, obj):
        return str(obj.content_object) if obj.content_object else 'N/A'
    content_object_display.short_description = 'Related Object'


@admin.register(FieldApprovalGroup)
class FieldApprovalGroupAdmin(admin.ModelAdmin):
    list_display = ['group_label', 'content_object_display', 'field_count', 'group_status']
    list_filter = ['group_name']
    search_fields = ['group_name', 'group_label']
    
    fieldsets = (
        ('Group Information', {
            'fields': ('content_type', 'object_id', 'group_name', 'group_label')
        }),
        ('Fields', {
            'fields': ('field_names',)
        }),
    )
    
    def content_object_display(self, obj):
        return str(obj.content_object) if obj.content_object else 'N/A'
    content_object_display.short_description = 'Related Object'
    
    def field_count(self, obj):
        return len(obj.field_names)
    field_count.short_description = 'Number of Fields'
    
    def group_status(self, obj):
        return obj.get_group_status()
    group_status.short_description = 'Status'
