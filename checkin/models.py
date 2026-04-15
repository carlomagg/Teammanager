from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from documents.models import CustomUser
from tenants.models import Tenant
import os
from django.utils import timezone




def visitor_doc_path(instance, filename):
    
    date_str = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")   # e.g. 2026-03-13_16-11-57
    ext      = os.path.splitext(filename)[1]                   # keep original extension
    return f"visitor_documents/{instance.tenant.name}/{date_str}{ext}"

# prevents existing migration from breaking
upload_visitor_document = visitor_doc_path


# Work Schedule

class WorkSchedule(models.Model):
    """Per-tenant work hours and late threshold."""
    tenant          = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='work_schedule')
    work_start_time = models.TimeField(help_text="e.g. 08:00")
    work_end_time   = models.TimeField(help_text="e.g. 17:00")
    late_after      = models.TimeField(help_text="Arrivals after this time are marked Late (e.g. 08:15)")
    created_by      = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_work_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.tenant.name}: {self.work_start_time}–{self.work_end_time} (late after {self.late_after})"


# Staff Check-in

class StaffCheckIn(models.Model):
    METHOD_CHOICES = [
        ('fingerprint', 'Fingerprint'),
        ('faceid',      'Face ID'),
        ('qrcode',      'QR Code'),
        ('pin',         'PIN'),
        ('manual',      'Manual'),
    ]
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('late',    'Late'),
        ('absent',  'Absent'),
    ]

    tenant         = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='staff_checkins')
    staff          = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='checkins')
    date           = models.DateField(default=timezone.now)
    check_in_time  = models.DateTimeField(null=True, blank=True)
    check_out_time = models.DateTimeField(null=True, blank=True)
    method         = models.CharField(max_length=20, choices=METHOD_CHOICES, default='manual')
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    is_late        = models.BooleanField(default=False)
    checked_in_by  = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_staff_checkins'
    )
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'staff', 'date')
        ordering = ['-date', '-check_in_time']

    def __str__(self):
        return f"{self.staff.username} – {self.date} ({self.status})"

    @property
    def duration(self):
        if self.check_in_time and self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            h, rem = divmod(int(delta.total_seconds()), 3600)
            return f"{h}h {rem // 60}m"
        return "—"



# PIN & QR Credentials

class StaffPIN(models.Model):
    """Hashed 4-6 digit PIN for check-in."""
    user       = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='checkin_pin')
    pin_hash   = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_pin(self, raw_pin: str):
        self.pin_hash = make_password(raw_pin)

    def verify_pin(self, raw_pin: str) -> bool:
        return check_password(raw_pin, self.pin_hash)

    def __str__(self):
        return f"PIN for {self.user.username}"


class StaffQRToken(models.Model):
    """One stable UUID per staff member used as QR payload."""
    user       = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='qr_token')
    token      = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def regenerate(self):
        self.token = uuid.uuid4()
        self.save(update_fields=['token'])

    def __str__(self):
        return f"QR token for {self.user.username}"



# Biometric Credential  (WebAuthn – Fingerprint / Face ID)


class BiometricCredential(models.Model):
    """
    Stores a WebAuthn public-key credential for fingerprint / Face ID.
    Requires:  pip install py_webauthn
    """
    AUTHENTICATOR_TYPE = [
        ('fingerprint', 'Fingerprint'),
        ('faceid',      'Face ID'),
    ]
    user              = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='biometric_credentials')
    credential_id     = models.TextField(unique=True, help_text="Base64URL-encoded credential ID")
    public_key        = models.TextField(help_text="CBOR-encoded public key (base64)")
    sign_count        = models.PositiveIntegerField(default=0)
    authenticator_type = models.CharField(max_length=20, choices=AUTHENTICATOR_TYPE, default='fingerprint')
    created_at        = models.DateTimeField(auto_now_add=True)
    last_used_at      = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.authenticator_type} credential for {self.user.username}"


# Visitor

class Visitor(models.Model):
    """
    Stored visitor profile – reused on repeat visits.
    Name + phone required; everything else optional.
    """
    tenant       = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='visitors')
    name         = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email        = models.EmailField(blank=True, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'phone_number')

    def __str__(self):
        return f"{self.name} ({self.phone_number})"




class VisitorLog(models.Model):
    """One record per visit."""
    ID_TYPE_CHOICES = [
        ('national_id',     'National ID'),
        ('passport',        'Passport'),
        ('drivers_license', "Driver's License"),
        ('voters_card',     "Voter's Card"),
        ('other',           'Other'),
    ]
    PURPOSE_CHOICES = [
        ('meeting',     'Meeting'),
        ('delivery',    'Delivery'),
        ('interview',   'Interview'),
        ('maintenance', 'Maintenance'),
        ('personal',    'Personal'),
        ('other',       'Other'),
    ]

    tenant         = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='visitor_logs')
    visitor        = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='logs')
    date           = models.DateField(default=timezone.now)
    visitor_tag    = models.CharField(max_length=10, help_text="Daily sequential tag e.g. 0001")

    # Visit details (all optional except tag)
    purpose        = models.CharField(max_length=50, choices=PURPOSE_CHOICES, blank=True, null=True)
    purpose_detail = models.TextField(blank=True, null=True)
    visitee        = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='visitor_logs', help_text="Staff member being visited"
    )
    on_appointment = models.BooleanField(default=False)
    id_type        = models.CharField(max_length=30, choices=ID_TYPE_CHOICES, blank=True, null=True)
    id_number      = models.CharField(max_length=100, blank=True, null=True)

    # Document
    has_document  = models.BooleanField(default=False)
   
    
    #  FileField — accepts any file type including PDFs
    document_scan = models.FileField(upload_to=visitor_doc_path, null=True, blank=True)
    # Time
    time_in  = models.DateTimeField(default=timezone.now)
    time_out = models.DateTimeField(null=True, blank=True)

    # Processed by
    checked_in_by  = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_visitor_checkins'
    )
    checked_out_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_visitor_checkouts'
    )
    notes      = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-time_in']
        unique_together = ('tenant', 'visitor_tag', 'date')

    def __str__(self):
        return f"{self.visitor.name} [{self.visitor_tag}] – {self.date}"

    @property
    def duration(self):
        if self.time_in and self.time_out:
            delta = self.time_out - self.time_in
            h, rem = divmod(int(delta.total_seconds()), 3600)
            return f"{h}h {rem // 60}m"
        return "Still inside"

    @property
    def is_checked_out(self):
        return self.time_out is not None


#
# Daily Tag Counter  – resets each new day

class VisitorTagCounter(models.Model):
    tenant      = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='visitor_tag_counters')
    date        = models.DateField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('tenant', 'date')

    @classmethod
    def get_next_tag(cls, tenant) -> str:
        """Atomically increment today's counter and return a zero-padded tag."""
        from django.db import transaction
        with transaction.atomic():
            today = timezone.now().date()
            counter, _ = cls.objects.select_for_update().get_or_create(
                tenant=tenant, date=today
            )
            counter.last_number += 1
            counter.save(update_fields=['last_number'])
            return str(counter.last_number).zfill(4)

    def __str__(self):
        return f"{self.tenant.name} – {self.date}: {self.last_number}"