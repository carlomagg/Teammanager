from django.urls import path
from .viewfuncs import invoice_views as v
from .viewfuncs import ticket_views as tf   


urlpatterns = [


 # ── List views ───────────────────────────────────────────────────────────
    path('',                v.sent_invoices_list,     name='sent_invoices_list'),
    path('received/',       v.received_invoices_list, name='received_invoices_list'),

    # ── Create ───────────────────────────────────────────────────────────────
    path('new/',            v.create_send_invoice,    name='create_send_invoice'),
    path('new/received/',   v.create_receive_invoice, name='create_receive_invoice'),

    # ── Detail (staff) ───────────────────────────────────────────────────────
    path('<int:pk>/',       v.invoice_detail,         name='invoice_detail'),

    # ── Actions ──────────────────────────────────────────────────────────────
    path('<int:pk>/send/',       v.send_invoice_email,  name='send_invoice_email'),
    path('<int:pk>/mark-paid/',  v.mark_invoice_paid,   name='mark_invoice_paid'),

    # ── Receipt download ─────────────────────────────────────────────────────
    path('receipt/<int:receipt_pk>/download/',v.download_receipt, name='download_receipt'),

    # ── Public tracking (no login required) ──────────────────────────────────
    #path('track/<uuid:share_token>/',v.invoice_tracking_view, name='invoice_tracking_view'),

    # ── AJAX ─────────────────────────────────────────────────────────────────
    path('ajax/product/',v.product_lookup,name='invoice_product_lookup'),

# ── External / public invoice submission ─────────────────────────────────────
    path('submit/<slug:tenant_slug>/',v.invoice_submit_external,name='invoice_submit_external'),

    path('submitted/<uuid:token>/',v.invoice_external_submitted,name='invoice_external_submitted'),

# Public tracking (replaces old tracking view — works for both external & staff)
    path('track/<uuid:share_token>/',v.invoice_external_track,name='invoice_tracking_view'),

# Staff: review an externally submitted invoice
    path('<int:pk>/review/',v.invoice_review,name='invoice_review'),
    path('receipts/new/',      v.receipt_create_standalone, name='receipt_create'),
    path('receipts/<int:pk>/', v.receipt_detail,            name='receipt_detail'),
]


#https://yoursite.com/invoices/submit/your-tenant-slug/