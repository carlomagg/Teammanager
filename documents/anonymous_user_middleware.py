"""
Middleware to add subscription_status attribute to AnonymousUser
to prevent AttributeError when templates try to access it
"""
from django.contrib.auth.models import AnonymousUser


class AnonymousUserAttributeMiddleware:
    """
    Add subscription_status and other attributes to AnonymousUser
    to prevent template errors
    """
    def __init__(self, get_response):
        self.get_response = get_response
        # Add attributes to AnonymousUser class
        if not hasattr(AnonymousUser, 'subscription_status'):
            AnonymousUser.subscription_status = 'inactive'
        if not hasattr(AnonymousUser, 'subscription_end_date'):
            AnonymousUser.subscription_end_date = None
        if not hasattr(AnonymousUser, 'subscription_plan'):
            AnonymousUser.subscription_plan = None
        if not hasattr(AnonymousUser, 'is_personal'):
            AnonymousUser.is_personal = False
        if not hasattr(AnonymousUser, 'roles'):
            # Add an empty roles manager to prevent AttributeError
            from documents.models import Role
            
            class EmptyRolesManager:
                def all(self):
                    return Role.objects.none()
                
                def exists(self):
                    return False
                
                def filter(self, *args, **kwargs):
                    return Role.objects.none()
                
                def count(self):
                    return 0
            
            AnonymousUser.roles = EmptyRolesManager()

    def __call__(self, request):
        response = self.get_response(request)
        return response
