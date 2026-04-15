from datetime import date, timedelta
from django.utils import timezone

from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Divide the value by the argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def subtract(value, arg):
    """Subtract argument from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add_days(value, days):
    """Add days to a date"""
    try:
        return value + timedelta(days=int(days))
    except (ValueError, TypeError):
        return value

@register.simple_tag
def calculate_discount(price, discount_percentage):
    """Calculate discounted price"""
    try:
        discount = float(price) * (float(discount_percentage) / 100)
        return float(price) - discount
    except (ValueError, TypeError):
        return price

@register.filter
def percentage_of(value, arg):
    """Calculate percentage of value"""
    try:
        return (float(value) / float(arg)) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def days_until(date):
    """Calculate days until a date"""
    from datetime import date
    try:
        delta = date - date.today()
        return delta.days
    except (ValueError, TypeError):
        return 0

@register.filter
def payment_method_icon(method):
    """Return Font Awesome icon for payment method"""
    icons = {
        'card': 'fa-credit-card',
        'bank_transfer': 'fa-university',
        'paypal': 'fa-paypal',
        'cash': 'fa-money-bill',
        'credit': 'fa-gift',
    }
    return icons.get(method, 'fa-credit-card')


@register.filter
def days_until(value):
    """Returns days until a date"""
    if not value:
        return None
    if isinstance(value, date):
        delta = value - timezone.now().date()
        return delta.days
    return None

@register.filter
def days_since(value):
    """Returns days since a date"""
    if not value:
        return None
    if isinstance(value, date):
        delta = timezone.now().date() - value
        return delta.days
    return None

@register.filter
def humanize_date_diff(value):
    """Human readable date difference"""
    if not value:
        return ""
    
    if isinstance(value, date):
        today = timezone.now().date()
        delta = value - today
        
        if delta.days == 0:
            return "Today"
        elif delta.days == 1:
            return "Tomorrow"
        elif delta.days == -1:
            return "Yesterday"
        elif delta.days > 0:
            if delta.days < 7:
                return f"In {delta.days} days"
            elif delta.days < 30:
                weeks = delta.days // 7
                return f"In {weeks} week{'s' if weeks > 1 else ''}"
            else:
                months = delta.days // 30
                return f"In {months} month{'s' if months > 1 else ''}"
        else:
            abs_days = abs(delta.days)
            if abs_days < 7:
                return f"{abs_days} days ago"
            elif abs_days < 30:
                weeks = abs_days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            else:
                months = abs_days // 30
                return f"{months} month{'s' if months > 1 else ''} ago"
    
    return str(value)


@register.filter
def add_days(value, days):
    """Add days to a date"""
    try:
        return value + timedelta(days=int(days))
    except (ValueError, TypeError, AttributeError):
        return value


# List of public paths that don't require subscription warnings
PUBLIC_PATHS = [
    '/tenants/quick-services/',
    '/job-board/',
    '/conference-board/',
    '/getting-started/',
    '/policies/',
    '/accounts/login/',
    '/accounts/logout/',
    '/register/',
    '/signup/',
    # Quick Service Items
    '/tickets/submit/',
    '/tickets/check/',
    '/tickets/submitted/',
    '/files/upload/public/',
    '/company-profile/',
    '/invoices/submit/',
    '/contact-support/',
    '/visitors/checkin/',
    '/visitors/checkout/',
    '/visitors/tag/',
]

PUBLIC_PATH_PREFIXES = [
    '/share/',
    '/p/',
    '/guest/dashboard/',
    '/vacancy/post/',
    '/conference/post/',
    '/bookings/book/',
    '/api/bookings/public-create/',
    '/memo/external/',
]

@register.simple_tag
def is_public_path(path):
    """
    Check if the current path is a public path that shouldn't show subscription warnings
    """
    if not path:
        return False
    
    # Check exact matches
    if path in PUBLIC_PATHS:
        return True
    
    # Check prefix matches
    for prefix in PUBLIC_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    
    return False
