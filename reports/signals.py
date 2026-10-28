from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Invoice
from .tasks import transmit_invoice_to_etims_task

@receiver(post_save, sender=Invoice)
def queue_etims_transmission(sender, instance, created, **kwargs):
    """
    Listens for new invoices and forwards them to Celery.
    Uses transaction.on_commit to ensure database records are fully saved before the worker picks it up.
    """
    if created and instance.etims_status == "PENDING":
        transaction.on_commit(
            lambda: transmit_invoice_to_etims_task.delay(instance.id)
        )
