from django.contrib.auth.decorators import login_required, user_passes_test
from collections import defaultdict
from documents.viewfuncs.send_mails import (
    send_bank_verification_request_email,
    send_bank_verification_request_for_user_email,
    send_bank_verification_request_for_staff_email,
)
from .rba_decorators import is_admin
from django.db.models import Sum, Q
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from decimal import Decimal, InvalidOperation
from documents.models import (
    CompanyProfile, CustomUser, TenantBalance,
    Payment, Remittance, UserProfile, StaffProfile,
)
from documents.forms import EducationHistoryForm, WorkHistoryForm, AchievementForm
from tenants.models import Tenant
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib import messages
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LOW-LEVEL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _is_tenant_admin(user):
    from .rba_decorators import is_admin as _ia
    return _ia(user)


def _is_staff_user(user):
    """Staff member: belongs to a tenant but is NOT the admin."""
    return (
        not user.is_personal and
        user.tenant is not None and
        not _is_tenant_admin(user)
    )


def _profile_has_complete_bank(profile):
    if profile is None:
        return False
    return all([
        getattr(profile, 'bank_name', None),
        getattr(profile, 'bank_account_name', None),
        getattr(profile, 'bank_account_number', None),
        getattr(profile, 'bank_code', None),
    ])


def _profile_bank_verified(profile):
    return bool(profile and getattr(profile, 'bank_verified', False))


# ─────────────────────────────────────────────────────────────────────────────
# WALLET SUMMARY BUILDER  (reusable for any owner/tenant combination)
# ─────────────────────────────────────────────────────────────────────────────

def _build_wallet_summary(wallet, payments_qs):
    """
    Given a wallet and a queryset of Payment objects, return:
      - summary dict  (totals, unremitted)
      - adjusted total (Decimal)
    """
    total_adjusted = Decimal('0.00')
    total_original = Decimal('0.00')
    total_deductions = Decimal('0.00')
    unremitted_adjusted = Decimal('0.00')

    for p in payments_qs:
        adj = wallet.calculate_adjusted_amount(p.amount)
        orig = Decimal(str(p.amount))
        total_adjusted += adj
        total_original += orig
        total_deductions += orig - adj
        if p.remittance_status == 'unremitted':
            unremitted_adjusted += adj

    return {
        'total_original': total_original,
        'total_adjusted': total_adjusted,
        'total_deductions': total_deductions,
        'total_transactions': payments_qs.count(),
        'unremitted_amount': unremitted_adjusted,
    }


def _build_conference_summary(wallet, conf_payments):
    """Group conference payments by conference, return sorted list."""
    earnings = defaultdict(Decimal)
    titles = {}

    for p in conf_payments.select_related('conference_registration__conference'):
        adj = wallet.calculate_adjusted_amount(p.amount)
        try:
            reg = p.conference_registration
            if reg and reg.id:
                conf = reg.conference
                titles.setdefault(conf.id, conf.title)
                earnings[conf.id] += adj
            else:
                earnings['unlinked'] += adj
        except Exception as e:
            logger.error(f"Conference payment {p.id} error: {e}")
            earnings['error'] += adj

    titles.setdefault('unlinked', 'Payments from deleted / unlinked registrations')

    return [
        {'conference_id': cid, 'title': titles.get(cid, 'Unknown'), 'total_earned': amt}
        for cid, amt in sorted(earnings.items(), key=lambda x: x[1], reverse=True)
    ]


def _build_booking_summary(wallet, book_payments):
    """Group booking payments by booking type, return sorted list."""
    earnings = defaultdict(Decimal)
    titles = {}

    for p in book_payments.select_related('booking_event__booking_type', 'booking_payment__booking_type'):
        adj = wallet.calculate_adjusted_amount(p.amount)
        try:
            bt = None
            be = getattr(p, 'booking_event', None)
            bp = getattr(p, 'booking_payment', None)
            if be and be.booking_type_id:
                bt = be.booking_type
            elif bp and bp.booking_type_id:
                bt = bp.booking_type

            if bt:
                titles.setdefault(bt.id, bt.name)
                earnings[bt.id] += adj
            else:
                earnings['unlinked'] += adj
        except Exception as e:
            logger.error(f"Booking payment {p.id} error: {e}")
            earnings['error'] += adj

    titles.setdefault('unlinked', 'Payments from deleted / unlinked bookings')

    return [
        {'booking_type_id': bid, 'title': titles.get(bid, 'Unknown'), 'total_earned': amt}
        for bid, amt in sorted(earnings.items(), key=lambda x: x[1], reverse=True)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# WALLET DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def tenant_wallet_dashboard(request):
    """
    One-page wallet dashboard with up to TWO sections:

    Case A – Personal user (is_personal=True, tenant=None)
        Single section: conference_fee + booking_fee, owner-keyed wallet.

    Case B – Tenant admin (is_admin, tenant set)
        TWO sections:
          • Org wallet   → TenantBalance(tenant=...)  ← conference + org bookings
          • Personal wallet → TenantBalance(owner=...) ← personal conference + bookings
        Both shown on the same page.

    Case C – Staff member (has tenant, not admin)
        Single section: booking_fee only, owner-keyed wallet.
    """
    user = request.effective_user
    tenant = getattr(request, 'effective_tenant', None)

    is_admin_user = _is_tenant_admin(user)
    is_staff = _is_staff_user(user)

    if not (is_admin_user or user.is_personal or is_staff):
        messages.error(request, "You do not have permission to view the wallet.")
        return redirect('home')

    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    # ── ORG WALLET (tenant admins only) ──────────────────────────────────────
    org_ctx = None
    if is_admin_user and tenant:
        org_wallet, _ = TenantBalance.objects.get_or_create(tenant=tenant)
        org_wallet.update_balance()

        org_conf = Payment.objects.filter(
            tenant=tenant, payment_type='conference_fee',
            direction='incoming', status='success',
        )
        org_book = Payment.objects.filter(
            tenant=tenant, payment_type='booking_fee',
            direction='incoming', status='success', owner__isnull=True,
        )
        if from_date:
            org_conf = org_conf.filter(payment_date__date__gte=from_date)
            org_book = org_book.filter(payment_date__date__gte=from_date)
        if to_date:
            org_conf = org_conf.filter(payment_date__date__lte=to_date)
            org_book = org_book.filter(payment_date__date__lte=to_date)

        all_org_payments = Payment.objects.filter(
            id__in=list(org_conf.values_list('id', flat=True)) +
                   list(org_book.values_list('id', flat=True))
        )

        org_profile = None
        org_has_bank = org_bank_verified = False
        try:
            org_profile = tenant.company_profile
            org_has_bank = _profile_has_complete_bank(org_profile)
            org_bank_verified = _profile_bank_verified(org_profile)
        except CompanyProfile.DoesNotExist:
            pass

        org_recent_remittances = Remittance.objects.filter(
            tenant=tenant, status='completed'
        ).order_by('-completion_date')[:10]

        org_ctx = {
            'wallet': org_wallet,
            'summary': _build_wallet_summary(org_wallet, all_org_payments),
            'conference_summary': _build_conference_summary(org_wallet, org_conf),
            'booking_summary': _build_booking_summary(org_wallet, org_book),
            'recent_remittances': org_recent_remittances,
            'profile': org_profile,
            'has_bank_details': org_has_bank,
            'bank_verified': org_bank_verified,
            'profile_type': 'company',
            'label': 'Organisation',
            'page_obj': Paginator(
                all_org_payments.order_by('-payment_date'), 20
            ).get_page(request.GET.get('org_page')),
        }

    # ── PERSONAL WALLET (admins + personal users; NOT staff) ─────────────────
    #
    # Tenant admin personal earnings:
    #   • Payment type : booking_fee ONLY (from personal booking types)
    #   • Wallet key   : owner=user  (separate TenantBalance row from org)
    #   • Bank details : StaffProfile  (admin has one as they belong to the tenant)
    #
    # Pure personal user earnings:
    #   • Payment types: conference_fee + booking_fee
    #   • Wallet key   : owner=user
    #   • Bank details : UserProfile
    personal_ctx = None
    if is_admin_user or user.is_personal:
        pers_wallet, _ = TenantBalance.objects.get_or_create(owner=user)
        pers_wallet.update_balance()

        if is_admin_user:
            # Admin personal wallet: booking fees only
            pers_book = Payment.objects.filter(
                owner=user, payment_type='booking_fee',
                direction='incoming', status='success', tenant=tenant
            )
            if from_date:
                pers_book = pers_book.filter(payment_date__date__gte=from_date)
            if to_date:
                pers_book = pers_book.filter(payment_date__date__lte=to_date)
            all_pers_payments = pers_book
            pers_conf = Payment.objects.none()   # no conference earnings for admin personal

            # Bank details from StaffProfile
            pers_profile = pers_has_bank = pers_bank_verified = None
            try:
                pers_profile = user.staff_profile
                pers_has_bank = _profile_has_complete_bank(pers_profile)
                pers_bank_verified = _profile_bank_verified(pers_profile)
            except StaffProfile.DoesNotExist:
                pers_has_bank = pers_bank_verified = False
            pers_profile_type = 'staff'

        else:
            # Pure personal user: conference + booking fees
            pers_conf = Payment.objects.filter(
                owner=user, payment_type='conference_fee',
                direction='incoming', status='success', tenant=None
            )
            pers_book = Payment.objects.filter(
                owner=user, payment_type='booking_fee',
                direction='incoming', status='success', tenant=None
            )
            if from_date:
                pers_conf = pers_conf.filter(payment_date__date__gte=from_date)
                pers_book = pers_book.filter(payment_date__date__gte=from_date)
            if to_date:
                pers_conf = pers_conf.filter(payment_date__date__lte=to_date)
                pers_book = pers_book.filter(payment_date__date__lte=to_date)
            all_pers_payments = Payment.objects.filter(
                id__in=list(pers_conf.values_list('id', flat=True)) +
                       list(pers_book.values_list('id', flat=True))
            )

            # Bank details from UserProfile
            pers_profile = pers_has_bank = pers_bank_verified = None
            try:
                pers_profile = user.user_profile
                pers_has_bank = _profile_has_complete_bank(pers_profile)
                pers_bank_verified = _profile_bank_verified(pers_profile)
            except UserProfile.DoesNotExist:
                pers_has_bank = pers_bank_verified = False
            pers_profile_type = 'user'

        pers_recent_remittances = Remittance.objects.filter(
            owner=user, status='completed'
        ).order_by('-completion_date')[:10]

        personal_ctx = {
            'wallet': pers_wallet,
            'summary': _build_wallet_summary(pers_wallet, all_pers_payments),
            'conference_summary': _build_conference_summary(pers_wallet, pers_conf),
            'booking_summary': _build_booking_summary(pers_wallet, pers_book),
            'recent_remittances': pers_recent_remittances,
            'profile': pers_profile,
            'has_bank_details': pers_has_bank,
            'bank_verified': pers_bank_verified,
            'profile_type': pers_profile_type,
            'label': 'Personal' if is_admin_user else 'My Earnings',
            'page_obj': Paginator(
                all_pers_payments.order_by('-payment_date'), 20
            ).get_page(request.GET.get('pers_page')),
        }

    # ── STAFF WALLET (booking fees only, owner-keyed) ────────────────────────
    staff_ctx = None
    if is_staff:
        staff_wallet, _ = TenantBalance.objects.get_or_create(owner=user)
        staff_wallet.update_balance()

        staff_book = Payment.objects.filter(
            owner=user, payment_type='booking_fee',
            direction='incoming', status='success', tenant=None
        )
        if from_date:
            staff_book = staff_book.filter(payment_date__date__gte=from_date)
        if to_date:
            staff_book = staff_book.filter(payment_date__date__lte=to_date)

        staff_profile = staff_has_bank = staff_bank_verified = None
        try:
            staff_profile = user.staff_profile
            staff_has_bank = _profile_has_complete_bank(staff_profile)
            staff_bank_verified = _profile_bank_verified(staff_profile)
        except StaffProfile.DoesNotExist:
            staff_has_bank = staff_bank_verified = False

        staff_recent_remittances = Remittance.objects.filter(
            owner=user, status='completed'
        ).order_by('-completion_date')[:10]

        staff_ctx = {
            'wallet': staff_wallet,
            'summary': _build_wallet_summary(staff_wallet, staff_book),
            'conference_summary': [],
            'booking_summary': _build_booking_summary(staff_wallet, staff_book),
            'recent_remittances': staff_recent_remittances,
            'profile': staff_profile,
            'has_bank_details': staff_has_bank,
            'bank_verified': staff_bank_verified,
            'profile_type': 'staff',
            'label': 'My Earnings',
            'page_obj': Paginator(
                staff_book.order_by('-payment_date'), 20
            ).get_page(request.GET.get('page')),
        }

    context = {
        'org_ctx': org_ctx,
        'personal_ctx': personal_ctx,
        'staff_ctx': staff_ctx,
        'is_admin_user': is_admin_user,
        'is_staff': is_staff,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'wallet/tenant_dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# TRANSACTION DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def tenant_transaction_detail(request, payment_id):
    user = request.effective_user
    tenant = getattr(request, 'effective_tenant', None)
    is_admin_user = _is_tenant_admin(user)
    is_staff = _is_staff_user(user)

    if not (is_admin_user or user.is_personal or is_staff):
        messages.error(request, "Permission denied.")
        return redirect('home')

    allowed_types = ['conference_fee', 'booking_fee']

    # Try tenant-owned payment first (org earnings), then owner-keyed (personal/staff)
    payment = None
    wallet = None

    if is_admin_user and tenant:
        payment = Payment.objects.filter(
            id=payment_id, tenant=tenant,
            payment_type__in=allowed_types, direction='incoming',
        ).first()
        if payment:
            wallet, _ = TenantBalance.objects.get_or_create(tenant=tenant)

    if payment is None:
        payment = get_object_or_404(
            Payment, id=payment_id, owner=user,
            payment_type__in=allowed_types, direction='incoming',
        )
        wallet, _ = TenantBalance.objects.get_or_create(owner=user)

    amount = Decimal(str(payment.amount))

    if payment.payment_type == 'conference_fee':
        conference = payment.conference_registration.conference
        base_price = Decimal(str(conference.get_current_price(
            registration_time=payment.conference_registration.registered_at
        )))
        platform_fee = Decimal('0.00')
        if conference.platform_fee_percent:
            platform_fee += base_price * Decimal(str(conference.platform_fee_percent)) / Decimal('100')
        if conference.platform_fee_fixed:
            platform_fee += Decimal(str(conference.platform_fee_fixed))
        tenant_share = amount - platform_fee
        fixed_ded = Decimal('100.00')
        after_fixed = tenant_share - fixed_ded
        if after_fixed <= 0:
            final_amount = one_eleventh = Decimal('0.00')
        else:
            one_eleventh = after_fixed / Decimal('11')
            final_amount = after_fixed - one_eleventh
        total_ded = platform_fee + fixed_ded + one_eleventh
        breakdown = {
            'original_payment': amount,
            'platform_fee_percent': conference.platform_fee_percent or 0,
            'platform_fee_fixed': conference.platform_fee_fixed or 0,
            'platform_fee_amount': platform_fee,
            'tenant_share_before_deductions': tenant_share,
            'fixed_deduction': fixed_ded,
            'amount_after_fixed': max(after_fixed, Decimal('0.00')),
            'one_eleventh_deduction': one_eleventh,
            'final_amount': final_amount,
            'total_deduction': total_ded,
            'deduction_percentage': (total_ded / amount * 100) if amount else Decimal('0'),
        }
        context = {
            'payment': payment, 'wallet': wallet,
            'participant': payment.conference_registration,
            'conference': conference,
            'breakdown': breakdown,
            'payment_category': 'conference',
        }
    else:
        adjusted = wallet.calculate_adjusted_amount(amount)
        fixed_ded = Decimal('100.00')
        after_fixed = amount - fixed_ded
        one_eleventh = (after_fixed / Decimal('11')) if after_fixed > 0 else Decimal('0')
        total_ded = fixed_ded + one_eleventh
        be = getattr(payment, 'booking_event', None)
        bp = getattr(payment, 'booking_payment', None)
        booking_type = None
        if be and be.booking_type_id:
            booking_type = be.booking_type
        elif bp and bp.booking_type_id:
            booking_type = bp.booking_type
        breakdown = {
            'original_payment': amount,
            'fixed_deduction': fixed_ded,
            'amount_after_fixed': max(after_fixed, Decimal('0.00')),
            'one_eleventh_deduction': one_eleventh,
            'final_amount': adjusted,
            'total_deduction': total_ded,
            'deduction_percentage': (total_ded / amount * 100) if amount else Decimal('0'),
        }
        context = {
            'payment': payment, 'wallet': wallet,
            'booking_type': booking_type,
            'booking_event': be,
            'breakdown': breakdown,
            'payment_category': 'booking',
        }

    return render(request, 'wallet/transaction_detail.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN REMITTANCE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(lambda u: u.is_superuser)
def admin_remittance_dashboard(request):
    from itertools import chain

    tenant_search = request.GET.get('tenant_search', '')
    remittance_search = request.GET.get('remittance_search', '')
    remittance_date = request.GET.get('remittance_date', '')
    recent_search = request.GET.get('recent_search', '')
    recent_date = request.GET.get('recent_date', '')
    bank_confirm_search = request.GET.get('bank_confirm_search', '')

    all_balances = TenantBalance.objects.filter(available_balance__gt=0)
    all_pending = Remittance.objects.filter(status__in=['pending', 'processing', 'failed'])

    stats = {
        'total_outstanding': sum(b.available_balance for b in all_balances),
        'total_tenants_with_balance': all_balances.count(),
        'pending_remittance_count': all_pending.count(),
    }

    # Wallets with balance — tenant-keyed (org) and owner-keyed (personal/staff/admin-personal)
    tenants_with_balance = TenantBalance.objects.filter(
        available_balance__gt=0, tenant__isnull=False
    ).select_related('tenant', 'tenant__admin')

    users_with_balance = TenantBalance.objects.filter(
        available_balance__gt=0, owner__isnull=False
    ).select_related('owner', 'owner__staff_profile', 'owner__user_profile')

    if tenant_search:
        tenants_with_balance = tenants_with_balance.filter(
            Q(tenant__name__icontains=tenant_search) |
            Q(tenant__admin__email__icontains=tenant_search)
        )
        users_with_balance = users_with_balance.filter(
            Q(owner__email__icontains=tenant_search) |
            Q(owner__username__icontains=tenant_search) |
            Q(owner__first_name__icontains=tenant_search) |
            Q(owner__last_name__icontains=tenant_search)
        )

    combined_list = sorted(
        list(chain(tenants_with_balance, users_with_balance)),
        key=lambda x: x.last_updated, reverse=True,
    )

    # Annotate each balance entry so the template can label it correctly
    for bal in combined_list:
        if bal.tenant is not None:
            bal._display_label = f"{bal.tenant.name} (Organisation)"
            bal._wallet_type = 'org'
        elif bal.owner is not None:
            owner = bal.owner
            if _is_staff_user(owner):
                bal._display_label = f"{owner.get_full_name() or owner.username} (Staff)"
                bal._wallet_type = 'staff'
            elif _is_tenant_admin(owner):
                bal._display_label = f"{owner.get_full_name() or owner.username} (Admin – Personal)"
                bal._wallet_type = 'admin_personal'
            else:
                bal._display_label = f"{owner.get_full_name() or owner.username} (Personal)"
                bal._wallet_type = 'personal'

    tenant_page_obj = Paginator(combined_list, 10).get_page(
        request.GET.get('tenant_page', 1)
    )

    # Pending remittances — tenant-keyed (org) and owner-keyed (personal/staff)
    tenants_pending = Remittance.objects.filter(
        status__in=['pending', 'processing', 'failed'], tenant__isnull=False
    ).select_related('tenant').order_by('-created_at')

    users_pending = Remittance.objects.filter(
        status__in=['pending', 'processing', 'failed'], owner__isnull=False
    ).select_related('owner').order_by('-created_at')

    if remittance_search:
        tenants_pending = tenants_pending.filter(
            Q(reference__icontains=remittance_search) |
            Q(tenant__name__icontains=remittance_search) |
            Q(description__icontains=remittance_search)
        )
        users_pending = users_pending.filter(
            Q(reference__icontains=remittance_search) |
            Q(owner__email__icontains=remittance_search) |
            Q(description__icontains=remittance_search)
        )

    if remittance_date:
        try:
            d = datetime.strptime(remittance_date, '%Y-%m-%d').date()
            tenants_pending = tenants_pending.filter(created_at__date=d)
            users_pending = users_pending.filter(created_at__date=d)
        except ValueError:
            pass

    pending_combined = sorted(
        list(chain(tenants_pending, users_pending)),
        key=lambda x: x.created_at, reverse=True,
    )
    remittance_page_obj = Paginator(pending_combined, 15).get_page(
        request.GET.get('page')
    )

    # Pending bank confirmations
    tenant_bank_confirm = Remittance.objects.filter(
        status='pending', bank_confirmation__in=['pending', 'rejected'],
        tenant__isnull=False,
    ).select_related('tenant', 'tenant__company_profile').order_by('created_at')

    user_bank_confirm = Remittance.objects.filter(
        status='pending', bank_confirmation__in=['pending', 'rejected'],
        owner__isnull=False,
    ).select_related('owner', 'owner__user_profile', 'owner__staff_profile').order_by('created_at')

    if bank_confirm_search:
        tenant_bank_confirm = tenant_bank_confirm.filter(
            Q(reference__icontains=bank_confirm_search) |
            Q(tenant__name__icontains=bank_confirm_search) |
            Q(tenant__company_profile__bank_account_name__icontains=bank_confirm_search)
        )
        user_bank_confirm = user_bank_confirm.filter(
            Q(reference__icontains=bank_confirm_search) |
            Q(owner__email__icontains=bank_confirm_search) |
            Q(owner__user_profile__bank_account_name__icontains=bank_confirm_search) |
            Q(owner__staff_profile__bank_account_name__icontains=bank_confirm_search)
        )

    pending_bank_confirmation = list(chain(tenant_bank_confirm, user_bank_confirm))

    # Recent completed remittances
    thirty_days_ago = timezone.now() - timedelta(days=30)

    tenant_recent = Remittance.objects.filter(
        status='completed', completion_date__gte=thirty_days_ago, tenant__isnull=False
    ).select_related('tenant').order_by('-completion_date')

    user_recent = Remittance.objects.filter(
        status='completed', completion_date__gte=thirty_days_ago, owner__isnull=False
    ).select_related('owner').order_by('-completion_date')

    if recent_search:
        tenant_recent = tenant_recent.filter(
            Q(reference__icontains=recent_search) |
            Q(tenant__name__icontains=recent_search) |
            Q(bank_reference__icontains=recent_search)
        )
        user_recent = user_recent.filter(
            Q(reference__icontains=recent_search) |
            Q(owner__email__icontains=recent_search) |
            Q(bank_reference__icontains=recent_search)
        )

    if recent_date:
        try:
            d = datetime.strptime(recent_date, '%Y-%m-%d').date()
            tenant_recent = tenant_recent.filter(completion_date__date=d)
            user_recent = user_recent.filter(completion_date__date=d)
        except ValueError:
            pass

    recent_combined = sorted(
        list(chain(tenant_recent, user_recent)),
        key=lambda x: x.completion_date, reverse=True,
    )[:50]

    stats['recent_remittance_count'] = Remittance.objects.filter(
        status='completed', completion_date__gte=thirty_days_ago
    ).count()
    stats['pending_bank_confirmation_count'] = len(pending_bank_confirmation)

    context = {
        'tenant_page_obj': tenant_page_obj,
        'remittance_page_obj': remittance_page_obj,
        'pending_bank_confirmation': pending_bank_confirmation,
        'recent_remittances': recent_combined,
        'stats': stats,
        'tenant_search': tenant_search,
        'remittance_search': remittance_search,
        'remittance_date': remittance_date,
        'recent_search': recent_search,
        'recent_date': recent_date,
        'bank_confirm_search': bank_confirm_search,
        'today': timezone.now().date(),
        'thirty_days_ago': thirty_days_ago.date(),
    }
    return render(request, 'wallet/admin_remittance_dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# REMITTANCE CREATION — ORG (tenant-keyed)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_remittance(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id)
    wallet = get_object_or_404(TenantBalance, tenant=tenant)

    existing = Remittance.objects.filter(tenant=tenant, status__in=['pending', 'processing'])
    if existing.exists():
        messages.error(request,
            f"Organisation already has {existing.count()} pending remittance(s). "
            "Complete or cancel them before creating a new one."
        )
        return redirect('admin_remittance_dashboard')

    if request.method == 'POST':
        amount_str = (
            request.POST.get('amount', '0').strip()
            .replace(',', '').replace('₦', '').replace('$', '')
        )
        try:
            amount = Decimal(amount_str or '0')
        except (InvalidOperation, ValueError):
            messages.error(request, "Invalid amount format.")
            return redirect('admin_remittance_dashboard')

        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
        elif amount > wallet.available_balance:
            messages.error(request, "Amount exceeds available balance.")
        else:
            remittance = Remittance.objects.create(
                tenant=tenant,
                amount=amount,
                description=request.POST.get('description', ''),
                created_by=request.user,
                status='pending',
            )
            unremitted = Payment.objects.filter(
                tenant=tenant,
                payment_type__in=['conference_fee', 'booking_fee'],
                direction='incoming', status='success',
                remittance_status='unremitted',
            ).order_by('payment_date')
            remittance.payments.set(unremitted)

            try:
                company_profile, _ = CompanyProfile.objects.get_or_create(
                    tenant=tenant, defaults={'company_name': tenant.name}
                )
                if company_profile.email or (tenant.admin and tenant.admin.email):
                    send_bank_verification_request_email(request, company_profile)
                    messages.info(request, "Bank verification email sent.")
                else:
                    messages.warning(request, "Remittance created but no email address found.")
            except Exception as e:
                logger.error(f"Email error for {remittance.reference}: {e}")
                messages.warning(request, f"Remittance created but email failed: {e}")

            messages.success(request, f"Remittance {remittance.reference} created successfully.")
            return redirect('admin_remittance_dashboard')

    return render(request, 'wallet/create_remittance.html', {'tenant': tenant, 'wallet': wallet})


# ─────────────────────────────────────────────────────────────────────────────
# REMITTANCE CREATION — USER (owner-keyed: personal, admin-personal, staff)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_user_remittance(request, user_id):
    """
    Create a remittance for a personal user, an admin's personal wallet,
    or a staff member. All are owner-keyed. Bank details come from:
      - personal user  → UserProfile
      - admin personal → UserProfile
      - staff          → StaffProfile
    """
    owner = get_object_or_404(CustomUser, id=user_id)
    wallet = get_object_or_404(TenantBalance, owner=owner)

    existing = Remittance.objects.filter(owner=owner, status__in=['pending', 'processing'])
    if existing.exists():
        messages.error(request,
            f"User already has {existing.count()} pending remittance(s). "
            "Complete or cancel them first."
        )
        return redirect('admin_remittance_dashboard')

    is_staff = _is_staff_user(owner)

    if request.method == 'POST':
        amount_str = (
            request.POST.get('amount', '0').strip()
            .replace(',', '').replace('₦', '').replace('$', '')
        )
        try:
            amount = Decimal(amount_str or '0')
        except (InvalidOperation, ValueError):
            messages.error(request, f"Invalid amount format: '{amount_str}'.")
            return redirect('admin_remittance_dashboard')

        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
        elif amount > wallet.available_balance:
            messages.error(request, "Amount exceeds available balance.")
        else:
            remittance = Remittance.objects.create(
                owner=owner,
                amount=amount,
                description=request.POST.get('description', ''),
                created_by=request.user,
                status='pending',
            )

            # Staff earn booking fees only.
            # Tenant admins' personal wallet is also booking fees only.
            # Pure personal users earn both.
            is_admin_personal = _is_tenant_admin(owner)
            if is_staff or is_admin_personal:
                payment_types = ['booking_fee']
            else:
                payment_types = ['conference_fee', 'booking_fee']
            unremitted = Payment.objects.filter(
                owner=owner,
                payment_type__in=payment_types,
                direction='incoming', status='success',
                remittance_status='unremitted',
            ).order_by('payment_date')
            remittance.payments.set(unremitted)

            # Send bank verification email using the right profile.
            # Staff → StaffProfile
            # Tenant admin personal → StaffProfile (they have one; personal bank details live there)
            # Pure personal user → UserProfile
            try:
                if is_staff or is_admin_personal:
                    staff_profile = getattr(owner, 'staff_profile', None)
                    if staff_profile and owner.email:
                        send_bank_verification_request_for_staff_email(request, staff_profile)
                        messages.info(request, "Bank verification email sent.")
                    else:
                        messages.warning(request, "Remittance created but no email found.")
                else:
                    user_profile, _ = UserProfile.objects.get_or_create(
                        user=owner, defaults={'email': owner.email}
                    )
                    if owner.email:
                        send_bank_verification_request_for_user_email(request, user_profile)
                        messages.info(request, "Bank verification email sent.")
                    else:
                        messages.warning(request, "Remittance created but no email found.")
            except Exception as e:
                logger.error(f"Email error for {remittance.reference}: {e}")
                messages.warning(request, f"Remittance created but email failed: {e}")

            messages.success(request, f"Remittance {remittance.reference} created successfully.")
            return redirect('admin_remittance_dashboard')

    context = {
        'owner': owner,
        'wallet': wallet,
        'is_staff_user': is_staff,
        'wallet_label': (
            'Staff Earnings' if is_staff
            else 'Personal Earnings (Booking)' if _is_tenant_admin(owner)
            else 'Earnings'
        ),
    }
    return render(request, 'wallet/create_user_remittance.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# REMAINING ADMIN VIEWS (mark completed, bulk, edit, delete, process, retry)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@user_passes_test(lambda u: u.is_superuser)
def mark_remittance_completed(request, remittance_id):
    remittance = get_object_or_404(Remittance, id=remittance_id)
    if request.method == 'POST':
        bank_reference = request.POST.get('bank_reference', '')
        remittance_date = request.POST.get('remittance_date')
        if remittance_date:
            remittance.remittance_date = remittance_date
        remittance.mark_as_completed(bank_reference=bank_reference or None, user=request.user)
        remittance.payments.update(remittance_status='remitted', remitted_at=timezone.now())
        messages.success(request, f"Remittance {remittance.reference} marked as completed.")
        return redirect('admin_remittance_dashboard')
    return render(request, 'wallet/mark_completed.html', {
        'remittance': remittance, 'today': timezone.now().date(),
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def bulk_mark_remitted(request):
    if request.method != 'POST':
        return redirect('admin_remittance_dashboard')

    remittance_ids = request.POST.getlist('remittance_ids')
    bank_reference = request.POST.get('bank_reference', '')
    remittance_date = request.POST.get('remittance_date', timezone.now().date())
    payment_method = request.POST.get('payment_method', '')
    tenant_search = request.POST.get('tenant_search', '')
    remittance_search = request.POST.get('remittance_search', '')
    tenant_page = request.POST.get('tenant_page', 1)
    remittance_page = request.POST.get('remittance_page', 1)

    remittances = Remittance.objects.filter(
        id__in=remittance_ids, status__in=['pending', 'processing']
    )
    count = 0
    for rem in remittances:
        if payment_method:
            current = rem.description or ''
            rem.description = f"{current}\nPayment Method: {payment_method}" if current else f"Payment Method: {payment_method}"
        rem.mark_as_completed(
            bank_reference=bank_reference or f"BATCH-{timezone.now().strftime('%Y%m%d')}",
            user=request.user,
        )
        try:
            rem.remittance_date = remittance_date
            rem.save()
        except Exception:
            pass
        rem.payments.update(remittance_status='remitted', remitted_at=timezone.now())
        count += 1

    messages.success(request, f"Successfully marked {count} remittance(s) as completed.")
    redirect_url = reverse('admin_remittance_dashboard') + '?'
    for key, val in [('tenant_search', tenant_search), ('remittance_search', remittance_search),
                     ('tenant_page', tenant_page), ('remittance_page', remittance_page)]:
        if val:
            redirect_url += f"{key}={val}&"
    return redirect(redirect_url.rstrip('&'))


@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_remittance(request, remittance_id):
    remittance = get_object_or_404(Remittance, id=remittance_id)
    if request.method == 'POST':
        try:
            raw = request.POST.get('raw_amount')
            amount = Decimal(raw) if raw else Decimal(request.POST.get('amount', '0').replace(',', ''))
            original_status = remittance.status
            remittance.amount = amount
            remittance.status = request.POST.get('status', 'pending')
            remittance.description = request.POST.get('description', '')
            rd = request.POST.get('remittance_date')
            if rd:
                remittance.remittance_date = rd
            br = request.POST.get('bank_reference', '')
            if br:
                remittance.bank_reference = br
            if remittance.status == 'completed' and original_status != 'completed':
                remittance.completion_date = timezone.now()
                remittance.updated_by = request.user
            remittance.save()

            if original_status == 'completed' and remittance.status != 'completed':
                bal_key = {'tenant': remittance.tenant} if remittance.tenant else {'owner': remittance.owner}
                tb = TenantBalance.objects.filter(**bal_key).first()
                if tb:
                    tb.update_balance()
                remittance.payments.update(remittance_status='pending_remittance', remitted_at=None)

            messages.success(request, f"Remittance {remittance.reference} updated successfully.")
            return redirect('admin_remittance_dashboard')
        except Exception as e:
            messages.error(request, f"Error updating remittance: {e}")

    return render(request, 'wallet/edit_remittance.html', {
        'remittance': remittance, 'status_choices': Remittance.STATUS_CHOICES,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_remittance(request, remittance_id):
    try:
        remittance = Remittance.objects.get(id=remittance_id)
        reference = remittance.reference
        remittance.payments.update(remittance_status='unremitted', remittance=None, remitted_at=None)
        remittance.delete()
        bal_key = {'tenant': remittance.tenant} if remittance.tenant else {'owner': remittance.owner}
        tb = TenantBalance.objects.filter(**bal_key).first()
        if tb:
            tb.update_balance()
        messages.success(request, f"Remittance {reference} deleted successfully.")
    except Remittance.DoesNotExist:
        messages.error(request, "Remittance not found.")
    except Exception as e:
        logger.error(f"Error deleting remittance {remittance_id}: {e}")
        messages.error(request, f"Error deleting remittance: {e}")
    return redirect('admin_remittance_dashboard')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def process_remittance_payment(request, remittance_id):
    remittance = get_object_or_404(Remittance, id=remittance_id)
    if not remittance.can_process_payment():
        messages.error(request,
            f"Cannot process remittance {remittance.reference}. "
            f"Confirmation: {remittance.get_bank_confirmation_display()}"
        )
        return redirect('admin_remittance_dashboard')
    if remittance.status in ['processing', 'completed']:
        messages.warning(request,
            f"Remittance {remittance.reference} is already {remittance.get_status_display()}."
        )
        return redirect('admin_remittance_dashboard')
    try:
        result = remittance.process_payment(user=request.user)
        if result.get('success'):
            messages.success(request,
                f"Payment initiated for {remittance.reference}. "
                f"Transfer code: {result.get('transfer_code')}."
            )
        else:
            messages.error(request, f"Payment failed: {result.get('message')}")
    except Exception as e:
        messages.error(request, f"Error: {e}")
        logger.error(f"Error processing remittance {remittance.reference}: {e}")
    return redirect('admin_remittance_dashboard')


@login_required
@user_passes_test(lambda u: u.is_superuser)
def retry_remittance(request, remittance_id):
    import traceback
    from documents.models import Payee

    remittance = get_object_or_404(Remittance, id=remittance_id)
    if remittance.status not in ['pending', 'failed']:
        messages.error(request, f"Cannot retry: status is {remittance.get_status_display()}.")
        return redirect('admin_remittance_dashboard')

    try:
        amount_decimal = (
            remittance.amount if isinstance(remittance.amount, Decimal)
            else Decimal(str(remittance.amount))
        )
        content_type = ContentType.objects.get_for_model(remittance)
        previous_payment = Payment.objects.filter(
            remittance=remittance, direction='outgoing',
            payment_type='remittance', content_type=content_type,
            object_id=remittance.id,
        ).first()

        profile = remittance.company_profile  # handles all three types via model property

        if remittance.tenant is not None:
            payee, created = Payee.objects.get_or_create(
                tenant=remittance.tenant,
                defaults={
                    'name': profile.bank_account_name,
                    'email': getattr(profile, 'email', None),
                    'account_number': profile.bank_account_number,
                    'bank_name': profile.bank_name,
                }
            )
            if not created:
                payee.name = profile.bank_account_name
                payee.account_number = profile.bank_account_number
                payee.bank_name = profile.bank_name
                payee.save()
        else:
            try:
                payee = Payee.objects.get(user=remittance.owner)
                payee.name = profile.bank_account_name
                payee.account_number = profile.bank_account_number
                payee.bank_name = profile.bank_name
                payee.save()
            except Payee.DoesNotExist:
                payee = Payee.objects.create(
                    user=remittance.owner,
                    name=profile.bank_account_name,
                    email=getattr(profile, 'email', remittance.owner.email),
                    account_number=profile.bank_account_number,
                    bank_name=profile.bank_name,
                )

        if previous_payment and previous_payment.status == 'failed':
            previous_payment.status = 'processing'
            previous_payment.payee = payee
            previous_payment.save()
        else:
            kwargs = {
                'payee': payee, 'payment_type': 'remittance',
                'direction': 'outgoing', 'amount': amount_decimal,
                'net_amount': amount_decimal,
                'description': f"Retry: Remittance {remittance.reference}",
                'reference_number': f"RETRY-{remittance.reference}",
                'status': 'processing', 'payment_method': 'bank_transfer',
                'created_by': request.user, 'remittance_status': 'pending_remittance',
                'remittance': remittance, 'content_object': remittance,
            }
            if remittance.tenant:
                kwargs['tenant'] = remittance.tenant
            else:
                kwargs['owner'] = remittance.owner
            previous_payment = Payment.objects.create(**kwargs)

        remittance.paystack_transfer_code = None
        result = remittance.process_payment(user=request.user, is_retry=True)
        if result.get('success'):
            messages.success(request,
                f"Retry initiated for {remittance.reference}. "
                f"Transfer code: {result.get('transfer_code')}"
            )
            if result.get('transfer_code'):
                previous_payment.transaction_id = result['transfer_code']
                previous_payment.save()
        else:
            messages.error(request, f"Retry failed: {result.get('message')}")
            previous_payment.status = 'failed'
            previous_payment.save()

    except Exception as e:
        logger.error(f"Retry error for {remittance_id}: {e}\n{traceback.format_exc()}")
        messages.error(request, f"Error setting up retry: {e}")

    return redirect('admin_remittance_dashboard')


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN USER PROFILE (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def admin_user_profile(request):
    if not (request.effective_user.is_superuser or request.effective_user.is_personal):
        return render(request, 'tenant_error.html', {
            'error_code': '403',
            'message': 'You do not have permission to view this profile.',
        })
    user_id = request.GET.get('user_id') if request.effective_user.is_staff else request.effective_user.id
    user = get_object_or_404(CustomUser, id=user_id)
    profile = getattr(user, 'user_profile', None)

    if request.method == 'POST' and profile:
        action = request.POST.get('action')
        if action == 'edit_bio':
            profile.bio = request.POST.get('bio')
            profile.save()
        elif action == 'add_education':
            form = EducationHistoryForm(request.POST)
            if form.is_valid():
                edu = form.save(commit=False)
                edu.user_profile = profile
                edu.save()
        elif action == 'add_experience':
            form = WorkHistoryForm(request.POST)
            if form.is_valid():
                exp = form.save(commit=False)
                exp.user_profile = profile
                exp.save()
        elif action == 'add_achievement':
            form = AchievementForm(request.POST)
            if form.is_valid():
                ach = form.save(commit=False)
                ach.user_profile = profile
                ach.save()
        redirect_url = reverse('admin_user_profile')
        if request.GET.urlencode():
            redirect_url += '?' + request.GET.urlencode()
        return redirect(redirect_url)

    context = {
        'user': user, 'profile': profile,
        'education_form': EducationHistoryForm(),
        'experience_form': WorkHistoryForm(),
        'achievement_form': AchievementForm(),
        'is_admin_view': request.effective_user.is_staff and user_id != str(request.effective_user.id),
    }
    return render(request, 'users/user_company_profile.html', context)