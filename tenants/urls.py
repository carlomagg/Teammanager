from django.urls import path
from .views import home, apply_for_tenant, application_status, create_tenant, tenant_list, reject_tenant, tenant_applications, check_status, edit_tenant, delete_tenant, verify_tenant, delete_tenant_app, users_list, superuser_dashboard, company_group_dashboard, quick_services
from .views import add_company_group_member, edit_company_group_member, remove_company_group_member, get_company_group_member, bulk_add_company_group_members, company_group_list, company_group_detail, create_company_group_admin, edit_company_group_admin, edit_company_group, create_company_group
from .views import tenant_application_with_group, company_group_dashboard_admin
from .viewfuncs.conference_dashboard import track_conference

urlpatterns = [
    path('', home, name='tenant_home'),
    path('quick-services/', quick_services, name='quick_services'),
    path('apply-tenant/', apply_for_tenant, name='apply_for_tenant'),
    path('application-status/<int:identifier>/', application_status, name='application_status'),
    path('check-status/', check_status, name='check_status'),
    path('tenant-applications/', tenant_applications, name='tenant_applications'),
    path('tenant-applications/delte/<int:tenant_application_id>/', delete_tenant_app, name='delete_tenant_app'),
    path('create/<int:tenant_application_id>/', create_tenant, name='create_tenant'),
    path('reject/<int:tenant_application_id>/', reject_tenant, name='reject_tenant'),
    path('edit/<int:tenant_id>/', edit_tenant, name='edit_tenant'),
    path('delete/<int:tenant_id>/', delete_tenant, name='delete_tenant'),
    path('verify/<int:tenant_id>/', verify_tenant, name='verify_tenant'),
    path('list/', tenant_list, name='tenant_list'),
    path('users/list/', users_list, name='all_users_list'),
    path('dashboard/', superuser_dashboard, name='superuser_dashboard'),
    path('company-group/', company_group_dashboard, name='company_group_dashboard'),
    path('company-group-admin/', company_group_dashboard_admin, name='company_group_dashboard_admin'),
    path('company-group/list/', company_group_list, name='company_group_list'),
    path('company-group/<int:group_id>/register-tenant/', tenant_application_with_group, name='tenant_application_with_group'),
    path('company-groups/<int:group_id>/', company_group_detail, name='company_group_detail'),
    path('company-groups-admin/create/', create_company_group_admin, name='create_company_group_admin'),
    path('company-groups-admin/<int:group_id>/edit/', edit_company_group_admin, name='edit_company_group_admin'),
    path('company-groups/create/', create_company_group, name='create_company_group'),
    path('company-groups/<int:group_id>/edit/', edit_company_group, name='edit_company_group'),
    path('company-groups/<int:group_id>/members/', add_company_group_member, name='add_company_group_member'),
    path('company-groups/<int:group_id>/members/<int:tenant_id>/', get_company_group_member, name='get_company_group_member'),
    path('company-groups/<int:group_id>/members/<int:tenant_id>/edit/', edit_company_group_member, name='edit_company_group_member'),
    path('company-groups/<int:group_id>/members/<int:tenant_id>/delete/', remove_company_group_member, name='delete_company_group_member'),
    path('company-groups/<int:group_id>/bulk-add-members/', bulk_add_company_group_members, name='bulk_add_company_group_members'),
    path("tracking/conference-dashboard/", track_conference, name="track_conference"),     

]