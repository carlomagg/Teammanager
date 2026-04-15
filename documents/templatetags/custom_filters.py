from django import template

register = template.Library()

@register.filter
def extension_is_image(value):
    """Check if the file extension is an image (JPEG, PNG, JPG)."""
    if not value:
        return False
    extension = value.split('.')[-1].lower()
    return extension in ['jpg', 'jpeg', 'png']

@register.filter
def extension_is_pdf(value):
    """Check if the file extension is PDF."""
    if not value:
        return False
    extension = value.split('.')[-1].lower()
    return extension == 'pdf'

@register.filter
def underscore_to_space_upper(value):
    """Replaces underscores with spaces and converts to uppercase."""
    if isinstance(value, str):
        return value.replace('_', ' ').upper()
    return value

@register.filter(name='underscore_to_space')
def underscore_to_space(value):
    """Replaces underscores with spaces and converts to uppercase."""
    if isinstance(value, str):
        return value.replace('_', ' ')
    return value

@register.filter(name='dict_get')
def dict_get(obj, key):
    """Access dictionary or object attributes dynamically."""
    try:
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key)
    except:
        return ''
    
@register.filter
def get_file_extension(value):
    if isinstance(value, str):
        split_value = value.split('.')[-1]
    return split_value.lower()

@register.filter
def get_file_name(value):
    if isinstance(value, str):
        if '\\' in value:
            split_value = value.split('\\')[-1]
        elif '/' in value:
            split_value = value.split('/')[-1]
        else:
            split_value = value
        # split_value = value.split('\\')[-1] or value.split('/')[-1]
    return split_value

@register.filter
def subtract(value, arg):
    """
    Subtracts arg from value.
    Example: {{ 100|subtract:completion_percentage }}
    """
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value
    
@register.filter
def is_previewable(filename):
    return get_file_extension(filename) in ['pdf', 'jpeg', 'jpg', 'png']

@register.filter
def file_type(filename):
    ext = get_file_extension(filename)
    return 'pdf' if ext == 'pdf' else 'image' if ext in ['jpeg', 'jpg', 'png'] else 'other'

@register.filter
def file_icon(filename):
    ext = get_file_extension(filename)
    return {
        'jpeg': 'fa-file-image',
        'jpg': 'fa-file-image',
        'png': 'fa-file-image',
        'pdf': 'fa-file-pdf',
        'docx': 'fa-file-word',
        'csv': 'fa-file-csv',
        'xlsx': 'fa-file-excel'
    }.get(ext, 'fa-file')

@register.filter
def file_color(filename):
    ext = get_file_extension(filename)
    return {
        'jpeg': '#08428e',
        'jpg': '#08428e',
        'png': '#08428e',
        'pdf': '#a10707',
        'docx': '#2a6ec6',
        'csv': '#178939',
        'xlsx': '#178939'
    }.get(ext, '#0e0f11')

@register.filter
def format_teams(value, separator=', '):
    """
    Convert a ManyToManyField queryset (e.g., teams) to a string with names separated by the given separator.
    """
    if value is None:
        return "N/A"
    try:
        # Assuming teams is a queryset of related objects with a name field
        return separator.join(str(team) for team in value.all())
    except AttributeError:
        return "N/A"
    
@register.filter
def union(list1, list2):
    """Returns the union of two lists without duplicates based on IDs."""
    if not list1:
        return list2
    if not list2:
        return list1

    seen_ids = set()
    result = []

    for obj in list1 + list2:
        obj_id = getattr(obj, 'id', None)
        if obj_id not in seen_ids:
            seen_ids.add(obj_id)
            result.append(obj)
    return result

@register.filter
def page_obj_count(value):
    try:
        return value.paginator.count
    except AttributeError:
        return 0  # Handle cases where value is not a Page object
    

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def multiply(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def divide(value, arg):
    """Divide value by arg"""
    try:
        if float(arg) != 0:
            return float(value) / float(arg)
        return 0
    except (ValueError, TypeError):
        return value

@register.filter
def calculate_adjusted_amount(payment, wallet):
    """Calculate adjusted amount for a payment"""
    try:
        return wallet.calculate_adjusted_amount(payment.amount)
    except (AttributeError, TypeError):
        return payment.amount

@register.filter
def format_percentage(value):
    """Format a decimal as percentage"""
    try:
        return f"{float(value):.1f}%"
    except (ValueError, TypeError):
        return "0.0%"

@register.filter
def get_deduction(payment, wallet):
    """Get deduction amount for a payment"""
    try:
        adjusted = wallet.calculate_adjusted_amount(payment.amount)
        return payment.amount - adjusted
    except (AttributeError, TypeError):
        return 0

@register.filter
def get_deduction_percentage(payment, wallet):
    """Get deduction percentage for a payment"""
    try:
        adjusted = wallet.calculate_adjusted_amount(payment.amount)
        if payment.amount > 0:
            return ((payment.amount - adjusted) / payment.amount) * 100
        return 0
    except (AttributeError, TypeError):
        return 0

@register.filter
def filter_by_bank_verification_status(tenants, needs_verification=True):
    """
    Filter tenants by bank verification status
    Usage: {{ tenants|filter_by_bank_verification_status:False }}
    """
    filtered_tenants = []
    
    for tenant_wallet in tenants:
        try:
            profile = tenant_wallet.tenant.company_profile
            if needs_verification:
                # Return tenants that need verification
                if profile and profile.has_complete_bank_details() and not profile.bank_verified:
                    filtered_tenants.append(tenant_wallet)
            else:
                # Return tenants that are already verified
                if profile and profile.bank_verified:
                    filtered_tenants.append(tenant_wallet)
        except:
            continue
    
    return filtered_tenants

@register.filter
def user_is_admin(user):
    for role in user.roles.all():
        if role.name == "Admin":
            return True
    return False

@register.filter
def tier_count(tier):
    count = tier.participants.filter(status__in=['pending','accepted']).count()
    return count

@register.filter
def active_tier_order(conference):
    return conference.price_tiers.filter(is_active=True).order_by('price')

@register.filter
def check_admin_hr_receptionist(user):
    if user.roles.filter(name__in=['Admin', 'HR', 'Receptionist']).exists():
        return True
    return False

@register.filter
def get_item_payroll(custom_field_values, name):
    return custom_field_values.get(name)