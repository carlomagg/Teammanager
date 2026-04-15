import uuid
import requests
import logging, hashlib, hmac, json
from raadaa import settings
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import render, redirect, get_object_or_404
from documents.viewfuncs.send_mails import send_conf_reg_accepted, send_payment_failed_email, send_remittance_for_user_failed_email, send_remittance_success_for_user_email
from .access_urls import build_conference_access_url, build_guest_dashboard_url, build_user_activity_dashboard_url
from ..send_mails import send_booking_request_email, send_booking_confirmed_email
from documents.models import Payment, CustomUser, Conference, GuestUser, Remittance, Booking
from tenants.models import Subscription, SubscriptionType  # Import Subscription models
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import unquote, urlencode
from django.db import transaction
from documents.viewfuncs.send_mails import send_remittance_success_email, send_remittance_failed_email

logger = logging.getLogger(__name__)

def initialize_paystack_payment(email: str, amount_ngn: float, metadata: dict = None, callback_url: str = None):
    """
    Initialize Paystack transaction
    Returns: authorization_url, reference (from Paystack)
    """
    if amount_ngn <= 0:
        return None, None

    amount_in_kobo = int(amount_ngn * 100)

    payload = {
        "email": email.strip().lower(),
        "amount": amount_in_kobo,
        "currency": "NGN",
        "metadata": metadata or {},
        # No callback_url — we rely on webhook
    }
    if callback_url := settings.PAYSTACK_CALLBACK_URL:
        payload['callback_url'] = callback_url

    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status"):
            return data['data']['authorization_url'], data['data']['reference']
        else:
            logger.error(f"Paystack init failed: {data}")
    except Exception as e:
        logger.exception("Paystack initialization error")

    return None, None


def get_bank_list(request):
    """
    Fetch bank list from Paystack.
    Returns a JSON list of banks.
    """
    url = "https://api.paystack.co/bank?currency=NGN"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error fetching banks from Paystack: {e}")
        return JsonResponse({"status": False, "message": "Could not fetch bank list"}, status=500)



# def verify_paystack_payment(reference: str):
#     """
#     Verify transaction by reference
#     Returns: success (bool), data (dict)
#     """
#     if not reference:
#         return False, None

#     headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
#     url = f"https://api.paystack.co/transaction/verify/{reference}"

#     try:
#         response = requests.get(url, headers=headers, timeout=30)
#         response.raise_for_status()
#         data = response.json()
#         if data.get("status") and data['data']['status'] == 'success':
#             return True, data['data']
#     except Exception as e:
#         logger.exception("Paystack verification error")

#     return False, None


def generic_payment_callback(request):
    """
    Single, reusable Paystack callback for ALL payment flows.
    Uses metadata.source_url for redirect - perfect UX.
    """
    status = request.GET.get('status')
    reference = request.GET.get("reference")
    # status = request.GET.get("status")
    print(f"status: {status}, reference: {reference}")
    if not reference:
        messages.warning(request, "Payment completed, but reference was missing.")
        return redirect("home")

    try:
        payment = Payment.objects.get(transaction_id=reference)
    except Payment.DoesNotExist:
        messages.warning(request, "Payment received, but could not be verified.")
        return redirect("home")

    # Extract metadata fields sent by Paystack
    source_url = request.GET.get('source_url')
    participant_name = request.GET.get('participant_name')
    print(f"source_url: {source_url}, participant_name: {participant_name}")

    if status == 'success':
        name_msg = f", {participant_name}" if participant_name else ""
        messages.success(
            request,
            f"Payment successful{name_msg}! 🎉 "
            "Your registration is confirmed. Check your email for details."
        )
    else:
        messages.warning(
            request,
            "Payment was not completed. You can try again."
        )

    # 👇 THIS MAKES IT GENERIC
    if payment.return_url:
        return redirect(payment.return_url)

    return redirect("home")


@csrf_exempt
def paystack_unified_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=400)

    # ── Log EVERY incoming webhook ───────────────────────────────────────────
    print("=== PAYSTACK WEBHOOK RECEIVED ===")
    print(f"Headers: {dict(request.headers)}")
    print(f"Raw body: {request.body[:1000]}...")  # first 1KB

    signature = request.headers.get('x-paystack-signature')
    if not signature:
        print("No signature header")
        return HttpResponse(status=400)

    # Verify signature (keep this)
    computed = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(),
        request.body,
        hashlib.sha512
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        print("Signature verification FAILED")
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
        print("Payload parsed successfully")
        print(f"Full event: {payload.get('event')}")
        print(f"Reference: {payload.get('data', {}).get('reference')}")
        print(f"Metadata raw: {payload.get('data', {}).get('metadata')}")
    except Exception as e:
        print(f"JSON parse error: {e}")
        return HttpResponse(status=400)

    event = payload.get('event')
    data = payload.get('data', {})
    reference = data.get('reference')
    meta = data.get('metadata', {})
    source = meta.get('source')

    print(f"Extracted event: {event}, source: {source}, ref: {reference}")
    print(f"Metadata keys: {list(meta.keys())}")

    if not event:
        return JsonResponse({"status": "ignored — no event"})
    
    # meta = data.get('metadata', {})   # ← this comes back from Paystack exactly as you sent it
    # source = meta.get('source')

    # ────────────────────────────────────────────────
    #  Payment / Charge events  (incoming money)
    # ────────────────────────────────────────────────
    if event in ('charge.success', 'charge.failed', 'charge.dispute.create', ...):   # add others you care about
        print(f"Source: {source}, Reference: {reference}")
        print(f"CHARGE EVENT RECEIVED:\nevent={event}\nreference={reference}\ndata={json.dumps(meta, indent=2)}")
        # Reuse or call your existing charge logic
        if source == 'conference':
            return handle_conference_charge(request, event, data, reference, payload)
        elif source == 'subscription':
            return handle_subscription_charge(request, event, data, reference, payload)
        elif source == 'booking':
            return handle_booking_charge(request, event, data, reference, payload)

        # return handle_charge_event(request, event, data, reference, payload)

    # ────────────────────────────────────────────────
    #  Transfer events  (outgoing money — remittance)
    # ────────────────────────────────────────────────
    elif event.startswith('transfer.'):
        source = data.get('source')
        print(f"Source: {source}")
        print(f"TRANSFER EVENT RECEIVED:\nevent={event}\nreference={reference}\ndata={json.dumps(data, indent=2)}")
        # messages.info(f"TRANSFER EVENT RECEIVED:\nevent={event}\nreference={reference}\ndata={json.dumps(data, indent=2)}")
    # elif event in ('transfer.success', 'transfer.failed', 'transfer.reversed'):
        if source == 'balance':
            return handle_remittance_transfer(request, event, data, payload)
        # return handle_transfer_event(request, event, data, payload)

    # ────────────────────────────────────────────────
    #  Future events (subscriptions, invoices, dedicated accounts, etc.)
    # ────────────────────────────────────────────────
    # elif event.startswith('subscription.'):
    #     return handle_subscription_event(event, data)

    # elif event.startswith('invoice.'):
    #     return handle_invoice_event(event, data)

    # Unknown / ignored event — still return 200
    logger.info(f"Ignored Paystack event: {event}")
    return JsonResponse({"status": "received"})


def handle_conference_charge(request, event: str, data: dict, reference: str, full_payload: dict) -> JsonResponse:
    """
    Handles charge.success, charge.failed and other charge-related events for conferences
    """
    if not reference:
        logger.warning("Webhook charge event received without reference")
        return JsonResponse({"status": "ignored — no reference"})

    try:
        # Try to fetch the payment with useful relations preloaded
        payment = Payment.objects.select_related(
            'conference_registration',
            'conference_registration__conference',
            'tenant'
        ).get(transaction_id=reference, payment_type='conference_fee')
    except Payment.DoesNotExist:
        logger.info(f"Webhook: No matching conference payment found for ref {reference}")
        # You could still return 200 — Paystack requires it
        return JsonResponse({"status": "not_found"})

    participant = payment.conference_registration
    if not participant:
        logger.warning(f"Payment {reference} has no linked conference_registration")
        return JsonResponse({"status": "no participant"})

    conference = participant.conference

    if event == 'charge.success':
        if payment.status == 'pending':
            # ── Update payment ───────────────────────────────────────
            payment.status = 'success'
            payment.payment_date = timezone.now()
            payment.save()

            # ── Update participant ───────────────────────────────────
            participant.ticket_paid = True
            participant.status = 'accepted'
            participant.is_confirmed = True
            participant.save()

            # ── Prepare URLs ─────────────────────────────────────────
            access_url = build_conference_access_url(conference, participant)

            # Dashboard URL logic (guest vs authenticated user)
            if request.user.is_anonymous or request.user.email != participant.email:
                guest_user, _ = GuestUser.objects.get_or_create(
                    email=participant.email,
                    defaults={"token": uuid.uuid4()}
                )
                dashboard_url = build_guest_dashboard_url(str(guest_user.token))
            else:
                dashboard_url = build_user_activity_dashboard_url(request.user)

            # ── Send confirmation email ──────────────────────────────
            try:
                sender = CustomUser.objects.filter(is_superuser=True).first()
                cc = []
                if conference.organizer:
                    cc.append(conference.organizer.email)
                if payment.tenant and payment.tenant.admin:
                    cc.append(payment.tenant.admin.email)

                send_conf_reg_accepted(
                    participant=participant,
                    access_url=access_url,
                    dashboard_url=dashboard_url,
                    sender=sender,
                    cc=cc
                )
            except Exception as mail_err:
                logger.error(f"Failed to send confirmation email for {reference}: {mail_err}")

            # ── Update tenant wallet balance ─────────────────────────
            try:
                from documents.models import TenantBalance
                tenant_balance, _ = TenantBalance.objects.get_or_create(tenant=payment.tenant)
                tenant_balance.update_balance()
                logger.info(f"Tenant wallet updated after successful payment {reference}")
            except Exception as wallet_err:
                logger.error(f"Failed to update tenant wallet for payment {reference}: {wallet_err}")

            logger.info(f"Payment SUCCESS via webhook: {participant.full_name} - {conference.title}")
        
        else:
            logger.info(f"charge.success webhook received but payment already processed: {reference}")

    elif event == 'charge.failed':
        if payment.status == 'pending':
            payment.status = 'failed'
            payment.save()

            # Keep participant pending - allows retry
            logger.info(f"Payment FAILED via webhook: {participant.full_name} - ref {reference}")

            # Prepare retry URL
            retry_path = reverse('conference_post', kwargs={'conference_id': conference.id})
            retry_url = f"{request.build_absolute_uri(retry_path)}?retry={participant.id}"

            try:
                sender = CustomUser.objects.filter(is_superuser=True).first()
                cc = [conference.organizer.email] if conference.organizer else []

                send_payment_failed_email(
                    participant=participant,
                    conference=conference,
                    retry_url=retry_url,
                    sender=sender,
                    cc=cc
                )
            except Exception as mail_err:
                logger.error(f"Failed to send payment failed email for {reference}: {mail_err}")

    # You can add more charge.* events here in the future
    # e.g. elif event == 'charge.dispute.create': ...

    return JsonResponse({"status": "processed"})

def handle_booking_charge(request, event: str, data: dict, reference: str, full_payload: dict) -> JsonResponse:
    """
    Handles charge.success and charge.failed for booking payments.
    - success: confirm booking/event
    - failed: delete booking/event/payment (no ghost records)
    """
    if not reference:
        logger.warning("Webhook charge event received without reference")
        return JsonResponse({"status": "ignored — no reference"})

    try:
        payment = Payment.objects.select_related(
            'booking_event', 'booking_payment',
            'tenant'
        ).get(
            transaction_id=reference,
            payment_type='booking_fee',
            status='pending'  # only act on still-pending ones
        )
    except Payment.DoesNotExist:
        logger.info(f"No pending booking payment found for ref {reference}")
        return JsonResponse({"status": "not_found"})

    booking = payment.content_object
    if not isinstance(booking, Booking) or not booking.event:
        logger.warning(f"Payment {reference} has no linked Booking or Event")
        return JsonResponse({"status": "invalid content"})

    event_obj = booking.event
    booking_type = booking.booking_type
    booking_type_owner = booking_type.host_user if booking_type.booking_for == 'personal' else None

    if event == 'charge.success':
        # ── Confirm everything ───────────────────────────────────────────────
        payment.status = 'success'
        payment.payment_date = timezone.now()
        payment.owner = booking_type_owner
        payment.save()

        booking.status = 'confirmed'
        booking.payment = payment
        booking.amount_paid = booking.booking_type.price
        booking.payment_status = 'paid'
        booking.save()

        event_obj.status = 'confirmed'
        event_obj.payment = payment
        event_obj.payment_status = 'paid'
        event_obj.save()

        # Optional: update tenant/org wallet if you have such logic
        # try:
        #     tenant_balance = booking_type.tenant.tenantbalance
        #     tenant_balance.update_balance()
        # except:
        #     pass

        # Send confirmation emails
        try:
            send_booking_request_email(booking)
            send_booking_confirmed_email(booking)
            # send_booking_confirmed_email(booking)
            # send_new_booking_to_host_email(booking)
            pass
        except Exception as e:
            logger.error(f"Failed to send booking confirmation emails: {e}")

        logger.info(f"Booking confirmed via webhook: {booking.first_name} {booking.last_name} - ref {reference}")

    elif event == 'charge.failed':
        # ── Delete everything ────────────────────────────────────────────────
        try:
            # Delete in reverse order to respect constraints
            event_obj.delete()       # cascades to Booking if set up properly
            payment.delete()         # or delete first if no cascade
            logger.info(f"Booking payment failed - deleted records for ref {reference}")
        except Exception as delete_err:
            logger.error(f"Failed to delete failed booking records {reference}: {delete_err}")
            # Still return 200 — Paystack doesn't retry on failure here

        # Optional: send "payment failed, slot released" email
        # send_booking_payment_failed_email(booking, retry_url=...)

    else:
        # Other charge.* events (dispute, etc.) — ignore for now
        pass

    return JsonResponse({"status": "processed"})


def handle_subscription_charge(request, event: str, data: dict, reference: str, full_payload: dict) -> JsonResponse:
    """
    Handles charge.success, charge.failed and other charge-related events for subscriptions
    """
    if not reference:
        logger.warning("Webhook subscription charge event received without reference")
        return JsonResponse({"status": "ignored — no reference"})

    try:
        from django.contrib.contenttypes.models import ContentType
        from tenants.models import Subscription
        
        # Get the ContentType for Subscription
        subscription_content_type = ContentType.objects.get_for_model(Subscription)
        
        # Query payment with explicit content_type filter
        payment = Payment.objects.select_related(
            'tenant',
            'owner',
            'content_type'
        ).get(
            transaction_id=reference,
            payment_type='subscription',
            content_type=subscription_content_type
        )
        
    except Payment.DoesNotExist:
        logger.info(f"Webhook: No matching subscription payment found for ref {reference}")
        return JsonResponse({"status": "not_found"})

    # Get the subscription using the stored object_id
    try:
        subscription = Subscription.objects.get(id=payment.object_id)
    except Subscription.DoesNotExist:
        logger.error(f"Subscription with id {payment.object_id} not found for payment {reference}")
        return JsonResponse({"status": "subscription_not_found"})

    if event == 'charge.success':
        if payment.status == 'pending':
            with transaction.atomic():
                # Update payment
                payment.status = 'success'
                payment.payment_date = timezone.now()
                payment.save()

                # Mark any other pending payments for this subscription as abandoned
                other_pending = Payment.objects.filter(
                    content_type=subscription_content_type,
                    object_id=subscription.id,
                    status='pending'
                ).exclude(id=payment.id)
                
                for old_payment in other_pending:
                    old_payment.status = 'abandoned'
                    old_payment.metadata = old_payment.metadata or {}
                    old_payment.metadata['abandoned_reason'] = 'another_payment_succeeded'
                    old_payment.metadata['abandoned_at'] = timezone.now().isoformat()
                    old_payment.save()
                
                # Update subscription
                subscription.status = 'active'
                subscription.save()
                
                # Handle covered users based on subscription type
                if subscription.tenant:
                    # Get covered users based on subscription scope
                    covered_users = subscription.get_covered_users()
                    
                    # Update covered users to active
                    updated_count = covered_users.update(
                        subscription_status='active',
                        subscription_end_date=subscription.end_date,
                        subscription_plan=subscription.plan
                    )
                    
                    logger.info(f"Activated subscription for tenant {subscription.tenant.id}, updated {updated_count} users")
                elif subscription.user:
                    # Individual user subscription
                    subscription.user.subscription_status = 'active'
                    subscription.user.subscription_end_date = subscription.end_date
                    subscription.user.subscription_plan = subscription.plan
                    subscription.user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
                    
                    logger.info(f"Activated subscription for user {subscription.user.id}")

            # Send confirmation email (outside transaction)
            try:
                from documents.viewfuncs.send_mails import send_subscription_confirmation
                
                subscriber = subscription.user or subscription.tenant
                if subscriber:
                    detail_url = reverse('subscription_detail', kwargs={'pk': subscription.id})
                    from django.contrib.sites.models import Site
                    current_site = Site.objects.get_current()
                    protocol = 'https' if not settings.DEBUG else 'http'
                    detail_url = f"{protocol}://{current_site.domain}{detail_url}"
                    
                    send_subscription_confirmation(
                        subscription=subscription,
                        detail_url=detail_url,
                        user=subscription.user,
                        tenant=subscription.tenant
                    )
            except Exception as mail_err:
                logger.error(f"Failed to send subscription confirmation email for {reference}: {mail_err}")

            logger.info(f"Subscription payment SUCCESS via webhook: {subscription.id} - {subscription.plan.name}")
        
        else:
            logger.info(f"charge.success webhook received but subscription payment already processed: {reference}")

    elif event == 'charge.failed':
        if payment.status == 'pending':
            payment.status = 'failed'
            payment.save()

            # Keep subscription pending
            subscription.status = 'pending'
            subscription.save()
            
            # Ensure covered users remain inactive
            if subscription.tenant:
                covered_users = subscription.get_covered_users()
                covered_users.update(
                    subscription_status='inactive',
                    subscription_end_date=None,
                    subscription_plan=None
                )
                logger.info(f"Updated {covered_users.count()} users to inactive after failed payment")

            logger.info(f"Subscription payment FAILED via webhook: {subscription.id} - ref {reference}")

            # Prepare retry URL
            retry_path = reverse('subscription_payment_breakdown', kwargs={'subscription_id': subscription.id})
            retry_url = request.build_absolute_uri(retry_path)

            try:
                from documents.viewfuncs.send_mails import send_subscription_payment_failed
                
                send_subscription_payment_failed(
                    subscription=subscription,
                    retry_url=retry_url,
                    user=subscription.user,
                    tenant=subscription.tenant
                )
            except Exception as mail_err:
                logger.error(f"Failed to send subscription payment failed email for {reference}: {mail_err}")

    return JsonResponse({"status": "processed"})

def handle_successful_subscription_payment(payment):
    """Helper function to handle successful subscription payment"""
    try:
        # Get the subscription from the content_object
        subscription = payment.content_object
        
        if not isinstance(subscription, Subscription):
            logger.error(f"Payment {payment.id} content_object is not a Subscription")
            return
        
        # Update subscription
        subscription.status = 'active'
        subscription.save()

        # Handle covered users based on subscription type
        if subscription.tenant:
            # Get covered users based on subscription scope
            covered_users = subscription.get_covered_users()
            
            # Update covered users to active
            updated_count = covered_users.update(
                subscription_status='active',
                subscription_end_date=subscription.end_date,
                subscription_plan=subscription.plan
            )
            
            logger.info(f"Activated subscription for tenant {subscription.tenant.id}, updated {updated_count} users")
        elif subscription.user:
            # Individual user subscription
            subscription.user.subscription_status = 'active'
            subscription.user.subscription_end_date = subscription.end_date
            subscription.user.subscription_plan = subscription.plan
            subscription.user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
            
            logger.info(f"Activated subscription for user {subscription.user.id}")
        
        # Send confirmation email (implement your email function)
        try:
            from documents.viewfuncs.send_mails import send_subscription_confirmation
            subscriber = subscription.user or subscription.tenant
            if subscriber:
                send_subscription_confirmation(
                    subscription=subscription,
                    user=subscription.user,
                    tenant=subscription.tenant
                )
        except Exception as mail_err:
            logger.error(f"Failed to send subscription confirmation email: {mail_err}")
        
        logger.info(f"Subscription {subscription.id} activated via payment {payment.id}")
        
    except Exception as e:
        logger.exception(f"Error handling successful subscription payment: {e}")


def handle_failed_subscription_payment(payment):
    """Helper function to handle failed subscription payment"""
    try:
        # Get the subscription from the content_object
        subscription = payment.content_object
        
        if not isinstance(subscription, Subscription):
            return
        
        # Keep subscription as pending, don't activate
        subscription.status = 'pending'
        subscription.save()
        
        # Ensure covered users remain inactive
        if subscription.tenant:
            covered_users = subscription.get_covered_users()
            covered_users.update(
                subscription_status='inactive',
                subscription_end_date=None,
                subscription_plan=None
            )
            logger.info(f"Updated {covered_users.count()} users to inactive after failed payment")
        elif subscription.user:
            subscription.user.subscription_status = 'inactive'
            subscription.user.subscription_end_date = None
            subscription.user.subscription_plan = None
            subscription.user.save(update_fields=['subscription_status', 'subscription_end_date', 'subscription_plan'])
        
        # Send failure notification email
        try:
            from documents.viewfuncs.send_mails import send_subscription_payment_failed
            subscriber = subscription.user or subscription.tenant
            if subscriber:
                retry_url = reverse('subscription_payment_breakdown', kwargs={'subscription_id': subscription.id})
                
                # Build absolute URL
                from django.contrib.sites.models import Site
                current_site = Site.objects.get_current()
                protocol = 'https' if not settings.DEBUG else 'http'
                retry_url = f"{protocol}://{current_site.domain}{retry_url}"
                
                send_subscription_payment_failed(
                    subscription=subscription,
                    retry_url=retry_url,
                    user=subscription.user,
                    tenant=subscription.tenant
                )
        except Exception as mail_err:
            logger.error(f"Failed to send subscription payment failed email: {mail_err}")
        
        logger.info(f"Subscription payment failed for {subscription.id}")
        
    except Exception as e:
        logger.exception(f"Error handling failed subscription payment: {e}")

def handle_remittance_transfer(request, event: str, data: dict, full_payload: dict) -> JsonResponse:
    """
    Handles Paystack transfer.* events (outgoing money / remittance):
    - transfer.success
    - transfer.failed
    - transfer.reversed
    """
    transfer_code = data.get('transfer_code')
    reference     = data.get('reference')       # often the bank reference / transaction ref
    reason        = data.get('reason', 'Unknown reason')

    print(f"Transfer code: {transfer_code}")
    print(f"Reference: {reference}")
    print(f"Reason: {reason}")

    if not transfer_code:
        logger.warning("Transfer webhook received without transfer_code")
        return JsonResponse({"status": "ignored — no transfer_code"})

    try:
        remittance = Remittance.objects.get(paystack_transfer_code=transfer_code)
    except Remittance.DoesNotExist:
        logger.warning(f"Remittance not found for transfer_code: {transfer_code}")
        return JsonResponse({"status": "not_found"})

    # Prepare content type once (used for related Payment lookup)
    content_type = ContentType.objects.get_for_model(Remittance)

    if event == 'transfer.success':
        if remittance.status != 'completed':
            # Mark remittance as completed
            remittance.mark_as_completed(
                bank_reference=reference,
                user=remittance.updated_by or CustomUser.objects.filter(is_superuser=True).first()
            )

            # Update related outgoing Payment record (if exists)
            try:
                payment = Payment.objects.get(
                    remittance=remittance,
                    direction='outgoing',
                    payment_type='remittance',
                    content_type=content_type,
                    object_id=remittance.id
                )
                payment.status = 'success'
                payment.payment_date = timezone.now()
                payment.remittance_status = 'remitted'
                payment.remitted_at = timezone.now()
                payment.save()
            except Payment.DoesNotExist:
                logger.warning(f"No outgoing payment found for remittance {remittance.reference}")

            # Send success notification
            try:
                if remittance.tenant is not None:
                    send_remittance_success_email(request, remittance)
                else:
                    send_remittance_success_for_user_email(request, remittance)
                logger.info(f"Remittance {remittance.reference} completed successfully")
            except Exception as e:
                logger.error(f"Failed to send remittance success email for {remittance.reference}: {e}")

        else:
            logger.info(f"transfer.success received but remittance already completed: {remittance.reference}")

    elif event == 'transfer.failed':
        if remittance.status == 'pending' or remittance.status == 'processing':
            # Reset to pending - allows retry / manual intervention
            remittance.status = 'pending'
            remittance.paystack_response = remittance.paystack_response or {}
            remittance.paystack_response.update({
                'last_failure': reason,
                'failed_at': timezone.now().isoformat(),
                'last_event': 'transfer.failed'
            })
            remittance.save()

            # Update related Payment
            try:
                payment = Payment.objects.get(
                    remittance=remittance,
                    direction='outgoing',
                    payment_type='remittance',
                    content_type=content_type,
                    object_id=remittance.id
                )
                payment.status = 'failed'
                payment.save()
            except Payment.DoesNotExist:
                logger.warning(f"No outgoing payment found for remittance {remittance.reference}")

            # Notify (admin / user)
            try:
                if remittance.tenant is not None:
                    send_remittance_failed_email(request, remittance, reason)
                else:
                    send_remittance_for_user_failed_email(request, remittance, reason)
                logger.info(f"Remittance {remittance.reference} failed: {reason} - set to pending")
            except Exception as e:
                logger.error(f"Failed to send remittance failed email: {e}")

        else:
            logger.info(f"transfer.failed ignored (already final): {remittance.reference} - {reason}")

    elif event == 'transfer.reversed':
        if remittance.status not in ('cancelled', 'reversed'):
            remittance.status = 'cancelled'
            remittance.paystack_response = remittance.paystack_response or {}
            remittance.paystack_response['reversed_at'] = timezone.now().isoformat()
            remittance.save()

            # Update related Payment
            try:
                payment = Payment.objects.get(
                    remittance=remittance,
                    direction='outgoing',
                    payment_type='remittance',
                    content_type=content_type,
                    object_id=remittance.id
                )
                payment.status = 'cancelled'
                payment.save()
            except Payment.DoesNotExist:
                logger.warning(f"No outgoing payment found for remittance {remittance.reference}")

            logger.info(f"Remittance {remittance.reference} was reversed")

            # Optional: you could send a separate "reversed" notification here

    else:
        logger.info(f"Unhandled transfer event: {event} for transfer_code {transfer_code}")

    # return JsonResponse({"status": "processed"})
    return JsonResponse({'status': 'received'})