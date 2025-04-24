from __future__ import absolute_import

__author__ = "chris"
from django.db import models
from ..forms import fields as scriptly_form_fields


class ScriptlyOutputFileField(models.FileField):
    def formfield(self, **kwargs):
        # TODO: Make this from an app that is plugged in
        defaults = {"form_class": scriptly_form_fields.ScriptlyOutputFileField}
        defaults.update(kwargs)
        return super(ScriptlyOutputFileField, self).formfield(**defaults)


class ScriptlyUploadFileField(models.FileField):
    def formfield(self, **kwargs):
        # TODO: Make this from an app that is plugged in
        defaults = {"form_class": scriptly_form_fields.ScriptlyUploadFileField}
        defaults.update(kwargs)
        return super(ScriptlyUploadFileField, self).formfield(**defaults)
