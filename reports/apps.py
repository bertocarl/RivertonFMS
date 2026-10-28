from django.apps import AppConfig

class ReportsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reports'

    def ready(self):
        # Implicitly load signal listeners into runtime operational memory
        import reports.signals
