from django.urls import path
from . import views

app_name = 'memo'

urlpatterns = [
    # Dashboard
    path('', views.memo_dashboard, name='dashboard'),
    
    # Super Admin Dashboard
    path('superadmin/', views.superadmin_memo_dashboard, name='superadmin_dashboard'),

    # Memo CRUD & list
    path('list/', views.memo_list, name='memo_list'),
    path('create/', views.memo_create, name='memo_create'),
    path('<int:pk>/edit/', views.memo_edit, name='memo_edit'),
    path('<int:pk>/', views.memo_detail, name='memo_detail'),

    # Routing actions
    path('<int:pk>/keep-in-view/', views.memo_keep_in_view, name='memo_keep_in_view'),
    path('<int:pk>/keep-in-view-note/', views.memo_keep_in_view_with_note, name='memo_keep_in_view_with_note'),
    path('<int:pk>/withdraw/', views.memo_withdraw, name='memo_withdraw'),
    path('<int:pk>/mark-in-progress/', views.memo_mark_in_progress, name='memo_mark_in_progress'),
    path('<int:pk>/forward/', views.memo_forward, name='memo_forward'),
    path('<int:pk>/approve/', views.memo_approve, name='memo_approve'),
    path('<int:pk>/reject/', views.memo_reject, name='memo_reject'),
    path('<int:pk>/positive-response/', views.memo_positive_response, name='memo_positive_response'),
    path('<int:pk>/negative-response/', views.memo_negative_response, name='memo_negative_response'),
    path('<int:pk>/escalate/', views.memo_escalate, name='memo_escalate'),
    path('<int:pk>/request-info/', views.memo_request_info, name='memo_request_info'),
    path('<int:pk>/complete/', views.memo_complete, name='memo_complete'),
    path('<int:pk>/close/', views.memo_close, name='memo_close'),
    path('<int:pk>/reopen/', views.memo_reopen, name='memo_reopen'),

    # Comments
    path('<int:pk>/comment/', views.memo_add_comment, name='memo_add_comment'),

    # External
    path('external/<slug:slug>/', views.memo_external_submit, name='external_submit'),
    path('external/personal/<uuid:token>/', views.memo_external_submit_personal, name='external_submit_personal'),
    path('external/status/<uuid:token>/', views.memo_external_status, name='external_status'),
    path('external/complete/<uuid:token>/', views.memo_external_complete, name='external_complete'),

    # Categories
    path('categories/', views.memo_categories, name='categories'),
    path('categories/create/', views.memo_category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.memo_category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.memo_category_delete, name='category_delete'),

    # Settings
    path('settings/', views.memo_settings, name='settings'),

    # Receptionist management
    path('receptionist/', views.memo_manage_receptionist, name='manage_receptionist'),
]
