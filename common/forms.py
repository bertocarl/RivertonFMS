from django import forms


class StyledMixin:
    """Adds the app's input styling and native date pickers to every field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css = "h-4 w-4" if isinstance(widget, forms.CheckboxInput) else "fld"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"


class StyledModelForm(StyledMixin, forms.ModelForm):
    pass


class StyledForm(StyledMixin, forms.Form):
    pass
