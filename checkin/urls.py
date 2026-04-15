from django.urls import path
from . import views
from checkin.views_biometric import (
    biometric_register_page,
    biometric_register_begin,
    biometric_register_complete,
    biometric_checkin_begin,
    biometric_checkin_complete,
    biometric_delete,
)

app_name = "checkin"

urlpatterns = [
    # ── Dashboards ───────────────────────────────────────────────────────────
    path("",           views.checkin_dashboard, name="checkin_dashboard"),
    path("visitors/",  views.visitor_dashboard,  name="visitor_dashboard"),

    # ── Work schedule ─────────────────────────────────────────────────────────
    path("schedule/",  views.work_schedule_setup, name="work_schedule_setup"),

    # ── Staff check-in methods ────────────────────────────────────────────────
    path("staff/qr/",     views.staff_checkin_qr,     name="staff_checkin_qr"),
    path("staff/pin/",    views.staff_checkin_pin,     name="staff_checkin_pin"),
    path("staff/manual/", views.staff_checkin_manual,  name="staff_checkin_manual"),

    # ── Biometric: registration (one-time per device) ─────────────────────────
    path("biometric/register/",          biometric_register_page,     name="biometric_register_page"),
    path("biometric/register/begin/",    biometric_register_begin,    name="biometric_register_begin"),
    path("biometric/register/complete/", biometric_register_complete, name="biometric_register_complete"),

    # ── Biometric: authentication (check-in) ──────────────────────────────────
    path("biometric/begin/",    biometric_checkin_begin,    name="biometric_checkin_begin"),
    path("biometric/complete/", biometric_checkin_complete, name="biometric_checkin_complete"),

    # ── Biometric: delete credential ──────────────────────────────────────────
    path("biometric/delete/<int:credential_pk>/", biometric_delete, name="biometric_delete"),

    # ── Staff check-out ───────────────────────────────────────────────────────
    path("staff/checkout/<int:checkin_id>/", views.staff_checkout, name="staff_checkout"),

    # ── Self-service ──────────────────────────────────────────────────────────
    path("my-pin/",           views.set_staff_pin,  name="set_staff_pin"),
    path("my-qr/",            views.my_qr_code,     name="my_qr_code"),
    path("my-qr/regenerate/", views.regenerate_qr,  name="regenerate_qr"),

    # ── Visitor flow ──────────────────────────────────────────────────────────
    path("visitors/checkin/",          views.visitor_checkin,     name="visitor_checkin"),
    path("visitors/checkout/",         views.visitor_checkout,    name="visitor_checkout"),
    path("visitors/tag/<int:log_id>/", views.visitor_tag_display, name="visitor_tag_display"),

    # ── AJAX ──────────────────────────────────────────────────────────────────
    path("ajax/visitor-lookup/", views.visitor_lookup, name="visitor_lookup"),
    path("ajax/qr-lookup/",      views.qr_lookup,      name="qr_lookup"),
    
    # ── Public PIN Request (no login required) ────────────────────────────────
    path("get-pin/", views.get_pin_public, name="get_pin_public"),
]