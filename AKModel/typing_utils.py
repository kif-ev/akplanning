"""
Base classes for mixins, only relevant for static type checking

Mixins are always combined with a concrete class (e.g., a view or a model form) providing the attributes and methods
they use. During type checking, the mixins inherit from that kind of class to make these attributes known.
At runtime, they are plain mixins (inheriting from object only) to not interfere with the method resolution order.

Additionally, helpers to make types known to type checking that cannot be inferred.
"""
from django import forms
from typing import cast, TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.admin import ModelAdmin
    from django.test import TestCase
    from django.views.generic import View
    from django.views.generic.base import ContextMixin

    from AKModel.models import Event


    class ViewMixinBase(ContextMixin, View):
        """
        Base for mixins combined with (generic) views
        """


    class EventViewMixinBase(ViewMixinBase):
        """
        Base for mixins combined with views that provide the event they are about (see EventSlugMixin)
        """
        event: Event


    ModelFormMixinBase = forms.ModelForm
    ModelAdminMixinBase = ModelAdmin
    TestCaseMixinBase = TestCase
else:
    ViewMixinBase = object
    EventViewMixinBase = object
    ModelFormMixinBase = object
    ModelAdminMixinBase = object
    TestCaseMixinBase = object


def model_choice_field(form: forms.BaseForm, field_name: str) -> forms.ModelChoiceField:
    """
    Get a (multiple) model choice field of a form, e.g., to access or restrict its queryset

    Form fields are only known as generic fields to type checking, which do not have a queryset

    :param form: form containing the field
    :param field_name: name of the field
    :return: the field
    """
    return cast(forms.ModelChoiceField, form.fields[field_name])
