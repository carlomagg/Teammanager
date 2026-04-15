# documents/viewfuncs/invoice_views.py

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.db.models import Q, Sum
from documents.viewfuncs.helper_funcs.paystack import initialize_paystack_payment
from documents.models import Invoice, Receipt
from documents.invoice_forms import (
    InvoiceExternalSubmitForm,ReceiptStandaloneForm,InvoiceSendScheduleForm,InvoiceSendSchedule, InvoiceSendForm,
    InvoiceReceiveForm, MarkPaidForm
)

try:
    from crm.models import Product
    HAS_PRODUCT = True
except ImportError:
    HAS_PRODUCT = False


# ─── helpers ──────────────────────────────────────────────────────────────────

def _send_invoice_email(invoice, request=None):
    """
    Send invoice to counterparty using the tenant's configured email system.
    Uses the existing send_email infrastructure in the project.
    """
    try:
        # from documents.email_utils import send_tenant_email  # adjust import to project
        recipient = invoice.party_email
        if not recipient:
            return False

        subject  = f"Invoice {invoice.invoice_number} from {invoice.tenant.name}"
        track_url = request.build_absolute_uri(
            f"/invoices/track/{invoice.share_token}/") if request else \
            f"/invoices/track/{invoice.share_token}/"

        context = {
            'invoice':   invoice,
            'track_url': track_url,
        }
        # send_tenant_email(
        #     tenant=invoice.tenant,
        #     to=[recipient],
        #     subject=subject,
        #     template='invoices/email/invoice_email.html',
        #     context=context,
        # )
        invoice.sent_at = timezone.now()
        if invoice.status == 'draft':
            invoice.status = 'sent'
        invoice.save(update_fields=['sent_at', 'status'])
        return True
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            f"Invoice email failed for {invoice.invoice_number}: {exc}")
        return False


def _send_receipt_email(receipt, request=None):
    """Email the receipt PDF to both parties after payment."""
    try:
        # from documents.email_utils import send_tenant_email
        invoice   = receipt.invoice
        recipient = invoice.party_email
        if not recipient:
            return False

        subject = f"Receipt {receipt.receipt_number} — Payment Confirmed"
        context = {'receipt': receipt, 'invoice': invoice}
        # send_tenant_email(
        #     tenant=invoice.tenant,
        #     to=[recipient],
        #     subject=subject,
        #     template='invoices/email/receipt_email.html',
        #     context=context,
        # )
        return True
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            f"Receipt email failed for {receipt.receipt_number}: {exc}")
        return False


# def _generate_receipt_pdf(receipt):
#     """
#     Renders receipt_pdf_template.html to PDF and saves to receipt.pdf_file.
#     Uses WeasyPrint if available; falls back to HTML file storage.
#     """
#     from django.template.loader import render_to_string
#     html = render_to_string('invoices/receipt_pdf_template.html',
#                             {'receipt': receipt, 'invoice': receipt.invoice})
#     try:
#         from weasyprint import HTML as WP
#         import io
#         pdf_bytes = WP(string=html).write_pdf()
#         from django.core.files.base import ContentFile
#         filename = f"receipt_{receipt.receipt_number}.pdf"
#         receipt.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
#     except ImportError:
#         pass  # WeasyPrint not installed — PDF generation skipped gracefully


def _generate_receipt_pdf(receipt):
    """
    Renders receipt to PDF via WeasyPrint if GTK libraries are available.
    Silently skips on Windows or any system missing libgobject (OSError).
    """
    from django.template.loader import render_to_string
    html = render_to_string(
        'invoices/receipt_pdf_template.html',
        {'receipt': receipt, 'invoice': receipt.invoice}
    )
    try:
        from weasyprint import HTML as WP
        import io
        pdf_bytes = WP(string=html).write_pdf()
        from django.core.files.base import ContentFile
        filename = f"receipt_{receipt.receipt_number}.pdf"
        receipt.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

    except (ImportError, OSError, Exception):
        # WeasyPrint not installed OR GTK/GObject libraries missing (common on Windows).
        # Receipt record is still created — PDF can be generated later or skipped.
        pass




# ══════════════════════════════════════════════════════════════════════════════
# LIST VIEWS
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def sent_invoices_list(request):
    """All outgoing invoices for the tenant with filters."""
    tenant = request.user.tenant
    qs = Invoice.objects.filter(tenant=tenant, direction='out').select_related(
        'contact', 'created_by'
    )
    qs = _apply_invoice_filters(request, qs)

    paginator = Paginator(qs, 20)
    page      = paginator.get_page(request.GET.get('page'))

    summary = Invoice.objects.filter(tenant=tenant, direction='out').aggregate(
        total_sent=Sum('total_amount'),
        total_paid=Sum('total_amount', filter=Q(status='paid')),
        total_overdue=Sum('total_amount', filter=Q(status='overdue')),
    )

    return render(request, 'invoices/invoice_list.html', {
        'invoices':      page,
        'direction':     'out',
        'page_title':    'Sent Invoices',
        'summary':       summary,
        'status_choices': Invoice.STATUS,
        'filters': {
            'status': request.GET.get('status', ''),
            'q':      request.GET.get('q', ''),
        },
    })


@login_required
def received_invoices_list(request):
    """All incoming invoices for the tenant."""
    tenant = request.user.tenant
    qs = Invoice.objects.filter(tenant=tenant, direction='in').select_related(
        'contact', 'created_by'
    )
    qs = _apply_invoice_filters(request, qs)

    paginator = Paginator(qs, 20)
    page      = paginator.get_page(request.GET.get('page'))

    return render(request, 'invoices/invoice_list.html', {
        'invoices':      page,
        'direction':     'in',
        'page_title':    'Received Invoices',
        'status_choices': Invoice.STATUS,
        'filters': {
            'status': request.GET.get('status', ''),
            'q':      request.GET.get('q', ''),
        },
    })


def _apply_invoice_filters(request, qs):
    status = request.GET.get('status', '')
    q      = request.GET.get('q', '')
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(invoice_number__icontains=q) |
            Q(contact__name__icontains=q)  |
            Q(payee_name__icontains=q)     |
            Q(payer_name__icontains=q)
        )
    return qs.order_by('-issue_date', '-id')


@login_required
def create_send_invoice(request):
    tenant = request.user.tenant

    if request.method == 'POST':
        form = InvoiceSendForm(request.POST, request.FILES,
                               tenant=tenant, user=request.user)
        if form.is_valid():
            invoice = form.save(commit=False)  # ← don't save yet
            invoice.tenant     = tenant         # ← set tenant FIRST
            invoice.direction  = 'out'
            invoice.items      = form.cleaned_data['items']
            invoice.total_amount = form.cleaned_data['total_amount']
            invoice.created_by = request.user
            invoice.save()                      # ← now safe to save

            # Optionally generate Paystack link
            if not invoice.payment_link:
                try:
                    from documents.viewfuncs.helper_funcs import initialize_paystack_payment
                    link = initialize_paystack_payment(
                        amount=int(invoice.total_amount * 100),
                        email=invoice.party_email or request.user.email,
                        metadata={'invoice_number': invoice.invoice_number,
                                  'tenant_id': tenant.pk},
                    )
                    if link:
                        invoice.payment_link = link
                        invoice.save(update_fields=['payment_link'])
                except Exception:
                    pass

            messages.success(request, f"Invoice {invoice.invoice_number} created.")
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceSendForm(tenant=tenant, user=request.user)

    products = []
    if HAS_PRODUCT:
        products = list(Product.objects.filter(
            tenant=tenant, is_active=True
        ).values('id', 'name', 'unit_price'))

    return render(request, 'invoices/invoice_form.html', {
        'form':          form,
        'direction':     'out',
        'products_json': json.dumps(products),
        'page_title':    'Create Invoice',
    })






@login_required
@require_POST
def send_invoice_email(request, pk):
    """Sends the invoice email to the counterparty and marks status='sent'."""
    tenant  = request.user.tenant
    invoice = get_object_or_404(Invoice, pk=pk, tenant=tenant, direction='out')

    if invoice.status == 'cancelled':
        messages.error(request, "Cannot send a cancelled invoice.")
        return redirect('invoice_detail', pk=pk)

    sent = _send_invoice_email(invoice, request)
    if sent:
        messages.success(request,
            f"Invoice {invoice.invoice_number} emailed to {invoice.party_email}.")
    else:
        messages.warning(request,
            "Invoice saved, but email could not be sent. "
            "Share the tracking link manually.")
    return redirect('invoice_detail', pk=pk)


@login_required
def create_receive_invoice(request):
    tenant = request.user.tenant

    if request.method == 'POST':
        form = InvoiceReceiveForm(request.POST, request.FILES,
                                  tenant=tenant, user=request.user)
        if form.is_valid():
            invoice = form.save(commit=False)  # ← don't save yet
            invoice.tenant     = tenant         # ← set tenant FIRST
            invoice.direction  = 'in'
            invoice.items      = form.cleaned_data['items']
            invoice.total_amount = form.cleaned_data['total_amount']
            invoice.created_by = request.user
            invoice.save()                      # ← now safe to save

            messages.success(request, f"Incoming invoice {invoice.invoice_number} recorded.")
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceReceiveForm(tenant=tenant, user=request.user)

    return render(request, 'invoices/invoice_form.html', {
        'form':          form,
        'direction':     'in',
        'products_json': '[]',
        'page_title':    'Record Received Invoice',
    })


# ══════════════════════════════════════════════════════════════════════════════
# DETAIL VIEW (staff)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def invoice_detail(request, pk):
    tenant  = request.user.tenant
    invoice = get_object_or_404(Invoice, pk=pk, tenant=tenant)
    receipt = getattr(invoice, 'receipt', None)

    return render(request, 'invoices/invoice_detail.html', {
        'invoice':    invoice,
        'receipt':    receipt,
        'is_public':  False,
        'page_title': f"Invoice {invoice.invoice_number}",
    })


# ══════════════════════════════════════════════════════════════════════════════
# MARK PAID → CREATE RECEIPT
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def mark_invoice_paid(request, pk):
    """
    1. Validates the MarkPaidForm
    2. Updates invoice status → paid
    3. Creates a Receipt record
    4. Generates PDF receipt
    5. Emails receipt to both parties
    """
    tenant  = request.user.tenant
    invoice = get_object_or_404(Invoice, pk=pk, tenant=tenant)

    if invoice.status in ('paid', 'cancelled'):
        messages.error(request,
            f"Invoice is already {invoice.get_status_display().lower()}.")
        return redirect('invoice_detail', pk=pk)

    if request.method == 'POST':
        form = MarkPaidForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data

            # 1. Mark invoice paid
            invoice.status  = 'paid'
            invoice.paid_at = d['paid_at']
            invoice.save(update_fields=['status', 'paid_at', 'updated_at'])

            # 2. Create receipt
            receipt_number = Receipt.generate_receipt_number(tenant)
            receipt = Receipt.objects.create(
                invoice=invoice,
                receipt_number=receipt_number,
                amount_paid=d['amount_paid'],
                paid_at=d['paid_at'],
                notes=d.get('notes', ''),
                issued_by=request.user,
            )

            # 3. Generate PDF
            _generate_receipt_pdf(receipt)

            # 4. Send emails
            _send_receipt_email(receipt, request)

            messages.success(request,
                f"Invoice marked as paid. "
                f"Receipt {receipt.receipt_number} generated.")
            return redirect('invoice_detail', pk=pk)
    else:
        form = MarkPaidForm(initial={
            'amount_paid': invoice.total_amount,
            'paid_at':     timezone.now(),
        })

    return render(request, 'invoices/invoice_mark_paid.html', {
        'form':    form,
        'invoice': invoice,
    })


# ══════════════════════════════════════════════════════════════════════════════
# RECEIPT DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def download_receipt(request, receipt_pk):
    """Serve the receipt PDF for download."""
    tenant  = request.user.tenant
    receipt = get_object_or_404(Receipt, pk=receipt_pk,
                                invoice__tenant=tenant)
    if receipt.pdf_file:
        with open(receipt.pdf_file.path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = (
                f'attachment; filename="{receipt.receipt_number}.pdf"')
            return response
    messages.error(request, "Receipt PDF not available.")
    return redirect('invoice_detail', pk=receipt.invoice.pk)


# ══════════════════════════════════════════════════════════════════════════════
# AJAX: Product lookup for line-item autofill
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def product_lookup(request):
    """
    AJAX endpoint — returns product name + unit_price for autofill.
    Called by the line-items JS when a product is selected from select2.
    """
    if not HAS_PRODUCT:
        return JsonResponse({'found': False})

    product_id = request.GET.get('id')
    tenant     = request.user.tenant
    try:
        product = Product.objects.get(pk=product_id, tenant=tenant, is_active=True)
        return JsonResponse({
            'found':      True,
            'name':       product.name,
            'unit_price': float(product.unit_price),
        })
    except Product.DoesNotExist:
        return JsonResponse({'found': False})
    

# documents/viewfuncs/invoice_views.py — add these views

# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE RECEIPT (created from scratch, no invoice)
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def receipt_create_standalone(request):
    """Create a receipt without a linked invoice."""
    tenant = request.user.tenant

    # Pull saved bank accounts to populate the dropdown in invoice_form
    try:
        from documents.models import BankAccount
        saved_accounts = BankAccount.objects.filter(tenant=tenant)
    except Exception:
        saved_accounts = []

    if request.method == 'POST':
        form = ReceiptStandaloneForm(
            request.POST, request.FILES,
            tenant=tenant, user=request.user,
        )
        if form.is_valid():
            receipt = form.save(commit=False)
            receipt.tenant    = tenant
            receipt.issued_by = request.user
            receipt.receipt_number = Receipt.generate_receipt_number(tenant)
            receipt.save()

            _generate_receipt_pdf(receipt)

            messages.success(request,
                f"Receipt {receipt.receipt_number} created.")
            return redirect('receipt_detail', pk=receipt.pk)
    else:
        form = ReceiptStandaloneForm(tenant=tenant, user=request.user)

    return render(request, 'invoices/receipt_standalone.html', {
        'form':           form,
        'saved_accounts': saved_accounts,
    })


@login_required
def receipt_detail(request, pk):
    """View a single receipt."""
    tenant  = request.user.tenant
    receipt = get_object_or_404(Receipt, pk=pk, tenant=tenant)
    return render(request, 'invoices/receipt_detail.html', {
        'receipt': receipt,
    })




def _save_send_schedule(invoice, request):
    """
    Parse schedule fields from POST and create/update InvoiceSendSchedule.
    Called after the invoice is saved.
    """
    POST       = request.POST
    freq       = POST.get('schedule_freq', 'once')
    send_now   = bool(POST.get('send_now'))
    send_date  = POST.get('send_date') or None
    send_time  = POST.get('send_time') or POST.get(f'send_time_{freq}') or None
    interval   = int(POST.get(f'interval_{freq}', 1) or 1)

    import json as _json
    days_of_week  = []
    days_of_month = []
    try:
        days_of_week  = _json.loads(POST.get('days_of_week',  '[]') or '[]')
        days_of_month = _json.loads(POST.get('days_of_month', '[]') or '[]')
    except (ValueError, TypeError):
        pass

    # Yearly: parse the date field into month_day + month_month
    month_day   = None
    month_month = None
    if freq == 'yearly':
        yearly_date = POST.get('yearly_date', '')
        if yearly_date:
            try:
                from datetime import date as _date
                parts = yearly_date.split('-')
                if len(parts) == 3:
                    month_month = int(parts[1])
                    month_day   = int(parts[2])
            except (ValueError, IndexError):
                pass

    InvoiceSendSchedule.objects.update_or_create(
        invoice=invoice,
        defaults={
            'frequency':     freq,
            'send_now':      send_now,
            'send_date':     send_date or None,
            'send_time':     send_time or None,
            'interval':      interval,
            'days_of_week':  days_of_week,
            'days_of_month': days_of_month,
            'month_day':     month_day,
            'month_month':   month_month,
            'is_active':     True,
        },
    )

    # If send_now → trigger email immediately
    if send_now and freq == 'once':
        _send_invoice_email(invoice, request)


# ══════════════════════════════════════════════════════════════════════════════
# create_send_invoice view — 
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def create_send_invoice(request):
    tenant = request.user.tenant

    try:
        from documents.models import BankAccount
        saved_accounts = BankAccount.objects.filter(tenant=tenant)
    except Exception:
        saved_accounts = []

    sched_form = InvoiceSendScheduleForm()
    month_days = list(range(1, 32))

    if request.method == 'POST':
        form = InvoiceSendForm(
            request.POST, request.FILES,
            tenant=tenant, user=request.user,
        )
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.tenant      = tenant
            invoice.direction   = 'out'
            invoice.items       = form.cleaned_data['items']
            invoice.total_amount = form.cleaned_data['total_amount']
            invoice.created_by  = request.user
            invoice.save()

            # Save send schedule
            _save_send_schedule(invoice, request)

            # Optionally generate Paystack link
            if not invoice.payment_link:
                try:
                    from documents.viewfuncs.helper_funcs import initialize_paystack_payment
                    link = initialize_paystack_payment(
                        amount=int(invoice.total_amount * 100),
                        email=invoice.party_email or request.user.email,
                        metadata={'invoice_number': invoice.invoice_number,
                                  'tenant_id': tenant.pk},
                    )
                    if link:
                        invoice.payment_link = link
                        invoice.save(update_fields=['payment_link'])
                except Exception:
                    pass

            messages.success(request, f"Invoice {invoice.invoice_number} created.")
            return redirect('invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceSendForm(tenant=tenant, user=request.user)

    products = []
    if HAS_PRODUCT:
        products = list(Product.objects.filter(
            tenant=tenant, is_active=True
        ).values('id', 'name', 'unit_price'))
        for prod in products:
            prod['unit_price'] = float(prod['unit_price'])

    return render(request, 'invoices/invoice_form.html', {
        'form':           form,
        'direction':      'out',
        'products_json':  json.dumps(products),
        'page_title':     'Create Invoice',
        'saved_accounts': saved_accounts,
        'sched_form':     sched_form,
        'month_days':     month_days,
    })












# ══════════════════════════════════════════════════════════════════════════════
# EXTERNAL / PUBLIC INVOICE SUBMISSION 
# ══════════════════════════════════════════════════════════════════════════════

def invoice_submit_external(request, tenant_slug):
    """
    Public view — no login required.
    External vendors/suppliers submit invoices to a specific tenant.
    URL: /invoices/submit/<tenant_slug>/
    """
    from tenants.models import Tenant
    tenant = get_object_or_404(Tenant, slug=tenant_slug)

    # Pull tenant's saved bank accounts for the account toggle
    try:
        from documents.models import BankAccount
        saved_accounts = BankAccount.objects.filter(tenant=tenant)
    except Exception:
        saved_accounts = []

    if request.method == 'POST':
        form = InvoiceExternalSubmitForm(request.POST, request.FILES, tenant=tenant)
        if form.is_valid():
            invoice = form.save(commit=False)
            invoice.tenant     = tenant
            invoice.direction  = 'in'          # received by tenant
            invoice.status     = 'draft'
            invoice.items      = form.cleaned_data['items']
            invoice.total_amount = form.cleaned_data['total_amount']
            # created_by is null for external submissions — guest fields carry contact
            invoice.save()

            # Email the external submitter their tracking link
            _send_external_submission_email(invoice, request)

            # Notify tenant staff that a new invoice arrived
            _notify_tenant_new_invoice(invoice, request)

            return redirect('invoice_external_submitted', token=invoice.share_token)
    else:
        form = InvoiceExternalSubmitForm(tenant=tenant)

    return render(request, 'invoices/submit.html', {
        'form':           form,
        'tenant':         tenant,
        'saved_accounts': saved_accounts,
    })


def invoice_external_submitted(request, token):
    """
    Confirmation page for external submitter.
    Shows invoice summary + tracking link.
    """
    invoice = get_object_or_404(Invoice, share_token=token, direction='in')
    return render(request, 'invoices/submitted.html', {
        'invoice':    invoice,
        'track_url':  request.build_absolute_uri(
                          f"/invoices/track/{invoice.share_token}/"),
    })


def invoice_external_track(request, token):
    """
    Public tracking page — external submitter checks invoice status.
    No login required; accessible via share_token UUID link.
    Marks invoice as 'viewed' on first staff access (separate flag).
    """
    invoice = get_object_or_404(Invoice, share_token=token)

    # If the invoice hasn't been viewed by staff yet, record first public view
    if not invoice.viewed_at and invoice.status == 'draft':
        invoice.viewed_at = timezone.now()
        invoice.save(update_fields=['viewed_at'])

    receipt = getattr(invoice, 'receipt', None)

    return render(request, 'invoices/track.html', {
        'invoice': invoice,
        'receipt': receipt,
    })


# ── Email helpers ──────────────────────────────────────────────────────────────

def _send_external_submission_email(invoice, request):
    """Email the submitter confirming receipt + their tracking link."""
    recipient = invoice.payer_email or invoice.party_email
    if not recipient:
        return
    try:
        # from documents.email_utils import send_tenant_email
        track_url = request.build_absolute_uri(
            f"/invoices/track/{invoice.share_token}/")
        # send_tenant_email(
        #     tenant=invoice.tenant,
        #     to=[recipient],
        #     subject=f"Invoice Received — {invoice.invoice_number}",
        #     template='invoices/email/external_submission_email.html',
        #     context={'invoice': invoice, 'track_url': track_url},
        # )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"External submission email failed: {e}")


def _notify_tenant_new_invoice(invoice, request):
    """Notify tenant admin/finance staff that a new external invoice arrived."""
    try:
        from documents.models import CustomUser, Notification, UserNotification
        from django.contrib.contenttypes.models import ContentType
        
        # Notify all staff with admin/finance role — adjust to your role names
        recipients = list(
            CustomUser.objects.filter(
                tenant=invoice.tenant,
                is_active=True,
                roles__name__in=['Admin', 'Finance', 'HR'],
            ).distinct()
        )
        if not recipients:
            # Fall back to all staff
            recipients = list(
                CustomUser.objects.filter(
                    tenant=invoice.tenant, is_active=True, is_staff=True,
                )
            )
        if not recipients:
            return

        # Create bell notification
        notification = Notification.objects.create(
            tenant=invoice.tenant,
            title=f"New Invoice from {invoice.party_display}",
            message=f"Invoice {invoice.invoice_number} for {invoice.currency} {invoice.total_amount:,.2f} has been submitted",
            type=Notification.NotificationType.ALERT,
            content_type=ContentType.objects.get_for_model(invoice),
            object_id=invoice.id,
            link=f'/invoices/{invoice.pk}/'
        )
        
        # Create user notifications for each recipient
        for user in recipients:
            UserNotification.objects.create(
                tenant=invoice.tenant,
                user=user,
                notification=notification
            )

        # Send email notifications
        detail_url = request.build_absolute_uri(f"/invoices/{invoice.pk}/")
        recipient_emails = [u.email for u in recipients if u.email]
        
        if recipient_emails:
            from django.core.mail import send_mail
            from django.conf import settings
            
            send_mail(
                subject=f"New Invoice Received from {invoice.party_display} — {invoice.invoice_number}",
                message=f"A new invoice has been submitted.\n\nInvoice Number: {invoice.invoice_number}\nFrom: {invoice.party_display}\nAmount: {invoice.currency} {invoice.total_amount:,.2f}\n\nView details: {detail_url}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_emails,
                fail_silently=True,
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Tenant invoice notification failed: {e}")


# ── Staff: review + accept / reject external invoice ──────────────────────────

@login_required
def invoice_review(request, pk):
    """
    Staff reviews an externally submitted incoming invoice.
    Actions: accept (moves to 'sent' status) or reject (cancels it).
    """
    tenant  = request.user.tenant
    invoice = get_object_or_404(Invoice, pk=pk, tenant=tenant, direction='in')

    # Pull tenant's saved bank accounts for the account toggle
    try:
        from documents.models import BankAccount
        saved_accounts = BankAccount.objects.filter(tenant=tenant)
    except Exception:
        saved_accounts = []

    if request.method == 'POST':
        action = request.POST.get('action')
        note   = request.POST.get('note', '').strip()

        if action == 'accept':
            invoice.status = 'sent'       # accepted / acknowledged
            invoice.save(update_fields=['status', 'updated_at'])
            _notify_submitter_status(invoice, 'accepted', note, request)
            messages.success(request,
                f"Invoice {invoice.invoice_number} accepted.")

        elif action == 'reject':
            invoice.status = 'cancelled'
            invoice.save(update_fields=['status', 'updated_at'])
            _notify_submitter_status(invoice, 'rejected', note, request)
            messages.warning(request,
                f"Invoice {invoice.invoice_number} rejected.")

        return redirect('invoice_detail', pk=pk)

    return render(request, 'invoices/invoice_review.html', {
        'invoice': invoice,
    })


def _notify_submitter_status(invoice, action, note, request):
    """Email the external submitter when their invoice is accepted/rejected."""
    recipient = invoice.payer_email or invoice.party_email
    if not recipient:
        return
    try:
        # from documents.email_utils import send_tenant_email
        track_url = request.build_absolute_uri(
            f"/invoices/track/{invoice.share_token}/")
        # send_tenant_email(
        #     tenant=invoice.tenant,
        #     to=[recipient],
        #     subject=f"Invoice {invoice.invoice_number} — "
        #             f"{'Accepted' if action == 'accepted' else 'Rejected'}",
        #     template='invoices/email/invoice_status_update.html',
        #     context={
        #         'invoice':   invoice,
        #         'action':    action,
        #         'note':      note,
        #         'track_url': track_url,
        #     },
        # )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Status notification failed: {e}")