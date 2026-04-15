from django.urls import path
from . import views

app_name = 'conference_loan'

urlpatterns = [
    # Dashboard
    path('', views.loan_dashboard, name='dashboard'),
    
    # Admin Dashboard (for tenant admin and superuser)
    path('admin-dashboard/', views.admin_loan_dashboard, name='admin_dashboard'),
    
    # Loan CRUD
    path('list/', views.loan_list, name='loan_list'),
    path('create/', views.loan_create, name='loan_create'),
    path('<int:pk>/', views.loan_detail, name='loan_detail'),
    path('<int:pk>/edit/', views.loan_edit, name='loan_edit'),
    path('<int:pk>/submit/', views.loan_submit, name='loan_submit'),
    
    # Documents
    path('<int:pk>/upload-document/', views.loan_upload_document, name='loan_upload_document'),
    
    # Review (staff only)
    path('<int:pk>/review/', views.loan_review, name='loan_review'),
    
    # AJAX
    path('check-kyc/', views.check_kyc_status, name='check_kyc_status'),
]


# Field-level approval URLs
from . import field_approval_views

urlpatterns += [
    path('field-approval/<int:loan_id>/<str:field_name>/approve/',
         field_approval_views.approve_loan_field,
         name='approve_loan_field'),
    
    path('field-approval/<int:loan_id>/<str:field_name>/reject/',
         field_approval_views.reject_loan_field,
         name='reject_loan_field'),
    
    path('field-approval/<int:loan_id>/approve-all/',
         field_approval_views.approve_all_loan_fields,
         name='approve_all_loan_fields'),
    
    path('field-approval/<int:loan_id>/status/',
         field_approval_views.get_loan_field_status,
         name='get_loan_field_status'),
]
