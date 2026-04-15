"""
SEO and Utility Views for TeamManager

This module contains views for SEO optimization and general utilities:
- robots_txt: Dynamically generated robots.txt for search engine crawlers
"""

from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def robots_txt(request):
    """
    Generate robots.txt file dynamically.
    
    This file instructs search engine crawlers which pages to index
    and which to avoid. It protects private/authenticated areas while
    allowing public pages to be discovered.
    
    Structure:
    - Allow: Public pages (home, contact, public posts)
    - Disallow: All authenticated/private areas
    - Sitemap: Reference to sitemap.xml for crawler efficiency
    
    Args:
        request: HTTP request object
        
    Returns:
        HttpResponse with robots.txt content (text/plain)
    """
    host = request.get_host().lower()
    is_subdomain = host.count(".") >= 2

    if is_subdomain:
        # 🚫 Block ALL tenant subdomains
        lines = [
            "User-agent: *",
            "Disallow: /",
        ]
    else:
        # ✅ Main domain rules
        lines = [
            "User-agent: *",
            "",
            "# Allow public pages",
            "Allow: /$",
            "Allow: /contact-support/$",
            "Allow: /conference-board/post/$",
            "Allow: /job-board/$",
            "Allow: /vacancy/post/$",
            "Allow: /share/$",
            "",
            "# Disallow all private/authenticated areas",
            "Disallow: /admin/",
            "Disallow: /admins/",
            "Disallow: /dashboard/",
            "Disallow: /conference/",
            "Disallow: /tasks/",
            "Disallow: /folders/",
            "Disallow: /staff/",
            "Disallow: /users/",
            "Disallow: /hr/",
            "Disallow: /vacancy/",
            "Disallow: /interview/",
            "Disallow: /tracking/",
            "Disallow: /calendar/",
            "Disallow: /notifications/",
            "Disallow: /api/",
            "Disallow: /accounts/",
            "Disallow: /tenants/",
            "Disallow: /ckeditor/",
            "Disallow: /oauth2callback/",
            "",
            "# Sitemap location for efficient crawling",
            f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
        ]
    
    return HttpResponse("\n".join(lines), content_type="text/plain")
