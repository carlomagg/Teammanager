"""
Custom validators for CRM app.
"""
from django.core.exceptions import ValidationError
import re


def validate_phone_number(phone):
    """
    Validate phone number format.
    Allows digits, spaces, hyphens, plus signs, and parentheses.
    
    Args:
        phone (str): Phone number to validate
        
    Raises:
        ValidationError: If phone number format is invalid
    """
    if not phone:
        return phone
    
    # Pattern allows: +234-xxx-xxxx, (234) xxx-xxxx, +234 xxx xxxx, etc.
    pattern = r'^[\d\s\-\+\(\)]+$'
    
    if not re.match(pattern, phone):
        raise ValidationError(
            'Phone number can only contain digits, spaces, hyphens, plus signs, and parentheses.',
            code='invalid_phone'
        )
    
    return phone
