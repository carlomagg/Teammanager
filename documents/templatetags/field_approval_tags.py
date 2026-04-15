# documents/templatetags/field_approval_tags.py
from django import template
from django.contrib.contenttypes.models import ContentType
from documents.kyc_field_approval_models import FieldApprovalStatus

register = template.Library()


@register.simple_tag
def get_field_approval(instance, field_name):
    """Get the approval status for a specific field"""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        approval = FieldApprovalStatus.objects.filter(
            content_type=content_type,
            object_id=instance.pk,
            field_name=field_name
        ).first()
        return approval
    except Exception:
        return None


@register.simple_tag
def get_field_status(instance, field_name):
    """Get just the status string for a field"""
    approval = get_field_approval(instance, field_name)
    return approval.status if approval else 'pending'


@register.simple_tag
def get_field_rejection_reason(instance, field_name):
    """Get the rejection reason for a field"""
    approval = get_field_approval(instance, field_name)
    return approval.rejection_reason if approval and approval.status == 'rejected' else None


@register.simple_tag
def get_content_type_id(instance):
    """Get the content type ID for an instance"""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        return content_type.id
    except Exception:
        return None


@register.filter
def field_approval_badge_class(status):
    """Return Bootstrap badge class for field status"""
    if status == 'approved':
        return 'bg-success'
    elif status == 'rejected':
        return 'bg-danger'
    else:
        return 'bg-warning text-dark'


@register.filter
def field_approval_icon(status):
    """Return Bootstrap icon for field status"""
    if status == 'approved':
        return 'bi-check-circle-fill'
    elif status == 'rejected':
        return 'bi-x-circle-fill'
    else:
        return 'bi-clock'


@register.inclusion_tag('documents/_field_approval_buttons.html')
def render_field_approval(instance, field_name, field_label, field_value=None, field_type='text', can_review=False):
    """Render field approval buttons and status"""
    content_type = ContentType.objects.get_for_model(instance)
    approval = get_field_approval(instance, field_name)
    
    # Check if this is a loan instance to use loan-specific URLs
    loan_id = None
    if content_type.model == 'conferenceloan':
        loan_id = instance.pk
    
    return {
        'field_name': field_name,
        'field_label': field_label,
        'field_value': field_value,
        'field_type': field_type,
        'field_status': approval.status if approval else 'pending',
        'rejection_reason': approval.rejection_reason if approval else None,
        'content_type_id': content_type.id,
        'object_id': instance.pk,
        'loan_id': loan_id,
        'can_review': can_review,
    }
