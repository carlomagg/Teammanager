# documents/views.py
from .viewfuncs.booking_crud_views import booking_type_list, booking_type_create, booking_type_update, booking_type_delete
from .viewfuncs.booking_views import public_booking_page, ToggleBookingTypePublicAPIView, unified_calendar_public_view, PublicBookingCreateAPIView, booking_dashboard, bookings_list, booking_action, unified_organization_public_view, booking_success#, AvailableSlotsAPIView
from .viewfuncs.company_profile_views import view_company_profile, edit_user_profile
from .viewfuncs.conference_views import conference_create, conference_delete,conference_list, conference_update,conference_detail, conference_tag_autocomplete, post_conference, withdraw_conference_post, get_conference_feedbacks, conference_feedback, conference_feedback_code, get_speaker_detail, get_speakers_list, create_speaker_ajax, get_participant_responses, participant_detail
from .viewfuncs.conference_participant_views import conference_register, conference_access, participant_card, accept_conf_participant, decline_conf_participant, unregister_conf_participation, manage_conference_participants, manage_conference_participant, send_conference_reminders_manual, conference_payment_breakdown, conference_reg_success, export_participants_csv
from .viewfuncs.conference_participant_views import print_participants_pdf, checkin_scanner, process_checkin, manual_checkin, bulk_checkin, load_participants_custom_responses, conference_checkin_dashboard, conference_attended_list, conference_checkin_export_csv, conference_checkin_export_pdf, conference_checkin_manual, bulk_accept_participants
from .viewfuncs.conference_participant_views import conference_participant_uploads, conference_participant_uploads_anon
from .viewfuncs.conference_board_views import conference_board, conference_board_filters_view, conference_post
from .viewfuncs.contact_views import contact_list, create_contact, edit_contact, delete_contact, view_contact_detail
from .viewfuncs.custom_auth import CustomLoginView, home, register, account_activation_sent, get_tenant_url, forgot_password, reset_password, password_reset_sent, password_reset_success, post_login_redirect
from .viewfuncs.custom_errors import custom_400, custom_403, custom_404, custom_500
from .viewfuncs.custom_settings import email_config, email_config_success_view, custom_settings, change_password, change_password_success
from .viewfuncs.document_views import document_list, delete_document
from .viewfuncs.editor_docs import custom_ckeditor_upload, create_from_editor
from .viewfuncs.email_views import email_list, save_draft, send_email, email_detail, delete_email, delete_email_attachment, edit_email
from .viewfuncs.events_views import EventViewSet, UserViewSet, EventParticipantResponseView, calendar_view, BookingActionAPIView, InviteExternalParticipantAPIView
from .viewfuncs.file_views import upload_file, upload_file_anon, delete_file, move_file, rename_file, shared_file_view, enable_file_sharing, public_file_upload
from .viewfuncs.folder_views import folder_view, create_folder, shared_folder_view, enable_folder_sharing, delete_folder, move_folder, rename_folder
from .viewfuncs.guest_dashboard_views import guest_dashboard, guest_give_feedback
from .viewfuncs.help_views import contact_support
from .viewfuncs.helper_funcs.google_meet_calendar import google_oauth_callback
from .viewfuncs.helper_funcs.paystack import initialize_paystack_payment, generic_payment_callback, paystack_unified_webhook, get_bank_list
from .viewfuncs.helper_funcs.search_funcs import user_search, contact_search, accepted_vac_app_search, tag_search, skill_search, cities_search
from .viewfuncs.job_board_views import job_board, job_board_filters_view, vacancy_detail_view
from .viewfuncs.notification_views import notifications_view, dismiss_notification, dismiss_all_notifications, notification_redirect
from .viewfuncs.notification_api import check_new_notifications, notification_settings
from .viewfuncs.performance_dashboard import performance_dashboard, hod_performance_dashboard
from .viewfuncs.profile_views import view_my_profile, edit_my_profile, give_recommendation, delete_recommendation
from .viewfuncs.public_profile_views import public_profile_view, toggle_profile_public, toggle_section_visibility, toggle_company_public, toggle_company_section
from .viewfuncs.staff_views import staff_directory, view_staff_profile, staff_list, add_staff_document, delete_staff_document, staff_list, export_staff_csv
from .viewfuncs.task_views import task_list, task_detail, create_task, update_task_status, reassign_task, delete_task, task_edit, delete_task_document
from .viewfuncs.template_docs import create_document, approve_document, autocomplete_sales_rep, send_approved_email
from .viewfuncs.user_activity_dashboard import user_activity_dashboard, user_give_feedback
from .viewfuncs.admin.bulk_actions import bulk_delete, bulk_action_users
from .viewfuncs.admin.company_profile_views import edit_company_profile, add_company_document, delete_company_document, verify_bank_details, bank_verification, bank_confirmation, admin_verify_bank_details, admin_verify_user_bank_details
from .viewfuncs.admin.dashboard_views import admin_dashboard
from .viewfuncs.admin.department_views import assign_users_to_department, department_list, create_department, edit_department, delete_department, department_members
from .viewfuncs.admin.document_views import admin_documents_list, admin_document_details, admin_delete_document
from .viewfuncs.admin.event_views import create_event, event_list, delete_event, create_event_participant, event_participant_list, delete_event_participant, edit_event, edit_event_participant
from .viewfuncs.admin.file_views import admin_file_list, admin_delete_file
from .viewfuncs.admin.folder_views import admin_folder_list, admin_delete_folder, admin_folder_details
from .viewfuncs.admin.notifications_views import admin_notification_list, create_notification, edit_notification, delete_notification
from .viewfuncs.admin.staff_profile_views import staff_profile_list, create_staff_profile, edit_staff_profile, delete_staff_profile
from .viewfuncs.admin.task_views import admin_task_list, admin_task_detail
from .viewfuncs.admin.team_views import assign_users_to_team, admin_team_list, create_team, edit_team, delete_team, team_members
from .viewfuncs.admin.user_notifications_views import user_notification_list, create_user_notification, edit_user_notification, delete_user_notification
from .viewfuncs.admin.user_views import create_user, users_list, view_user_details, approve_user, edit_user, delete_user
from .viewfuncs.hr.dashboard_views import hr_dashboard
from .viewfuncs.hr.interview_funcs import interview_list, schedule_interview_from_scratch, interview_detail, schedule_interview_from_applications, load_applications_ajax, update_interview, cancel_interview, delete_interview, reschedule_interview, complete_interview
from .viewfuncs.hr.job_offer_views import onboard_employee, send_offer, offer_response, offer_thank_you, offer_list
from .viewfuncs.hr.vacancy_application_views import vacancy_application_list, send_vacancy_application_received, create_vacancy_application
from .viewfuncs.hr.vacancy_application_views import applications_per_vacancy, vacancy_application_detail, delete_vacancy_application, send_vacancy_accepted_mail, send_vacancy_rejected_mail, accept_vac_app, reject_vac_app, fetch_accepted_applications, fetch_rejected_applications
from .viewfuncs.hr.vacancy_views import vacancy_list, create_vacancy, edit_vacancy, vacancy_detail, delete_vacancy, share_vacancy, withdraw_vacancy, vacancy_post
from .viewfuncs.wallet_views import tenant_wallet_dashboard, tenant_transaction_detail, admin_remittance_dashboard, create_remittance, create_user_remittance, mark_remittance_completed, bulk_mark_remitted, edit_remittance, delete_remittance, process_remittance_payment, retry_remittance, admin_user_profile
# KYC/KYB Views
from .viewfuncs.kyc_views import kyc_status_view, complete_user_kyc, complete_staff_kyc, complete_company_kyb, add_company_director, edit_company_director, delete_company_director
from .viewfuncs.admin.kyc_admin_views import admin_kyc_dashboard, review_user_kyc, review_staff_kyc, review_company_kyb, auto_verify_user_kyc, auto_verify_staff_kyc, auto_verify_company_kyb
from .viewfuncs.payroll_views import (
    payroll_dashboard, payroll_list, payroll_detail, create_payroll, payroll_edit,
    submit_for_approval, approve_payroll, pay_payroll, manage_custom_fields,
    edit_custom_field, delete_custom_field, set_payroll_password_view,
    payroll_create, payroll_clone, payroll_add_row, payroll_add_column, payroll_update_item,
    payroll_update_column_value, payroll_delete_row, payroll_submit_approval,
    payroll_process_payment, payroll_export, payroll_update_column, payroll_delete_column
)
# from .viewfuncs.helper_funcs.paystack import paystack_transfer_webhook