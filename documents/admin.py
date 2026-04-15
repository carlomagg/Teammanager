from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.sessions.models import Session
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from django.utils.text import Truncator
from django.db.models import Sum
from .invoice_admin import *
from .models import CustomUser, Role, Department, Team, StaffProfile, Notification, UserNotification, StaffDocument, Event, EventParticipant, CompanyProfile, Contact, Email, Folder, File, Attachment, Vacancy, VacancyApplication
from .models import Interview, InterviewParticipant, GoogleOAuthToken, Payment, Payee, Payer, Payroll, PayrollCustomColumn, PayrollColumnTemplate, PayrollItem, PayrollApproval, GuestUser, UserFeatureFlag, FeatureAnnouncement, ConferenceTag, CustomerSupport, Feedback, TenantBalance, Remittance, JobOffer, ContactTag
from .models import CustomAnswer, CustomQuestion, UserProfile, BookingType, Booking, ExternalParticipant, ConferencePriceTier, Recommendation
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    fieldsets = UserAdmin.fieldsets + (
        ("Additional Info", {
            "fields": ("tenant","roles", "phone_number","department","teams", "email_provider","email_address", "email_password", 
                        'is_personal', 'must_reset_password', 'subscription_status', 'subscription_end_date', 'subscription_plan',),
        }),
    )
    filter_horizontal = ("roles",)  # Allows multi-select in admin
    list_display = ("tenant","username", "email", "phone_number", "is_staff", "is_active", "is_personal", "email_address", "subscription_status", "subscription_end_date", "subscription_plan")
    list_filter = ("tenant", "roles", "is_staff", "is_active", "is_personal")

class SessionAdmin(admin.ModelAdmin):
    def _session_data(self, obj):
        return obj.get_decoded()

    list_display = ['session_key', '_session_data', 'expire_date']
    list_filter = ['expire_date']
    readonly_fields = ['_session_data']
    exclude = ['session_data'] # Exclude the raw session_data field

class FolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'tenant', 'is_public', 'is_shared', 'created_by', 'share_time_end']
    list_filter = ['parent', 'is_public', 'is_shared', 'tenant']

class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'hod']
    list_filter = ['tenant']

class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'tenant', 'department']
    list_filter = ['tenant']

class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'tenant', 'start_time', 'end_time']
    list_filter = ['tenant']

@admin.register(ExternalParticipant)
class ExternalParticipantAdmin(admin.ModelAdmin):
    list_display = ['email', 'event', 'response', 'invited_at', 'invited_by']
    list_filter = ['event', 'response', 'invited_at']
    search_fields = ['email']
    raw_id_fields = ['event', 'invited_by']   # helpful if many events/users
    readonly_fields = ['token']

class ContactAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'name', 'email', 'phone', 'organization', 'designation', 'priority', 'is_public']
    list_filter = ['tenant', 'priority', 'is_public']

class EmailAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'subject', 'sender', 'to_emails', 'created_at']
    list_filter = ['tenant', 'created_at']

class VacancyAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'title', 'country', 'status', 'is_shared', 'created_by', 'created_at', 'share_token']
    list_filter = ['tenant', 'status', 'country', 'is_shared', 'created_at']

class VacancyApplicationAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'vacancy', 'first_name', 'last_name', 'phone', 'email', 'status', 'created_at']
    list_filter = ['tenant', 'status', 'created_at']
class StaffDocumentInline(admin.TabularInline):
    model = StaffDocument
    extra = 1

class StaffProfileAdmin(admin.ModelAdmin):
    inlines = [StaffDocumentInline]



#document/admin.py

from django.contrib import admin
from .models import Conference, ConferenceParticipant

class ConferencePriceTierInline(admin.TabularInline):
    model = ConferencePriceTier
    extra = 1
    fields = ['name', 'price', 'capacity', 'is_active', 'order', 'description']

@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    inlines = [ConferencePriceTierInline]
    list_display = ('title', 'tenant', 'start_date', 'end_date', 'organizer', 'registration_required', 'ticket_price')
    list_filter = ('tenant', 'start_date', 'organizer', 'registration_required')
    search_fields = ('title', 'description', 'venue', 'organizer__email')
    date_hierarchy = 'start_date'

@admin.register(ConferenceParticipant)
class ConferenceParticipantAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'conference', 'registered_at', 'unique_token')
    list_filter = ('conference', 'registered_at')
    search_fields = ('first_name', 'last_name', 'email', 'conference__title', 'unique_token')


    
admin.site.register(Session, SessionAdmin)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Role)
admin.site.register(Department, DepartmentAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(StaffProfile, StaffProfileAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(EventParticipant)
admin.site.register(UserNotification)
admin.site.register(CompanyProfile)
admin.site.register(Contact, ContactAdmin)
admin.site.register(Email, EmailAdmin)
admin.site.register(Folder, FolderAdmin)
admin.site.register(File)
admin.site.register(Attachment)
admin.site.register(Vacancy, VacancyAdmin)
admin.site.register(VacancyApplication, VacancyApplicationAdmin)
admin.site.register(GoogleOAuthToken)
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'created_at', 'expires_at', 'is_active')
    list_filter = ('type', 'is_active')

class InterviewAdmin(admin.ModelAdmin):
    list_display = ('tenant','vacancy', 'status', 'schedule_start', 'schedule_end', 'is_virtual', 'scheduled_by', 'created_at', 'updated_at')
    list_filter = ('tenant', 'status', 'is_virtual', 'created_at', 'updated_at')
admin.site.register(Interview, InterviewAdmin)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'owner', 'payer', 'payee', 'amount', 'status', 'direction', 'created_at', 'updated_at', 'id', 'payment_type', 'linked_subscription')
    list_filter = ('tenant', 'owner', 'payee', 'status', 'direction','created_at', 'updated_at', 'payment_type')
    list_display = ['transaction_id', 'tenant', 'owner', 'payee','payment_type', 'amount', 'status', 'remittance_status', 'payment_date']
    list_filter = ['remittance_status', 'payment_type', 'status', 'tenant']
    search_fields = ['transaction_id', 'description']
    readonly_fields = ['created_at', 'updated_at']

    def linked_subscription(self, obj):
        if obj.content_object:
            return format_html('<a href="/admin/tenant/subscription/{}/change/">{}</a>', 
                             obj.object_id, obj.content_object)
        return '-'
    linked_subscription.short_description = 'Subscription'
    
    # fieldsets = (
    #     ('Remittance', {
    #         'fields': ('remittance_status', 'remittance', 'remitted_at'),
    #         'classes': ('collapse',)
    #     }),
    # )


@admin.register(Payer)
class PayerAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'user', 'name', 'email', 'phone', 'organization', 'address', 'paystack_customer_id', 'stripe_customer_id', 'created_at', 'updated_at')
    list_filter = ('tenant', 'created_at', 'updated_at')

@admin.register(Payee)
class PayeeAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'user', 'name', 'email', 'address', 'account_name', 'account_number', 'bank_name', 'routing_number', 'tax_id', 'created_at', 'updated_at')
    list_filter = ('tenant', 'created_at', 'updated_at')

@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'title', 'total_gross', 'total_net', 'status', 'is_locked', 'created_at', 'updated_at')
    list_filter = ('tenant', 'status', 'is_locked', 'created_at', 'updated_at')
    readonly_fields = ('total_gross', 'total_net', 'created_at', 'updated_at', 'paid_at', 'paid_by')
    search_fields = ('title', 'notes')


@admin.register(PayrollCustomColumn)
class PayrollCustomColumnAdmin(admin.ModelAdmin):
    list_display = ('payroll', 'name', 'operation', 'order', 'created_at')
    list_filter = ('payroll__tenant', 'operation', 'created_at')
    search_fields = ('name', 'payroll__title')
    ordering = ('payroll', 'order', 'name')


@admin.register(PayrollColumnTemplate)
class PayrollColumnTemplateAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'name', 'operation', 'is_default', 'created_at')
    list_filter = ('tenant', 'operation', 'is_default', 'created_at')
    search_fields = ('name',)
    ordering = ('tenant', 'name')


@admin.register(PayrollItem)
class PayrollItemAdmin(admin.ModelAdmin):
    list_display = ('payroll', 'staff_name', 'gross_amount', 'net_amount', 'order', 'created_at')
    list_filter = ('payroll__tenant', 'created_at')
    search_fields = ('staff_name', 'staff__username', 'staff__email')
    readonly_fields = ('created_at', 'updated_at', 'net_amount')
    ordering = ('payroll', 'order', 'staff_name')


@admin.register(PayrollApproval)
class PayrollApprovalAdmin(admin.ModelAdmin):
    list_display = ('payroll', 'approver', 'level', 'status', 'actioned_at', 'created_at')
    list_filter = ('payroll__tenant', 'status', 'level', 'created_at')
    search_fields = ('payroll__title', 'approver__username', 'approver__email')
    readonly_fields = ('created_at', 'actioned_at')
    ordering = ('payroll', 'level')

@admin.register(GuestUser)
class GuestUserAdmin(admin.ModelAdmin):
    list_display = ('email', 'token', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')

@admin.register(FeatureAnnouncement)
class FeatureAnnouncementAdmin(admin.ModelAdmin):
    list_display = ('key', 'label', 'days_visible', 'active', 'created_at')
    list_editable = ('label', 'days_visible', 'active')
    search_fields = ('key',)

# Keep your UserFeatureFlag admin too
@admin.register(UserFeatureFlag)
class UserFeatureFlagAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature_key', 'first_seen', 'dismissed')
    list_filter = ('feature_key', 'first_seen')
    search_fields = ('user__username', 'feature_key')

admin.site.register(ConferenceTag)
admin.site.register(ContactTag)


@admin.register(TenantBalance)
class TenantBalanceAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'owner','total_earned', 'total_remitted', 'available_balance', 'last_updated']
    list_filter = ['tenant', 'owner']
    readonly_fields = ['total_earned', 'total_remitted', 'available_balance', 'last_updated']
    search_fields = ['tenant__name', 'owner__username']
    
    # def has_add_permission(self, request):
    #     return False
    
    # def has_delete_permission(self, request, obj=None):
    #     return False


@admin.register(Remittance)
class RemittanceAdmin(admin.ModelAdmin):
    list_display = ['reference', 'tenant', 'owner', 'amount', 'status', 'created_at', 'completion_date', 'admin_actions']
    list_filter = ['status', 'created_at', 'tenant']
    search_fields = ['reference', 'tenant__name', 'bank_reference', 'owner__username']
    readonly_fields = ['reference', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Remittance Details', {
            'fields': ('tenant', 'owner', 'amount', 'description', 'status', 'remittance_date')
        }),
        ('Bank Details', {
            'fields': ('bank_reference', 'completion_date', 'bank_confirmation'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('reference', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Payments', {
            'fields': ('payments',),
            'classes': ('collapse',)
        }),
    )
    
    # ✅ RENAMED: Changed from 'actions' to 'admin_actions'
    def admin_actions(self, obj):
        if obj.status in ['pending', 'processing']:
            url = reverse('mark_remittance_completed', args=[obj.id])  # Fixed URL name
            return format_html(
                '<a href="{}" class="button" style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none;">Mark Completed</a>', 
                url
            )
        elif obj.status == 'completed':
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Completed</span>'
            )
        return '-'
    admin_actions.short_description = 'Actions'
    
    # ✅ CORRECT: This is the Django admin actions list
    actions = ['mark_as_completed']
    
    def mark_as_completed(self, request, queryset):
        updated_count = 0
        for remittance in queryset.filter(status__in=['pending', 'processing']):
            remittance.mark_as_completed(user=request.user)
            updated_count += 1
        
        if updated_count:
            self.message_user(
                request, 
                f"Successfully marked {updated_count} remittance(s) as completed.",
                messages.SUCCESS
            )
        else:
            self.message_user(
                request, 
                "No pending or processing remittances were selected.",
                messages.WARNING
            )
    mark_as_completed.short_description = "✅ Mark as completed"
    
    # Optional: Add more admin actions
    def mark_as_pending(self, request, queryset):
        queryset.update(status='pending', completion_date=None, bank_reference='')
        self.message_user(request, f"Marked {queryset.count()} remittances as pending")
    mark_as_pending.short_description = "⏳ Mark as pending"
    
    # Add this action to the actions list
    actions = ['mark_as_completed', 'mark_as_pending']
    
    # Make the payments field more user-friendly
    filter_horizontal = ['payments']
    
    # Custom form/save if needed
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
@admin.register(CustomerSupport)
class CustomerSupportAdmin(admin.ModelAdmin):
    list_display = ('entity_type', 'status', 'contacted_by', 'contacted_at', 'created_at', 'updated_at')
    list_filter = ('entity_type', 'status', 'contacted_at', 'created_at', 'updated_at')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('get_submitter', 'get_target_link', 'rating_stars', 'topic', 'comment_preview', 'tenant', 'created_at',)
    list_filter = ('tenant', 'content_type', 'rating', 'created_at', 'user', 'guest_user',)
    search_fields = ('comment', 'topic', 'anonymous_name', 'anonymous_email', 'user__email', 'user__username', 'guest_user__email',)
    readonly_fields = ('created_at', 'updated_at', 'get_target_link',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    def get_submitter(self, obj):
        if obj.user:
            try:
                ct = ContentType.objects.get_for_model(obj.user)
                url = reverse(
                    f'admin:{ct.app_label}_{ct.model}_change',
                    args=[obj.user.id]
                )
                return format_html('<a href="{}">{}</a>', url, str(obj.user))
            except (AttributeError):
                # Fallback: no admin link (e.g., custom User not registered properly)
                return f"User: {str(obj.user)}"

        elif obj.guest_user:
            try:
                ct = ContentType.objects.get_for_model(obj.guest_user)
                url = reverse(
                    f'admin:{ct.app_label}_{ct.model}_change',
                    args=[obj.guest_user.id]
                )
                # Adjust display as needed (e.g., show email if GuestUser has it)
                display = getattr(obj.guest_user, 'email', str(obj.guest_user))
                return format_html('<a href="{}">Guest: {}</a>', url, display)
            except (AttributeError):
                display = getattr(obj.guest_user, 'email', str(obj.guest_user))
                return f"Guest: {display}"

        elif obj.anonymous_name:
            return f"Anonymous: {obj.anonymous_name}"
        elif obj.anonymous_email:
            return f"Anonymous: {obj.anonymous_email}"
        else:
            return "Fully Anonymous"

    get_submitter.short_description = "Submitter"
    # Sorting will be approximate (by user ID if present)
    get_submitter.admin_order_field = 'user__id'

    def get_target_link(self, obj):
        if not obj.content_object:
            return "-"
        try:
            url = reverse(
                f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
                args=[obj.object_id]
            )
            return format_html('<a href="{}">{}</a>', url, str(obj.content_object))
        except Exception:
            # Fallback if the target model isn't registered in admin
            return str(obj.content_object)
    get_target_link.short_description = "Target Object"

    def rating_stars(self, obj):
        if obj.rating:
            full = '★' * obj.rating
            empty = '☆' * (5 - obj.rating)
            return format_html('<span title="{} stars">{}{}</span>', obj.rating, full, empty)
        return "-"
    rating_stars.short_description = "Rating"

    def comment_preview(self, obj):
        if obj.comment:
            # Truncate to ~100 characters for readability
            return Truncator(obj.comment).chars(100)
        return "-"
    comment_preview.short_description = "Comment Preview"

@admin.register(JobOffer)
class JobOfferAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'status', 'sent_at', 'created_by')
    list_filter = ('status', 'sent_at', 'created_by')
    search_fields = ('tenant', 'created_by__username', 'created_by__email')
    date_hierarchy = 'sent_at'
    ordering = ('-sent_at',)

# ADMIN CONFIGURATION FOR CUSTOM QUESTIONS

# ==================== INLINE ADMINS ====================

class CustomQuestionInline(admin.TabularInline):
    """Inline admin for editing custom questions within Conference admin"""
    model = CustomQuestion
    extra = 1
    fields = ['question', 'required', 'order']
    ordering = ['order']


class CustomAnswerInline(admin.TabularInline):
    """Inline admin for viewing custom answers within ConferenceParticipant admin"""
    model = CustomAnswer
    extra = 0
    readonly_fields = ['question', 'answer', 'created_at']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False


# ==================== MODEL ADMINS ====================

@admin.register(CustomQuestion)
class CustomQuestionAdmin(admin.ModelAdmin):
    list_display = ['question', 'conference', 'required', 'order', 'created_at']
    list_filter = ['required', 'conference', 'created_at']
    search_fields = ['question', 'conference__title']
    ordering = ['conference', 'order']
    
    fieldsets = (
        ('Question Details', {
            'fields': ('conference', 'question', 'required', 'order')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at']


@admin.register(CustomAnswer)
class CustomAnswerAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'conference', 'question_preview', 'answer_preview', 'created_at']
    list_filter = ['question__conference', 'created_at']
    search_fields = [
        'participant__first_name', 
        'participant__last_name', 
        'participant__email',
        'question__question', 
        'answer'
    ]
    readonly_fields = ['participant', 'question', 'answer', 'created_at']
    
    fieldsets = (
        ('Registration Info', {
            'fields': ('participant',)
        }),
        ('Question & Answer', {
            'fields': ('question', 'answer')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def participant_name(self, obj):
        """Display participant's full name"""
        return obj.participant.full_name
    participant_name.short_description = 'Participant'
    
    def conference(self, obj):
        """Display conference title"""
        return obj.question.conference.title
    conference.short_description = 'Conference'
    
    def question_preview(self, obj):
        """Show first 50 characters of question"""
        return obj.question.question[:50] + '...' if len(obj.question.question) > 50 else obj.question.question
    question_preview.short_description = 'Question'
    
    def answer_preview(self, obj):
        """Show first 50 characters of answer"""
        return obj.answer[:50] + '...' if len(obj.answer) > 50 else obj.answer
    answer_preview.short_description = 'Answer'





# ==================== CUSTOM ADMIN ACTIONS ====================

@admin.action(description='Export selected participants with custom answers')
def export_participants_with_answers(modeladmin, request, queryset):
    """
    Admin action to export selected participants with their custom answers to CSV
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="participants_export.csv"'
    
    writer = csv.writer(response)
    
    # Get all custom questions from the conferences of selected participants
    conferences = set(queryset.values_list('conference', flat=True))
    all_questions = CustomQuestion.objects.filter(
        conference__in=conferences
    ).order_by('conference', 'order')
    
    # Write header
    header = [
        'Conference', 'First Name', 'Last Name', 'Email', 
        'Phone', 'Organization', 'Status', 'Registered At'
    ]
    
    for question in all_questions:
        header.append(f"{question.conference.title}: {question.question}")
    
    writer.writerow(header)
    
    # Write data
    for participant in queryset.select_related('conference').prefetch_related('custom_answers'):
        row = [
            participant.conference.title,
            participant.first_name,
            participant.last_name,
            participant.email,
            participant.phone_number,
            participant.organization,
            participant.status,
            participant.registered_at.strftime('%Y-%m-%d %H:%M:%S'),
        ]
        
        # Add custom answers
        answers_dict = {
            answer.question_id: answer.answer 
            for answer in participant.custom_answers.all()
        }
        
        for question in all_questions:
            row.append(answers_dict.get(question.id, ''))
        
        writer.writerow(row)
    
    return response

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    # For personal user accounts
    list_display = ('first_name', 'last_name', 'email', 'sex', 'phone_number')
    list_filter = ('sex', 'religion')

@admin.register(BookingType)
class BookingTypeAdmin(admin.ModelAdmin):
    list_display = ('tenant',  'created_by', 'name', 'slug', 'uuid', 'duration_minutes', 'price', 'is_public', 'created_at')
    list_filter = ('tenant', 'is_public', 'created_at')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'email', 'first_name', 'last_name', 'booking_type', 'payment_status', 'status')
    list_filter = ('booking_type', 'created_at',)

@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ('recommender', 'staff_profile', 'user_profile', 'relationship', 'created_at', 'is_visible')
    list_filter = ('is_visible', 'created_at')
    search_fields = ('recommender__username', 'recommender__email', 'relationship', 'body')

# Register KYC/KYB models
from .admin_kyc import *
