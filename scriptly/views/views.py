from __future__ import absolute_import, unicode_literals
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.template.loader import render_to_string
from datetime import time
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
                    job.execute_sync()  # Execute the job synchronously
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


class ScriptlyScrapbookView(TemplateView):
    template_name = "scriptly/scrapbook.html"

    def get_context_data(self, **kwargs):
        ctx = super(ScriptlyScrapbookView, self).get_context_data(**kwargs)

        # Get the id of every favorite (scrapbook) file
        ctype = ContentType.objects.get_for_model(UserFile)
        favorite_file_ids = Favorite.objects.filter(
            content_type=ctype, user=self.request.user
        ).values_list("object_id", flat=True)

        out_files = utils.get_file_previews_by_ids(favorite_file_ids)

        all = out_files.pop("all", [])
        archives = out_files.pop("archives", [])

        ctx["file_groups"] = out_files
        ctx["favorite_file_ids"] = favorite_file_ids

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

            # Run it synchronously
            try:
                job.execute_sync()  # Run the actual script logic here

                # ✅ Mark job as completed
                job.status = ScriptlyJob.COMPLETED
                job.stdout = job.stdout or "Job completed successfully."
                job.save()

                return JsonResponse({
                    "valid": True,
                    "message": "Job completed successfully",
                    "job_id": job.id,
                    "redirect": reverse("scriptly:celery_results", kwargs={"job_id": job.id}),
                })

            except Exception as e:
                job.status = ScriptlyJob.FAILED
                job.stderr = traceback.format_exc()
                job.stdout = job.stdout or "Job execution failed."
                job.save()

                return JsonResponse({
                    "valid": False,
                    "errors": {"__all__": [f"Script execution failed: {str(e)}"]}
                })

        except Exception as outer_error:
            return JsonResponse({
                "valid": False,
                "errors": {"__all__": [f"Unexpected error: {str(outer_error)}"]}
            })




def celery_results_view(request, job_id):
    """
    View to get the results of a job.
    """
    try:
        # Retrieve the job by its ID
        job = ScriptlyJob.objects.get(id=job_id)

        # Check if the job exists and the user has permission to view it
        if job.can_user_view(request.user):
            # Return the job status and any other relevant details
            return JsonResponse({
                'job_id': job.id,
                'job_name': job.job_name,
                'status': job.status,
                'stdout': job.stdout,
                'stderr': job.stderr,
            })
        else:
            return JsonResponse({'error': 'You do not have permission to view this job.'}, status=403)

    except ScriptlyJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found.'}, status=404)

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