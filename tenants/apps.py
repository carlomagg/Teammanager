from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'
    
    def ready(self):
        """
        Production-ready signal registration
        This runs when Django starts in both development and production
        """
        try:
            # Import signals module
            import tenants.signals
            logger.info("✅ Subscription signals loaded successfully")
        except ImportError as e:
            logger.error(f"❌ Failed to load signals: {e}")
        except Exception as e:
            logger.error(f"❌ Unexpected error loading signals: {e}")
