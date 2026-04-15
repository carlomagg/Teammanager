# Custom errors
from django.shortcuts import render

def custom_404(request, exception):
    return render(request, '404.html', {'subdomain': request.get_host().split('.')[0], 'message': str(exception)}, status=404)

def custom_403(request, exception):
    return render(request, '403.html', {'message': str(exception)}, status=403)

def custom_400(request, exception):
    return render(request, '400.html', {'message': str(exception)}, status=400)

def custom_500(request):
    return render(request, '500.html', status=500)