from django.urls import path
from .viewfuncs import ticket_views as tf   


urlpatterns = [
    path('submit/',                            tf.ticket_submit_public, name='ticket_submit_public'),
    path('submit/<slug:tenant_slug>/',         tf.ticket_submit_public, name='ticket_submit_tenant'),
    path('submitted/<uuid:token>/',            tf.ticket_submitted,     name='ticket_submitted'),
    path('check/',                             tf.ticket_status_lookup, name='ticket_status_lookup'),
    path('new/',                               tf.ticket_create_staff,  name='ticket_create_staff'),

    # ── Queue paths — MUST be before <str:ticket_number> ──────────────────────
    path('queue/',                             tf.queue_dashboard,      name='queue_dashboard'),
    path('queue/issue/',                       tf.queue_issue,          name='queue_issue'),
    path('queue/call-next/<int:category_id>/', tf.queue_call_next,      name='queue_call_next'),
    path('queue/entry/<int:entry_id>/served/', tf.queue_mark_served,    name='queue_mark_served'),
    path('queue/entry/<int:entry_id>/no-show/',tf.queue_mark_no_show,   name='queue_mark_no_show'),
    path('queue/status.json',                  tf.queue_status_json,    name='queue_status_json'),
    path('',                                      tf.ticket_list,          name='ticket_list'),
    # # MUST be last — <str> catches everything
    path('<str:ticket_number>/',                  tf.ticket_detail,        name='ticket_detail'),
    # urls.py

    
    # path('ajax/verify-ticket/',tf.ajax_verify_ticket, name='ajax_verify_ticket'),
    # Add this to raadaa/urls.py inside the ticket URL block:
    path('ajax/verify-ticket/', tf.ajax_verify_ticket, name='ajax_verify_ticket'),
]