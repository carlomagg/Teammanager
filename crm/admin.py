from django.contrib import admin
from .models import Product, PipelineStage, Opportunity, Activity


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'unit_price', 'is_active', 'tenant', 'created_by', 'created_at']
    list_filter = ['tenant', 'category', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_active']


@admin.register(PipelineStage)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'order', 'is_terminal', 'tenant', 'created_at']
    list_filter = ['tenant', 'category', 'is_terminal', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['category', 'order']


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'company_name', 'category', 'stage', 'deal_size', 
        'estimated_amount', 'tenant', 'assigned_to', 'created_at'
    ]
    list_filter = [
        'tenant', 'category', 'stage', 'deal_type', 'company_type', 
        'industry', 'delivery_method', 'is_competitive', 'created_at'
    ]
    search_fields = ['title', 'company_name', 'description', 'contact_email']
    readonly_fields = ['deal_size', 'created_at', 'updated_at']
    filter_horizontal = ['products']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'category', 'deal_type')
        }),
        ('Company Information', {
            'fields': ('company_name', 'company_type', 'company_website', 'industry')
        }),
        ('Company Address', {
            'fields': ('country', 'city', 'address')
        }),
        ('Contact Person', {
            'fields': (
                'contact', 'contact_first_name', 'contact_last_name', 
                'contact_title', 'contact_email', 'contact_phone'
            )
        }),
        ('Products & Services', {
            'fields': ('products', 'product_details')
        }),
        ('Delivery', {
            'fields': (
                'delivery_method', 'partner_contact', 'partner_org_name', 
                'partner_contact_name', 'partner_phone', 'partner_email', 'partner_address'
            )
        }),
        ('Deal Value', {
            'fields': ('estimated_amount', 'actual_amount', 'deal_size', 'recurring_revenue')
        }),
        ('Timeline & Source', {
            'fields': (
                'expected_close_date', 'source', 'referrer_name', 
                'referrer_phone', 'referrer_email', 'referrer_address'
            )
        }),
        ('Competition', {
            'fields': ('is_competitive', 'competitor_names')
        }),
        ('Assignment & Stage', {
            'fields': ('assigned_to', 'stage')
        }),
        ('Audit', {
            'fields': ('tenant', 'created_by', 'updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = [
        'subject', 'activity_type', 'due_date', 'completed', 
        'tenant', 'assigned_to', 'created_at'
    ]
    list_filter = ['tenant', 'activity_type', 'completed', 'due_date']
    search_fields = ['subject', 'description']
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
