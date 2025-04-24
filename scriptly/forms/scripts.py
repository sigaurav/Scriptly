from __future__ import absolute_import
from django import forms


class ScriptlyForm(forms.Form):
    scriptly_type = forms.IntegerField(widget=forms.HiddenInput)
    scriptly_parser = forms.IntegerField(widget=forms.HiddenInput, required=False)

    def add_scriptly_fields(self):
        # This adds fields such as job name, description that we like to validate on but don't want to include in
        # form rendering
        self.fields["job_name"] = forms.CharField()
        self.fields["job_description"] = forms.CharField(required=False)
