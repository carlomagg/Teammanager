"""
Reusable view mixins for CRM app.
"""
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator


class TenantContextMixin:
    """
    Mixin to extract tenant and user context from request.
    Eliminates duplicate code across all views.
    """
    def get_tenant_context(self, request):
        """Extract tenant and user from request"""
        return {
            'tenant': request.effective_tenant,
            'user': request.effective_user
        }


class CRMCreateViewMixin(TenantContextMixin):
    """
    Mixin for CRM create views.
    Handles common create logic: form processing, tenant/user assignment, messages.
    
    Usage:
        def opportunity_create(request):
            return CRMCreateViewMixin().handle_create(
                request=request,
                form_class=OpportunityForm,
                template_name='crm/opportunity_form.html',
                success_url_name='crm:opportunity_detail',
                object_name='Opportunity'
            )
    """
    
    def handle_create(self, request, form_class, template_name, success_url_name, object_name):
        """
        Generic create handler.
        
        Args:
            request: Django request object
            form_class: Form class to use
            template_name: Template to render
            success_url_name: URL name to redirect to on success
            object_name: Name of object for success message
        """
        from django.shortcuts import render
        
        context = self.get_tenant_context(request)
        tenant = context['tenant']
        user = context['user']
        
        if request.method == 'POST':
            form = form_class(request.POST, request=request)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.tenant = tenant
                obj.created_by = user
                obj.save()
                
                # Save many-to-many relationships if form has save_m2m
                if hasattr(form, 'save_m2m'):
                    form.save_m2m()
                
                messages.success(request, f'{object_name} "{obj}" created successfully.')
                return redirect(success_url_name, pk=obj.pk)
            else:
                # Debug: Print form errors to console
                print(f"Form validation errors: {form.errors}")
                print(f"Form non-field errors: {form.non_field_errors()}")
                messages.error(request, 'Please correct the errors below.')
        else:
            form = form_class(request=request)
        
        return render(request, template_name, {
            'form': form,
            'action': 'Create',
        })


class CRMUpdateViewMixin(TenantContextMixin):
    """
    Mixin for CRM update views.
    Handles common update logic: object retrieval, form processing, messages.
    """
    
    def handle_update(self, request, pk, model_class, form_class, template_name, 
                     success_url_name, object_name):
        """
        Generic update handler.
        
        Args:
            request: Django request object
            pk: Primary key of object to update
            model_class: Model class
            form_class: Form class to use
            template_name: Template to render
            success_url_name: URL name to redirect to on success
            object_name: Name of object for success message
        """
        from django.shortcuts import render
        
        context = self.get_tenant_context(request)
        tenant = context['tenant']
        user = context['user']
        
        # Get object with tenant filtering
        obj = get_object_or_404(
            model_class.objects.get_assigned_or_all(user, tenant),
            pk=pk
        )
        
        if request.method == 'POST':
            form = form_class(request.POST, instance=obj, request=request)
            if form.is_valid():
                obj = form.save(commit=False)
                obj.updated_by = user
                obj.save()
                
                # Save many-to-many relationships if form has save_m2m
                if hasattr(form, 'save_m2m'):
                    form.save_m2m()
                
                messages.success(request, f'{object_name} "{obj}" updated successfully.')
                return redirect(success_url_name, pk=obj.pk)
            else:
                messages.error(request, 'Please correct the errors below.')
        else:
            form = form_class(instance=obj, request=request)
        
        return render(request, template_name, {
            'form': form,
            'action': 'Update',
            object_name.lower(): obj,
        })


class CRMDeleteViewMixin(TenantContextMixin):
    """
    Mixin for CRM delete views.
    Handles common delete logic: object retrieval, deletion, messages.
    """
    
    def handle_delete(self, request, pk, model_class, template_name, 
                     success_url_name, list_url_name, object_name):
        """
        Generic delete handler.
        
        Args:
            request: Django request object
            pk: Primary key of object to delete
            model_class: Model class
            template_name: Template to render for confirmation
            success_url_name: URL name to redirect to on success
            list_url_name: URL name for list view
            object_name: Name of object for success message
        """
        from django.shortcuts import render
        
        context = self.get_tenant_context(request)
        tenant = context['tenant']
        user = context['user']
        
        # Get object with tenant filtering
        obj = get_object_or_404(
            model_class.objects.get_assigned_or_all(user, tenant),
            pk=pk
        )
        
        if request.method == 'POST':
            obj_str = str(obj)
            obj.delete()
            messages.success(request, f'{object_name} "{obj_str}" deleted successfully.')
            return redirect(list_url_name)
        
        return render(request, template_name, {
            object_name.lower(): obj,
        })
