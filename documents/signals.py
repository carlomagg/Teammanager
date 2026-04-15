from django.db.models.signals import post_save, m2m_changed, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import StaffProfile, Role, CustomUser, Team, CustomerSupport, Vacancy, Conference, GuestUser, Payment, TenantBalance, CompanyProfile, Remittance, PromotionHistory, UserProfile
from tenants.models import Tenant
from django.db import transaction


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def sync_user_to_profile_department(sender, instance, created, **kwargs):
    """
    When CustomUser is saved, sync department, team, and designation to StaffProfile.
    Also auto-derives department from the assigned team when department is not set directly.
    """
    try:
        profile = instance.staff_profile
        changed_fields = []

        # --- Department ---
        # If department is missing but user has a team with an attached department, derive it
        resolved_department = instance.department
        if not resolved_department:
            first_team = instance.teams.select_related('department').first()
            if first_team and first_team.department:
                resolved_department = first_team.department

        if profile.department != resolved_department:
            profile.department = resolved_department
            changed_fields.append('department')

        # --- Team ---
        user_teams = list(instance.teams.all())
        first_user_team = user_teams[0] if user_teams else None
        if profile.team != first_user_team:
            profile.team = first_user_team
            changed_fields.append('team')

        # --- Designation (from profile; CustomUser has no designation field,
        #     so keep StaffProfile.designation in sync with latest PromotionHistory) ---
        latest_promotion = profile.promotion_history.order_by('-start_date').first()
        if latest_promotion and latest_promotion.designation:
            if profile.designation != latest_promotion.designation:
                profile.designation = latest_promotion.designation
                changed_fields.append('designation')

        # --- Phone ---
        if instance.phone_number and profile.phone_number != instance.phone_number:
            profile.phone_number = instance.phone_number
            changed_fields.append('phone_number')

        if changed_fields:
            profile.save(update_fields=changed_fields)

    except StaffProfile.DoesNotExist:
        # If no StaffProfile exists yet, create one with the synced fields
        if instance.department or instance.teams.exists():
            team = instance.teams.first()
            department = instance.department
            if not department and team and team.department:
                department = team.department
            StaffProfile.objects.create(
                user=instance,
                tenant=instance.tenant,
                department=department,
                team=team,
                first_name=instance.first_name,
                last_name=instance.last_name,
                phone_number=instance.phone_number,
                email=instance.email
            )


@receiver(m2m_changed, sender=CustomUser.teams.through)
def sync_user_teams_to_staff_profile(sender, instance, action, pk_set, **kwargs):
    """
    When a user's teams M2M relationship changes, sync the team and derived
    department back to StaffProfile and also update CustomUser.department.
    """
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return

    try:
        profile = instance.staff_profile
    except StaffProfile.DoesNotExist:
        return

    changed_fields = []

    # Determine first team (primary team for StaffProfile)
    first_team = instance.teams.select_related('department').first()

    if profile.team != first_team:
        profile.team = first_team
        changed_fields.append('team')

    # Derive department from team when CustomUser.department is not explicitly set
    resolved_department = instance.department
    if not resolved_department and first_team and first_team.department:
        resolved_department = first_team.department

    if profile.department != resolved_department:
        profile.department = resolved_department
        changed_fields.append('department')

    # Also push resolved department back to CustomUser if it was derived
    if not instance.department and resolved_department:
        instance.department = resolved_department
        instance.save(update_fields=['department'])

    if changed_fields:
        profile.save(update_fields=changed_fields)


@receiver(post_save, sender=PromotionHistory)
def sync_promotion_to_staff_profile(sender, instance, created, **kwargs):
    """
    When PromotionHistory is saved, update StaffProfile's department, team,
    and designation to the latest promotion's values. Also cascade to CustomUser.
    """
    if not instance.staff_profile:
        return

    latest_promotion = instance.staff_profile.promotion_history.order_by('-start_date').first()
    if not latest_promotion:
        return

    profile = instance.staff_profile
    profile_changed = []

    if latest_promotion.department and profile.department != latest_promotion.department:
        profile.department = latest_promotion.department
        profile_changed.append('department')

    if latest_promotion.team and profile.team != latest_promotion.team:
        profile.team = latest_promotion.team
        profile_changed.append('team')

    if latest_promotion.designation and profile.designation != latest_promotion.designation:
        profile.designation = latest_promotion.designation
        profile_changed.append('designation')

    if profile_changed:
        profile.save(update_fields=profile_changed)

    # Cascade to CustomUser
    user = profile.user
    if user:
        user_changed = []

        if latest_promotion.department and user.department != latest_promotion.department:
            user.department = latest_promotion.department
            user_changed.append('department')

        if user_changed:
            user.save(update_fields=user_changed)

        # Sync teams M2M (always replace with promotion team)
        if latest_promotion.team:
            current_teams = set(user.teams.values_list('id', flat=True))
            if current_teams != {latest_promotion.team.id}:
                user.teams.set([latest_promotion.team])
        elif not latest_promotion.team:
            # Promotion explicitly has no team – leave teams unchanged
            pass


@receiver(m2m_changed, sender=CustomUser.roles.through)
def update_user_permissions(sender, instance, action, pk_set, **kwargs):
    if action == 'post_add':
        roles = Role.objects.filter(pk__in=pk_set)
        for role in roles:
            instance.user_permissions.add(*role.permissions.all())
    elif action == 'post_remove':
        roles = Role.objects.filter(pk__in=pk_set)
        for role in roles:
            instance.user_permissions.remove(*role.permissions.all())
    elif action == 'post_clear':
        instance.user_permissions.clear()



# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────
 
def _is_earning_payment(instance):
    """
    Return True if this Payment should affect a wallet balance.
    Conditions:
      • direction = incoming
      • status    = success
      • type      = conference_fee  OR  booking_fee
    """
    return (
        instance.direction == 'incoming' and
        instance.status == 'success' and
        instance.payment_type in ('conference_fee', 'booking_fee')
    )
 
 
def _is_staff_or_admin_personal(user):
    """
    True for any user whose owner-keyed wallet earns booking fees only:
      • Staff members (has tenant, not personal)
      • Tenant admins (has tenant, not personal — their personal wallet
                       is booking-only, bank details via StaffProfile)
    Pure personal users (is_personal=True) are excluded.
    """
    return (
        user is not None and
        not user.is_personal and
        user.tenant is not None
    )
 
# Keep old name as alias so nothing else breaks if referenced elsewhere
_is_staff_owner = _is_staff_or_admin_personal
 
 
def _get_balance_for_payment(instance):
    """
    Resolve (or create) the correct TenantBalance for a Payment instance.
    Tenant payments  → keyed on tenant.
    Personal users   → keyed on owner.
    Staff members    → keyed on owner  (NEW).
    Returns the TenantBalance instance, or None on failure.
    """
    try:
        if instance.tenant is not None:
            return TenantBalance.get_or_create_for_tenant(
                tenant=instance.tenant, owner=None
            )
        elif instance.owner is not None:
            return TenantBalance.get_or_create_for_tenant(
                tenant=None, owner=instance.owner
            )
    except Exception as e:
        print(f"❌ Could not resolve wallet for payment #{instance.id}: {e}")
    return None
 
 
def _get_balance_for_remittance(instance):
    """
    Resolve (or create) the correct TenantBalance for a Remittance instance.
    Same three-way logic as payments.
    """
    try:
        if instance.tenant is not None:
            return TenantBalance.get_or_create_for_tenant(
                tenant=instance.tenant, owner=None
            )
        elif instance.owner is not None:
            return TenantBalance.get_or_create_for_tenant(
                tenant=None, owner=instance.owner
            )
    except Exception as e:
        print(f"❌ Could not resolve wallet for remittance #{instance.reference}: {e}")
    return None
 
 
def _owner_label(instance):
    """Human-readable owner name for debug prints."""
    if instance.tenant is not None:
        return instance.tenant.name
    if instance.owner is not None:
        return instance.owner.username
    return "unknown"
 
 
# ─────────────────────────────────────────────────────────────────────────────
# PAYMENT SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
 
@receiver(post_save, sender=Payment)
def update_tenant_balance_on_payment(sender, instance, created, **kwargs):
    """
    Update wallet balance when an incoming earning payment is saved.
 
    Covers:
      • conference_fee  – orgs and personal users
      • booking_fee     – orgs, personal users, AND staff members  (NEW)
 
    Staff member payments are owner-keyed (instance.owner set,
    instance.tenant is None), so _get_balance_for_payment handles them
    the same way as personal users — the distinction (booking-only) is
    enforced by TenantBalance.update_balance() itself.
    """
    if not _is_earning_payment(instance):
        return
 
    # Extra guard: conference_fee must never feed a staff/admin-personal wallet.
    # Any payment with owner set and owner.tenant set is either a staff member
    # or a tenant admin acting on their personal wallet — both earn booking only.
    if instance.payment_type == 'conference_fee' and instance.owner is not None:
        if _is_staff_or_admin_personal(instance.owner):
            return
 
    try:
        with transaction.atomic():
            balance = _get_balance_for_payment(instance)
            if balance is None:
                return
 
            result = balance.update_balance()
 
            action = "New payment" if created else "Updated payment"
            print(
                f"✅ {action} #{instance.id} ({instance.payment_type}): "
                f"₦{instance.amount}"
            )
            print(f"   Owner: {_owner_label(instance)}")
            print(f"   Adjusted total earned: ₦{result['total_earned']}")
            print(f"   Available balance:     ₦{result['available_balance']}")
 
    except Exception as e:
        print(f"❌ Error updating balance for payment #{instance.id}: {e}")
 
 
@receiver(post_delete, sender=Payment)
def update_balance_on_payment_delete(sender, instance, **kwargs):
    """
    Recalculate wallet balance when an earning payment is deleted.
    Previously only handled tenant; now also handles owner-keyed wallets
    (personal users and staff members).
    """
    if not _is_earning_payment(instance):
        return
 
    try:
        with transaction.atomic():
            # Resolve the right balance object
            if instance.tenant is not None:
                balance = TenantBalance.objects.filter(tenant=instance.tenant).first()
            elif instance.owner is not None:
                balance = TenantBalance.objects.filter(owner=instance.owner).first()
            else:
                return
 
            if balance:
                result = balance.update_balance()
                print(
                    f"🗑️ Payment #{instance.id} ({instance.payment_type}) deleted"
                )
                print(f"   Owner: {_owner_label(instance)}")
                print(f"   Updated balance: ₦{result['available_balance']}")
 
    except Exception as e:
        print(f"❌ Error updating balance after payment delete #{instance.id}: {e}")
 
 
# ─────────────────────────────────────────────────────────────────────────────
# REMITTANCE SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
 
@receiver(post_save, sender=Remittance)
def update_balance_on_remittance_change(sender, instance, created, **kwargs):
    """
    Recalculate wallet balance when a remittance is completed.
    Works for tenant, personal, and staff (owner-keyed) remittances.
    """
    if instance.status != 'completed':
        return
 
    try:
        with transaction.atomic():
            balance = _get_balance_for_remittance(instance)
            if balance is None:
                return
 
            result = balance.update_balance()
 
            print(
                f"💰 Remittance {instance.reference} completed: ₦{instance.amount}"
            )
            print(f"   Owner: {_owner_label(instance)}")
            print(f"   Total remitted:    ₦{result['total_remitted']}")
            print(f"   Available balance: ₦{result['available_balance']}")
 
    except Exception as e:
        print(
            f"❌ Error updating balance for remittance {instance.reference}: {e}"
        )
 
 
@receiver(post_save, sender=Remittance)
def handle_remittance_bank_confirmation(sender, instance, created, **kwargs):
    """
    When bank_confirmation flips to 'confirmed' or 'changed', attempt to
    auto-process the payment if all conditions are met.
    Reads the pre-save state from the DB to detect the change reliably.
    """
    if created:
        return
 
    try:
        old = Remittance.objects.get(id=instance.id)
    except Remittance.DoesNotExist:
        return
 
    if old.bank_confirmation == instance.bank_confirmation:
        return  # nothing changed
 
    if instance.bank_confirmation not in ('confirmed', 'changed'):
        return
 
    try:
        if instance.can_process_payment():
            result = instance.process_payment()
            if result and result.get('success'):
                print(
                    f"✅ Payment processing initiated for "
                    f"remittance {instance.reference}"
                )
            else:
                msg = result.get('message', 'unknown error') if result else 'no result'
                print(
                    f"❌ Payment processing failed for "
                    f"remittance {instance.reference}: {msg}"
                )
    except Exception as e:
        print(
            f"❌ Error processing payment for remittance "
            f"{instance.reference}: {e}"
        )
 
 
@receiver(post_delete, sender=Remittance)
def update_balance_on_remittance_delete(sender, instance, **kwargs):
    """
    Recalculate wallet balance when a completed remittance is deleted.
    Previously only handled the tenant FK; now also handles owner-keyed
    wallets (personal users and staff members).
    """
    if instance.status != 'completed':
        return
 
    try:
        with transaction.atomic():
            if instance.tenant is not None:
                balance = TenantBalance.objects.filter(
                    tenant=instance.tenant
                ).first()
            elif instance.owner is not None:
                balance = TenantBalance.objects.filter(
                    owner=instance.owner
                ).first()
            else:
                return
 
            if balance:
                result = balance.update_balance()
                print(
                    f"🗑️ Remittance {instance.reference} deleted"
                )
                print(f"   Owner: {_owner_label(instance)}")
                print(f"   Updated balance: ₦{result['available_balance']}")
 
    except Exception as e:
        print(
            f"❌ Error updating balance after remittance delete "
            f"{instance.reference}: {e}"
        )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# COMPANY / USER / STAFF PROFILE BANK DETAIL SIGNALS
# ─────────────────────────────────────────────────────────────────────────────
 
@receiver(post_save, sender=CompanyProfile)
def verify_company_bank_details(sender, instance, created, **kwargs):
    """
    Reset bank_verified to False whenever the tenant's bank details change,
    so admin must re-verify before the next remittance can be processed.
    """
    if created:
        return
    if not instance.has_complete_bank_details():
        return
 
    try:
        old = CompanyProfile.objects.get(id=instance.id)
    except CompanyProfile.DoesNotExist:
        return
 
    if (
        old.bank_name != instance.bank_name or
        old.bank_account_number != instance.bank_account_number or
        old.bank_account_name != instance.bank_account_name or
        old.bank_code != instance.bank_code
    ):
        # Use update() to avoid re-triggering this signal recursively
        CompanyProfile.objects.filter(id=instance.id).update(
            bank_verified=False,
            bank_verification_date=None,
        )
        print(
            f"🔄 Bank details changed for {instance.company_name} — "
            f"verification reset"
        )
 
 
@receiver(post_save, sender=UserProfile)
def verify_user_bank_details(sender, instance, created, **kwargs):
    """
    Reset bank_verified when a personal user's bank details change.
    Mirrors the CompanyProfile signal above.
    """
    if created:
        return
    if not instance.has_complete_bank_details():
        return
 
    try:
        old = UserProfile.objects.get(id=instance.id)
    except UserProfile.DoesNotExist:
        return
 
    if (
        old.bank_name != instance.bank_name or
        old.bank_account_number != instance.bank_account_number or
        old.bank_account_name != instance.bank_account_name or
        old.bank_code != instance.bank_code
    ):
        UserProfile.objects.filter(id=instance.id).update(
            bank_verified=False,
            bank_verification_date=None,
        )
        print(
            f"🔄 Bank details changed for user {instance.user.username} — "
            f"verification reset"
        )
 
 
@receiver(post_save, sender=StaffProfile)
def verify_staff_bank_details(sender, instance, created, **kwargs):
    """
    Reset bank_verified when a staff member's bank details change.
    Staff bank fields mirror UserProfile's new bank fields.
    """
    if created:
        return
    if not instance.has_complete_bank_details():
        return
 
    try:
        old = StaffProfile.objects.get(id=instance.id)
    except StaffProfile.DoesNotExist:
        return
 
    if (
        old.bank_name != instance.bank_name or
        old.bank_account_number != instance.bank_account_number or
        old.bank_account_name != instance.bank_account_name or
        old.bank_code != instance.bank_code
    ):
        StaffProfile.objects.filter(id=instance.id).update(
            bank_verified=False,
            bank_verification_date=None,
        )
        print(
            f"🔄 Bank details changed for staff {instance.full_name} — "
            f"verification reset"
        )

@receiver(post_save, sender=Payment)
def auto_create_wallet_on_booking(sender, instance, created, **kwargs):
    """
    Ensure a TenantBalance exists for any user/tenant that just received
    a successful booking_fee or conference_fee payment.
    """
    if instance.status != 'success' or instance.direction != 'incoming':
        return
    if instance.payment_type not in ('booking_fee', 'conference_fee'):
        return

    if instance.tenant is not None:
        TenantBalance.objects.get_or_create(tenant=instance.tenant)
    elif instance.owner is not None:
        TenantBalance.objects.get_or_create(owner=instance.owner)
 
 
# Customer Support Auto-Creation Signals

@receiver(post_save, sender=Tenant)
def create_support_record_for_tenant(sender, instance, created, **kwargs):
    """
    Automatically create a CustomerSupport record when a new Tenant is created.
    This allows the support team to track and follow up with new tenants.
    """
    if created:
        CustomerSupport.objects.get_or_create(
            entity_type='tenant',
            entity_id=instance.id,
            defaults={'status': 'new'}
        )


@receiver(post_save, sender=Vacancy)
def create_support_record_for_vacancy(sender, instance, created, **kwargs):
    """
    Automatically create a CustomerSupport record when a new Vacancy is created.
    This allows the support team to track and follow up with new job postings.
    Tracks the Tenant that created the vacancy.
    """
    if created:
        from django.contrib.contenttypes.models import ContentType
        source_ct = None
        source_id = None
        
        if instance.tenant:
            source_ct = ContentType.objects.get_for_model(Tenant)
            source_id = instance.tenant.id
        
        CustomerSupport.objects.get_or_create(
            entity_type='vacancy',
            entity_id=instance.id,
            defaults={
                'status': 'new',
                'source_content_type': source_ct,
                'source_object_id': source_id
            }
        )


@receiver(post_save, sender=Conference)
def create_support_record_for_conference(sender, instance, created, **kwargs):
    """
    Automatically create a CustomerSupport record when a new Conference is created.
    This allows the support team to track and follow up with new conferences.
    Tracks the Tenant that created the conference.
    """
    if created:
        from django.contrib.contenttypes.models import ContentType
        source_ct = None
        source_id = None
        
        if instance.tenant:
            source_ct = ContentType.objects.get_for_model(Tenant)
            source_id = instance.tenant.id
        
        CustomerSupport.objects.get_or_create(
            entity_type='conference',
            entity_id=instance.id,
            defaults={
                'status': 'new',
                'source_content_type': source_ct,
                'source_object_id': source_id
            }
        )


@receiver(post_save, sender=CustomUser)
def create_support_record_for_user(sender, instance, created, **kwargs):
    """
    Automatically create a CustomerSupport record when a new User is created.
    This allows the support team to track and follow up with new user registrations.
    Tracks the Tenant the user belongs to.
    Also generates personal_external_token if not set.
    """
    # Generate personal external token if not set
    if not instance.personal_external_token:
        from uuid import uuid4
        instance.personal_external_token = uuid4()
        instance.save(update_fields=['personal_external_token'])
    
    if created:
        from django.contrib.contenttypes.models import ContentType
        source_ct = None
        source_id = None
        
        if instance.tenant:
            source_ct = ContentType.objects.get_for_model(Tenant)
            source_id = instance.tenant.id
        
        CustomerSupport.objects.get_or_create(
            entity_type='user',
            entity_id=instance.id,
            defaults={
                'status': 'new',
                'source_content_type': source_ct,
                'source_object_id': source_id
            }
        )


@receiver(post_save, sender=GuestUser)
def create_support_record_for_guest(sender, instance, created, **kwargs):
    """
    Automatically create a CustomerSupport record when a new GuestUser is created.
    This allows the support team to track and follow up with guest user activity.
    Tracks the source (Conference, Vacancy, etc.) that the guest user came from.
    """
    if created:
        CustomerSupport.objects.get_or_create(
            entity_type='guest',
            entity_id=instance.id,
            defaults={
                'status': 'new',
                'source_content_type': instance.source_content_type,
                'source_object_id': instance.source_object_id
            }
        )


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION EMAIL SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

from .models import UserNotification

@receiver(post_save, sender=UserNotification)
def send_notification_email_on_create(sender, instance, created, **kwargs):
    """
    Send an email alert to the user when a new notification is assigned to them.
    This triggers for every notification created via any method (helper functions,
    direct model creation, etc.).
    """
    if created:
        from .notification_helpers import send_notification_email
        # Import here to avoid circular imports
        import threading
        
        def send_email_async():
            try:
                send_notification_email(instance)
            except Exception as e:
                print(f"Error sending notification email: {e}")
        
        # Send email in a separate thread to avoid blocking the request
        email_thread = threading.Thread(target=send_email_async)
        email_thread.daemon = True
        email_thread.start()
