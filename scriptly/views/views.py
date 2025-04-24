from __future__ import absolute_import, unicode_literals
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from collections import defaultdict
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.urls import reverse

from django.utils.encoding import force_str

from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, TemplateView, View
from ..backend import utils
from ..models import (
    APIKey,
    ScriptlyJob,
    Script,
    UserFile,
    Favorite,
    ScriptVersion,
    ScriptlyProfile,
    ScriptGroup,
)
from .. import settings as Scriptly_settings
import importlib


class ScriptlyScriptBase(DetailView):
    model = Script
    slug_field = "slug"
    slug_url_kwarg = "slug"

    @staticmethod
    def render_fn(s):
        return s

    def get_context_data(self, **kwargs):
        context = super(ScriptlyScriptBase, self).get_context_data(**kwargs)
        version = self.kwargs.get("script_version")
        iteration = self.kwargs.get("script_iteration")

        # returns the models required and optional fields as html
        job_id = self.kwargs.get("job_id")
        initial = defaultdict(list)

        if job_id:
            job = ScriptlyJob.objects.get(pk=job_id)
            if job.can_user_view(self.request.user):
                context["job_info"] = {"job_id": job_id}

                parser_used = None
                for i in job.get_parameters():
                    value = i.value
                    if value is not None:
                        script_parameter = i.parameter
                        if script_parameter.parser.name:
                            parser_used = script_parameter.parser.pk
                        initial[script_parameter.form_slug].append(value)

                if parser_used is not None:
                    initial["Scriptly_parser"] = parser_used

        script_version = ScriptVersion.objects.filter(
            script=self.object,
        )
        if not (version or iteration):
            script_version = script_version.get(default_version=True)
        else:
            if version:
                script_version = script_version.filter(script_version=version)
            if iteration:
                script_version = script_version.filter(script_iteration=iteration)

            script_version = script_version.order_by(
                "script_version", "script_iteration"
            ).last()

        # Set parameter initial values by parsing the URL parameters
        # and matching them to the script parameters.
        for param in script_version.get_parameters():
            if param.script_param in self.request.GET:
                value = (
                    self.request.GET.getlist(param.script_param)
                    if param.multiple_choice
                    else self.request.GET.get(param.script_param)
                )
                initial[param.form_slug] = value

        context["form"] = utils.get_form_groups(
            script_version=script_version,
            initial_dict=initial,
            render_fn=self.render_fn,
        )

        # Additional script info to display.
        context["script_version"] = script_version.script_version
        context["script_iteration"] = script_version.script_iteration
        context["script_created_by"] = script_version.created_by
        context["script_created_date"] = script_version.created_date
        context["script_modified_by"] = script_version.modified_by
        context["script_modified_date"] = script_version.modified_date
        return context

    def post(self, request, *args, **kwargs):
        post = request.POST.copy()
        user = request.user if request.user.is_authenticated else None
        if not Scriptly_settings.SCRIPTLY_ALLOW_ANONYMOUS and user is None:
            return {
                "valid": False,
                "errors": {
                    "__all__": [
                        force_str(_("You are not permitted to access this script."))
                    ]
                },
            }

        form = utils.get_master_form(
            pk=int(post["scriptly_type"]), parser=int(post.get("scriptly_parser", 0))
        )
        utils.validate_form(form=form, data=post, files=request.FILES)

        if not form.errors:
            version_pk = form.cleaned_data.get("scriptly_type")
            parser_pk = form.cleaned_data.get("scriptly_parser")
            script_version = ScriptVersion.objects.get(pk=version_pk)
            valid = utils.valid_user(script_version.script, request.user).get("valid")
            if valid:
                group_valid = utils.valid_user(
                    script_version.script.script_group, request.user
                )["valid"]
                if valid and group_valid:
                    job = utils.create_scriptly_job(
                        script_parser_pk=parser_pk,
                        script_version_pk=version_pk,
                        user=user,
                        data=form.cleaned_data,
                    )
                    tasks = importlib.import_module(Scriptly_settings.SCRIPTLY_CELERY_TASKS)
                    tasks.run_scriptly_job.delay(job.id)  # Execute the job synchronously
                    return {"valid": True, "job_id": job.id}

            return {
                "valid": False,
                "errors": {
                    "__all__": [
                        force_str(_("You are not permitted to access this script."))
                    ]
                },
            }

        return {"valid": False, "errors": form.errors}


class ScriptlyScriptView(ScriptlyScriptBase):
    template_name = "scriptly/scripts/script_view.html"

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponse
        from scriptly.models import Script

        slug = kwargs.get('slug')
        print("DEBUG: Received slug =", slug)

        try:
            script = Script.objects.get(slug=slug)
            print("DEBUG: Script found:", script.script_name, "| Active:", script.is_active)
        except Script.DoesNotExist:
            print("DEBUG: No script found with slug:", slug)
            return HttpResponse("Script not found", status=404)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = super(ScriptlyScriptView, self).post(request, *args, **kwargs)
        print("DEBUG: POST response data =", data)

        response_payload = {
            "valid": data.get("valid", False),
            "job_id": data.get("job_id"),
            "message": "",
            "redirect": "",
        }

        if data.get("valid"):
            job_id = data.get("job_id")
            job = ScriptlyJob.objects.get(pk=job_id)

            if job.status == ScriptlyJob.COMPLETED:
                response_payload["message"] = "✅ Job completed successfully"
                response_payload["redirect"] = reverse("scriptly:job_results", kwargs={"job_id": job_id})
            elif job.status == ScriptlyJob.FAILED:
                response_payload["message"] = "❌ Job failed"
            else:
                response_payload["message"] = f"⚠️ Job ended with status: {job.status}"
        else:
            response_payload["errors"] = data.get("errors", {})

        return JsonResponse(response_payload)


class ScriptlyHomeView(TemplateView):
    template_name = "scriptly/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        script_groups = ScriptGroup.objects.all().order_by("group_name")
        groups = []

        for group in script_groups:
            scripts = Script.objects.filter(script_group=group, is_active=True).order_by("script_name")

            script_data = []
            for script in scripts:
                latest_version = (
                    ScriptVersion.objects.filter(script=script)
                    .order_by("-script_version", "-script_iteration")
                    .first()
                )

                script_data.append({
                    "id": script.id,
                    "slug": script.slug,
                    "script_name": script.script_name,
                    "script_description": script.script_description,
                    "modified_date": getattr(latest_version, "modified_date", None),
                    "created_by": getattr(latest_version, "created_by", None),
                    "uploaded_by": getattr(latest_version, "created_by", None),
                    "modified_by": getattr(latest_version, "modified_by", None),
                })

            groups.append({
                "group_name": group.group_name,
                "description": group.description,
                "scripts": script_data,
            })

        ctx["groups"] = groups
        return ctx


class ScriptlyProfileView(TemplateView):
    template_name = "scriptly/profile/profile.html"

    def get_context_data(self, **kwargs):
        ctx = super(ScriptlyProfileView, self).get_context_data(**kwargs)

        user = None
        if "username" in self.kwargs:
            User = get_user_model()
            user = User.objects.get(username=self.kwargs.get("username"))
        else:
            if self.request.user and self.request.user.is_authenticated:
                user = self.request.user

        ctx["user_obj"] = user
        is_logged_in_user = False

        if self.request.user.is_authenticated:
            user_profile, _ = ScriptlyProfile.objects.get_or_create(user=user)
            ctx["user_profile"] = user_profile
            is_logged_in_user = user_profile.user == self.request.user

            if is_logged_in_user:
                ctx["api_keys"] = [
                    {
                        "id": i.id,
                        "name": i.name,
                        "active": i.active,
                        "created_date": i.created_date,
                        "last_used": i.last_used,
                    }
                    for i in APIKey.objects.filter(profile=user_profile)
                ]

        ctx["is_logged_in_user"] = is_logged_in_user

        return ctx


# Synchronous task execution for job submission
from django.views import View
from django.http import JsonResponse
from ..models import ScriptVersion, ScriptlyJob
from ..backend import utils
import time
import traceback

class ScriptlyScriptSubmitView(View):
    def post(self, request, *args, **kwargs):
        post = request.POST.copy()
        user = request.user if request.user.is_authenticated else None

        try:
            form = utils.get_master_form(
                pk=int(post["scriptly_type"]),
                parser=int(post.get("scriptly_parser", 0))
            )
            utils.validate_form(form=form, data=post, files=request.FILES)

            if form.errors:
                return JsonResponse({"valid": False, "errors": form.errors})

            version_pk = form.cleaned_data.get("scriptly_type")
            parser_pk = form.cleaned_data.get("scriptly_parser")
            script_version = ScriptVersion.objects.get(pk=version_pk)

            # Auth check
            valid = utils.valid_user(script_version.script, user).get("valid")
            group_valid = utils.valid_user(script_version.script.script_group, user)["valid"]

            if not (valid and group_valid):
                return JsonResponse({
                    "valid": False,
                    "errors": {"__all__": ["Permission denied."]}
                })

            # Create job
            job = utils.create_scriptly_job(
                script_parser_pk=parser_pk,
                script_version_pk=version_pk,
                user=user,
                data=form.cleaned_data,
            )

            # Run it asynchronously
            try:
                tasks = importlib.import_module(Scriptly_settings.SCRIPTLY_CELERY_TASKS)
                tasks.run_scriptly_job.delay(job.id)  # Run the actual script logic here

                # ✅ Mark job as completed
                job.status = ScriptlyJob.COMPLETED

                if not job.stdout:
                    output_files = job.get_output_files()  # ← if you have a method like this
                    if output_files:
                        job.stdout = f"✅ Output saved to: {output_files[0].file_path}"  # adjust as needed
                    else:
                        job.stdout = "✅ Job completed successfully. (No output file generated)"

                job.save()

                return JsonResponse({
                    "valid": True,
                    "message": "Job completed successfully",
                    "job_id": job.id,
                    "redirect": reverse("scriptly_job_detail", kwargs={"job_id": job.id})
                })

            except Exception as e:
                job.status = ScriptlyJob.FAILED
                job.stderr = traceback.format_exc()
                job.stdout = job.stdout or "Job execution failed."
                job.save()
                print("🔁 Redirecting to:", reverse("scriptly_job_detail", kwargs={"job_id": job.id})) # To be deleted
                return JsonResponse({
                    "valid": False,
                    "errors": {"__all__": [f"Script execution failed: {str(e)}"]}
                })

        except Exception as outer_error:
            return JsonResponse({
                "valid": False,
                "errors": {"__all__": [f"Unexpected error: {str(outer_error)}"]}
            })


class ScriptlyScriptSearchJSON(View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("query", "")
        scripts = Script.objects.filter(script_name__icontains=query)
        result = [{
            "id": script.id,
            "name": script.script_name,
            "url": reverse("scriptly:script_group_detail",
                           kwargs={"group_id": script.script_group.id}) + f"#script-{script.id}"
        } for script in scripts]

        return JsonResponse({"scripts": result})

class ScriptlyScriptSearchJSONHTML(View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("query", "")
        scripts = Script.objects.filter(script_name__icontains=query)
        return render(request, "scriptly/search_results.html", {"scripts": scripts})


def scriptly_job_detail(request, job_id):
    print("✅ HTML view triggered for job:", job_id)
    job = get_object_or_404(ScriptlyJob, pk=job_id)
    return render(request, "scriptly/job_detail.html", {"job": job})
