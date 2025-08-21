from django import template

register = template.Library()

@register.filter(name="add_class")
def add_class(field, css):
    """Usage: {{ form.field|add_class:'form-control' }}"""
    return field.as_widget(attrs={
        **field.field.widget.attrs,
        "class": (field.field.widget.attrs.get("class", "") + " " + css).strip()
    })
