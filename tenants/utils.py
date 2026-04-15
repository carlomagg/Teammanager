from documents.models import CustomUser, RolePermission

def user_has_permission(user, permission_codename, tenant):
    return CustomUser.objects.filter(
        id=user.id,
        tenant=tenant,
        roles__rolepermission__permission__codename=permission_codename,
        roles__tenant=tenant
    ).exists()