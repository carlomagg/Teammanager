from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.crm_dashboard, name='dashboard'),
    
    # Opportunities
    path('opportunities/', views.opportunity_list, name='opportunity_list'),
    path('opportunities/create/', views.opportunity_create, name='opportunity_create'),
    path('opportunities/<int:pk>/', views.opportunity_detail, name='opportunity_detail'),
    path('opportunities/<int:pk>/update/', views.opportunity_update, name='opportunity_update'),
    path('opportunities/<int:pk>/delete/', views.opportunity_delete, name='opportunity_delete'),
    
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/update/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    
    # Activities
    path('activity/create/<int:content_type_id>/<int:object_id>/', views.activity_create, name='activity_create'),
    path('activity/<int:activity_id>/mark-completed/', views.mark_activity_completed, name='mark_activity_completed'),
    
    # API endpoints
    path('api/cities/', views.get_cities_by_country, name='get_cities_by_country'),
    path('api/stages/', views.get_stages_by_category, name='get_stages_by_category'),
]
