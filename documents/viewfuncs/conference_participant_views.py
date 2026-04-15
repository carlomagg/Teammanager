from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Count, When, Case, IntegerField
from django.http import HttpResponseForbidden, Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import get_object_or_404, render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import timedelta
from documents.cron import ConferenceReminderSender
from documents.forms import ConferenceParticipantForm, FileUploadForm, FileUploadAnonForm
from documents.models import Conference, ConferenceParticipant, GuestUser, CustomUser, Payment, Payer, CustomAnswer, Payee, File
from documents.viewfuncs.send_mails import send_conf_reg_pending, send_conf_reg_accepted, send_conf_reg_declined, send_conference_reminder
from documents.viewfuncs.helper_funcs.paystack import initialize_paystack_payment
from .helper_funcs.permissions import can_manage_conference_participant
from .helper_funcs.access_urls import build_conference_access_url, build_guest_dashboard_url, build_user_activity_dashboard_url
from raadaa import settings
from raadaa.tasks import conf_bulk_accept_and_notify, send_conference_reminders_task
import uuid, io, base64, logging, csv, json, os
from urllib.parse import urlencode
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT


logger = logging.getLogger(__name__)

# ============================================================================
# FILE VALIDATION SETTINGS
# ============================================================================
ALLOWED_EXTENSIONS = [
    '.pdf', '.doc', '.docx',  # Documents
    '.ppt', '.pptx',          # Presentations
    '.xls', '.xlsx',          # Spreadsheets
    '.jpg', '.jpeg', '.png', '.gif',  # Images
    '.zip', '.rar'            # Archives
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes


def validate_uploaded_file(file):
    """Validate file extension and size."""
    # Check extension
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'File type "{ext}" is not allowed. '
            f'Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
        )
    
    # Check size
    if file.size > MAX_FILE_SIZE:
        size_mb = file.size / (1024 * 1024)
        raise ValidationError(
            f'File "{file.name}" is too large ({size_mb:.2f}MB). '
            f'Maximum allowed size is 10MB.'
        )
    
    return True


def conference_register(request, conference_id):
    conference = get_object_or_404(Conference, id=conference_id)

    if not conference.registration_required:
        messages.error(request, "Registration is not required for this conference.")
        return redirect("conference_post", conference_id=conference.id)

    # ---- Capacity check (soft) ----
    # Only perform capacity checks if there are limits set
    has_physical_limit = conference.max_participants_physical is not None and conference.max_participants_physical > 0
    has_virtual_limit = conference.max_participants_virtual is not None and conference.max_participants_virtual > 0

    if not has_physical_limit and not has_virtual_limit:
        # No capacity limits — allow registration
        # (Continue to registration form or processing)
        pass  # Remove this and add your registration logic here

    # Define a recent time window to count unpaid but recently registered users (soft reserve)
    recent_cutoff = timezone.now() - timedelta(hours=2)
    reserved_q = Q(ticket_paid=True) | Q(registered_at__gte=recent_cutoff)

    # Base queryset: all reserved participants for this conference
    reserved_participants = ConferenceParticipant.objects.filter(
        reserved_q,
        conference=conference,
    )

    physical_reserved = 0
    virtual_reserved = 0

    if conference.conference_type == "physical":
        # All participants count as physical
        physical_reserved = reserved_participants.count()

    elif conference.conference_type == "virtual":
        # All participants count as virtual
        virtual_reserved = reserved_participants.count()

    elif conference.conference_type == "hybrid":
        # Only in hybrid do users choose attendance_mode
        physical_reserved = reserved_participants.filter(
            attendance_mode="physical"
        ).count()

        virtual_reserved = reserved_participants.filter(
            attendance_mode="virtual"
        ).count()

    else:
        # Safety fallback
        physical_reserved = virtual_reserved = reserved_participants.count()

    # Physical capacity check
    if (conference.max_participants_physical and 
        physical_reserved >= conference.max_participants_physical):
        
        if conference.conference_type == "physical":
            messages.error(request, "Sorry, this conference is fully booked.")
        else:  # hybrid
            messages.error(request, "Sorry, physical attendance is fully booked.")
        return redirect("conference_post", conference_id=conference.id)

    # Virtual capacity check
    if (conference.max_participants_virtual and 
        virtual_reserved >= conference.max_participants_virtual):
        
        if conference.conference_type == "virtual":
            messages.error(request, "Sorry, this conference is fully booked.")
        else:  # hybrid
            messages.error(request, "Sorry, virtual attendance is fully booked.")
        return redirect("conference_post", conference_id=conference.id)

    # For hybrid: optional extra message if both are full
    if conference.conference_type == "hybrid":
        if (conference.max_participants_physical and conference.max_participants_virtual and
            physical_reserved >= conference.max_participants_physical and
            virtual_reserved >= conference.max_participants_virtual):
            messages.error(request, "Sorry, both physical and virtual seats are fully booked.")
            return redirect("conference_post", conference_id=conference.id)


    # ---- Retry handling ----
    retry_id = request.GET.get("retry")
    retry_participant = None

    if retry_id:
        retry_participant = ConferenceParticipant.objects.filter(
            id=retry_id,
            conference=conference,
            status="pending",
            ticket_paid=False
        ).first()

        if not retry_participant:
            messages.error(request, "Invalid or expired retry link.")
            return redirect("conference_post", conference_id=conference.id)

        # Always send retry users to breakdown
        return redirect(
            "conference_payment_breakdown",
            conference_id=conference.id,
            participant_id=retry_participant.id
        )

    # ---- New registration ----
    if request.method == "POST":
        form = ConferenceParticipantForm(request.POST, conference=conference)

        # if not form.is_valid():
        #     return render(request, "conference/conference_register.html", {
        #         "conference": conference,
        #         "form": form
        #     })

        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            first_name = form.cleaned_data["first_name"]
            last_name = form.cleaned_data["last_name"]
            full_name = f"{first_name} {last_name}"

            with transaction.atomic():
                # Lock rows to prevent overselling
                locked = ConferenceParticipant.objects.select_for_update().filter(
                    conference=conference
                )

                accepted_count = locked.filter(status="accepted").count()
                recent_cutoff = timezone.now() - timedelta(hours=2)
                reserved_after_lock = accepted_count + locked.filter(
                    status="pending",
                    registered_at__gte=recent_cutoff
                ).count()

                if conference.conference_type == "physical":
                    if conference.max_participants_physical and reserved_after_lock >= conference.max_participants_physical:
                        messages.error(request, "Sorry, this conference just reached capacity.")
                        return redirect("conference_post", conference_id=conference.id)
                elif conference.conference_type == "virtual":
                    if conference.max_participants_virtual and reserved_after_lock >= conference.max_participants_virtual:
                        messages.error(request, "Sorry, this conference just reached capacity.")
                        return redirect("conference_post", conference_id=conference.id)
                elif conference.conference_type == "hybrid":
                    if conference.max_participants_virtual and conference.max_participants_physical and reserved_after_lock >= conference.max_participants_virtual + conference.max_participants_physical:
                        messages.error(request, "Sorry, this conference just reached capacity.")
                        return redirect("conference_post", conference_id=conference.id)

                # Prevent duplicate registration
                participant = locked.filter(email=email).first()
                if participant:
                    if participant.ticket_paid:
                        messages.info(request, "You are already registered.")
                        return redirect("conference_post", conference_id=conference.id)
                else:
                    payer, _ = Payer.objects.get_or_create(
                        tenant=conference.tenant,
                        email=email,
                        defaults={
                            "name": full_name,
                            "phone": form.cleaned_data.get("phone_number"),
                            "organization": form.cleaned_data.get("organization"),
                        }
                    )

                    payer.name = full_name
                    payer.phone = form.cleaned_data.get("phone_number")
                    payer.organization = form.cleaned_data.get("organization")
                    payer.save()

                    participant = form.save(commit=False)
                    participant.conference = conference
                    participant.tenant = conference.tenant
                    participant.email = email
                    participant.payer = payer
                    participant.registered_at = timezone.now()
                    participant.unique_token = uuid.uuid4()
                    participant.status = "pending"
                    participant.ticket_paid = False
                    participant.is_confirmed = False
                    participant.save()

                    # ---- Save custom answers ----
                    for question in conference.custom_questions.all():
                        answer_key = f"custom_answer_{question.id}"
                        answer_text = request.POST.get(answer_key, "").strip()

                        if answer_text:
                            CustomAnswer.objects.create(
                                participant=participant,
                                question=question,
                                answer=answer_text
                            )
                        elif question.required:
                            form.add_error(
                                None,
                                f"Please answer the required question: {question.question}"
                            )
                            # Re-render form with errors and custom questions
                            return render(request, "conference/conference_register.html", {
                                "conference": conference,
                                "form": form,
                                "custom_questions": conference.custom_questions.all().order_by('order'),
                                "retry_participant": retry_participant,
                            })
                        
                    # ────────────────────────────────────────────────────────────
                    # HANDLE FILE UPLOADS (if folder exists)
                    # ────────────────────────────────────────────────────────────
                    uploaded_files = request.FILES.getlist('participant_files')
                    upload_success_count = 0
                    upload_errors = []
                    
                    if uploaded_files and conference.upload_folder:
                        effective_user = request.user if request.user.is_authenticated else None
                        
                        for uploaded_file in uploaded_files:
                            try:
                                # Validate file
                                validate_uploaded_file(uploaded_file)
                                
                                # Create File object
                                File.objects.create(
                                    file=uploaded_file,
                                    original_name=uploaded_file.name,
                                    folder=conference.upload_folder,
                                    uploaded_by=effective_user,
                                    anon_name=full_name if not effective_user else None,
                                    tenant=conference.tenant,
                                    is_public=conference.upload_folder.is_public
                                )
                                
                                upload_success_count += 1
                                
                            except ValidationError as e:
                                upload_errors.append(str(e))
                            except Exception as e:
                                upload_errors.append(f'Error uploading {uploaded_file.name}: {str(e)}')

                # ---- Pricing calculation (freeze it at registration time) ----
                now = timezone.now()
                selected_tier = participant.price_tier   # may be None for tier-less conferences

                if selected_tier is not None:
                    base_price = selected_tier.price
                else:
                    # Legacy flat / time-based pricing
                    if (conference.free_first_n_participants is not None
                            and accepted_count < conference.free_first_n_participants):
                        base_price = Decimal("0.00")
                    elif (conference.early_bird_price and conference.early_bird_deadline
                            and now <= conference.early_bird_deadline):
                        base_price = conference.early_bird_price
                    elif (conference.late_price and conference.late_deadline
                            and now >= conference.late_deadline):
                        base_price = conference.late_price
                    else:
                        base_price = conference.ticket_price or Decimal("0.00")

                payable_amount = conference.get_payable_amount(base_price)

                if request.user.is_anonymous:
                    from django.contrib.contenttypes.models import ContentType
                    conference_ct = ContentType.objects.get_for_model(Conference)
                    
                    guest_user, created = GuestUser.objects.get_or_create(
                        email=participant.email,
                        defaults={
                            "token": uuid.uuid4(),
                            "source_content_type": conference_ct,
                            "source_object_id": conference.id
                        }
                    )
                    # Update source if it wasn't set before
                    if not created and not guest_user.source_content_type:
                        guest_user.source_content_type = conference_ct
                        guest_user.source_object_id = conference.id
                        guest_user.save(update_fields=['source_content_type', 'source_object_id'])
                    
                    guest_token = str(guest_user.token)
                    dashboard_url = build_guest_dashboard_url(guest_token)
                elif request.user.is_authenticated and request.user.email != participant.email:
                    guest_user, _ = GuestUser.objects.get_or_create(
                        email=participant.email,
                        defaults={"token": uuid.uuid4()}
                    )
                    guest_token = str(guest_user.token)
                    dashboard_url = build_guest_dashboard_url(guest_token)
                elif request.user.email == participant.email:
                    user = CustomUser.objects.get(email=participant.email)
                    dashboard_url = build_user_activity_dashboard_url(user)
                else:
                    guest_token = None
                    dashboard_url = None

                # ---- Free conference ----
                if payable_amount <= 0:
                    participant.status = "pending"
                    participant.ticket_paid = True
                    participant.is_confirmed = False
                    participant.save()

                    # Payment.objects.create(
                    #     tenant=conference.tenant,
                    #     payer=participant.payer,
                    #     payment_type="conference_fee",
                    #     direction="incoming",
                    #     amount=Decimal("0.00"),
                    #     net_amount=Decimal("0.00"),
                    #     status="success",
                    #     description=f"Free registration: {conference.title}",
                    #     payment_date=timezone.now(),
                    #     created_by=conference.organizer,
                    #     return_url=reverse("conference_post", kwargs={"conference_id": conference.id}),
                    # )
                    # access_url =  request.build_absolute_uri(reverse("conference_access", kwargs={"conference_id": conference.id, "token": participant.unique_token}))

                    access_url = build_conference_access_url(conference, participant)

                    sender = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
                    cc = [conference.organizer.email]

                    send_conf_reg_pending(participant, access_url=access_url, dashboard_url=dashboard_url, sender=sender, cc=cc)

                    messages.success(request, "Registration successful! Check your email.")
                     # Success messages with file upload info
                    if upload_success_count > 0:
                        messages.success(
                            request,
                            f"Registration successful! {upload_success_count} file(s) uploaded. Check your email."
                        )
                    else:
                        messages.success(request, "Registration successful! Check your email.")
                    
                    # Show upload errors as warnings (non-blocking)
                    if upload_errors:
                        for error in upload_errors:
                            messages.warning(request, error)

                # return redirect("conference_post", conference_id=conference.id)
                # return render(request, "conference/conf_reg_success.html", {"conference": conference, "participant": participant, "payable_amount": payable_amount})
                response = redirect(conference_reg_success)
                response.set_cookie(
                    "guest_token",
                    # str(guest_user.token),
                    guest_token,
                    max_age=60 * 60 * 24 * 365,
                    httponly=True,
                    secure=not settings.DEBUG,
                    samesite="Lax"
                )
                request.session["conf_reg_success_data"]={
                    "conference_id":conference.id,
                    "participant_id":participant.id,
                    "payable_amount": str(payable_amount),
                    "upload_count": upload_success_count,
                }
                return response



                # # ---- Paid conference → Breakdown ----
                # messages.success(request, "Registration successful. Please review payment details.")
                # return redirect(
                #     "conference_payment_breakdown",
                #     conference_id=conference.id,
                #     participant_id=participant.id
                # )
        # Form invalid → re-render with custom questions
        return render(request, "conference/conference_register.html", {
            "conference": conference,
            "form": form,
            "custom_questions": conference.custom_questions.all().order_by('order'),
            "retry_participant": retry_participant,
            "price_tiers": conference.price_tiers.filter(is_active=True).order_by('order', 'price'),
            "has_tiers": conference.price_tiers.filter(is_active=True).exists(),
        })

    # ---- GET ----
    return render(request, "conference/conference_register.html", {
        "retry_participant": retry_participant,
        "conference": conference,
        "form": ConferenceParticipantForm(conference=conference),
        "custom_questions": conference.custom_questions.all().order_by('order'),
        "price_tiers": conference.price_tiers.filter(is_active=True).order_by('order', 'price'),
        "has_tiers": conference.price_tiers.filter(is_active=True).exists(),
    })

def conference_reg_success(request):
    data = data = request.session.pop("conf_reg_success_data", None)

    if not data:
        return redirect("conference_board")  # or registration page

    conference_id = data["conference_id"]
    participant_id = data["participant_id"]
    payable_amount = Decimal(data["payable_amount"])
    upload_count = data["upload_count"]
    conference = get_object_or_404(Conference, id=conference_id)
    participant = get_object_or_404(ConferenceParticipant, id=participant_id, conference=conference)
    uploaded_files_count = upload_count
    can_upload_later = bool(conference.upload_folder)
    # Get upload URL if available
    upload_url = None
    if can_upload_later:
        from django.urls import reverse
        try:
            if request.user.is_authenticated:
                upload_url = reverse('conference_participant_uploads', args=[conference.id])
            elif participant.unique_token:
                upload_url = reverse(
                    'conference_participant_uploads_anon', 
                    args=[conference.id, str(participant.unique_token)]
                )
        except:
            pass

    return render(request, "conference/conf_reg_success.html", {"conference": conference, "participant": participant, 
                "payable_amount": payable_amount, 'uploaded_files_count': uploaded_files_count,
                'can_upload_later': can_upload_later, 'upload_url': upload_url,})

def conference_payment_breakdown(request, conference_id, participant_id):
    participant = get_object_or_404(
        ConferenceParticipant,
        id=participant_id,
        conference_id=conference_id,
        status="pending",
        ticket_paid=False
    )

    conference = participant.conference
    base_price = conference.get_current_price(registration_time=participant.registered_at, price_tier=participant.price_tier,)
    payable_amount = conference.get_payable_amount(base_price)

    percent_fee = (
        base_price * (conference.platform_fee_percent / Decimal("100"))
        if base_price and base_price > 0 else Decimal("0.00")
    )

    context = {
        "conference": conference,
        "participant": participant,
        "base_price": base_price,
        "percent_fee_amount": percent_fee,
        "fixed_fee": conference.platform_fee_fixed,
        "payable_amount": payable_amount,
        "currency": conference.currency or "NGN",
    }

    if request.method == "POST":
        metadata = {
            "source": "conference",
            "source_id": str(conference.id),
            "source_url": request.build_absolute_uri(
                reverse("conference_post", kwargs={"conference_id": conference.id})
            ),
            "participant_id": str(participant.id),
            "participant_name": participant.full_name,
            "participant_email": participant.email,
            "base_price": str(base_price),
            "payable_amount": str(payable_amount),
        }

        auth_url, reference = initialize_paystack_payment(
            email=participant.email,
            amount_ngn=float(payable_amount),
            metadata=metadata,
        )

        if not auth_url or not reference:
            messages.error(request, "Payment service unavailable. Please try again.")
            return render(request, "conference/payment_breakdown.html", context)

        payment, _ = Payment.objects.update_or_create(
            conference_registration=participant,
            defaults={
                "tenant": conference.tenant,
                "owner":conference.organizer,
                "payer": participant.payer,
                "payment_type": "conference_fee",
                "direction": "incoming",
                "amount": payable_amount,
                "net_amount": payable_amount,
                "status": "pending",
                "transaction_id": reference,
                "description": f"Conference ticket: {conference.title}",
                "created_by": conference.organizer,
                "return_url":reverse("conference_post", kwargs={"conference_id": conference.id}),
                "content_object": participant,
            }
        )

        participant.payment = payment
        participant.save(update_fields=["payment"])

        if request.user.is_anonymous:
            from django.contrib.contenttypes.models import ContentType
            conference_ct = ContentType.objects.get_for_model(Conference)
            
            guest_user, created = GuestUser.objects.get_or_create(
                email=participant.email,
                defaults={
                    "token": uuid.uuid4(),
                    "source_content_type": conference_ct,
                    "source_object_id": conference.id
                }
            )
            # Update source if it wasn't set before
            if not created and not guest_user.source_content_type:
                guest_user.source_content_type = conference_ct
                guest_user.source_object_id = conference.id
                guest_user.save(update_fields=['source_content_type', 'source_object_id'])
            
            response = redirect(auth_url)
            response.set_cookie(
                "guest_token",
                str(guest_user.token),
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax"
            )
            return response

        return redirect(auth_url)

    return render(request, "conference/payment_breakdown.html", context)


def conference_access(request, conference_id, token):
    """View to grant access to Conference participants.
    Args:
        request: The HTTP request object.
    Returns:
        Rendered template with access URL.
    """
    from django.contrib.contenttypes.models import ContentType
    
    conference = Conference.objects.get(id=conference_id)
    participant = ConferenceParticipant.objects.get(unique_token=token, conference=conference)
    email = participant.email.lower()
    conference_ct = ContentType.objects.get_for_model(Conference)
    
    guest_user, created = GuestUser.objects.get_or_create(
        email=email, 
        defaults={
            'token': uuid.uuid4(),
            'source_content_type': conference_ct,
            'source_object_id': conference.id
        }
    )
    # Update source if it wasn't set before
    if not created and not guest_user.source_content_type:
        guest_user.source_content_type = conference_ct
        guest_user.source_object_id = conference.id
        guest_user.save(update_fields=['source_content_type', 'source_object_id'])

    response = render(request, "conference/conference_access.html", {'conference': conference, 'participant': participant, 'now': timezone.now()})

    response.set_cookie(
        'guest_token',
        str(guest_user.token),
        max_age=60*60*24*365,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
        path='/'
    )

    return response


def _generate_qr_data_uri(data: str) -> str | None:
    """
    Generate a PNG QR code for `data` and return a data URI (base64).
    If qrcode/Pillow is not installed or generation fails, return None.
    """
    try:
        import qrcode  # requires `qrcode[pil]` or `qrcode` + Pillow installed

        buf = io.BytesIO()
        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(buf, format="PNG")
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:
        logger.debug("QR generation failed: %s", exc)
        return None


def participant_card(request, id):
    """
    Render a printable participant card containing:
      - participant name & email
      - conference title & dates
      - unique token
      - QR code encoding the participant access URL (if qrcode is available)

    Tenant-safe: verifies participant's conference belongs to the current tenant.
    """
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    # Ensure tenant isolation on lookup
    participant = get_object_or_404(ConferenceParticipant, id=id)
    conference = participant.conference

    # Build absolute access URL for the participant (same link sent in confirmation emails)
    access_url = build_conference_access_url(conference, participant)

    qr_data_uri = _generate_qr_data_uri(access_url)

    return render(
        request,
        "conference/participant_card.html",
        {
            "participant": participant,
            "conference": conference,
            "access_url": access_url,
            "qr_data_uri": qr_data_uri,
        },
    )

@login_required
def accept_conf_participant(request, id):
    """
    Accept a pending participant. Only organizer or staff may accept.
    After accepting, send confirmation email to participant.
    """
    tenant = request.tenant
    participant = get_object_or_404(ConferenceParticipant, id=id, conference__tenant=tenant)
    conference = participant.conference

    if not (request.user == conference.organizer or request.user.is_staff):
        return HttpResponseForbidden("You do not have permission to accept registrations for this conference.")

    if participant.status != "pending":
        messages.warning(request, "Participant is not pending; no action taken.")
        return redirect('conference_detail', conference_id=conference.id)

    participant.accept()

    # build access_url
    access_url = build_conference_access_url(conference, participant)

    guest_user = GuestUser.objects.filter(email__iexact=participant.email).first()
    if guest_user is not None:
        dashboard_url = build_guest_dashboard_url(guest_user.token)
    else:
        user = CustomUser.objects.filter(email__iexact=participant.email).first()
        if user is not None:
            dashboard_url = build_user_activity_dashboard_url(user)
    superuser = CustomUser.objects.filter(is_superuser=True).first()
    cc=[conference.organizer.email]
    send_conf_reg_accepted(participant, access_url, dashboard_url, sender=superuser, cc=cc)
    messages.success(request, f"{participant.full_name} has been accepted and notified.")
    return redirect('conference_detail', conference_id=conference.id)

@login_required
def bulk_accept_participants(request, conference_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    participant_ids = request.POST.getlist("participant_ids[]")
    if not participant_ids:
        return JsonResponse({"success": False, "error": "No participants selected"}, status=400)

    # Minimal permission check (full check is inside task)
    conference = get_object_or_404(Conference, id=conference_id)
    if not (request.user == conference.organizer or request.user.is_staff):
        return JsonResponse({"success": False, "error": "Permission denied"}, status=403)

    # Launch background task
    task = conf_bulk_accept_and_notify.delay(
        participant_ids=participant_ids,
        conference_id=conference_id,
        user_id=request.user.id
    )

    return JsonResponse({
        "success": True,
        "task_id": task.id,
        "message": f"Acceptance & notifications started for {len(participant_ids)} participants (running in background)"
    })

@login_required
def decline_conf_participant(request, id):
    """
    Decline a pending participant. Only organizer or staff may decline.
    After declining, send decline email to participant.
    """
    tenant = request.tenant
    participant = get_object_or_404(ConferenceParticipant, id=id, conference__tenant=tenant)
    conference = participant.conference

    if not (request.user == conference.organizer or request.user.is_staff):
        return HttpResponseForbidden("You do not have permission to decline registrations for this conference.")

    if participant.status != "pending":
        messages.warning(request, "Participant is not pending; no action taken.")
        return redirect('conference_detail', conference_id=conference.id)

    participant.decline()

    # You can include organizer contact if available
    organizer_contact = None
    if conference.organizer:
        organizer_contact = getattr(conference.organizer, 'email', None)

    superuser = CustomUser.objects.get(is_superuser=True, is_active=True)
    cc=[conference.organizer.email]
    send_conf_reg_declined(participant, organizer_contact, sender=superuser, cc=cc)
    messages.success(request, f"{participant.full_name}'s registration has been declined and they were notified.")
    return redirect('conference_detail', conference_id=conference.id)


def unregister_conf_participation(request, id):
    """
    Allows a participant to unregister from a conference.
    If token provided, the participant must own the token of the participant_profile
    associated with that registration. If called by authenticated organizer/staff, token can be omitted.
    """
    participant = get_object_or_404(ConferenceParticipant, id=id)
    conference = participant.conference
    tenant = getattr(request, 'tenant', None)
    if tenant and conference.tenant != tenant:
        raise Http404

    # If caller is organizer or staff, allow unregister without token
    if request.user.is_authenticated and (request.user == conference.organizer or request.user.is_staff):
        # organizer can remove registration
        participant.unregister()
        messages.success(request, "Participant registration removed.")
        return redirect('conference_detail', conference_id=conference.id)
    
    token = participant.unique_token

    # Otherwise require token match
    if not token:
        return HttpResponseForbidden("Token required to unregister.")

    participant.unregister()
    return redirect('guest_dashboard')
    # return render(request, "conference/conf_unreg_success.html"
    # ".html", {
    #     'conference': conference,
    # })


@login_required
def participant_bulk_action(request, conference_pk):
    conference = get_object_or_404(Conference, pk=conference_pk)

    # Permission check: only the organizer can manage participants
    if conference.organizer != request.user:
        messages.error(request, "You are not authorized to manage this conference.")
        return redirect('conference:detail', pk=conference_pk)  # or wherever you want to redirect

    if request.method != 'POST':
        return redirect('conference:manage_participants', conference_pk=conference_pk)

    action = request.POST.get('action')
    participant_pks = request.POST.getlist('participants')

    if not participant_pks:
        messages.warning(request, "No participants selected.")
        return redirect('conference:manage_participants', conference_pk=conference_pk)

    if action not in ['accept', 'decline', 'resend_link']:
        messages.error(request, "Invalid action.")
        return redirect('conference:manage_participants', conference_pk=conference_pk)

    # Filter to only participants of this conference (security)
    queryset = ConferenceParticipant.objects.filter(
        pk__in=participant_pks,
        conference=conference
    ).select_related('conference', 'participant_profile')

    if action == 'accept':
        return _bulk_accept(request, queryset, conference)
    elif action == 'decline':
        return _bulk_decline(request, queryset, conference)
    # elif action == 'resend_link':
    #     return _bulk_resend_link(request, queryset, conference)
    

@transaction.atomic
def _bulk_accept(request, queryset, conference):
    pending_qs = queryset.exclude(status="accepted")
    if not pending_qs.exists():
        messages.warning(request, "No participants to accept.")
        return redirect('conference:manage_participants', conference_pk=conference.pk)

    accepted = 0
    failed = 0

    for participant in pending_qs:
        try:
            participant.status = "accepted"
            participant.is_confirmed = True
            participant.save(update_fields=["status", "is_confirmed"])

            # build access_url
            access_url = build_conference_access_url(conference, participant)
            
            guest_user = GuestUser.objects.filter(email__iexact=participant.email).first()
            if guest_user is not None:
                dashboard_url = request.build_absolute_uri(reverse("guest_dashboard"))+ "?" + urlencode({"token": guest_user.token})
            else:
                user = CustomUser.objects.filter(email__iexact=participant.email).first()
                if user is not None:
                    dashboard_url = build_user_activity_dashboard_url(user)

            superuser = CustomUser.objects.filter(is_superuser=True).first()
            cc=[conference.organizer.email]
            send_conf_reg_accepted(participant, access_url, dashboard_url,sender=superuser, cc=cc)
            accepted += 1
        except Exception as e:
            # In production, log the exception
            failed += 1

    if accepted:
        messages.success(request, f"Accepted and notified {accepted} participant(s).")
    if failed:
        messages.error(request, f"Failed to accept/notify {failed} participant(s). See logs.")

    return redirect('conference:manage_participants', conference_pk=conference.pk)


@transaction.atomic
def _bulk_decline(request, queryset, conference):
    to_decline = queryset.exclude(status="declined")
    if not to_decline.exists():
        messages.warning(request, "No participants to decline.")
        return redirect('conference:manage_participants', conference_pk=conference.pk)

    declined = 0
    failed = 0

    for participant in to_decline:
        try:
            participant.status = "declined"
            participant.is_confirmed = False
            participant.save(update_fields=["status", "is_confirmed"])

            organizer_contact = None
            if conference.organizer:
                organizer_contact = getattr(conference.organizer, 'email', None)

            superuser = CustomUser.objects.filter(is_superuser=True).first()
            cc=[conference.organizer.email]
            send_conf_reg_declined(participant, organizer_contact, sender=superuser, cc=cc)
            declined += 1
        except Exception:
            failed += 1

    if declined:
        messages.success(request, f"Declined and notified {declined} participant(s).")
    if failed:
        messages.error(request, f"Failed to decline/notify {failed} participant(s). See logs.")

    return redirect('conference:manage_participants', conference_pk=conference.pk)


# def _bulk_resend_link(request, queryset, conference):
#     sent = 0
#     failed = 0

#     for participant in queryset:
#         try:
#             access_url = _build_absolute_access_url(conference, participant)
#             context = {
#                 "participant": participant,
#                 "conference": conference,
#                 "access_url": access_url
#             }
#             subject = f"Access link: {conference.title}"
#             html_body = render_to_string("emails/registration_confirmation.html", context)

#             email = EmailMessage(
#                 subject=subject,
#                 body=html_body,
#                 from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
#                 to=[participant.email],
#             )
#             email.content_subtype = "html"
#             email.send(fail_silently=False)
#             sent += 1
#         except Exception:
#             failed += 1

#     if sent:
#         messages.success(request, f"Resent access link to {sent} participant(s).")
#     if failed:
#         messages.error(request, f"Failed to send to {failed} participant(s). See logs.")

#     return redirect('conference:manage_participants', conference_pk=conference.pk)

@login_required
def manage_conference_participants(request, conference_id):
    if request.effective_tenant is None and request.effective_user.is_personal:
        conference = get_object_or_404(Conference, id=conference_id, organizer=request.effective_user)
    else:
        conference = get_object_or_404(Conference, id=conference_id, tenant=request.effective_tenant)

    if not can_manage_conference_participant(request, conference):
        messages.error(request, "You do not have permission to manage this conference participants.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to manage this conference participants.'
        })

    participants_qs = ConferenceParticipant.objects.filter(conference=conference).order_by('-registered_at')

    # === SEARCH & FILTER ===
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    checked_in = request.GET.get('checkedin', '').strip()

    if query:
        participants_qs = participants_qs.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(organization__icontains=query) |
            Q(designation__icontains=query) |
            Q(country__icontains=query) |
            Q(city__icontains=query) 
        )

    if status in ['pending', 'accepted', 'declined']:
        participants_qs = participants_qs.filter(status=status)
    
    if checked_in in ['yes', 'no']:
        if checked_in == 'yes':
            participants_qs = participants_qs.filter(check_in_status=True)
        else:
            participants_qs = participants_qs.filter(check_in_status=False)

    participants = participants_qs

    return render(request, "conference/manage_conf_participants.html", {"conference": conference, "participants": participants})


@login_required
def manage_conference_participant(request, conference_id, participant_id):
    if request.effective_tenant is None and request.effective_user.is_personal:
        conference = get_object_or_404(Conference, id=conference_id, organizer=request.effective_user)
    else:
        conference = get_object_or_404(Conference, id=conference_id, tenant=request.effective_tenant)

    if not can_manage_conference_participant(request, conference):
        messages.error(request, "You do not have permission to manage this conference participants.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to manage this conference participants.'
        })

    participant = ConferenceParticipant.objects.get(id=participant_id, conference=conference)

    return render(request, "conference/conf_participant.html", {"conference": conference, "participant": participant})

@require_GET
def load_participants_custom_responses(request, participant_id):
    try:
        # Optional: check if participant exists
        # participant = Participant.objects.get(id=participant_id)

        custom_responses = CustomAnswer.objects.filter(
            participant__id=participant_id
        ).select_related('question')  # very useful if you have a ForeignKey to question

        # You can structure the response in different ways — choose what your frontend needs
        data = [
            {
                "id": answer.id,
                "question_id": answer.question_id,
                "question_text": answer.question.text if hasattr(answer.question, 'text') else str(answer.question),
                "answer": answer.answer,
                "answer_type": answer.question.type if hasattr(answer.question, 'type') else None,  # optional
                "created_at": answer.created_at.isoformat() if answer.created_at else None,
            }
            for answer in custom_responses.order_by('question__order', 'created_at')
        ]

        return JsonResponse({
            "success": True,
            "responses": data,
            "count": len(data),
            # "participant_id": participant_id,  # optional
        })

    except ConferenceParticipant.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Participant not found"
        }, status=404)

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": "Server error"
        }, status=500)

@login_required
def checkin_scanner(request, conference_id):
    if request.effective_tenant is None and request.effective_user.is_personal:
        conference = get_object_or_404(Conference, id=conference_id, organizer=request.effective_user)
    else:
        conference = get_object_or_404(Conference, id=conference_id, tenant=request.effective_tenant)
    
    # # Prefix helps JS validate & reconstruct — e.g. "https://.../conference/123/access/"
    # access_prefix = request.build_absolute_uri(
    #     reverse('conference_access', args=[conference.id, '00000000-0000-0000-0000-000000000000'])
    # ).rstrip('00000000-0000-0000-0000-000000000000')
    
    context = {
        'conference': conference,
        # 'access_url_prefix': access_prefix,
    }
    return render(request, 'conference/checkin_scanner.html', context)

@login_required
@require_POST
def process_checkin(request, token):
    participant = get_object_or_404(ConferenceParticipant, unique_token=token)
    
    # Security: ensure token belongs to the active conference (extra safety)
    data = json.loads(request.body)
    conference_id_from_post = str(data.get("conference_id"))
    if str(participant.conference_id) != conference_id_from_post:
        return JsonResponse({
            'success': False,
            'message': 'Token does not belong to this conference'
        }, status=403)
    
    if participant.check_in_status:
        return JsonResponse({
            'success': False,
            'message': f'Already checked in at {participant.check_in_time:%Y-%m-%d %H:%M:%S}'
        })
    
    # Perform check-in
    participant.check_in_status = True
    participant.check_in_time   = timezone.now()
    participant.checked_in_by   = request.user  # the logged-in organizer
    participant.check_in_method = 'qr_scan'
    participant.save()
    
    display_name = participant.email
    if hasattr(participant, 'name') and participant.full_name:
        display_name = f"{participant.full_name} ({participant.email})"
    
    return JsonResponse({
        'success': True,
        'message': f'Checked in: {display_name}',
        'participant_id': participant.id,  # optional: for future HTMX refresh
    })

def manual_checkin(request, conference_id, participant_id):
    if request.effective_tenant is None and request.effective_user.is_personal:
        conference = get_object_or_404(Conference, id=conference_id, organizer=request.effective_user)
    else:
        conference = get_object_or_404(Conference, id=conference_id, tenant=request.effective_tenant)
    
    participant = get_object_or_404(ConferenceParticipant, id=participant_id, conference=conference)
    
    participant.check_in_status = True
    participant.check_in_time   = timezone.now()
    participant.checked_in_by   = request.user  # the logged-in organizer
    participant.check_in_method = 'manual'
    participant.save()
    
    return redirect('manage_conference_participants', conference_id=conference.id)

@require_POST
def bulk_checkin(request, conference_id):
    print("🔥 BULK CHECKIN VIEW HIT")

    ids = request.POST.getlist("participant_ids[]")
    print("Participant IDs:", ids)

    if request.effective_tenant is None and request.effective_user.is_personal:
        conference = get_object_or_404(Conference, id=conference_id, organizer=request.effective_user)
    else:
        conference = get_object_or_404(Conference, id=conference_id, tenant=request.effective_tenant)

    participants = ConferenceParticipant.objects.filter(
        id__in=ids,
        conference=conference
    )

    count = 0
    for participant in participants:
        if not participant.check_in_status:
            participant.check_in_status = True
            participant.check_in_time = timezone.now()
            participant.checked_in_by = request.user
            participant.save()
            count += 1

    return JsonResponse({
        "success": True,
        "checked_in": count
    })


# @login_required
# def send_conference_reminders_manual(request, conference_id, reminder_method, message):
#     conference = get_object_or_404(Conference, id=conference_id, tenant=request.tenant)
#     participants = ConferenceParticipant.objects.filter(tenant=request.tenant, conference=conference, status='accepted', is_confirmed=True)

#     if request.user != conference.organizer:
#         return HttpResponseForbidden("Only the organizer can send reminders.")
    
#     superuser = CustomUser.objects.filter(is_superuser=True).first()
    
#     if reminder_method == "email":
#         send_conference_reminder(participants, conference, superuser, cc=[conference.organizer.email, conference.tenant.admin.email])
#     if reminder_method == "sms":


#     return

@login_required
def send_conference_reminders_manual(request, conference_id):
    if request.user.is_superuser or (request.user.is_staff and request.user.tenant is None):
        conference = get_object_or_404(Conference, id=conference_id)
    else:
        conference = get_object_or_404(Conference, id=conference_id, tenant=request.effective_tenant)

    if not can_manage_conference_participant(request, conference):
        messages.error(request, "You do not have permission to manage this conference participants.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to manage this conference participants.'
        })
    participants = ConferenceParticipant.objects.filter(conference=conference, status='accepted', is_confirmed=True)
    
    sender = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
    cc_list = []
    if conference.organizer and conference.organizer.email:
        cc_list = [conference.organizer.email]
    print("Trying to send reminders...")
    send_conference_reminders_task.delay(conference.id, sender.id, cc_emails=cc_list)
    print("Reminders have been sent to eligible participants.")

    messages.success(request, "Reminders have been sent to eligible participants.")
    # return redirect('manage_conference_participants', conference_id=conference.id)
    return redirect('conference_detail', conference_id=conference.id)

    # return redirect('manage_conference_participants', conference_id=conference.id)


@login_required
def export_participants_csv(request, conference_id):
    effective_user   = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    conference = get_object_or_404(Conference, id=conference_id, organizer=effective_user)
    
    # Determine which participants
    if request.GET.get('all'):
        participants = conference.participants.all()
    else:
        ids = request.GET.get('ids', '')
        if not ids:
            return HttpResponse("No participants selected.", status=400)
        participant_ids = [int(pid) for pid in ids.split(',') if pid.isdigit()]
        participants = conference.participants.filter(id__in=participant_ids)

    response = HttpResponse(content_type='text/csv')
    filename = f"{conference.title.replace(' ', '_')}_participants_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Email', 'Phone', 'Organization', 'Designation',
        'Country', 'City', 'Attendance Mode', 'Registered At', 'Registration Status',
        'Checked In Status', 'Checked In At', 'Checked In By'
    ])

    for p in participants:
        writer.writerow([
            p.full_name,
            p.email,
            p.phone_number or '',
            p.organization or '',
            p.designation or '',
            p.country or '',
            p.city or '',
            p.get_attendance_mode_display() if p.attendance_mode else '',
            p.registered_at.strftime('%Y-%m-%d %H:%M'),
            p.get_status_display(),
            p.check_in_status,
            p.check_in_time.strftime('%Y-%m-%d %H:%M') if p.check_in_time else '',
            p.checked_in_by.username if p.checked_in_by else '',
        ])

    return response

@login_required
def print_participants_pdf(request, conference_id):
    effective_user   = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', getattr(request, 'tenant', None))
    conference = get_object_or_404(Conference, id=conference_id, organizer=effective_user)
    
    if request.GET.get('all'):
        participants = conference.participants.all()
    else:
        ids = request.GET.get('ids', '')
        if not ids:
            return HttpResponse("No participants selected.", status=400)
        participant_ids = [int(pid) for pid in ids.split(',') if pid.isdigit()]
        participants = conference.participants.filter(id__in=participant_ids)

    context = {
        'conference': conference,
        'participants': participants,
        'print_mode': True,
    }
    return render(request, 'conference/print_participants.html', context)

@login_required
def conference_checkin_dashboard(request, conference_id):
    """Dashboard for conference organizers to manage check-ins"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Check if user is the organizer
    if conference.organizer != request.user:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('conference_detail', pk=conference_id)
    
    # Get statistics
    participants = ConferenceParticipant.objects.filter(
        conference=conference,
        ticket_paid=True
    )
    
    stats = participants.aggregate(
        total=Count('id'),
        checked_in=Count(Case(When(check_in_status=True, then=1), output_field=IntegerField())),
        physical=Count(Case(When(attendance_mode='physical', then=1), output_field=IntegerField())),
        virtual=Count(Case(When(attendance_mode='virtual', then=1), output_field=IntegerField())),
        physical_checked_in=Count(Case(
            When(attendance_mode='physical', check_in_status=True, then=1), 
            output_field=IntegerField()
        )),
        virtual_checked_in=Count(Case(
            When(attendance_mode='virtual', check_in_status=True, then=1), 
            output_field=IntegerField()
        )),
    )
    
    # Get recent check-ins
    recent_checkins = participants.filter(
        check_in_status=True
    ).select_related('checked_in_by').order_by('-check_in_time')[:10]
    
    context = {
        'conference': conference,
        'stats': stats,
        'recent_checkins': recent_checkins,
        'participants': participants.order_by('-last_name', '-first_name')
    }
    
    return render(request, 'conference/conference_checkin_dashboard.html', context)

@login_required
def conference_attended_list(request, conference_id):
    """List of participants who attended (checked in)"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    # Check if user is the organizer
    if conference.organizer != request.user:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('conference_detail', pk=conference_id)
    
    # Get attended participants
    attended_participants = ConferenceParticipant.objects.filter(
        conference=conference,
        ticket_paid=True,
        check_in_status=True
    ).select_related('checked_in_by').order_by('-check_in_time')
    
    # Get statistics
    stats = {
        'total_attended': attended_participants.count(),
        'physical_attended': attended_participants.filter(attendance_mode='physical').count(),
        'virtual_attended': attended_participants.filter(attendance_mode='virtual').count(),
        'qr_scan_count': attended_participants.filter(check_in_method='qr_scan').count(),
        'manual_count': attended_participants.filter(check_in_method='manual').count(),
        'online_count': attended_participants.filter(check_in_method='online').count(),
    }
    
    context = {
        'conference': conference,
        'attended_participants': attended_participants,
        'stats': stats,
    }
    
    return render(request, 'conference/conference_attended_list.html', context)

@login_required
def conference_checkin_export_csv(request, conference_id):
    """Export all check-in data as CSV"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    if conference.organizer != request.user:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('conference_detail', pk=conference_id)
    
    # Get filter parameter
    filter_type = request.GET.get('filter', 'all')  # 'all' or 'attended'
    
    # Create response
    response = HttpResponse(content_type='text/csv')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    
    if filter_type == 'attended':
        filename = f'attended_participants_{conference.id}_{timestamp}.csv'
        participants = ConferenceParticipant.objects.filter(
            conference=conference,
            ticket_paid=True,
            check_in_status=True
        ).select_related('checked_in_by')
    else:
        filename = f'all_participants_{conference.id}_{timestamp}.csv'
        participants = ConferenceParticipant.objects.filter(
            conference=conference,
            ticket_paid=True
        ).select_related('checked_in_by')
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Email', 'Phone', 'Attendance Type', 
        'Checked In', 'Check-in Time', 'Check-in Method', 
        'Checked In By', 'Registration Date'
    ])
    
    for p in participants.order_by('first_name', 'last_name'):
        writer.writerow([
            p.first_name,
            p.email,
            p.phone_number or '',
            p.get_attendance_mode_display(),
            'Yes' if p.check_in_status else 'No',
            p.check_in_time.strftime('%Y-%m-%d %H:%M:%S') if p.check_in_time else '',
            p.get_check_in_method_display() if p.check_in_method else '',
            p.checked_in_by.get_full_name() if p.checked_in_by else '',
            p.registered_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(p, 'registered_at') else ''
        ])
    
    return response


@login_required
def conference_checkin_export_pdf(request, conference_id):
    """Export attended participants as PDF"""
    conference = get_object_or_404(Conference, id=conference_id)
    
    if conference.organizer != request.user:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('conference_detail', pk=conference_id)
    
    # Get filter parameter
    filter_type = request.GET.get('filter', 'all')  # 'all' or 'attended'
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    
    if filter_type == 'attended':
        filename = f'attended_participants_{conference.id}_{timestamp}.pdf'
        participants = ConferenceParticipant.objects.filter(
            conference=conference,
            ticket_paid=True,
            check_in_status=True
        ).select_related('checked_in_by').order_by('-check_in_time')
        title = "Attended Participants Report"
    else:
        filename = f'all_participants_{conference.id}_{timestamp}.pdf'
        participants = ConferenceParticipant.objects.filter(
            conference=conference,
            ticket_paid=True
        ).select_related('checked_in_by').order_by('last_name', 'first_name')
        title = "All Participants Report"
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#319795'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c7a7b'),
        spaceAfter=12,
    )
    
    # Title
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(f"Conference: {conference.title}", heading_style))
    elements.append(Spacer(1, 12))
    
    # Conference Details
    info_text = f"""
    <b>Date:</b> {conference.start_date.strftime('%B %d, %Y')}<br/>
    <b>Time:</b> {conference.start_date.strftime('%I:%M %p')} - {conference.end_date.strftime('%I:%M %p')}<br/>
    <b>Venue:</b> {conference.venue if conference.venue else 'Virtual Event'}<br/>
    <b>Report Generated:</b> {timezone.now().strftime('%B %d, %Y at %I:%M %p')}<br/>
    """
    elements.append(Paragraph(info_text, styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Statistics
    total_count = participants.count()
    if filter_type == 'attended':
        physical = participants.filter(attendance_mode='physical').count()
        virtual = participants.filter(attendance_mode='virtual').count()
        stats_text = f"""
        <b>Total Attended:</b> {total_count}<br/>
        <b>Physical:</b> {physical}<br/>
        <b>Virtual:</b> {virtual}<br/>
        """
    else:
        attended = participants.filter(check_in_status=True).count()
        not_attended = total_count - attended
        stats_text = f"""
        <b>Total Registered:</b> {total_count}<br/>
        <b>Attended:</b> {attended}<br/>
        <b>Not Attended:</b> {not_attended}<br/>
        """
    
    elements.append(Paragraph(stats_text, styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Participants Table
    elements.append(Paragraph("Participant Details", heading_style))
    elements.append(Spacer(1, 12))
    
    # Table data
    if filter_type == 'attended':
        table_data = [['#', 'Name', 'Email', 'Type', 'Check-in Time', 'Method']]
        for idx, p in enumerate(participants, 1):
            table_data.append([
                str(idx),
                Paragraph(p.first_name, styles['Normal']),
                Paragraph(p.email, styles['Normal']),
                p.get_attendance_mode_display(),
                p.check_in_time.strftime('%m/%d %H:%M') if p.check_in_time else '',
                p.get_check_in_method_display() if p.check_in_method else ''
            ])
        col_widths = [0.5*inch, 1.5*inch, 2*inch, 1*inch, 1.2*inch, 1*inch]
    else:
        table_data = [['#', 'Name', 'Email', 'Type', 'Status']]
        for idx, p in enumerate(participants, 1):
            status = '✓ Attended' if p.check_in_status else '✗ Not Attended'
            table_data.append([
                str(idx),
                Paragraph(p.first_name, styles['Normal']),
                Paragraph(p.email, styles['Normal']),
                p.get_attendance_mode_display(),
                status
            ])
        col_widths = [0.5*inch, 2*inch, 2.5*inch, 1.2*inch, 1.2*inch]
    
    # Create table
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#319795')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    
    elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 30))
    footer_text = f"<i>Generated by {conference.tenant.name if conference.tenant else 'Conference System'}</i>"
    elements.append(Paragraph(footer_text, styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    
    return response

@login_required
@require_POST
def conference_checkin_manual(request, conference_id, participant_id):
    """Manual check-in for a participant"""
    conference = get_object_or_404(Conference, id=conference_id)
    participant = get_object_or_404(ConferenceParticipant, id=participant_id, conference=conference)
    
    # Check if user is the organizer
    if conference.organizer != request.user:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    # if not participant.ticket_paid:
    #     return JsonResponse({'success': False, 'error': 'Participant has not paid'})
    
    if participant.check_in_status:
        return JsonResponse({
            'success': False,
            'error': 'Already checked in',
            'check_in_time': participant.check_in_time.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    # Determine check-in method
    # method = 'online' if participant.attendance_mode == 'virtual' else 'manual'
    # participant.check_in(request.user, method=method)
    participant.check_in_status = True
    participant.check_in_time   = timezone.now()
    participant.checked_in_by   = request.user
    participant.save()
    
    return JsonResponse({
        'success': True,
        'participant': {
            'id': participant.id,
            'name': participant.first_name,
            'check_in_time': participant.check_in_time.strftime('%Y-%m-%d %H:%M:%S')
        }
    })


@login_required
def conference_participant_uploads(request, conference_id):
    """
    View for participants to upload files to conference folder.
    Only accessible to accepted participants.
    Follows existing file upload pattern from file_views.py.
    """
    # Tenant check (following your existing pattern)
    if not hasattr(request, 'tenant') or request.user.tenant != request.tenant:
        return HttpResponseForbidden("You are not authorized for this company.")
    
    effective_user = getattr(request, 'effective_user', request.user)
    effective_tenant = getattr(request, 'effective_tenant', request.tenant)
    
    # Get conference
    conference = get_object_or_404(Conference, id=conference_id, tenant=effective_tenant)
    
    # Check if user is an accepted participant
    participant = ConferenceParticipant.objects.filter(conference=conference, email=effective_user.email,
        status='accepted'
    ).first()
    
    if not participant:
        messages.error(request, "You must be an accepted participant to upload files.")
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'Only accepted participants can upload files to this conference.'
        })
    
    # Check if conference has upload folder
    if not conference.upload_folder:
        return render(request, 'conference/no_upload_folder.html', {
            'conference': conference,
            'participant': participant
        })
    
    upload_folder = conference.upload_folder
    
    # Handle file upload (POST request)
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.save(commit=False)
            uploaded_file.uploaded_by = effective_user
            uploaded_file.tenant = effective_tenant
            uploaded_file.folder = upload_folder
            uploaded_file.original_name = request.FILES['file'].name
            uploaded_file.is_public = upload_folder.is_public
            uploaded_file.save()
            
            return JsonResponse({
                'success': True,
                'file_id': uploaded_file.id,
                'file_name': uploaded_file.original_name,
                'message': 'File uploaded successfully!'
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    
    # GET request - show upload interface
    # Get participant's uploaded files
    participant_files = File.objects.filter(
        folder=upload_folder,
        uploaded_by=effective_user,
        tenant=effective_tenant
    ).order_by('-uploaded_at')
    
    # Get all files in folder (so participants can see what others uploaded)
    all_files = File.objects.filter(
        folder=upload_folder,
        tenant=effective_tenant
    ).order_by('-uploaded_at')
    
    file_form = FileUploadForm()
    
    return render(request, 'conference/participant_uploads.html', {
        'conference': conference,
        'participant': participant,
        'upload_folder': upload_folder,
        'participant_files': participant_files,
        'all_files': all_files,
        'file_form': file_form,
    })



# ANONYMOUS PARTICIPANT UPLOAD (using token from email)
# For participants who don't have user accounts
# ============================================================================

def conference_participant_uploads_anon(request, conference_id, token):
    """
    Allow participants to upload files using unique token from email.
    No login required. Follows pattern from file_views.py upload_file_anon.
    """
    effective_tenant = getattr(request, 'tenant', None)
    
    # Get conference
    conference = get_object_or_404(
        Conference,
        id=conference_id,
        tenant=effective_tenant
    )
    
    # Get participant by unique token
    participant = get_object_or_404(
        ConferenceParticipant,
        conference=conference,
        unique_token=token,
        status='accepted'
    )
    
    # Check if conference has upload folder
    if not conference.upload_folder:
        return render(request, 'conference/no_upload_folder.html', {
            'conference': conference,
            'participant': participant,
            'is_anonymous': True
        })
    
    upload_folder = conference.upload_folder
    
    # Handle file upload
    if request.method == 'POST':
        form = FileUploadAnonForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.save(commit=False)
            uploaded_file.anon_name = participant.name  # Use participant's name
            uploaded_file.tenant = effective_tenant
            uploaded_file.folder = upload_folder
            uploaded_file.original_name = request.FILES['file'].name
            uploaded_file.is_public = upload_folder.is_public
            uploaded_file.save()
            
            return JsonResponse({
                'success': True,
                'file_id': uploaded_file.id,
                'file_name': uploaded_file.original_name,
                'message': 'File uploaded successfully!'
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    
    # GET request - show upload interface
    # Get participant's uploaded files (match by anon_name)
    participant_files = File.objects.filter(
        folder=upload_folder,
        anon_name=participant.name,
        tenant=effective_tenant
    ).order_by('-uploaded_at')
    
    # Get all files
    all_files = File.objects.filter(
        folder=upload_folder,
        tenant=effective_tenant
    ).order_by('-uploaded_at')
    
    file_form = FileUploadAnonForm()
    
    return render(request, 'conference/participant_uploads_anon.html', {
        'conference': conference,
        'participant': participant,
        'upload_folder': upload_folder,
        'participant_files': participant_files,
        'all_files': all_files,
        'file_form': file_form,
        'token': token
    })
