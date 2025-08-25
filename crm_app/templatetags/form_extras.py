from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(field, css):
    """Usage: {{ form.field|add_class:'form-control' }}"""
    return field.as_widget(
        attrs={
            **field.field.widget.attrs,
            "class": (field.field.widget.attrs.get("class", "") + " " + css).strip(),
        }
    )

@register.filter(name="add_attr")
def add_attr(field, attr_string):
    """Usage: {{ form.field|add_attr:'disabled:true' }}"""
    attr_name, attr_value = attr_string.split(":")
    attrs = field.field.widget.attrs.copy()
    attrs[attr_name] = attr_value
    return field.as_widget(attrs=attrs)
