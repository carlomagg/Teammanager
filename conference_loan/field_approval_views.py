# conference_loan/field_approval_views.py
"""
Views for field-level approval/rejection of loan applications
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from documents.kyc_field_approval_models import FieldApprovalStatus
from .models import ConferenceLoan


def can_review_loans(user):
    """Check if user can review and approve/reject loans"""
    return user.is_superuser or (user.tenant and user.tenant.admin == user)


@login_required
@require_POST
def approve_loan_field(request, loan_id, field_name):
    """Approve a specific loan field"""
    loan = get_object_or_404(ConferenceLoan, pk=loan_id)
    
    if not can_review_loans(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to approve loan fields'
        }, status=403)
    
    if loan.tenant != request.user.tenant and not request.user.is_superuser:
        return JsonResponse({
            'success': False,
            'error': 'You can only review loans for your organization'
        }, status=403)
    
    content_type = ContentType.objects.get_for_model(ConferenceLoan)
    
    # Get or create the field approval status
    field_approval, created = FieldApprovalStatus.objects.get_or_create(
        content_type=content_type,
        object_id=loan.pk,
        field_name=field_name,
        defaults={
            'field_label': field_name.replace('_', ' ').title(),
            'field_type': 'file' if 'file' in field_name or field_name in ['guarantor_id', 'guarantor_signature'] else 'text',
        }
    )
    
    # Approve the field
    field_approval.approve(request.user)
    
    # Check if all fields are approved
    all_approvals = FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=loan.pk
    )
    
    all_approved = all_approvals.filter(status='approved').count() == all_approvals.count()
    has_rejections = all_approvals.filter(status='rejected').exists()
    
    # Send notification to applicant about field approval
    send_loan_field_approval_notification(loan, field_approval)
    
    # If all fields approved, send full approval notification
    if all_approved:
        send_loan_full_approval_notification(loan)
    
    return JsonResponse({
        'success': True,
        'field_name': field_name,
        'status': 'approved',
        'all_approved': all_approved,
        'has_rejections': has_rejections,
        'message': f'{field_approval.field_label} approved successfully'
    })


@login_required
@require_POST
def reject_loan_field(request, loan_id, field_name):
    """Reject a specific loan field with a reason"""
    loan = get_object_or_404(ConferenceLoan, pk=loan_id)
    
    if not can_review_loans(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to reject loan fields'
        }, status=403)
    
    if loan.tenant != request.user.tenant and not request.user.is_superuser:
        return JsonResponse({
            'success': False,
            'error': 'You can only review loans for your organization'
        }, status=403)
    
    rejection_reason = request.POST.get('rejection_reason', '').strip()
    if not rejection_reason:
        return JsonResponse({
            'success': False,
            'error': 'Rejection reason is required'
        }, status=400)
    
    content_type = ContentType.objects.get_for_model(ConferenceLoan)
    
    # Get or create the field approval status
    field_approval, created = FieldApprovalStatus.objects.get_or_create(
        content_type=content_type,
        object_id=loan.pk,
        field_name=field_name,
        defaults={
            'field_label': field_name.replace('_', ' ').title(),
            'field_type': 'file' if 'file' in field_name or field_name in ['guarantor_id', 'guarantor_signature'] else 'text',
        }
    )
    
    # Reject the field
    field_approval.reject(rejection_reason, request.user)
    
    # Send notification to applicant about field rejection
    send_loan_field_rejection_notification(loan, field_approval, rejection_reason)
    
    return JsonResponse({
        'success': True,
        'field_name': field_name,
        'status': 'rejected',
        'rejection_reason': rejection_reason,
        'message': f'{field_approval.field_label} rejected'
    })


@login_required
@require_POST
def approve_all_loan_fields(request, loan_id):
    """Approve all loan fields at once (existing functionality preserved)"""
    loan = get_object_or_404(ConferenceLoan, pk=loan_id)
    
    if not can_review_loans(request.user):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to approve loans'
        }, status=403)
    
    if loan.tenant != request.user.tenant and not request.user.is_superuser:
        return JsonResponse({
            'success': False,
            'error': 'You can only review loans for your organization'
        }, status=403)
    
    # Create field approvals if they don't exist
    loan.get_or_create_field_approvals()
    
    content_type = ContentType.objects.get_for_model(ConferenceLoan)
    
    # Approve all fields
    FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=loan.pk
    ).update(
        status='approved',
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
        rejection_reason=None
    )
    
    # Send notification about full approval
    send_loan_full_approval_notification(loan)
    
    messages.success(request, f'All fields for loan {loan.reference_number} approved successfully')
    
    return JsonResponse({
        'success': True,
        'message': 'All fields approved successfully',
        'redirect_url': loan.get_absolute_url()
    })


def send_loan_field_approval_notification(loan, field_approval):
    """Send notification to loan applicant about field approval"""
    from documents.models import Notification, UserNotification
    
    notification_message = (
        f"Good news! Your loan application {loan.reference_number}: "
        f"The field '{field_approval.field_label}' has been approved. "
        f"You're one step closer to loan approval."
    )
    
    try:
        # Get the loan detail URL
        from django.urls import reverse
        view_link = reverse('conference_loan:loan_detail', kwargs={'pk': loan.pk})
        
        # Create notification
        notification = Notification.objects.create(
            tenant=loan.tenant,
            title=f"Loan Field Approved: {field_approval.field_label}",
            message=notification_message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link=view_link
        )
        
        # Create user notification
        UserNotification.objects.create(
            user=loan.applicant,
            tenant=loan.tenant,
            notification=notification,
            dismissed=False
        )
        
        print(f"Notification sent to {loan.applicant.username} for approved field: {field_approval.field_label}")
    except Exception as e:
        # Log error but don't fail the approval
        print(f"Failed to create approval notification: {e}")


def send_loan_full_approval_notification(loan):
    """Send notification when all loan fields are approved"""
    from documents.models import Notification, UserNotification
    
    notification_message = (
        f"Congratulations! All fields in your loan application {loan.reference_number} have been approved. "
        f"Your application is now under final review."
    )
    
    try:
        from django.urls import reverse
        view_link = reverse('conference_loan:loan_detail', kwargs={'pk': loan.pk})
        
        notification = Notification.objects.create(
            tenant=loan.tenant,
            title=f"Loan Application Fully Approved: {loan.reference_number}",
            message=notification_message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link=view_link
        )
        
        UserNotification.objects.create(
            user=loan.applicant,
            tenant=loan.tenant,
            notification=notification,
            dismissed=False
        )
        
        print(f"Full approval notification sent to {loan.applicant.username} for loan: {loan.reference_number}")
    except Exception as e:
        print(f"Failed to create full approval notification: {e}")


def send_loan_field_rejection_notification(loan, field_approval, rejection_reason):
    """Send notification to loan applicant about field rejection"""
    from documents.models import Notification, UserNotification
    
    notification_message = (
        f"Your loan application {loan.reference_number}: "
        f"The field '{field_approval.field_label}' has been rejected. "
        f"Reason: {rejection_reason}. "
        f"Please update and resubmit this information."
    )
    
    try:
        # Get the loan edit URL
        from django.urls import reverse
        resubmit_link = reverse('conference_loan:loan_edit', kwargs={'pk': loan.pk})
        
        # Create notification
        notification = Notification.objects.create(
            tenant=loan.tenant,
            title=f"Loan Field Rejected: {field_approval.field_label}",
            message=notification_message,
            type=Notification.NotificationType.ALERT,
            is_active=True,
            link=resubmit_link  # Link to loan edit page
        )
        
        # Create user notification
        UserNotification.objects.create(
            user=loan.applicant,
            tenant=loan.tenant,
            notification=notification,
            dismissed=False
        )
        
        print(f"Notification sent to {loan.applicant.username} for rejected field: {field_approval.field_label}")
    except Exception as e:
        # Log error but don't fail the rejection
        print(f"Failed to create notification: {e}")


@login_required
def get_loan_field_status(request, loan_id):
    """Get approval status for all loan fields (AJAX endpoint)"""
    loan = get_object_or_404(ConferenceLoan, pk=loan_id)
    
    content_type = ContentType.objects.get_for_model(ConferenceLoan)
    field_approvals = FieldApprovalStatus.objects.filter(
        content_type=content_type,
        object_id=loan.pk
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
        'fields': fields_data,
        'summary': loan.get_field_approval_summary()
    })
