from django.urls import path
from . import views

app_name = 'fund_request'

urlpatterns = [
    # Dashboard
    path('', views.fund_request_dashboard, name='dashboard'),
    
    # Super Admin Dashboard
    path('superadmin/', views.superadmin_fund_request_dashboard, name='superadmin_dashboard'),

    # FundRequest CRUD & list
    path('list/', views.fund_request_list, name='fund_request_list'),
    path('create/', views.fund_request_create, name='fund_request_create'),
    path('<int:pk>/edit/', views.fund_request_edit, name='fund_request_edit'),
    path('<int:pk>/', views.fund_request_detail, name='fund_request_detail'),

    # Routing actions
    path('<int:pk>/keep-in-view/', views.fund_request_keep_in_view, name='fund_request_keep_in_view'),
    path('<int:pk>/keep-in-view-note/', views.fund_request_keep_in_view_with_note, name='fund_request_keep_in_view_with_note'),
    path('<int:pk>/withdraw/', views.fund_request_withdraw, name='fund_request_withdraw'),
    path('<int:pk>/mark-in-progress/', views.fund_request_mark_in_progress, name='fund_request_mark_in_progress'),
    path('<int:pk>/forward/', views.fund_request_forward, name='fund_request_forward'),
    path('<int:pk>/approve/', views.fund_request_approve, name='fund_request_approve'),
    path('<int:pk>/reject/', views.fund_request_reject, name='fund_request_reject'),
    path('<int:pk>/positive-response/', views.fund_request_positive_response, name='fund_request_positive_response'),
    path('<int:pk>/negative-response/', views.fund_request_negative_response, name='fund_request_negative_response'),
    path('<int:pk>/escalate/', views.fund_request_escalate, name='fund_request_escalate'),
    path('<int:pk>/request-info/', views.fund_request_request_info, name='fund_request_request_info'),
    path('<int:pk>/complete/', views.fund_request_complete, name='fund_request_complete'),
    path('<int:pk>/close/', views.fund_request_close, name='fund_request_close'),
    path('<int:pk>/reopen/', views.fund_request_reopen, name='fund_request_reopen'),

    # Comments
    path('<int:pk>/comment/', views.fund_request_add_comment, name='fund_request_add_comment'),

    # Categories
    path('categories/', views.fund_request_categories, name='categories'),
    path('categories/create/', views.fund_request_category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.fund_request_category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.fund_request_category_delete, name='category_delete'),
    
    # Request Types
    path('request-types/', views.fund_request_types, name='request_types'),
    path('request-types/create/', views.fund_request_type_create, name='request_type_create'),
    path('request-types/<int:pk>/edit/', views.fund_request_type_edit, name='request_type_edit'),
    path('request-types/<int:pk>/delete/', views.fund_request_type_delete, name='request_type_delete'),
]
