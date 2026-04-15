from django.contrib import admin
from django.shortcuts import render
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include, register_converter
from django.contrib.sitemaps.views import sitemap
from rest_framework.routers import DefaultRouter
from documents import views as dv
from tenants import views as tv
from .sitemaps import StaticViewSitemap, PublicConferenceSitemap, PublicVacancySitemap
from .views import robots_txt
from documents.views import register, home, approve_document, send_approved_email, delete_document, view_my_profile
from documents.viewfuncs.custom_auth import unified_signup
from documents.views import edit_my_profile, staff_directory, view_staff_profile, staff_list, notifications_view
from documents.views import give_recommendation, delete_recommendation
from documents.views import public_profile_view, toggle_profile_public, toggle_section_visibility, toggle_company_public, toggle_company_section
from documents.views import dismiss_notification, add_staff_document, delete_staff_document, email_config, calendar_view
from documents.views import users_list, approve_user, account_activation_sent, delete_user, edit_user, custom_ckeditor_upload
from documents.views import dismiss_all_notifications, export_staff_csv, performance_dashboard, hod_performance_dashboard, notification_redirect
from documents.views import check_new_notifications, notification_settings
from documents.views import create_folder, upload_file, update_task_status, create_task, task_list, task_detail, reassign_task, delete_task
from documents.views import delete_folder, delete_file, rename_folder, rename_file, move_folder, move_file, task_edit, delete_task_document
from documents.views import performance_dashboard, hod_performance_dashboard
from documents.views import view_user_details, admin_dashboard, admin_delete_document, admin_delete_file, admin_delete_folder, admin_document_details
from documents.views import admin_folder_list, admin_folder_details, admin_file_list, department_list, bulk_delete, create_user, bulk_action_users
from documents.views import delete_department, edit_department, create_department, admin_team_list, create_team, delete_team, edit_team
from documents.views import staff_profile_list, create_staff_profile, delete_staff_profile, edit_staff_profile, event_list, create_event, edit_event, delete_event
from documents.views import event_participant_list, create_event_participant, edit_event_participant, delete_event_participant
from documents.views import admin_notification_list, create_notification, edit_notification, delete_notification, edit_company_profile, edit_user_profile, view_company_profile, verify_bank_details
from documents.views import user_notification_list, create_user_notification, edit_user_notification, delete_user_notification
from documents.views import custom_404, custom_403, custom_500, custom_400, post_login_redirect, contact_list, create_contact, edit_contact, delete_contact, view_contact_detail
from documents.views import email_list, send_email, edit_email, delete_email, email_detail, save_draft, CustomLoginView, upload_file_anon, public_file_upload
from documents.views import add_company_document, delete_company_document, shared_file_view, shared_folder_view, contact_support, folder_view, enable_folder_sharing, enable_file_sharing
from documents.viewfuncs.help_views import getting_started, policies, HR_landingPage, pricing, refund_policy
from documents.viewfuncs.helper_funcs import converters
from documents.views import tenant_wallet_dashboard, tenant_transaction_detail, admin_remittance_dashboard, create_remittance, create_user_remittance, mark_remittance_completed, bulk_mark_remitted, edit_remittance, delete_remittance
from documents.views import bank_confirmation, bank_verification, admin_verify_bank_details, admin_verify_user_bank_details, process_remittance_payment, retry_remittance, get_bank_list
from tenants.viewfuncs.subscription_views import cancel_subscription, create_subscription, client_subscription_payments, client_subscriptions, apply_credit, subscription_adjustments, subscription_base, subscription_detail, manage_paid_subscriptions, subscription_covered_users, get_plan_price, clear_subscription_restore_flag
from tenants.viewfuncs.subscription_views import subscription_payment_breakdown, subscription_payment_detail, subscription_success, manage_free_subscriptions, grant_free_access, revoke_free_access, extend_free_access, search_clients_for_free_access, get_tenant_users, get_tenant_users_with_subscription
from tenants.viewfuncs.subscription_type_views import create_subscription_plan, edit_subscription_plan, list_subscription_plans, toggle_subscription_plan_active, get_subscription_stats
from tenants.viewfuncs.promo_views import promo_create, promo_edit, promo_list, promo_stats, promo_toggle_active, validate_promo_code 
from documents.views import EventViewSet, UserViewSet, EventParticipantResponseView
from documents.viewfuncs import support_views
from django.http import HttpResponse

register_converter(converters.DecimalConverter, 'decimal')

router = DefaultRouter()
router.register('events', EventViewSet, basename='events')
router.register('users', UserViewSet, basename='event_users')

# SEO: Sitemap configuration
sitemaps = {
    'static': StaticViewSitemap,
    'conferences': PublicConferenceSitemap,
    'vacancies': PublicVacancySitemap,
}

def handle_well_known(request, path):
    return HttpResponse(status=204)  # Return 204 No Content

handler404 = custom_404
handler403 = custom_403
handler400 = custom_400
handler500 = custom_500

urlpatterns = [
    # SEO: Sitemap and robots.txt for search engine optimization
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
    
    path('admin/', admin.site.urls),
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('post-login/', post_login_redirect, name='post_login_redirect'),
    path("", home, name="home"),
    path("documents/", include("documents.urls")),  # Added namespace
    path("tenants/", include("tenants.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path('invoices/', include('documents.invoice_urls')),
    path('tickets/', include('documents.ticket_urls')),
    path('oauth2callback/', dv.google_oauth_callback, name='oauth2callback'),
    path('guest/dashboard/', dv.guest_dashboard, name='guest_dashboard'),
    path('dashboard/guest/give-feedback/<int:conference_id>/', dv.guest_give_feedback, name='guest_give_feedback'),
    # Override CKEditor upload
    path('ckeditor/upload/', custom_ckeditor_upload, name='ckeditor_upload'),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path("register/", register, name="register"),
    path("signup/", unified_signup, name="unified_signup"),
    path("getting-started/", getting_started, name="getting_started"),
    path("policies/", policies, name="policies"),
    path("refund-policy/", refund_policy, name="refund_policy"),
    path("pricing/", pricing, name="pricing"),
    path("pr/hr/" , HR_landingPage, name="HR_landingPage"),
    path("approve/<int:document_id>/", approve_document, name="approve_document"),
    path("send-email/<int:document_id>/", send_approved_email, name="send_approved_email"),
    path("delete/<int:document_id>/", delete_document, name="delete_document"),
    path("staff/", staff_directory, name="staff_directory"),
    path("staff/<int:user_id>/", view_staff_profile, name="view_staff_profile"),
    path("staff/list/", staff_list, name="staff_list"),
    path("staff/documents/add/", add_staff_document, name="add_staff_document"),
    path("staff/documents/delete/<int:document_id>", delete_staff_document, name="delete_staff_document"),
    path('staff/export-csv/', export_staff_csv, name='export_staff_csv'),
    path('notifications/', notifications_view, name='notifications'),
    path('notifications/<int:notification_id>/', notification_redirect, name='notification_redirect'),
    path('notifications/dismiss/', dismiss_notification, name='dismiss_notification'),
    path('notifications/dismiss-all/', dismiss_all_notifications, name='dismiss_all_notifications'),
    path('api/notifications/check/', check_new_notifications, name='check_new_notifications'),
    path('api/notifications/settings/', notification_settings, name='notification_settings'),
    path('dashboard/settings/', dv.custom_settings, name='custom_settings'),
    path('dashboard/password-change/', dv.change_password, name='change_password'),
    path('dashboard/password-change/success/', dv.change_password_success, name='change_password_success'),
    path('dashboard/email-config/', email_config, name='email_config'),
    path("dashboard/email-config/success/", dv.email_config_success_view, name="email_config_success"),
    path('api/', include(router.urls)),
    path('api/banks/', get_bank_list, name='get_bank_list'),
    path('api/events/<int:event_id>/respond/', EventParticipantResponseView.as_view(), name='event_participant_response'),
    path('calendar/', calendar_view, name='calendar'),
    path("dashboard/my-profile/", view_my_profile, name="view_my_profile"),
    path("dashboard/my-profile/edit/", edit_my_profile, name="edit_my_profile"),
    path('profile/<str:profile_type>/<int:profile_id>/recommend/', give_recommendation, name='give_recommendation'),
    path('profile/recommendation/<int:rec_id>/delete/', delete_recommendation, name='delete_recommendation'),

    # ── Public profile (no auth required) ────────────────────────────────
    path('p/<slug:slug>/', public_profile_view, name='public_profile'),

    # ── Profile toggle APIs (auth required) ──────────────────────────────
    path('api/profile/toggle-public/', toggle_profile_public, name='toggle_profile_public'),
    path('api/profile/toggle-section/', toggle_section_visibility, name='toggle_section_visibility'),
    path('api/company/toggle-public/', toggle_company_public, name='toggle_company_public'),
    path('api/company/toggle-section/', toggle_company_section, name='toggle_company_section'),
    path('dashboard/performance-dashboard/', performance_dashboard, name='performance_dashboard'),
    path('dashboard/hod-performance-dashboard/', hod_performance_dashboard, name='hod_performance_dashboard'),
    path('dashboard/contacts/', contact_list, name='contact_list'),
    path('dashboard/contacts/create/', create_contact, name='create_contact'),
    path('dashboard/contacts/<int:contact_id>/', view_contact_detail, name='view_contact_detail'),
    path('dashboard/contacts/edit/<int:contact_id>/', edit_contact, name='edit_contact'),
    path('dashboard/contacts/delete/<int:contact_id>/', delete_contact, name='delete_contact'),
    path('dashboard/emails/', email_list, name='email_list'),
    path('dashboard/emails/<int:email_id>', email_detail, name='email_detail'),
    path('dashboard/emails/<int:email_id>/delete-email-attachment/<int:attachment_id>/', dv.delete_email_attachment, name='delete_email_attachment'),
    path('dashboard/emails/save-draft/', save_draft, name='save_draft'),
    path('dashboard/emails/send/', send_email, name='send_email'),
    path('dashboard/activity/', dv.user_activity_dashboard, name='user_activity_dashboard'),
    path('dashboard/user/give-feedback/<int:conference_id>/', dv.user_give_feedback, name='user_give_feedback'),
    path('contacts/search/', dv.contact_search, name='contact_search'),
    path('tags/search/', dv.tag_search, name='tag_search'),
    path('skills/search/', dv.skill_search, name='skill_search'),
    path('cities/search/', dv.cities_search, name='cities_search'),
    path('dashboard/emails/edit/<int:email_id>', edit_email, name='edit_email'),
    path('dashboard/emails/delete/<int:email_id>', delete_email, name='delete_email'),
    path('folders/', folder_view, name="folder_view"),
    path('folders/public/<int:public_folder_id>/', folder_view, name='folder_view_public'),
    path('folders/personal/<int:personal_folder_id>/', folder_view, name='folder_view_personal'),
    path('folders/both/<int:public_folder_id>/<int:personal_folder_id>/', folder_view, name='folder_view_both'),
    path('share/<uuid:token>/', shared_file_view, name='shared_file_view'),
    path('share/folder/<uuid:token>/', shared_folder_view, name='shared_folder_view'),
    path('folders/<int:folder_id>/share/', enable_folder_sharing, name='enable_folder_sharing'),
    path('files/<int:file_id>/share/', enable_file_sharing, name='enable_file_sharing'),
    path('folders/create/', create_folder, name='create_folder'),
    # Updated upload_file patterns
    path('folders/upload/', upload_file, name='upload_file'),  # Root-level upload
    path('folders/upload/public/<int:public_folder_id>/', upload_file, name='upload_file_public'),  # Public folder upload
    path('folders/upload/personal/<int:personal_folder_id>/', upload_file, name='upload_file_personal'),  # Personal folder upload
    path('folders/upload/both/<int:public_folder_id>/<int:personal_folder_id>/', upload_file, name='upload_file_both'),  # Both folders
    path('folders/upload/shared/<int:folder_id>/', upload_file_anon, name='upload_file_public_anon'),  # Shared folder upload
    path('folders/upload/public/shared/<int:public_folder_id>/', upload_file_anon, name='upload_file_public_anon'),  # Shared folder public upload
    path('folders/upload/personal/shared/<int:personal_folder_id>/', upload_file_anon, name='upload_file_personal_anon'),  # Shared folder personal upload
    path('files/upload/public/<slug:tenant_slug>/', public_file_upload, name='public_file_upload'),  # General public upload (no login)
    path('folders/<int:folder_id>/delete/', delete_folder, name='delete_folder'),
    path('folders/files/<int:file_id>/delete/', delete_file, name='delete_file'),
    path('folders/<int:folder_id>/rename/', rename_folder, name='rename_folder'),
    path('folders/files/<int:file_id>/rename/', rename_file, name='rename_file'),
    path('folders/<int:folder_id>/move/', move_folder, name='move_folder'),
    path('folders/files/<int:file_id>/move/', move_file, name='move_file'),
    path('tasks/', task_list, name='task_list'),
    path('tasks/create/', create_task, name='create_task'),
    path('tasks/<int:task_id>/update-status/', update_task_status, name='update_task_status'),
    path('tasks/<int:task_id>/', task_detail, name='task_detail'),
    path('tasks/<int:task_id>/reassign/', reassign_task, name='reassign_task'),
    path('tasks/<int:task_id>/delete/', delete_task, name='delete_task'),
    path('tasks/<int:task_id>/edit/', task_edit, name='task_edit'),
    path('tasks/<int:task_id>/delete-task-document/<int:doc_id>/', delete_task_document, name='delete_document'),
    path("admins/dashboard/", admin_dashboard, name="admin_dashboard"),
    path('admins/bulk-delete/<str:model_name>/', bulk_delete, name='bulk_delete'),
    # Users URLs
    path('users-search/', dv.user_search, name='user_search'),
    path('admins/users/bulk-action/', bulk_action_users, name='bulk_action_users'),
    path('admins/users/list/', users_list, name='users_list'),
    path('admins/users/create/', create_user, name='create_user'),
    path('admins/users/view/<int:user_id>', view_user_details, name='view_user_details'),
    path('admins/users/approve/<int:user_id>', approve_user, name='approve_user'),
    path('admins/users/account-activation', account_activation_sent, name='account_activation_sent'),
    path('admins/users/account-activation/<int:user_id>', account_activation_sent, name='account_activation_sent'),
    path('admins/users/delete/<int:user_id>', delete_user, name='delete_user'),
    path('admins/users/edit/<int:user_id>', edit_user, name='edit_user'),
    # Department URLs
    path('admins/departments/', department_list, name='department_list'),
    path('admins/departments/create/', create_department, name='create_department'),
    path('admins/departments/edit/<int:department_id>/', edit_department, name='edit_department'),
    path('admins/departments/delete/<int:department_id>/', delete_department, name='delete_department'),
    path('admins/department/members/<int:department_id>/', dv.department_members, name='department_members'),
    # Team URLs
    path('admins/teams/', admin_team_list, name='admin_team_list'),
    path('admins/teams/create/', create_team, name='create_team'),
    path('admins/teams/edit/<int:team_id>/', edit_team, name='edit_team'),
    path('admins/teams/delete/<int:team_id>/', delete_team, name='delete_team'),
    path('admins/teams/members/<int:team_id>/', dv.team_members, name='team_members'),
    # New URLs for assigning users and teams
    path('department/<int:department_id>/assign-users/', dv.assign_users_to_department, name='assign_users_to_department'),
    path('team/<int:team_id>/assign-teams/', dv.assign_users_to_team, name='assign_teams_to_users'),
    # Staff Profile URLs
    path('admins/staff-profiles/', staff_profile_list, name='staff_profile_list'),
    path('admins/staff-profiles/create/', create_staff_profile, name='create_staff_profile'),
    path('admins/staff-profiles/edit/<int:staff_profile_id>/', edit_staff_profile, name='edit_staff_profile'),
    path('admins/staff-profiles/delete/<int:staff_profile_id>/', delete_staff_profile, name='delete_staff_profile'),
    # Events URLs
    path('admins/events/', event_list, name='event_list'),
    path('admins/events/create/', create_event, name='create_event'),
    path('admins/events/edit/<int:event_id>/', edit_event, name='edit_event'),
    path('admins/events/delete/<int:event_id>/', delete_event, name='delete_event'),
    # Event Participants URLs
    path('admins/event-participants/', event_participant_list, name='event_participant_list'),
    path('admins/event-participants/create/', create_event_participant, name='create_event_participant'),
    path('admins/event-participants/edit/<int:event_participant_id>/', edit_event_participant, name='edit_event_participant'),
    path('admins/event-participants/delete/<int:event_participant_id>/', delete_event_participant, name='delete_event_participant'),
    # Notifications URLs
    path('admins/notifications/list/', admin_notification_list, name='admin_notification_list'),
    path('admins/notifications/create/', create_notification, name='create_notification'),
    path('admins/notifications/edit/<int:notification_id>/', edit_notification, name='edit_notification'),
    path('admins/notifications/delete/<int:notification_id>/', delete_notification, name='delete_notification'),
    # User Notifications URLs
    path('admins/user-notifications/', user_notification_list, name='user_notification_list'),
    path('admins/user-notifications/create/', create_user_notification, name='create_user_notification'),
    path('admins/user-notifications/edit/<int:user_notification_id>/', edit_user_notification, name='edit_user_notification'),
    path('admins/user-notifications/delete/<int:user_notification_id>/', delete_user_notification, name='delete_user_notification'),
    # Company Profile URLs
    path('admins/company-profile/', edit_company_profile, name='edit_company_profile'),
    path('user-profile/', edit_user_profile, name='edit_user_profile'),
    path('admins/company/documents/add/', add_company_document, name="add_company_document"),
    path('admins/company/documents/delete/<int:document_id>/', delete_company_document, name="delete_company_document"),
    # path('admins/verify-bank-details/<int:profile_id>/', verify_bank_details, name='verify_bank_details'),

    path('company-profile/', view_company_profile, name='view_company_profile'),
    path('my-profile/', view_my_profile, name='view_user_profile'),
    path('contact-support/', contact_support, name='contact_support'),
    # Password Reset URLs
    path('forgot-password/', dv.forgot_password, name='forgot_password'),
    path('reset-password/<uidb64>/<token>/', dv.reset_password, name='reset_password'),
    path('password-reset-success/', dv.password_reset_success, name='password_reset_success'),
    path('password-reset-sent', dv.password_reset_sent, name="password_reset_sent"),
    # HR Vacancies
    path('hr/', dv.hr_dashboard, name='hr_dashboard'),
    path('vacancy/', dv.vacancy_list, name='vacancy_list'),
    path('vacancy/create/', dv.create_vacancy, name='create_vacancy'),
    path('vacancy/<int:vacancy_id>/', dv.vacancy_detail, name='vacancy_detail'),
    path('vacancy/edit/<int:vacancy_id>/', dv.edit_vacancy, name='edit_vacancy'),
    path('vacancy/delete/<int:vacancy_id>/', dv.delete_vacancy, name='delete_vacancy'),
    path('vacancy/share/<int:vacancy_id>/', dv.share_vacancy, name='share_vacancy'),
    path('vacancy/withdraw/<int:vacancy_id>/', dv.withdraw_vacancy, name='withdraw_vacancy'),
    path('vacancy/post/<uuid:token>/', dv.vacancy_post, name='vacancy_post'),
    # Vacancy Applications
    path('vacancy/apply/<int:vacancy_id>/', dv.create_vacancy_application, name='apply_vacancy'),
    path('vacancy/applications/', dv.vacancy_application_list, name='vacancy_application_list'),
    path('vacancy/applications/<int:vacancy_id>/accepted/', dv.fetch_accepted_applications, name='fetch_accepted_applications'),
    path('vacancy/applications/<int:vacancy_id>/rejected/', dv.fetch_rejected_applications, name='fetch_rejected_applications'),
    path('vacancy/applications/<int:vacancy_id>/', dv.applications_per_vacancy, name='applications_per_vacancy'),
    path('vacancy/applications/<int:vacancy_id>/<int:application_id>/', dv.vacancy_application_detail, name='vacancy_application_detail'),
    path('vacancy/applications/<int:vacancy_id>/<int:application_id>/delete/', dv.delete_vacancy_application, name='delete_vacancy_app'),
    path('vacancy/applications/<int:application_id>/accept/', dv.accept_vac_app, name='accept_vac_app'),
    path('vacancy/applications/<int:application_id>/reject/', dv.reject_vac_app, name='reject_vac_app'),
    path('vacancy/applications/accepted-applications/search/', dv.accepted_vac_app_search, name='accepted_vac_app_search'),

    # Interviews
    path('interview/', dv.interview_list, name='interview_list'),
    path('interview/create/', dv.schedule_interview_from_scratch, name='schedule_from_scratch'),
    path('interview/vacancy/<int:vacancy_id>/schedule/', dv.schedule_interview_from_applications, name='schedule_from_applications'),
    path('interview/<int:interview_id>/', dv.interview_detail, name='interview_detail'),
    path('interview/update/<int:interview_id>/', dv.update_interview, name='update_interview'),
    path('interview/cancel/<int:interview_id>/', dv.cancel_interview, name='cancel_interview'),
    path('interview/delete/<int:interview_id>/', dv.delete_interview, name='delete_interview'),
    path('ajax/load-applications/', dv.load_applications_ajax, name='ajax_load_applications'),
    path('interviews/<int:interview_id>/reschedule/', dv.reschedule_interview, name="reschedule_interview"),
    path('interviews/<int:interview_id>/complete/', dv.complete_interview, name="complete_interview"),

    # Job Offer / Onboard
    path('vacancy/application/onboard/<int:application_id>/<int:interview_id>/', dv.onboard_employee, name='onboard_employee'),
    path('vacancy/application/send-offer/<int:application_id>/<int:interview_id>/', dv.send_offer, name='send_offer'),
    path('vacancy/application/offer/response/<uuid:token>', dv.offer_response, name='offer_response'),
    path('vacancy/applicatio/offer/response/success/', dv.offer_thank_you, name='offer_thank_you'),
    path('hr/offers/list', dv.offer_list, name='offer_list'),

    # Tracking Dashboard
    path('tracking/', tv.tracking_dashboard, name='tracking_dashboard'),
    path('tracking/task/', tv.track_tasks, name='track_task'),
    path('tracking/folder-file/', tv.track_folder_file, name='track_folder_file'),
    path('tracking/vacancy/', tv.track_vacancy, name="track_vacancy"),
    path('tracking/users/', tv.track_user, name='track_user'),

    # Job Board

    # Job Board
    path('job-board/', dv.job_board, name='job_board'),
    path('job-board/filters/', dv.job_board_filters_view, name='job_board_filters'),
    # path('job-board/vacancy/<int:vacancy_id>/', dv.vacancy_detail_view, name='vacancy_detail'),

    # Conference
    # Add conference paths here
    path('conference/', dv.conference_list, name='conference_list'),
    path('conference/create/', dv.conference_create, name='create_conference'),
    path('conference/<int:conference_id>/', dv.conference_detail, name='conference_detail'),
    path('conference/edit/<int:conference_id>/', dv.conference_update, name='edit_conference'),
    path('conference/delete/<int:conference_id>/', dv.conference_delete, name='delete_conference'),
    path('conference/register/<int:conference_id>/', dv.conference_register, name='conference_register'),
    path('conference-board/', dv.conference_board, name='conference_board'),
    path('conference-board/filters', dv.conference_board_filters_view, name='conference_board_filters'),
    path('conference-board/post/<int:conference_id>', dv.conference_post, name='conference_post'),
    path('conference/participant/access/<int:conference_id>/<uuid:token>/', dv.conference_access, name='conference_access'),
    path('conference/participant/card/<int:id>/', dv.participant_card, name='participant_card'),
    path('conference/participant/accept/<int:id>/', dv.accept_conf_participant, name='accept_conf_participant'),
    path('conference/participant/decline/<int:id>/', dv.decline_conf_participant, name='decline_conf_participant'),
    path('conference/participant/unregister/<int:id>/', dv.unregister_conf_participation, name='unregister_conf_participation'),
    path('conference/participant/manage/all/<int:conference_id>/', dv.manage_conference_participants, name='manage_conference_participants'),
    path('conference/participant/manage/<int:conference_id>/<int:participant_id>/', dv.manage_conference_participant, name='manage_conference_participant'),
    path('conference/<int:conference_id>/participants/reminders/send/', dv.send_conference_reminders_manual, name='send_conference_reminders_manual'),
    path('conference/<int:conference_id>/payment/breakdown/<int:participant_id>/', dv.conference_payment_breakdown, name='conference_payment_breakdown'),
    path('conference/tags/autocomplete/', dv.conference_tag_autocomplete, name='conference_tag_autocomplete'),
    path('conference/registration/success/', dv.conference_reg_success, name='conference_reg_success'),
    path('conference/<int:conference_id>/participants/export/csv/', dv.export_participants_csv, name='export_participants_csv'),
    path('conference/<int:conference_id>/participants/print/', dv.print_participants_pdf, name='print_participants_pdf'),
    path('conference/post/<int:conference_id>', dv.post_conference, name='post_conference'),
    path('conference/post/withdraw/<int:conference_id>', dv.withdraw_conference_post, name='withdraw_conference_post'),
    path('conference/<int:conference_id>/give-feedback/', dv.conference_feedback, name='conference_feedback'),
    path('conference/<int:conference_id>/feedback/share/', dv.conference_feedback_code, name='conference_feedback_code'),
    path('conference/<int:conference_id>/feedbacks/', dv.get_conference_feedbacks, name='conference_feedbacks'),
    path('conference/<int:conference_id>/checkin/scan/', dv.checkin_scanner, name='checkin_scanner'),
    path('checkin/process/<uuid:token>/', dv.process_checkin, name='process_checkin'),
    path('manual-checkin/<int:conference_id>/<int:participant_id>/', dv.manual_checkin, name='manual_checkin'),
    path("conference/<int:conference_id>/bulk-checkin/", dv.bulk_checkin, name="bulk_checkin"),
    path('conference/participant/<int:participant_id>/responses/',  dv.load_participants_custom_responses, name='load_participants_custom_responses'),
    # path('conference/participant/<int:participant_id>/responses/',  dv.load_participants_custom_responses, name='load_participants_custom_responses'),
    path('conference/speakers/list/', dv.get_speakers_list, name='api_speakers_list'),
    path('conference/speakers/create/', dv.create_speaker_ajax, name='api_speaker_create'),
    path('conference/speakers/<int:speaker_id>/', dv.get_speaker_detail, name='api_speaker_detail'),
    # Participant responses endpoint
    path('conference/participant/<int:participant_id>/responses/', dv.get_participant_responses, name='participant_responses'),
    path('conference/participant/<int:participant_id>/', dv.participant_detail, name='participant_detail'),
    path('conference/<int:conference_id>/checkin/', dv.conference_checkin_dashboard, name='conference_checkin_dashboard'),
    path('conference/<int:conference_id>/attended/', dv.conference_attended_list, name='conference_attended_list'),
    path('conference/<int:conference_id>/export/csv/', dv.conference_checkin_export_csv, name='conference_checkin_export_csv'),
    path('conference/<int:conference_id>/export/pdf/', dv.conference_checkin_export_pdf, name='conference_checkin_export_pdf'),
    path('conference/<int:conference_id>/checkin/manual/<int:participant_id>/', dv.conference_checkin_manual, name='conference_checkin_manual'),
    path('conference/<int:conference_id>/bulk-accept/', dv.bulk_accept_participants, name='bulk_accept_participants'),
    path('conference/<int:conference_id>/uploads/', dv.conference_participant_uploads, name='conference_participant_uploads'),
    path('conference/<int:conference_id>/uploads/<str:token>/', dv.conference_participant_uploads_anon, name='conference_participant_uploads_anon'),
    
    # Customer Support Dashboard
    path('support/', support_views.support_dashboard, name='support_dashboard'),
    path('support/record/<int:support_id>/', support_views.support_record_detail, name='support_record_detail'),
    path('support/mark-contacted/<int:support_id>/', support_views.mark_as_contacted, name='mark_as_contacted'),
    path('support/update-status/<int:support_id>/', support_views.update_support_status, name='update_support_status'),
    path('support/add-notes/<int:support_id>/', support_views.add_support_notes, name='add_support_notes'),
    path('support/delete/<int:support_id>/', support_views.delete_support_record, name='delete_support_record'),
    path('support/convert-to-staff/<int:support_id>/', support_views.convert_user_to_staff, name='convert_user_to_staff'),
    path('support/convert-to-tenant/<int:support_id>/', support_views.convert_user_to_tenant, name='convert_user_to_tenant'),
    
    # Payments
    path('webhook/paystack/', dv.paystack_unified_webhook, name='paystack_webhook'),
    path('paystack/callback/', dv.generic_payment_callback, name='generic_payment_callback'),

    # Wallets
    path('wallet/', dv.tenant_wallet_dashboard, name='tenant_wallet'),
    path('wallet/transaction/<int:payment_id>/', dv.tenant_transaction_detail, name='transaction_detail'),

    # Payroll - Modern Dashboard
    path('payroll/', dv.payroll_dashboard, name='payroll_dashboard'),
    
    # Payroll AJAX Endpoints
    path('payroll/api/create/', dv.payroll_create, name='payroll_create'),
    path('payroll/api/clone/', dv.payroll_clone, name='payroll_clone'),
    path('payroll/api/add-row/', dv.payroll_add_row, name='payroll_add_row'),
    path('payroll/api/add-column/', dv.payroll_add_column, name='payroll_add_column'),
    path('payroll/api/update-column/', dv.payroll_update_column, name='payroll_update_column'),
    path('payroll/api/delete-column/', dv.payroll_delete_column, name='payroll_delete_column'),
    path('payroll/api/update-item/', dv.payroll_update_item, name='payroll_update_item'),
    path('payroll/api/update-column-value/', dv.payroll_update_column_value, name='payroll_update_column_value'),
    path('payroll/api/delete-row/', dv.payroll_delete_row, name='payroll_delete_row'),
    path('payroll/api/submit-approval/', dv.payroll_submit_approval, name='payroll_submit_approval'),
    path('payroll/api/process-payment/', dv.payroll_process_payment, name='payroll_process_payment'),
    path('payroll/export/', dv.payroll_export, name='payroll_export'),
    
    # Old Payroll URLs (keep for backward compatibility)
    path('payroll/list/', dv.payroll_list, name='payroll_list'),
    path('payroll/create/', dv.create_payroll, name='create_payroll'),
    path('payroll/<int:pk>/', dv.payroll_detail, name='payroll_detail'),
    path('payroll/<int:pk>/edit/', dv.payroll_edit, name='payroll_edit'),
    path('payroll/<int:pk>/submit/', dv.submit_for_approval, name='submit_for_approval'),
    path('payroll/<int:pk>/approve/', dv.approve_payroll, name='approve_payroll'),
    path('payroll/<int:pk>/pay/', dv.pay_payroll, name='pay_payroll'),
    path('payroll/custom-fields/', dv.manage_custom_fields, name='manage_custom_fields'),
    path('payroll/custom-fields/<int:pk>/edit/', dv.edit_custom_field, name='edit_custom_field'),
    path('payroll/custom-fields/<int:pk>/delete/', dv.delete_custom_field, name='delete_custom_field'),
    path('payroll/set-password/', dv.set_payroll_password_view, name='set_payroll_password'),

    # CRM
    path('crm/', include('crm.urls', namespace='crm')),

    # Mail & Memo
    path('memo/', include('memo.urls', namespace='memo')),

    # HR Staff Requests
    path('leave/', include('leave.urls', namespace='leave')),
    path('permissions/', include('permissions.urls', namespace='permissions')),
    path('fund-request/', include('fund_request.urls', namespace='fund_request')),

    # Conference Loans
    path('loans/', include('conference_loan.urls', namespace='conference_loan')),

    #checkin
    path('checkin/', include('checkin.urls', namespace='checkin')),
    
    # Admin remittance URLs
    path('admins/remittances/', dv.admin_remittance_dashboard, name='admin_remittance_dashboard'),
    path('admins/remittances/create/<int:tenant_id>/', dv.create_remittance, name='create_remittance'),
    path('admins/remittances/create/user/<int:user_id>/', dv.create_user_remittance, name='create_user_remittance'),
    path('admins/remittances/mark-completed/<int:remittance_id>/', dv.mark_remittance_completed, name='mark_remittance_completed'),
    path('admins/remittances/bulk-mark/', dv.bulk_mark_remitted, name='bulk_mark_remitted'),
    path('admins/remittances/edit/<int:remittance_id>/', dv.edit_remittance, name='edit_remittance'),  # Add this
    path('admins/remittances/delete/<int:remittance_id>/', dv.delete_remittance, name='delete_remittance'),
    path('wallet/transaction/<int:payment_id>/', dv.tenant_transaction_detail, name='tenant_transaction_detail'),
    path('wallet/bank-verification/', dv.bank_verification, name='bank_verification'),
    path('wallet/bank-confirmation/', dv.bank_confirmation, name='bank_confirmation'),
    path('admins/verify-bank/<int:tenant_id>/', dv.admin_verify_bank_details, name='admin_verify_bank_details'),
    path('admins/verify-bank/', dv.admin_verify_bank_details, name='admin_verify_own_bank'),
    path('admins/verify-user-bank/<int:user_id>/', dv.admin_verify_user_bank_details, name='admin_verify_user_bank_details'),
    path('admins/user-profile/', dv.admin_user_profile, name='admin_user_profile'),

    # Remittances
    path('remittance/<int:remittance_id>/process/', dv.process_remittance_payment, name='process_remittance_payment'),
    # path('webhook/paystack/transfer/', dv.paystack_transfer_webhook, name='paystack_transfer_webhook'),
    path('remittance/<int:remittance_id>/retry/', dv.retry_remittance, name='retry_remittance'),
    path('admin/company-profile/<int:tenant_id>/', view_company_profile, name='admin_company_profile'),

    path('subscriptions/', subscription_base, name='subscription_base'),
    path('subscriptions/my-subscriptions/', client_subscriptions, name='client_subscriptions'),
    path('subscriptions/create/', create_subscription, name='create_subscription'),
    path('subscriptions/<int:pk>/', subscription_detail, name='subscription_detail'),
    path('subscriptions/<int:pk>/cancel/', cancel_subscription, name='cancel_subscription'),
    path('subscriptions/<int:subscription_id>/apply-credit/', apply_credit, name='apply_credit'),
    
    path('subscriptions/plans/', list_subscription_plans, name='list_subscription_plans'),
    path('subscriptions/plans/create/', create_subscription_plan, name='create_subscription_plan'),
    path('subscriptions/plans/<int:pk>/edit/', edit_subscription_plan, name='edit_subscription_plan'),
    path('subscriptions/plans/<int:pk>/toggle/', toggle_subscription_plan_active, name='toggle_subscription_plan_active'),
    
    # Payment URLs
    path('subscriptions/payments/', client_subscription_payments, name='client_subscription_payments'),
    path('subscriptions/payments/<int:pk>/', subscription_payment_detail, name='subscription_payment_detail'),
    path('subscriptions/tenant-users/', get_tenant_users, name='get_tenant_users'),
    path('subscriptions/tenant-users-with-subscription/', get_tenant_users_with_subscription, name='get_tenant_users_with_subscription'),
    path('subscriptions/get-plan-price/<int:plan_id>/', get_plan_price, name='get_plan_price'),
    path('subscriptions/clear-restore/', clear_subscription_restore_flag, name='clear_subscription_restore'),

    
    # Admin URLs
    path('admins/subscription-adjustments/', subscription_adjustments, name='subscription_adjustments'),
    
    path('subscriptions/stats/', get_subscription_stats, name='get_subscription_stats'),

    path('validate-promo/', validate_promo_code, name='validate_promo_code'),
    
    path('admins/promos/', promo_list, name='promo_list'),
    path('admins/promos/create/', promo_create, name='promo_create'),
    path('admins/promos/<int:pk>/edit/', promo_edit, name='promo_edit'),
    path('admins/promos/<int:pk>/toggle/', promo_toggle_active, name='promo_toggle_active'),
    path('admins/promos/<int:pk>/stats/', promo_stats, name='promo_stats'),

    path('admins/subscriptions/free/',manage_free_subscriptions, name='manage_free_subscriptions'),
    path('admins/subscriptions/paid/', manage_paid_subscriptions, name='manage_paid_subscriptions'),
    path('admins/subscriptions/grant-free-access/',grant_free_access, name='grant_free_access'),
    path('admins/subscriptions/revoke-free-access/',revoke_free_access, name='revoke_free_access'),
    path('admins/subscriptions/extend-free-access/', extend_free_access, name='extend_free_access'),
    path('admins/subscriptions/free-search/', search_clients_for_free_access, name='search_clients_for_free_access'),
    
    path('payment/<int:subscription_id>/', subscription_payment_breakdown, name='subscription_payment_breakdown'),
    path('subscriptions/success/', subscription_success, name='subscription_success'),
    path('subscriptions/<int:subscription_id>/users/', subscription_covered_users, name='subscription_covered_users'),

    # Booking Types
    path('bookings/booking-types/', dv.booking_type_list, name='booking_type_list'),
    path('bookings/booking-types/create/', dv.booking_type_create, name='booking_type_create'),
    path('bookings/booking-types/<uuid:uuid>/edit/', dv.booking_type_update, name='booking_type_update'),
    path('bookings/booking-types/<uuid:uuid>/delete/', dv.booking_type_delete, name='booking_type_delete'),
    path('bookings/book/<uuid:booking_type_uuid>/', dv.public_booking_page, name='public_booking'),
    path('api/booking-types/<uuid:uuid>/toggle-public/', dv.ToggleBookingTypePublicAPIView.as_view(), name='toggle-booking-public'),
    path('bookings/book/<int:user_id>/', dv.unified_calendar_public_view, name='unified_calendar_public'),
    path('bookings/book/org/<slug:tenant_slug>/', dv.unified_organization_public_view, name='public_org_calendar'),
    path('api/bookings/public-create/', dv.PublicBookingCreateAPIView.as_view(), name='public-booking-create'),
    path('api/bookings/<uuid:booking_uuid>/confirm/', dv.BookingActionAPIView.as_view(), {'action': 'confirm'}),
    path('api/bookings/<uuid:booking_uuid>/decline/', dv.BookingActionAPIView.as_view(), {'action': 'decline'}),
    # path('api/bookings/available-slots/<int:user_id>/', dv.AvailableSlotsAPIView.as_view(), name='available_slots_api'),
    path('bookings/dashboard/', dv.booking_dashboard, name='booking_dashboard'),
    path('bookings/list/', dv.bookings_list, name='bookings_list'),
    path('bookings/<uuid:uuid>/action/<str:action>/', dv.booking_action, name='booking_action'),
    path('bookings/success/<uuid:uuid>/', dv.booking_success, name='booking_success'),
    path('api/events/<int:event_id>/invite-external/', dv.InviteExternalParticipantAPIView.as_view(), name='invite_external'),

    # KYC/KYB URLs
    path('dashboard/kyc/', dv.kyc_status_view, name='kyc_status'),
    path('dashboard/kyc/complete/user/', dv.complete_user_kyc, name='complete_user_kyc'),
    path('dashboard/kyc/complete/staff/', dv.complete_staff_kyc, name='complete_staff_kyc'),
    path('dashboard/kyb/complete/', dv.complete_company_kyb, name='complete_company_kyb'),
    path('dashboard/kyb/director/add/', dv.add_company_director, name='add_company_director'),
    path('dashboard/kyb/director/<int:director_id>/edit/', dv.edit_company_director, name='edit_company_director'),
    path('dashboard/kyb/director/<int:director_id>/delete/', dv.delete_company_director, name='delete_company_director'),
    
    # Admin KYC/KYB Review URLs
    path('admins/kyc/', dv.admin_kyc_dashboard, name='admin_kyc_dashboard'),
    path('admins/kyc/user/<int:kyc_id>/review/', dv.review_user_kyc, name='review_user_kyc'),
    path('admins/kyc/staff/<int:kyc_id>/review/', dv.review_staff_kyc, name='review_staff_kyc'),
    path('admins/kyb/<int:kyb_id>/review/', dv.review_company_kyb, name='review_company_kyb'),
    
    # Admin KYC/KYB Auto-Verify URLs (YouVerify API)
    path('admins/kyc/user/<int:kyc_id>/auto-verify/', dv.auto_verify_user_kyc, name='auto_verify_user_kyc'),
    path('admins/kyc/staff/<int:kyc_id>/auto-verify/', dv.auto_verify_staff_kyc, name='auto_verify_staff_kyc'),
    path('admins/kyb/<int:kyb_id>/auto-verify/', dv.auto_verify_company_kyb, name='auto_verify_company_kyb'),
    
    # KYC/KYB Field-Level Approval URLs
    path('kyc-field-approval/', include('documents.kyc_field_approval_urls')),

    # KYC/KYB URLs
    path('dashboard/kyc/', dv.kyc_status_view, name='kyc_status'),
    path('dashboard/kyc/complete/user/', dv.complete_user_kyc, name='complete_user_kyc'),
    path('dashboard/kyc/complete/staff/', dv.complete_staff_kyc, name='complete_staff_kyc'),
    path('dashboard/kyb/complete/', dv.complete_company_kyb, name='complete_company_kyb'),
    path('dashboard/kyb/director/add/', dv.add_company_director, name='add_company_director'),
    path('dashboard/kyb/director/<int:director_id>/edit/', dv.edit_company_director, name='edit_company_director'),
    path('dashboard/kyb/director/<int:director_id>/delete/', dv.delete_company_director, name='delete_company_director'),
    
    # Admin KYC/KYB Review URLs
    path('admins/kyc/', dv.admin_kyc_dashboard, name='admin_kyc_dashboard'),
    path('admins/kyc/user/<int:kyc_id>/review/', dv.review_user_kyc, name='review_user_kyc'),
    path('admins/kyc/staff/<int:kyc_id>/review/', dv.review_staff_kyc, name='review_staff_kyc'),
    path('admins/kyb/<int:kyb_id>/review/', dv.review_company_kyb, name='review_company_kyb'),
    
    # Admin KYC/KYB Auto-Verify URLs (YouVerify API)
    path('admins/kyc/user/<int:kyc_id>/auto-verify/', dv.auto_verify_user_kyc, name='auto_verify_user_kyc'),
    path('admins/kyc/staff/<int:kyc_id>/auto-verify/', dv.auto_verify_staff_kyc, name='auto_verify_staff_kyc'),
    path('admins/kyb/<int:kyb_id>/auto-verify/', dv.auto_verify_company_kyb, name='auto_verify_company_kyb'),

    path('.well-known/<path:path>', handle_well_known),  # Handle .well-known requests
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)