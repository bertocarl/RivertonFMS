try:
    from .celery import app as celery_app  # noqa: F401
except ImportError:  # Celery is optional when USE_CELERY=0
    celery_app = None
