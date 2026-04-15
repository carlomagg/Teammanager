"""
SEO Sitemaps Configuration for TeamManager

This module defines sitemaps for search engine crawlers to discover
and index public-facing pages while excluding private/authenticated content.

Sitemaps included:
- StaticViewSitemap: Public static pages (home, contact)
- PublicConferenceSitemap: Public conference posts
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from documents.models import Conference, Vacancy
from django.utils import timezone


class StaticViewSitemap(Sitemap):
    """
    Sitemap for static public pages that don't require authentication.
    
    These pages are safe to be indexed by search engines and provide
    general information about TeamManager.
    """
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        """
        Return list of public view names to include in sitemap.
        
        Only includes:
        - home: Landing page
        - contact_support: Public contact form
        - conference_board: Public conference board
        - job_board: Public job board
        """
        return ['home', 'contact_support', 'conference_board', 'job_board']

    def location(self, item):
        """Generate URL for each view name."""
        return reverse(item)


class PublicConferenceSitemap(Sitemap):
    """
    Sitemap for publicly accessible conference posts.
    
    Only includes conferences that have been published and are
    accessible via public URLs (conference_post view).
    """
    changefreq = 'daily'
    priority = 0.7

    def items(self):
        """
        Return queryset of public conferences.
        
        Filters:
        - Only conferences with start dates (published)
        - Limited to 100 most recent to avoid sitemap bloat
        - Ordered by creation date (newest first)
        """
        now = timezone.now()
        return Conference.objects.filter(
            start_date__isnull=False, end_date__gte=now, is_posted=True,
        ).order_by('-created_at')[:100]

    def lastmod(self, obj):
        """
        Return last modification date for conference.
        
        Uses updated_at if available, falls back to created_at.
        """
        return obj.updated_at if hasattr(obj, 'updated_at') else obj.created_at

    def location(self, obj):
        """Generate public URL for conference post."""
        return reverse('conference_post', kwargs={'conference_id': obj.id})
    

class PublicVacancySitemap(Sitemap):
    """
    Sitemap for publicly accessible vacancy posts.
    
    Only includes vacancies that have been published and are
    accessible via public URLs (vacancy_post view).
    """
    changefreq = 'daily'
    priority = 0.7

    def items(self):
        """
        Return queryset of public vacancies.
        
        Filters:
        - Only vacancies with start dates (published)
        - Limited to 100 most recent to avoid sitemap bloat
        - Ordered by creation date (newest first)
        """
        now = timezone.now()
        return Vacancy.objects.filter(
            status='active', is_shared=True
        ).order_by('-created_at')[:100]

    def lastmod(self, obj):
        """
        Return last modification date for vacancy.
        
        Uses updated_at if available, falls back to created_at.
        """
        return obj.updated_at if hasattr(obj, 'updated_at') else obj.created_at

    def location(self, obj):
        """Generate public URL for vacancy post."""
        return reverse('vacancy_post', kwargs={'conference_id': obj.share_token})
