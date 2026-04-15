# Role-based Access functions for user_passes_test in:
# 'from django.contrib.auth.decorators import user_passes_test'

def is_tenant_owner(user, tenant):
    return tenant.admin == user

# check for admin role
def is_admin(user):
    # Superusers always have admin access
    if user.is_superuser:
        return True
    
    # Check if the user has Admin role
    for role in user.roles.all():
        if role.name == "Admin":
            return True
    return False

# check for HR role
def is_hr(user):
    # Superusers always have HR access
    if user.is_superuser:
        return True
    
    # Check if the user has HR role
    for role in user.roles.all():
        if role.name == "HR":
            return True
    return False

def is_conference_organizer(user):
    if user.is_superuser:
        return True
    for role in user.roles.all():
        if role.name == "Conference Organizer":
            return True
    return False