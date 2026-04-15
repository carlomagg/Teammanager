"""
Full WebAuthn (py_webauthn) implementation for fingerprint / Face ID check-in.

Install:
    pip install py_webauthn

Two separate flows
──────────────────
REGISTRATION  (one-time, per device)
    GET  /checkin/biometric/register/           → biometric_register_page
    POST /checkin/biometric/register/begin/     → biometric_register_begin
    POST /checkin/biometric/register/complete/  → biometric_register_complete

AUTHENTICATION  (every check-in)
    POST /checkin/biometric/begin/              → biometric_checkin_begin
    POST /checkin/biometric/complete/           → biometric_checkin_complete
"""

import base64
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from .helpers import get_tenant_origin, get_rp_id

import webauthn
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
    AuthenticatorTransport,
)
from webauthn.helpers.exceptions import InvalidCBORData, InvalidAuthenticationResponse

from django.conf import settings

from .models import BiometricCredential, StaffCheckIn
from .views import checkin_required, _process_staff_checkin


# ─── helpers ─

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    # Re-pad before decoding
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)





# ─── REGISTRATION – page 

@login_required
def biometric_register_page(request):
    existing = BiometricCredential.objects.filter(user=request.user)
    return render(request, "checkin/biometric_register.html", {
        "credentials": existing,
        "rp_id": get_rp_id(request),
    })


# ─── REGISTRATION – step 1: generate challenge ─

@login_required
@require_POST
def biometric_register_begin(request):
    try:
        body   = json.loads(request.body)
        b_type = body.get("type", "fingerprint")   # "fingerprint" | "faceid"
    except (json.JSONDecodeError, AttributeError):
        b_type = "fingerprint"

    user = request.user

    # Collect already-registered credential IDs to exclude (prevent duplicates)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(cred.credential_id))
        for cred in BiometricCredential.objects.filter(user=user)
    ]

    registration_options = generate_registration_options(
        rp_id   = get_rp_id(request),
        rp_name = settings.WEBAUTHN_RP_NAME,
        user_id = str(user.pk).encode(),
        user_name      = user.username,
        user_display_name = user.get_full_name() or user.username,
        authenticator_selection = AuthenticatorSelectionCriteria(
            resident_key      = ResidentKeyRequirement.PREFERRED,
            user_verification = UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials = exclude_credentials,
    )

    # Store challenge + type in session for verification step
    request.session["webauthn_reg_challenge"] = _b64url_encode(
        registration_options.challenge
    )
    request.session["webauthn_reg_type"] = b_type

    return JsonResponse(json.loads(options_to_json(registration_options)))


# ─── REGISTRATION – step 2: verify & persist credential 

@login_required
@require_POST
def biometric_register_complete(request):
    challenge_b64 = request.session.get("webauthn_reg_challenge")
    b_type        = request.session.get("webauthn_reg_type", "fingerprint")

    if not challenge_b64:
        return JsonResponse({"ok": False, "error": "Session expired. Please try again."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)
    
    try:
        origin = get_tenant_origin(request)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    try:
        credential = verify_registration_response(
            credential                = body,
            expected_challenge        = _b64url_decode(challenge_b64),
            expected_rp_id            = get_rp_id(request),
            expected_origin           = origin,
            require_user_verification = True,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    # Persist – credential_id is bytes, store as base64url string
    cred_id_b64 = _b64url_encode(credential.credential_id)

    BiometricCredential.objects.update_or_create(
        user          = request.user,
        credential_id = cred_id_b64,
        defaults={
            "public_key":         _b64url_encode(credential.credential_public_key),
            "sign_count":         credential.sign_count,
            "authenticator_type": b_type,
        },
    )

    # Clean up session keys
    request.session.pop("webauthn_reg_challenge", None)
    request.session.pop("webauthn_reg_type", None)

    return JsonResponse({"ok": True, "type": b_type})


# ─── AUTHENTICATION – step 1: generate challenge 

@login_required
@require_POST
def biometric_checkin_begin(request):
    try:
        body   = json.loads(request.body)
        b_type = body.get("type", "fingerprint")
    except (json.JSONDecodeError, AttributeError):
        b_type = "fingerprint"

    user = request.user

    # Fetch only credentials matching the requested type for this user
    stored = BiometricCredential.objects.filter(
        user=user, authenticator_type=b_type
    )
    if not stored.exists():
        return JsonResponse({
            "ok": False,
            "error": f"No {b_type} credential registered. Please register one first.",
        }, status=400)

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=_b64url_decode(c.credential_id))
        for c in stored
    ]

    auth_options = generate_authentication_options(
        rp_id              = get_rp_id(request),
        allow_credentials  = allow_credentials,
        user_verification  = UserVerificationRequirement.REQUIRED,
    )

    # Store challenge + type for verification
    request.session["webauthn_auth_challenge"] = _b64url_encode(auth_options.challenge)
    request.session["webauthn_auth_type"]      = b_type

    return JsonResponse(json.loads(options_to_json(auth_options)))


# ─── AUTHENTICATION – step 2: verify assertion & record check-in 

@login_required
@require_POST
def biometric_checkin_complete(request):
    challenge_b64 = request.session.get("webauthn_auth_challenge")
    b_type        = request.session.get("webauthn_auth_type", "fingerprint")

    if not challenge_b64:
        return JsonResponse({"ok": False, "error": "Session expired. Please try again."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    # Look up the credential by the id the browser returned
    credential_id_b64 = body.get("id", "")
    try:
        stored_cred = BiometricCredential.objects.get(
            user=request.user,
            credential_id=credential_id_b64,
        )
    except BiometricCredential.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Credential not found."}, status=400)
    
    expected_origin = get_tenant_origin(request)

    try:
        verified = verify_authentication_response(
            credential                = body,
            expected_challenge        = _b64url_decode(challenge_b64),
            expected_rp_id            = get_rp_id(request),
            expected_origin           = expected_origin,
            credential_public_key     = _b64url_decode(stored_cred.public_key),
            credential_current_sign_count = stored_cred.sign_count,
            require_user_verification = True,
        )
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    # Update sign count (replay-attack protection)
    stored_cred.sign_count   = verified.new_sign_count
    stored_cred.last_used_at = timezone.now()
    stored_cred.save(update_fields=["sign_count", "last_used_at"])

    # Clean up session
    request.session.pop("webauthn_auth_challenge", None)
    request.session.pop("webauthn_auth_type", None)

    # Record staff check-in
    record = _process_staff_checkin(request, request.user, b_type)

    return JsonResponse({
        "ok":      True,
        "message": f"Checked in via {b_type}.",
        "already": record is None,   # True if already checked in today
    })


# ─── DELETE a registered credential ─

@login_required
@require_POST
def biometric_delete(request, credential_pk):
    cred = BiometricCredential.objects.filter(
        pk=credential_pk, user=request.user
    ).first()
    if cred:
        cred.delete()
        messages.success(request, "Biometric credential removed.")
    else:
        messages.error(request, "Credential not found.")
    return redirect("checkin:biometric_register_page")