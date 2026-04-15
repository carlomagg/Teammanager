from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import render
from ..rba_decorators import is_hr
from ..helper_funcs.staff_tenant_or_user import enforce_tenant_or_personal_access, get_context_filter_kwargs

@login_required
# @user_passes_test(is_hr)
def hr_dashboard(request):
    denied = enforce_tenant_or_personal_access(request)
    if denied:
        return denied

    base_filter = get_context_filter_kwargs(request)
    is_tenant_mode = 'tenant' in base_filter and base_filter['tenant'] is not None

    if is_tenant_mode:
        if not user_passes_test(is_hr)(request):
            return render(request, 'tenant_error.html', {'error_code': '401','message': 'You are not authorized to carry out this action.'})
    
    return render(request, 'hr/hr_dashboard.html')
