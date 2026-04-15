# documents/kyc_field_approval_views.py
"""
Views for field-level approval/rejection of KYC/KYB submissions
"""
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .kyc_field_approval_models import FieldApprovalStatus
from .kyc_models import UserKYC, StaffKYC, CompanyKYB, CompanyDirector


def can_review_kyc(user):
    """Check if user has permission to review KYC/KYB"""
    return user.has_perm('documents.verify_kyc') or user.is_superuser


@login_required
@require_POST
def approve_field(request, content_type_id, object_id, field_name):
    """Approve a specific field"""
    if not can_review_kyc(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to approve fields'
        }, status=403)
    
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    
    # Get or create the field approval status
    field_approval, created = FieldApprovalStatus.objects.get_or_create(
        content_type=content_type,
        object_id=object_id,
        field_name=field_name,
        defaults={
            'field_label': field_name.replace('_', ' ').title(),
            'field_type': 'file' if 'file' in field_name else 'text',
        }
    )
    
    # Approve the field
    field_approval.approve(request.user)
    
    # Check if all fields are approved
    all_approvals = FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=object_id
    )
    
    all_approved = all_approvals.filter(status='approved').count() == all_approvals.count()
    
    # Get the instance for notifications
    model_class = content_type.model_class()
    instance = model_class.objects.get(pk=object_id)
    
    # Send notification to user about field approval
    send_field_approval_notification(instance, field_approval)
    
    # If all fields approved, update the main KYC/KYB status
    if all_approved:
        if hasattr(instance, 'kyc_status'):
            instance.kyc_status = 'verified'
            instance.kyc_verified_at = timezone.now()
            instance.verified_by = request.user
        elif hasattr(instance, 'kyb_status'):
            instance.kyb_status = 'verified'
            instance.kyb_verified_at = timezone.now()
            instance.verified_by = request.user
        
        instance.save()
        
        # Send notification about full approval
        send_full_approval_notification(instance)
    
    return JsonResponse({
        'success': True,
        'field_name': field_name,
        'status': 'approved',
        'all_approved': all_approved,
        'message': f'{field_approval.field_label} approved successfully'
    })


@login_required
@require_POST
def reject_field(request, content_type_id, object_id, field_name):
    """Reject a specific field with a reason"""
    if not can_review_kyc(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to reject fields'
        }, status=403)
    
    rejection_reason = request.POST.get('rejection_reason', '').strip()
    if not rejection_reason:
        return JsonResponse({
            'success': False,
            'error': 'Rejection reason is required'
        }, status=400)
    
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    
    # Get or create the field approval status
    field_approval, created = FieldApprovalStatus.objects.get_or_create(
        content_type=content_type,
        object_id=object_id,
        field_name=field_name,
        defaults={
            'field_label': field_name.replace('_', ' ').title(),
            'field_type': 'file' if 'file' in field_name else 'text',
        }
    )
    
    # Reject the field
    field_approval.reject(rejection_reason, request.user)
    
    # Update the main KYC/KYB status to indicate rejection
    model_class = content_type.model_class()
    instance = model_class.objects.get(pk=object_id)
    
    # Send notification to user about field rejection
    send_field_rejection_notification(instance, field_approval, rejection_reason)
    
    return JsonResponse({
        'success': True,
        'field_name': field_name,
        'status': 'rejected',
        'rejection_reason': rejection_reason,
        'message': f'{field_approval.field_label} rejected'
    })


@login_required
@require_POST
def approve_all_fields(request, content_type_id, object_id):
    """Approve all fields at once (existing functionality preserved)"""
    if not can_review_kyc(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to approve'
        }, status=403)
    
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    model_class = content_type.model_class()
    instance = get_object_or_404(model_class, pk=object_id)
    
    # Create field approvals if they don't exist
    if hasattr(instance, 'get_or_create_field_approvals'):
        instance.get_or_create_field_approvals()
    
    # Approve all fields
    FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=object_id
    ).update(
        status='approved',
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
        rejection_reason=None
    )
    
    # Update main status
    if hasattr(instance, 'kyc_status'):
        instance.kyc_status = 'verified'
        instance.kyc_verified_at = timezone.now()
        instance.verified_by = request.user
        instance.kyc_rejection_reason = None
    elif hasattr(instance, 'kyb_status'):
        instance.kyb_status = 'verified'
        instance.kyb_verified_at = timezone.now()
        instance.verified_by = request.user
        instance.kyb_rejection_reason = None
    
    instance.save()
    
    # Send notification about full approval
    send_full_approval_notification(instance)
    
    messages.success(request, 'All fields approved successfully')
    
    return JsonResponse({
        'success': True,
        'message': 'All fields approved successfully',
        'redirect_url': instance.get_absolute_url() if hasattr(instance, 'get_absolute_url') else None
    })


def send_field_approval_notification(instance, field_approval):
    """Send notification to user about field approval"""
    from documents.models import Notification, UserNotification
    from django.urls import reverse
    
    # Determine the user to notify, tenant, and link
    user = None
    tenant = None
    notification_type = None
    view_link = None
    
    if hasattr(instance, 'user_profile'):
        user = instance.user_profile.user
        tenant = None  # Personal user has no tenant
        notification_type = 'User KYC'
        view_link = reverse('kyc_status')
    elif hasattr(instance, 'staff_profile'):
        user = instance.staff_profile.user
        tenant = instance.staff_profile.tenant
        notification_type = 'Staff KYC'
        view_link = reverse('kyc_status')
    elif hasattr(instance, 'company_profile'):
        # For company KYB, notify tenant admins
        from documents.models import CustomUser
        tenant = instance.company_profile.tenant
        admins = CustomUser.objects.filter(
            tenant=tenant,
            roles__name='Admin',
            is_active=True
        )
        notification_type = 'Company KYB'
        view_link = reverse('kyc_status')
    
    if not user and not (hasattr(instance, 'company_profile')):
        return
    
    # Create notification message
    notification_message = (
        f"Good news! Your {notification_type} field '{field_approval.field_label}' has been approved. "
        f"You're one step closer to completing your verification."
    )
    
    try:
        # Create notification
        notification = Notification.objects.create(
            tenant=tenant,
            title=f"{notification_type} Field Approved: {field_approval.field_label}",
            message=notification_message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link=view_link
        )
        
        # Create user notification(s)
        if hasattr(instance, 'company_profile'):
            # Notify all admins for company KYB
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=tenant,
                    notification=notification,
                    dismissed=False
                )
                print(f"Notification sent to admin {admin.username} for approved KYB field: {field_approval.field_label}")
        else:
            # Notify single user for User/Staff KYC
            UserNotification.objects.create(
                user=user,
                tenant=tenant,
                notification=notification,
                dismissed=False
            )
            print(f"Notification sent to {user.username} for approved {notification_type} field: {field_approval.field_label}")
            
    except Exception as e:
        # Log error but don't fail the approval
        print(f"Failed to create approval notification: {e}")


def send_full_approval_notification(instance):
    """Send notification when all fields are approved"""
    from documents.models import Notification, UserNotification
    from django.urls import reverse
    
    # Determine the user to notify, tenant, and link
    user = None
    tenant = None
    notification_type = None
    view_link = None
    
    if hasattr(instance, 'user_profile'):
        user = instance.user_profile.user
        tenant = None
        notification_type = 'User KYC'
        view_link = reverse('kyc_status')
    elif hasattr(instance, 'staff_profile'):
        user = instance.staff_profile.user
        tenant = instance.staff_profile.tenant
        notification_type = 'Staff KYC'
        view_link = reverse('kyc_status')
    elif hasattr(instance, 'company_profile'):
        from documents.models import CustomUser
        tenant = instance.company_profile.tenant
        admins = CustomUser.objects.filter(
            tenant=tenant,
            roles__name='Admin',
            is_active=True
        )
        notification_type = 'Company KYB'
        view_link = reverse('kyc_status')
    
    if not user and not (hasattr(instance, 'company_profile')):
        return
    
    notification_message = (
        f"Congratulations! Your {notification_type} has been fully verified. "
        f"All fields have been approved and you now have full access to all features."
    )
    
    try:
        notification = Notification.objects.create(
            tenant=tenant,
            title=f"{notification_type} Fully Verified!",
            message=notification_message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link=view_link
        )
        
        if hasattr(instance, 'company_profile'):
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=tenant,
                    notification=notification,
                    dismissed=False
                )
        else:
            UserNotification.objects.create(
                user=user,
                tenant=tenant,
                notification=notification,
                dismissed=False
            )
            
    except Exception as e:
        print(f"Failed to create full approval notification: {e}")


def send_field_rejection_notification(instance, field_approval, rejection_reason):
    """Send notification to user about field rejection"""
    from documents.models import Notification, UserNotification
    from django.urls import reverse
    
    # Determine the user to notify, tenant, and resubmission link
    user = None
    tenant = None
    notification_type = None
    resubmit_link = None
    
    if hasattr(instance, 'user_profile'):
        user = instance.user_profile.user
        tenant = None  # Personal user has no tenant
        notification_type = 'User KYC'
        resubmit_link = reverse('complete_user_kyc')
    elif hasattr(instance, 'staff_profile'):
        user = instance.staff_profile.user
        tenant = instance.staff_profile.tenant
        notification_type = 'Staff KYC'
        resubmit_link = reverse('complete_staff_kyc')
    elif hasattr(instance, 'company_profile'):
        # For company KYB, notify tenant admins
        from documents.models import CustomUser
        tenant = instance.company_profile.tenant
        admins = CustomUser.objects.filter(
            tenant=tenant,
            roles__name='Admin',
            is_active=True
        )
        notification_type = 'Company KYB'
        resubmit_link = reverse('complete_company_kyb')
    
    if not user and not (hasattr(instance, 'company_profile')):
        return
    
    # Create notification message with resubmission link
    notification_message = (
        f"Your {notification_type} field '{field_approval.field_label}' has been rejected. "
        f"Reason: {rejection_reason}. "
        f"Please update and resubmit this information by visiting your KYC/KYB page."
    )
    
    try:
        # Create notification
        notification = Notification.objects.create(
            tenant=tenant,
            title=f"{notification_type} Field Rejected: {field_approval.field_label}",
            message=notification_message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link=resubmit_link  # Link to resubmission page
        )
        
        # Create user notification(s)
        if hasattr(instance, 'company_profile'):
            # Notify all admins for company KYB
            for admin in admins:
                UserNotification.objects.create(
                    user=admin,
                    tenant=tenant,
                    notification=notification,
                    dismissed=False
                )
                print(f"Notification sent to admin {admin.username} for rejected KYB field: {field_approval.field_label}")
        else:
            # Notify single user for User/Staff KYC
            UserNotification.objects.create(
                user=user,
                tenant=tenant,
                notification=notification,
                dismissed=False
            )
            print(f"Notification sent to {user.username} for rejected {notification_type} field: {field_approval.field_label}")
            
    except Exception as e:
        # Log error but don't fail the rejection
        print(f"Failed to create notification: {e}")


@login_required
def get_field_status(request, content_type_id, object_id):
    """Get approval status for all fields (AJAX endpoint)"""
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    
    field_approvals = FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=object_id
    )
    
    fields_data = []
    for approval in field_approvals:
        fields_data.append({
            'field_name': approval.field_name,
            'field_label': approval.field_label,
            'field_type': approval.field_type,
            'status': approval.status,
            'rejection_reason': approval.rejection_reason,
            'reviewed_by': approval.reviewed_by.get_full_name() if approval.reviewed_by else None,
            'reviewed_at': approval.reviewed_at.isoformat() if approval.reviewed_at else None,
        })
    
    return JsonResponse({
        'success': True,
        'fields': fields_data
    })
