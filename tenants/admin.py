from django.contrib import admin
from django.core.management import call_command
from .models import Tenant, TenantApplication, CompanyGroup, SubscriptionType, Subscription, Credit, ExternalServiceLink
from documents.models import Role, CustomUser
import logging
from django.utils.html import format_html

logger = logging.getLogger(__name__)

# @admin.register(SuperUser)
# class SuperUserAdmin(admin.ModelAdmin):
#     list_display = ['username', 'email', 'password']

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at', 'created_by', 'admin', 'get_user_count']
    list_filter = ['created_at']
    search_fields = ['name', 'slug']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            return qs.filter(customuser__id=request.user.id)
        return qs
        
    def get_user_count(self, obj):
        return obj.get_user_count()
    get_user_count.short_description = 'Users'

@admin.register(TenantApplication)
class TenantApplicationAdmin(admin.ModelAdmin):
    list_display = ['organization_name', 'username', 'email', 'slug', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['organization_name', 'username', 'email', 'slug']
    actions = ['approve_application', 'reject_application']

    def approve_application(self, request, queryset):
        for application in queryset:
            if application.status != 'pending':
                self.message_user(request, f"Cannot approve non-pending application: {application.organization_name}")
                logger.warning(f"Cannot approve non-pending application: {application.organization_name}")
                continue
            try:
                tenant_admin = CustomUser.objects.get(username=application.username)
                tenant = Tenant.objects.create(
                    name=application.organization_name,
                    slug=application.slug,
                    created_by=request.user,
                    admin=tenant_admin
                )
                admin_role, _ = Role.objects.get_or_create(name='Admin')
                tenant_admin.tenant = tenant
                tenant_admin.roles.add(admin_role)
                tenant_admin.save()
                application.status = 'approved'
                application.save()
                logger.info(f"Approved tenant application: {application.organization_name} for user {application.username}")
            except Exception as e:
                logger.error(f"Error approving tenant application {application.organization_name}: {str(e)}")
                self.message_user(request, f"Error approving {application.organization_name}: {str(e)}", level='error')

    approve_application.short_description = "Approve selected tenant applications"

    def reject_application(self, request, queryset):
        for application in queryset:
            if application.status == 'pending':
                application.status = 'rejected'
                application.save()
                logger.info(f"Rejected tenant application: {application.organization_name}")
            else:
                logger.warning(f"Cannot reject non-pending application: {application.organization_name}")
                self.message_user(request, f"Cannot reject non-pending application: {application.organization_name}")

    reject_application.short_description = "Reject selected tenant applications"


@admin.register(CompanyGroup)
class CompanyGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'member_count', 'created_at', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'slug')
    filter_horizontal = ('members',)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Number of Companies"

    # def get_queryset(self, request):
    #     # Only show groups that belong to the "group" tenant
    #     return super().get_queryset(request).filter(tenant__slug='group')



@admin.register(SubscriptionType)
class SubscriptionTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'duration', 'discount_percentage', 'is_active', 'max_users', 'created_at']
    list_filter = ['is_active', 'duration']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'discount_percentage']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'price', 'duration')
        }),
        ('Pricing & Limits', {
            'fields': ('discount_percentage', 'max_users', 'is_active')
        }),
    )

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['id', 'subscriber_info', 'plan', 'status', 'start_date', 'end_date', 'current_user_count', 'get_monthly_rate', 'is_free']
    list_filter = ['status', 'billing_cycle', 'created_at']
    search_fields = ['tenant__name', 'user__email', 'promo_code']
    # readonly_fields = ['created_at', 'updated_at', 'current_user_count', 'last_user_count_updated_at']
    readonly_fields = ['created_at', 'updated_at', 'current_user_count', 'last_user_count_updated_at']
    fieldsets = (
        ('Subscriber', {
            'fields': ('tenant', 'user')
        }),
        ('Plan Details', {
            'fields': ('plan', 'billing_cycle', 'status', 'is_free', 'trial_end_date')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date', 'cancelled_at', 'grace_period_end')
        }),
        ('Pricing', {
            'fields': ('discount_applied', 'promo_code', 'promo_code_discount')
        }),
        ('User Tracking', {
            'fields': ('current_user_count', 'next_billing_user_count', 'last_user_count_updated_at')
        }),
        ('Settings', {
            'fields': ('auto_renew', 'created_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def subscriber_info(self, obj):
        if obj.tenant:
            return format_html('<strong>{}</strong><br><small>Tenant</small>', obj.tenant.name)
        elif obj.user:
            return format_html('<strong>{}</strong><br><small>Individual</small>', obj.user.email)
        return '-'
    subscriber_info.short_description = 'Subscriber'
    
    def get_monthly_rate(self, obj):
        return format_html('₦{}<br><small>Next: ₦{}</small>', 
                         obj.get_current_monthly_rate(), 
                         obj.get_next_monthly_rate())
    get_monthly_rate.short_description = 'Monthly Rate'


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = ['id', 'tenant', 'credit_type', 'amount', 'remaining_amount', 'expires_at', 'created_at']
    list_filter = ['credit_type', 'created_at']
    search_fields = ['tenant__name', 'reason']
    readonly_fields = ['created_at']



@admin.register(ExternalServiceLink)
class ExternalServiceLinkAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'external_url', 'is_active', 'display_order', 'created_at']
    list_filter = ['is_active', 'tenant', 'created_at']
    search_fields = ['name', 'description', 'tenant__name']
    list_editable = ['is_active', 'display_order']
    fieldsets = (
        ('Basic Information', {
            'fields': ('tenant', 'name', 'description', 'external_url')
        }),
        ('Display Settings', {
            'fields': ('icon', 'icon_color', 'display_order', 'open_in_new_tab')
        }),
        ('Status', {
            'fields': ('is_active', 'created_by')
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # Show only services for the user's tenant
            if hasattr(request.user, 'tenant') and request.user.tenant:
                return qs.filter(tenant=request.user.tenant)
            return qs.none()
        return qs
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
