from django.urls import path
from . import views

app_name = 'leave'

urlpatterns = [
    # Dashboard
    path('', views.leave_dashboard, name='dashboard'),
    
    # Super Admin Dashboard
    path('superadmin/', views.superadmin_leave_dashboard, name='superadmin_dashboard'),

    # Leave CRUD & list
    path('list/', views.leave_list, name='leave_list'),
    path('create/', views.leave_create, name='leave_create'),
    path('<int:pk>/edit/', views.leave_edit, name='leave_edit'),
    path('<int:pk>/', views.leave_detail, name='leave_detail'),

    # Routing actions
    path('<int:pk>/keep-in-view/', views.leave_keep_in_view, name='leave_keep_in_view'),
    path('<int:pk>/keep-in-view-note/', views.leave_keep_in_view_with_note, name='leave_keep_in_view_with_note'),
    path('<int:pk>/withdraw/', views.leave_withdraw, name='leave_withdraw'),
    path('<int:pk>/mark-in-progress/', views.leave_mark_in_progress, name='leave_mark_in_progress'),
    path('<int:pk>/forward/', views.leave_forward, name='leave_forward'),
    path('<int:pk>/approve/', views.leave_approve, name='leave_approve'),
    path('<int:pk>/reject/', views.leave_reject, name='leave_reject'),
    path('<int:pk>/positive-response/', views.leave_positive_response, name='leave_positive_response'),
    path('<int:pk>/negative-response/', views.leave_negative_response, name='leave_negative_response'),
    path('<int:pk>/escalate/', views.leave_escalate, name='leave_escalate'),
    path('<int:pk>/request-info/', views.leave_request_info, name='leave_request_info'),
    path('<int:pk>/complete/', views.leave_complete, name='leave_complete'),
    path('<int:pk>/close/', views.leave_close, name='leave_close'),
    path('<int:pk>/reopen/', views.leave_reopen, name='leave_reopen'),

    # Comments
    path('<int:pk>/comment/', views.leave_add_comment, name='leave_add_comment'),

    # Categories
    path('categories/', views.leave_categories, name='categories'),
    path('categories/create/', views.leave_category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.leave_category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.leave_category_delete, name='category_delete'),
]
