from django import forms
from django.utils import timezone

from common.forms import StyledForm

from .models import ReportRun


class ReportRequestForm(StyledForm):
    kind = forms.ChoiceField(choices=ReportRun.Kind.choices, label="Report")
    report_date = forms.DateField(label="Date", initial=timezone.localdate)
