from django.core.management.base import BaseCommand
from reports.models import Invoice
from reports.tasks import transmit_invoice_to_etims_task

class Command(BaseCommand):
    help = "Finds all FAILED or PENDING eTIMS invoices and re-queues them into the background Celery task pool."

    def handle(self, *args, **options):
        self.stdout.write("Scanning database for un-synchronized KRA invoices...")
        
        # Target records that have not been successfully marked as TRANSMITTED
        backlog_invoices = Invoice.objects.filter(etims_status__in=["PENDING", "FAILED"])
        total_count = backlog_invoices.count()

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("Perfect! All invoices match KRA eTIMS tracking metrics successfully."))
            return

        self.stdout.write(f"Found {total_count} records to sync. Launching asynchronous task queues...")
        
        queued_count = 0
        for invoice in backlog_invoices:
            # Trigger celery task pool asynchronously via Redis
            transmit_invoice_to_etims_task.delay(invoice.id)
            queued_count += 1
            self.stdout.write(f"Queued Invoice #{invoice.id} to Celery worker stream.")

        self.stdout.write(self.style.SUCCESS(f"Complete! Dispatched {queued_count} transactions to Redis."))
