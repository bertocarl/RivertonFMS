from django.utils import timezone

try:
    from celery import shared_task
except ImportError:  # Celery not installed: run inline so the app still works.

    def shared_task(func=None, **_kwargs):
        def decorate(f):
            f.delay = lambda *a, **k: f(*a, **k)
            return f

        return decorate(func) if func else decorate


@shared_task
def build_report(run_id):
    """Compute a report off the request thread and store the result on the run."""
    from .builders import BUILDERS
    from .models import ReportRun

    run = ReportRun.objects.get(pk=run_id)
    run.status = ReportRun.Status.RUNNING
    run.save(update_fields=["status"])
    try:
        run.result = BUILDERS[run.kind](run.report_date)
        run.status = ReportRun.Status.DONE
        run.error = ""
    except Exception as exc:
        run.status = ReportRun.Status.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
    run.finished_at = timezone.now()
    run.save()
    return run.status
