# documents/viewfuncs/admin/kyc_admin_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from documents.kyc_models import UserKYC, StaffKYC, CompanyKYB, CompanyDirector
from documents.models import CustomUser, Notification, UserNotification
from documents.decorators import kyc_verification_permission_required


@kyc_verification_permission_required
def admin_kyc_dashboard(request):
    """Admin dashboard for KYC/KYB review"""
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '')
    
    # User KYC
    user_kycs = UserKYC.objects.select_related('user_profile__user').all()
    if status_filter != 'all':
        user_kycs = user_kycs.filter(kyc_status=status_filter)
    if search_query:
        user_kycs = user_kycs.filter(
            Q(user_profile__user__username__icontains=search_query) |
            Q(user_profile__user__email__icontains=search_query) |
            Q(nin__icontains=search_query) |
            Q(bvn__icontains=search_query)
        )
    
    # Staff KYC
    staff_kycs = StaffKYC.objects.select_related('staff_profile__user', 'staff_profile__tenant').all()
    if status_filter != 'all':
        staff_kycs = staff_kycs.filter(kyc_status=status_filter)
    if search_query:
        staff_kycs = staff_kycs.filter(
            Q(staff_profile__user__username__icontains=search_query) |
            Q(staff_profile__user__email__icontains=search_query) |
            Q(nin__icontains=search_query) |
            Q(bvn__icontains=search_query)
        )
    
    # Company KYB
    company_kybs = CompanyKYB.objects.select_related('company_profile__tenant').all()
    if status_filter != 'all':
        company_kybs = company_kybs.filter(kyb_status=status_filter)
    if search_query:
        company_kybs = company_kybs.filter(
            Q(company_profile__company_name__icontains=search_query) |
            Q(tin__icontains=search_query)
        )
    
    # Count statistics
    stats = {
        'user_kyc_pending': UserKYC.objects.filter(kyc_status='submitted').count(),
        'staff_kyc_pending': StaffKYC.objects.filter(kyc_status='submitted').count(),
        'company_kyb_pending': CompanyKYB.objects.filter(kyb_status='submitted').count(),
        'total_pending': (
            UserKYC.objects.filter(kyc_status='submitted').count() +
            StaffKYC.objects.filter(kyc_status='submitted').count() +
            CompanyKYB.objects.filter(kyb_status='submitted').count()
        ),
    }
    
    context = {
        'user_kycs': user_kycs,
        'staff_kycs': staff_kycs,
        'company_kybs': company_kybs,
        'stats': stats,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'admin/kyc/dashboard.html', context)


@kyc_verification_permission_required
def review_user_kyc(request, kyc_id):
    """Review and approve/reject user KYC"""
    kyc = get_object_or_404(UserKYC, id=kyc_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            kyc.kyc_status = 'verified'
            kyc.kyc_verified_at = timezone.now()
            kyc.verified_by = request.user
            kyc.kyc_rejection_reason = None
            kyc.save()
            
            # Create notification for user
            notification = Notification.objects.create(
                tenant=None,  # Personal user has no tenant
                title="KYC Approved",
                message=f"Your KYC verification has been approved.",
                type=Notification.NotificationType.ALERT,
                is_active=True,
                link='/profile/'
            )
            UserNotification.objects.create(
                user=kyc.user_profile.user,
                tenant=None,
                notification=notification,
                dismissed=False
            )
            
            # Send approval email
            send_kyc_approval_email(kyc.user_profile.user, 'User KYC', approved=True)
            
            messages.success(request, f"KYC for {kyc.user_profile.user.username} has been approved.", extra_tags='kyc')
            return redirect('admin_kyc_dashboard')
        
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '')
            if not rejection_reason:
                messages.error(request, "Please provide a rejection reason.")
            else:
                kyc.kyc_status = 'rejected'
                kyc.kyc_rejection_reason = rejection_reason
                kyc.verified_by = request.user
                kyc.save()
                
                # Create notification for user
                notification = Notification.objects.create(
                    tenant=None,  # Personal user has no tenant
                    title="KYC Rejected",
                    message=f"Your KYC verification has been rejected. Reason: {rejection_reason}",
                    type=Notification.NotificationType.ALERT,
                    is_active=True,
                    link='/profile/'
                )
                UserNotification.objects.create(
                    user=kyc.user_profile.user,
                    tenant=None,
                    notification=notification,
                    dismissed=False
                )
                
                # Send rejection email
                send_kyc_approval_email(kyc.user_profile.user, 'User KYC', approved=False, reason=rejection_reason)
                
                messages.success(request, f"KYC for {kyc.user_profile.user.username} has been rejected.", extra_tags='kyc')
                return redirect('admin_kyc_dashboard')
    
    # Initialize field approvals if KYC is submitted
    if kyc.kyc_status == 'submitted':
        kyc.get_or_create_field_approvals()
    
    # Check if user can review
    can_review = request.user.has_perm('documents.verify_kyc') or request.user.is_superuser
    
    context = {
        'kyc': kyc,
        'profile': kyc.user_profile,
        'can_review': can_review,
    }
    return render(request, 'admin/kyc/review_user_kyc.html', context)


@kyc_verification_permission_required
def review_staff_kyc(request, kyc_id):
    """Review and approve/reject staff KYC"""
    kyc = get_object_or_404(StaffKYC, id=kyc_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            kyc.kyc_status = 'verified'
            kyc.kyc_verified_at = timezone.now()
            kyc.verified_by = request.user
            kyc.kyc_rejection_reason = None
            kyc.save()
            
            # Create notification for user
            notification = Notification.objects.create(
                tenant=kyc.staff_profile.tenant,
                title="KYC Approved",
                message=f"Your KYC verification has been approved.",
                type=Notification.NotificationType.ALERT,
                is_active=True,
                link='/profile/'
            )
            UserNotification.objects.create(
                user=kyc.staff_profile.user,
                tenant=kyc.staff_profile.tenant,
                notification=notification,
                dismissed=False
            )
            
            # Send approval email
            send_kyc_approval_email(kyc.staff_profile.user, 'Staff KYC', approved=True)
            
            messages.success(request, f"KYC for {kyc.staff_profile.user.username} has been approved.", extra_tags='kyc')
            return redirect('admin_kyc_dashboard')
        
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '')
            if not rejection_reason:
                messages.error(request, "Please provide a rejection reason.")
            else:
                kyc.kyc_status = 'rejected'
                kyc.kyc_rejection_reason = rejection_reason
                kyc.verified_by = request.user
                kyc.save()
                
                # Create notification for user
                notification = Notification.objects.create(
                    tenant=kyc.staff_profile.tenant,
                    title="KYC Rejected",
                    message=f"Your KYC verification has been rejected. Reason: {rejection_reason}",
                    type=Notification.NotificationType.ALERT,
                    is_active=True,
                    link='/profile/'
                )
                UserNotification.objects.create(
                    user=kyc.staff_profile.user,
                    tenant=kyc.staff_profile.tenant,
                    notification=notification,
                    dismissed=False
                )
                
                # Send rejection email
                send_kyc_approval_email(kyc.staff_profile.user, 'Staff KYC', approved=False, reason=rejection_reason)
                
                messages.success(request, f"KYC for {kyc.staff_profile.user.username} has been rejected.", extra_tags='kyc')
                return redirect('admin_kyc_dashboard')
    
    # Initialize field approvals if KYC is submitted
    if kyc.kyc_status == 'submitted':
        kyc.get_or_create_field_approvals()
    
    # Check if user can review
    can_review = request.user.has_perm('documents.verify_kyc') or request.user.is_superuser
    
    context = {
        'kyc': kyc,
        'profile': kyc.staff_profile,
        'can_review': can_review,
    }
    return render(request, 'admin/kyc/review_staff_kyc.html', context)


@kyc_verification_permission_required
def review_company_kyb(request, kyb_id):
    """Review and approve/reject company KYB"""
    kyb = get_object_or_404(CompanyKYB, id=kyb_id)
    directors = kyb.company_profile.directors.all()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            kyb.kyb_status = 'verified'
            kyb.kyb_verified_at = timezone.now()
            kyb.verified_by = request.user
            kyb.kyb_rejection_reason = None
            kyb.save()
            
            # Send approval email to tenant admins and create notifications
            tenant_admins = CustomUser.objects.filter(
                tenant=kyb.company_profile.tenant,
                roles__name='Admin',
                is_active=True
            )
            for admin in tenant_admins:
                # Create notification
                notification = Notification.objects.create(
                    tenant=kyb.company_profile.tenant,
                    title="Company KYB Approved",
                    message=f"The KYB verification for {kyb.company_profile.company_name} has been approved.",
                    type=Notification.NotificationType.ALERT,
                    is_active=True,
                    link='/admins/company-profile/'
                )
                UserNotification.objects.create(
                    user=admin,
                    tenant=kyb.company_profile.tenant,
                    notification=notification,
                    dismissed=False
                )
                send_kyb_approval_email(admin, kyb.company_profile, approved=True)
            
            messages.success(request, f"KYB for {kyb.company_profile.company_name} has been approved.", extra_tags='kyc')
            return redirect('admin_kyc_dashboard')
        
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '')
            if not rejection_reason:
                messages.error(request, "Please provide a rejection reason.")
            else:
                kyb.kyb_status = 'rejected'
                kyb.kyb_rejection_reason = rejection_reason
                kyb.verified_by = request.user
                kyb.save()
                
                # Send rejection email to tenant admins and create notifications
                tenant_admins = CustomUser.objects.filter(
                    tenant=kyb.company_profile.tenant,
                    roles__name='Admin',
                    is_active=True
                )
                for admin in tenant_admins:
                    # Create notification
                    notification = Notification.objects.create(
                        tenant=kyb.company_profile.tenant,
                        title="Company KYB Rejected",
                        message=f"The KYB verification for {kyb.company_profile.company_name} has been rejected. Reason: {rejection_reason}",
                        type=Notification.NotificationType.ALERT,
                        is_active=True,
                        link='/admins/company-profile/'
                    )
                    UserNotification.objects.create(
                        user=admin,
                        tenant=kyb.company_profile.tenant,
                        notification=notification,
                        dismissed=False
                    )
                    send_kyb_approval_email(admin, kyb.company_profile, approved=False, reason=rejection_reason)
                
                messages.success(request, f"KYB for {kyb.company_profile.company_name} has been rejected.", extra_tags='kyc')
                return redirect('admin_kyc_dashboard')
    
    # Initialize field approvals if KYB is submitted
    if kyb.kyb_status == 'submitted':
        kyb.get_or_create_field_approvals()
    
    # Check if user can review
    can_review = request.user.has_perm('documents.verify_kyc') or request.user.is_superuser
    
    context = {
        'kyb': kyb,
        'company_profile': kyb.company_profile,
        'directors': directors,
        'can_review': can_review,
    }
    return render(request, 'admin/kyc/review_company_kyb.html', context)


@kyc_verification_permission_required
def auto_verify_user_kyc(request, kyc_id):
    """Auto-verify user KYC using YouVerify API"""
    from documents.services.youverify_service import YouVerifyService
    
    kyc = get_object_or_404(UserKYC, id=kyc_id)
    
    if kyc.kyc_status == 'verified':
        messages.info(request, "This KYC is already verified.")
        return redirect('review_user_kyc', kyc_id=kyc_id)
    
    # Initialize YouVerify service
    youverify = YouVerifyService()
    
    # Check if API is configured
    if not youverify.is_configured():
        messages.error(request, "YouVerify API is not configured. Please add YOUVERIFY_API_KEY to your .env file.")
        return redirect('review_user_kyc', kyc_id=kyc_id)
    
    # Check if there's anything to verify
    if not kyc.nin and not kyc.bvn:
        messages.warning(request, "No NIN or BVN provided. Cannot auto-verify.")
        return redirect('review_user_kyc', kyc_id=kyc_id)
    
    verification_results = []
    all_passed = True
    
    # Get date of birth from user profile
    dob = kyc.user_profile.date_of_birth.strftime('%Y-%m-%d') if kyc.user_profile.date_of_birth else None
    
    # Verify NIN if provided
    if kyc.nin:
        nin_result = youverify.verify_nin(
            nin=kyc.nin,
            first_name=kyc.user_profile.user.first_name,
            last_name=kyc.user_profile.user.last_name,
            date_of_birth=dob
        )
        message = nin_result.get('message') or nin_result.get('error', 'Verification failed')
        verification_results.append(f"NIN: {message}")
        if not nin_result.get('success', False):
            all_passed = False
    
    # Verify BVN if provided
    if kyc.bvn:
        bvn_result = youverify.verify_bvn(
            bvn=kyc.bvn,
            first_name=kyc.user_profile.user.first_name,
            last_name=kyc.user_profile.user.last_name,
            date_of_birth=dob
        )
        message = bvn_result.get('message') or bvn_result.get('error', 'Verification failed')
        verification_results.append(f"BVN: {message}")
        if not bvn_result.get('success', False):
            all_passed = False
    
    # Update KYC status based on verification results
    if all_passed and verification_results:
        kyc.kyc_status = 'verified'
        kyc.kyc_verified_at = timezone.now()
        kyc.verified_by = request.user
        kyc.kyc_rejection_reason = None
        kyc.save()
        
        # Create notification for user
        notification = Notification.objects.create(
            tenant=None,
            title="KYC Auto-Verified",
            message=f"Your KYC has been automatically verified and approved.",
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link='/profile/'
        )
        UserNotification.objects.create(
            user=kyc.user_profile.user,
            tenant=None,
            notification=notification,
            dismissed=False
        )
        
        # Send approval email
        send_kyc_approval_email(kyc.user_profile.user, 'User KYC', approved=True)
        
        messages.success(request, f"✅ Auto-verification successful! {' | '.join(verification_results)}")
    else:
        messages.error(request, f"❌ Auto-verification failed: {' | '.join(verification_results)}")
    
    return redirect('review_user_kyc', kyc_id=kyc_id)


@kyc_verification_permission_required
def auto_verify_staff_kyc(request, kyc_id):
    """Auto-verify staff KYC using YouVerify API"""
    from documents.services.youverify_service import YouVerifyService
    
    kyc = get_object_or_404(StaffKYC, id=kyc_id)
    
    if kyc.kyc_status == 'verified':
        messages.info(request, "This KYC is already verified.")
        return redirect('review_staff_kyc', kyc_id=kyc_id)
    
    # Initialize YouVerify service
    youverify = YouVerifyService()
    
    # Check if API is configured
    if not youverify.is_configured():
        messages.error(request, "YouVerify API is not configured. Please add YOUVERIFY_API_KEY to your .env file.")
        return redirect('review_staff_kyc', kyc_id=kyc_id)
    
    # Check if there's anything to verify
    if not kyc.nin and not kyc.bvn:
        messages.warning(request, "No NIN or BVN provided. Cannot auto-verify.")
        return redirect('review_staff_kyc', kyc_id=kyc_id)
    
    verification_results = []
    all_passed = True
    
    # Get date of birth from staff profile
    dob = kyc.staff_profile.date_of_birth.strftime('%Y-%m-%d') if kyc.staff_profile.date_of_birth else None
    
    # Verify NIN if provided
    if kyc.nin:
        nin_result = youverify.verify_nin(
            nin=kyc.nin,
            first_name=kyc.staff_profile.user.first_name,
            last_name=kyc.staff_profile.user.last_name,
            date_of_birth=dob
        )
        message = nin_result.get('message') or nin_result.get('error', 'Verification failed')
        verification_results.append(f"NIN: {message}")
        if not nin_result.get('success', False):
            all_passed = False
    
    # Verify BVN if provided
    if kyc.bvn:
        bvn_result = youverify.verify_bvn(
            bvn=kyc.bvn,
            first_name=kyc.staff_profile.user.first_name,
            last_name=kyc.staff_profile.user.last_name,
            date_of_birth=dob
        )
        message = bvn_result.get('message') or bvn_result.get('error', 'Verification failed')
        verification_results.append(f"BVN: {message}")
        if not bvn_result.get('success', False):
            all_passed = False
    
    # Update KYC status based on verification results
    if all_passed and verification_results:
        kyc.kyc_status = 'verified'
        kyc.kyc_verified_at = timezone.now()
        kyc.verified_by = request.user
        kyc.kyc_rejection_reason = None
        kyc.save()
        
        # Create notification for user
        notification = Notification.objects.create(
            tenant=kyc.staff_profile.tenant,
            title="KYC Auto-Verified",
            message=f"Your KYC has been automatically verified and approved.",
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link='/profile/'
        )
        UserNotification.objects.create(
            user=kyc.staff_profile.user,
            tenant=kyc.staff_profile.tenant,
            notification=notification,
            dismissed=False
        )
        
        # Send approval email
        send_kyc_approval_email(kyc.staff_profile.user, 'Staff KYC', approved=True)
        
        messages.success(request, f"✅ Auto-verification successful! {' | '.join(verification_results)}")
    else:
        messages.error(request, f"❌ Auto-verification failed: {' | '.join(verification_results)}")
    
    return redirect('review_staff_kyc', kyc_id=kyc_id)


@kyc_verification_permission_required
def auto_verify_company_kyb(request, kyb_id):
    """Auto-verify company KYB using YouVerify API"""
    from documents.services.youverify_service import YouVerifyService
    
    kyb = get_object_or_404(CompanyKYB, id=kyb_id)
    
    if kyb.kyb_status == 'verified':
        messages.info(request, "This KYB is already verified.")
        return redirect('review_company_kyb', kyb_id=kyb_id)
    
    # Initialize YouVerify service
    youverify = YouVerifyService()
    
    # Check if API is configured
    if not youverify.is_configured():
        messages.error(request, "YouVerify API is not configured. Please add YOUVERIFY_API_KEY to your .env file.")
        return redirect('review_company_kyb', kyb_id=kyb_id)
    
    # Check if there's anything to verify
    if not kyb.tin and not kyb.company_profile.reg_number:
        messages.warning(request, "No TIN or CAC/RC Number provided. Cannot auto-verify.")
        return redirect('review_company_kyb', kyb_id=kyb_id)
    
    verification_results = []
    all_passed = True
    
    # Verify TIN if provided
    if kyb.tin:
        tin_result = youverify.verify_tin(
            tin=kyb.tin,
            company_name=kyb.company_profile.company_name
        )
        message = tin_result.get('message') or tin_result.get('error', 'Verification failed')
        verification_results.append(f"TIN: {message}")
        if not tin_result.get('success', False):
            all_passed = False
    
    # Verify CAC if RC number is available
    if kyb.company_profile.reg_number:
        cac_result = youverify.verify_cac(
            rc_number=kyb.company_profile.reg_number,
            company_name=kyb.company_profile.company_name
        )
        message = cac_result.get('message') or cac_result.get('error', 'Verification failed')
        verification_results.append(f"CAC: {message}")
        if not cac_result.get('success', False):
            all_passed = False
    
    # Update KYB status based on verification results
    if all_passed and verification_results:
        kyb.kyb_status = 'verified'
        kyb.kyb_verified_at = timezone.now()
        kyb.verified_by = request.user
        kyb.kyb_rejection_reason = None
        kyb.save()
        
        # Send approval email to tenant admins and create notifications
        tenant_admins = CustomUser.objects.filter(
            tenant=kyb.company_profile.tenant,
            roles__name='Admin',
            is_active=True
        )
        for admin in tenant_admins:
            # Create notification
            notification = Notification.objects.create(
                tenant=kyb.company_profile.tenant,
                title="Company KYB Auto-Verified",
                message=f"The KYB for {kyb.company_profile.company_name} has been automatically verified and approved.",
                type=Notification.NotificationType.ALERT,
                is_active=True,
                link='/admins/company-profile/'
            )
            UserNotification.objects.create(
                user=admin,
                tenant=kyb.company_profile.tenant,
                notification=notification,
                dismissed=False
            )
            send_kyb_approval_email(admin, kyb.company_profile, approved=True)
        
        messages.success(request, f"✅ Auto-verification successful! {' | '.join(verification_results)}")
    else:
        messages.error(request, f"❌ Auto-verification failed: {' | '.join(verification_results)}")
    
    return redirect('review_company_kyb', kyb_id=kyb_id)


# Helper functions
def send_kyc_approval_email(user, kyc_type, approved=True, reason=None):
    """Send email notification when KYC is approved/rejected"""
    try:
        if approved:
            subject = f"Your {kyc_type} has been Approved"
            message = f"""
            Dear {user.username},
            
            Your {kyc_type} has been successfully verified and approved.
            
            You can now access all features of the platform.
            
            Thank you for completing your verification.
            
            Best regards,
            The Team
            """
        else:
            subject = f"Your {kyc_type} has been Rejected"
            message = f"""
            Dear {user.username},
            
            Unfortunately, your {kyc_type} submission has been rejected.
            
            Reason: {reason}
            
            Please review the information and resubmit with the correct details.
            
            If you have any questions, please contact support.
            
            Best regards,
            The Team
            """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
    except Exception as e:
        print(f"Error sending KYC approval email: {e}")


def send_kyb_approval_email(user, company_profile, approved=True, reason=None):
    """Send email notification when KYB is approved/rejected"""
    try:
        if approved:
            subject = f"Company KYB Approved - {company_profile.company_name}"
            message = f"""
            Dear {user.username},
            
            The KYB verification for {company_profile.company_name} has been successfully approved.
            
            Your company can now access all business features of the platform.
            
            Thank you for completing your business verification.
            
            Best regards,
            The Team
            """
        else:
            subject = f"Company KYB Rejected - {company_profile.company_name}"
            message = f"""
            Dear {user.username},
            
            Unfortunately, the KYB submission for {company_profile.company_name} has been rejected.
            
            Reason: {reason}
            
            Please review the information and resubmit with the correct details.
            
            If you have any questions, please contact support.
            
            Best regards,
            The Team
            """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True,
        )
    except Exception as e:
        print(f"Error sending KYB approval email: {e}")
