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
from documents.viewfuncs.send_mails import send_conf_reg_confirm, send_conf_reg_accepted, send_payment_failed_email, send_remittance_for_user_failed_email, send_remittance_success_for_user_email
from .access_urls import build_conference_access_url, build_guest_dashboard_url, build_user_activity_dashboard_url
from documents.models import Payment, CustomUser, Conference, GuestUser, Remittance
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from urllib.parse import unquote, urlencode
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


def verify_paystack_payment(reference: str):
    """
    Verify transaction by reference and update wallet balance
    Returns: success (bool), message (str)
    """
    if not reference:
        return False, "No reference provided"

    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    url = f"https://api.paystack.co/transaction/verify/{reference}"

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") and data['data']['status'] == 'success':
            payment_data = data['data']
            
            try:
                # Get payment record
                payment = Payment.objects.select_related(
                    'conference_registration',
                    'conference_registration__conference',
                    'tenant'
                ).get(transaction_id=reference)
                
                # Update payment status if it's still pending
                if payment.status == 'pending':
                    payment.status = 'success'
                    payment.payment_date = timezone.now()
                    payment.save()
                    
                    # Update conference participant
                    if hasattr(payment, 'conference_registration'):
                        participant = payment.conference_registration
                        participant.ticket_paid = True
                        participant.status = 'accepted'
                        participant.is_confirmed = True
                        participant.save()
                        
                        # Send confirmation email
                        conference = participant.conference
                        access_url = reverse(
                            "conference_access", 
                            kwargs={
                                "conference_id": conference.id, 
                                "token": participant.unique_token
                            }
                        )
                        dashboard_url = reverse("guest_dashboard")
                        
                        # Build absolute URLs
                        from django.contrib.sites.models import Site
                        current_site = Site.objects.get_current()
                        protocol = 'https' if not settings.DEBUG else 'http'
                        
                        access_url = f"{protocol}://{current_site.domain}{access_url}"
                        dashboard_url = f"{protocol}://{current_site.domain}{dashboard_url}"
                        
                        sender = CustomUser.objects.filter(is_superuser=True).first()
                        cc = [conference.organizer.email, payment.tenant.admin.email]
                        
                        send_conf_reg_accepted(
                            participant=participant,
                            access_url=access_url,
                            dashboard_url=dashboard_url,
                            sender=sender,
                            cc=cc
                        )
                    
                    # Update tenant wallet balance
                    from documents.models import TenantBalance  # Or wherever your TenantBalance model is
                    
                    tenant_balance, created = TenantBalance.objects.get_or_create(
                        tenant=payment.tenant
                    )
                    tenant_balance.update_balance()
                    
                    logger.info(f"Payment SUCCESS and wallet updated: {reference} - {payment.amount}")
                    return True, "Payment verified and wallet updated"
                else:
                    # Payment already processed
                    return True, "Payment already verified"
                    
            except Payment.DoesNotExist:
                logger.error(f"Payment not found for reference: {reference}")
                return False, "Payment record not found"
            except Exception as e:
                logger.exception(f"Error updating payment/wallet for {reference}: {e}")
                return False, f"Error processing payment: {str(e)}"
        else:
            # Payment failed or not successful
            logger.warning(f"Payment not successful: {reference}")
            
            # Update payment status if it exists
            try:
                payment = Payment.objects.get(transaction_id=reference, )
                if payment.status == 'pending':
                    payment.status = 'failed'
                    payment.save()
                    
                    # Send payment failed email if participant exists
                    if hasattr(payment, 'conference_registration'):
                        participant = payment.conference_registration
                        conference = participant.conference
                        
                        retry_url = reverse(
                            'conference_post', 
                            kwargs={'conference_id': conference.id}
                        ) + f"?retry={participant.id}"
                        
                        # Build absolute URL
                        from django.contrib.sites.models import Site
                        current_site = Site.objects.get_current()
                        protocol = 'https' if not settings.DEBUG else 'http'
                        retry_url = f"{protocol}://{current_site.domain}{retry_url}"
                        
                        sender = CustomUser.objects.filter(is_superuser=True).first()
                        cc = [conference.organizer.email] if conference.organizer else []
                        
                        send_payment_failed_email(
                            participant=participant,
                            conference=conference,
                            retry_url=retry_url,
                            sender=sender,
                            cc=cc
                        )
            except Payment.DoesNotExist:
                pass
            
            return False, "Payment not successful"
            
    except requests.exceptions.RequestException as e:
        logger.exception(f"Paystack verification request failed: {e}")
        return False, f"Verification request failed: {str(e)}"
    except Exception as e:
        logger.exception(f"Unexpected error verifying payment {reference}: {e}")
        return False, f"Unexpected error: {str(e)}"

def generic_payment_callback(request):
    """
    Single, reusable Paystack callback for ALL payment flows.
    Uses metadata.source_url for redirect → perfect UX.
    """
    status = request.GET.get('status')
    reference = request.GET.get("reference")
    # status = request.GET.get("status")

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
def paystack_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=400)

    signature = request.headers.get('x-paystack-signature')
    if not signature:
        return HttpResponse(status=400)

    computed = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(),
        request.body,
        hashlib.sha512
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        logger.warning("Invalid Paystack webhook signature")
        return HttpResponse(status=400)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event = payload.get('event')
    data = payload.get('data')
    reference = data.get('reference')

    if not reference:
        return JsonResponse({"status": "no reference"})

    try:
        payment = Payment.objects.select_related(
            'conference_registration',
            'conference_registration__conference',
            'tenant'
        ).get(
            transaction_id=reference,
            payment_type='conference_fee'
        )
    except Payment.DoesNotExist:
        logger.info(f"Webhook: No matching payment found for ref {reference}")
        return JsonResponse({"status": "not_found"})

    participant = payment.conference_registration
    if not participant:
        return JsonResponse({"status": "no participant"})

    conference = participant.conference

    if event == 'charge.success':
        if payment.status == 'pending':
            payment.status = 'success'
            payment.payment_date = timezone.now()
            payment.save()

            participant.ticket_paid = True
            participant.status = 'accepted'
            participant.is_confirmed = True
            participant.save()

            access_url = build_conference_access_url(conference, participant)
            if request.user.is_anonymous:
                guest_user, _ = GuestUser.objects.get_or_create(
                    email=participant.email,
                    defaults={"token": uuid.uuid4()}
                )
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

            send_conf_reg_accepted(
                participant=participant,
                access_url=access_url,
                dashboard_url=dashboard_url,
                sender=CustomUser.objects.filter(is_superuser=True).first(),
                cc=[conference.organizer.email, payment.tenant.admin.email]
            )

            # 🔥 UPDATE TENANT WALLET BALANCE
            try:
                from documents.models import TenantBalance
                tenant_balance, created = TenantBalance.objects.get_or_create(
                    tenant=payment.tenant
                )
                tenant_balance.update_balance()
                logger.info(f"Wallet updated for tenant {payment.tenant.name}: {payment.amount}")
            except Exception as e:
                logger.error(f"Failed to update wallet for tenant {payment.tenant.name}: {e}")

            logger.info(f"Payment SUCCESS: {participant.full_name} confirmed for {conference.title}")

    elif event in ['charge.failed', 'transfer.failed']:
        if payment.status == 'pending':
            payment.status = 'failed'
            payment.save()

            # Keep participant as pending → allows retry within 2 hours
            logger.info(f"Payment FAILED: {participant.full_name} - ref {reference}")

            # Send "payment failed" email with retry link
            retry_url = request.build_absolute_uri(
                reverse('conference_post', kwargs={'conference_id': conference.id})
            ) + f"?retry={participant.id}"

            try:
                send_payment_failed_email(
                    participant=participant,
                    conference=conference,
                    retry_url=retry_url,
                    sender=CustomUser.objects.filter(is_superuser=True).first(),
                    cc=[conference.organizer.email]
                )
            except Exception as e:
                logger.error(f"Failed to send payment failed email: {e}")

    return JsonResponse({"status": "processed"})

@csrf_exempt
def paystack_transfer_webhook(request):
    """Handle PayStack transfer webhook events"""
    if request.method != 'POST':
        return HttpResponse(status=400)
    
    # Verify signature
    signature = request.headers.get('x-paystack-signature')
    if not signature:
        return HttpResponse(status=400)
    
    computed = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(),
        request.body,
        hashlib.sha512
    ).hexdigest()
    
    if not hmac.compare_digest(computed, signature):
        logger.warning("Invalid PayStack transfer webhook signature")
        return HttpResponse(status=400)
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    
    event = payload.get('event')
    data = payload.get('data')
    
    # Handle transfer events
    if event == 'transfer.success':
        transfer_code = data.get('transfer_code')
        reference = data.get('reference')
        
        try:
            remittance = Remittance.objects.get(paystack_transfer_code=transfer_code)
            
            # Mark as completed
            remittance.mark_as_completed(
                bank_reference=reference,
                user=remittance.updated_by
            )
            
            logger.info(f"Remittance {remittance.reference} completed via webhook")
            
            # Send success email
            if remittance.tenant is not None:
                send_remittance_success_email(request, remittance)
            else:
                send_remittance_success_for_user_email(request, remittance)
            
            content_type = ContentType.objects.get_for_model(remittance)

            # Update related payment
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
                logger.warning(f"No payment found for remittance {remittance.reference}")
            
        except Remittance.DoesNotExist:
            logger.warning(f"Remittance not found for transfer code: {transfer_code}")
    
    elif event == 'transfer.failed':
        transfer_code = data.get('transfer_code')
        reason = data.get('reason', 'Unknown')
        
        try:
            remittance = Remittance.objects.get(paystack_transfer_code=transfer_code)
            
            # DO NOT DELETE - set to pending for retry
            remittance.status = 'pending'
            remittance.paystack_response = {
                'last_failure': reason,
                'failed_at': timezone.now().isoformat()
            }
            remittance.save()
            content_type = ContentType.objects.get_for_model(remittance)
            # Update related payment
            try:
                payment = Payment.objects.get(
                    remittance=remittance,
                    direction='outgoing',
                    payment_type='remittance',
                    content_type=content_type,
                    object_id = remittance.id
                )
                payment.status = 'failed'
                payment.save()
            except Payment.DoesNotExist:
                logger.warning(f"No payment found for remittance {remittance.reference}")
            
            logger.warning(f"Remittance {remittance.reference} failed: {reason}. Set to pending for retry.")
            
            # Send failure email
            if remittance.tenant is not None:
                send_remittance_failed_email(request,remittance, reason)
            else:
                send_remittance_for_user_failed_email(request,remittance, reason)
            
        except Remittance.DoesNotExist:
            logger.warning(f"Remittance not found for transfer code: {transfer_code}")
    
    elif event == 'transfer.reversed':
        transfer_code = data.get('transfer_code')
        
        try:
            remittance = Remittance.objects.get(paystack_transfer_code=transfer_code)
            remittance.status = 'cancelled'
            remittance.save()
                           
            content_type = ContentType.objects.get_for_model(remittance)

            # Update related payment
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
                logger.warning(f"No payment found for remittance {remittance.reference}")
            
            logger.info(f"Remittance {remittance.reference} reversed")
            
        except Remittance.DoesNotExist:
            logger.warning(f"Remittance not found for transfer code: {transfer_code}")
    
    return JsonResponse({'status': 'received'})