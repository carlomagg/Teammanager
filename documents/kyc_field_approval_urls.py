# documents/kyc_field_approval_urls.py
from django.urls import path
from . import kyc_field_approval_views

app_name = 'kyc_field_approval'

urlpatterns = [
    # Field-level approval/rejection
    path('approve/<int:content_type_id>/<int:object_id>/<str:field_name>/',
         kyc_field_approval_views.approve_field,
         name='approve_field'),
    
    path('reject/<int:content_type_id>/<int:object_id>/<str:field_name>/',
         kyc_field_approval_views.reject_field,
         name='reject_field'),
    
    # Approve all fields at once
    path('approve-all/<int:content_type_id>/<int:object_id>/',
         kyc_field_approval_views.approve_all_fields,
         name='approve_all_fields'),
    
    # Get field status (AJAX)
    path('status/<int:content_type_id>/<int:object_id>/',
         kyc_field_approval_views.get_field_status,
         name='get_field_status'),
]
