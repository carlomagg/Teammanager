from django.urls import path
from . import views

app_name = 'permissions'

urlpatterns = [
    # Dashboard
    path('', views.permissions_dashboard, name='dashboard'),
    
    # Super Admin Dashboard
    path('superadmin/', views.superadmin_permissions_dashboard, name='superadmin_dashboard'),

    # Permission CRUD & list
    path('list/', views.permissions_list, name='permissions_list'),
    path('create/', views.permissions_create, name='permissions_create'),
    path('<int:pk>/edit/', views.permissions_edit, name='permissions_edit'),
    path('<int:pk>/', views.permissions_detail, name='permissions_detail'),

    # Routing actions
    path('<int:pk>/keep-in-view/', views.permissions_keep_in_view, name='permissions_keep_in_view'),
    path('<int:pk>/keep-in-view-note/', views.permissions_keep_in_view_with_note, name='permissions_keep_in_view_with_note'),
    path('<int:pk>/withdraw/', views.permissions_withdraw, name='permissions_withdraw'),
    path('<int:pk>/mark-in-progress/', views.permissions_mark_in_progress, name='permissions_mark_in_progress'),
    path('<int:pk>/forward/', views.permissions_forward, name='permissions_forward'),
    path('<int:pk>/approve/', views.permissions_approve, name='permissions_approve'),
    path('<int:pk>/reject/', views.permissions_reject, name='permissions_reject'),
    path('<int:pk>/positive-response/', views.permissions_positive_response, name='permissions_positive_response'),
    path('<int:pk>/negative-response/', views.permissions_negative_response, name='permissions_negative_response'),
    path('<int:pk>/escalate/', views.permissions_escalate, name='permissions_escalate'),
    path('<int:pk>/request-info/', views.permissions_request_info, name='permissions_request_info'),
    path('<int:pk>/complete/', views.permissions_complete, name='permissions_complete'),
    path('<int:pk>/close/', views.permissions_close, name='permissions_close'),
    path('<int:pk>/reopen/', views.permissions_reopen, name='permissions_reopen'),

    # Comments
    path('<int:pk>/comment/', views.permissions_add_comment, name='permissions_add_comment'),

    # Categories
    path('categories/', views.permissions_categories, name='categories'),
    path('categories/create/', views.permissions_category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.permissions_category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.permissions_category_delete, name='category_delete'),
]
