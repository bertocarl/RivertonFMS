from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.views.generic import CreateView, ListView, UpdateView

from .utils import fmt

# Role groups used across the project
MANAGERS = ("manager",)
SUPERVISORS = ("supervisor", "manager")
FINANCE = ("accountant", "manager")
ANYONE_OPS = ("attendant", "supervisor", "accountant", "manager")


class RoleMixin(LoginRequiredMixin, UserPassesTestMixin):
    """roles=None means any signed-in user. Superusers always pass."""

    roles = None

    def test_func(self):
        user = self.request.user
        return self.roles is None or user.has_role(*self.roles)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()


def render_cell(obj, spec):
    if callable(spec):
        value = spec(obj)
    else:
        value = obj
        for part in spec.split("__"):
            value = getattr(value, part, None)
            if callable(value):
                value = value()
            if value is None:
                break
    return fmt(value)


class TableListView(RoleMixin, ListView):
    template_name = "generic/list.html"
    title = ""
    columns = []  # [(header, "attr__path" | callable)]
    add_url = None
    add_label = "Add"
    edit_url = None
    paginate_by = 50

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title
        ctx["headers"] = [c[0] for c in self.columns]
        ctx["add_url"] = reverse(self.add_url) if self.add_url else None
        ctx["add_label"] = self.add_label
        ctx["rows"] = [
            {
                "cells": [render_cell(obj, c[1]) for c in self.columns],
                "edit": reverse(self.edit_url, args=[obj.pk]) if self.edit_url else None,
            }
            for obj in ctx["object_list"]
        ]
        return ctx


class SaveMixin:
    template_name = "generic/form.html"
    title = ""
    success_message = "Saved."

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = self.title
        ctx["cancel_url"] = str(self.success_url)
        return ctx


class CreateRecord(SaveMixin, RoleMixin, CreateView):
    pass


class UpdateRecord(SaveMixin, RoleMixin, UpdateView):
    pass
