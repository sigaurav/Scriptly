from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView, View
from django.http import JsonResponse, HttpResponse
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.core.serializers import serialize

import importlib

from .. import settings as scriptly_settings
from ..backend import utils
from ..models import ScriptGroup, Script, ScriptVersion, ScriptlyJob

# ------------------------------
# HOME VIEW
# ------------------------------
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
                latest_version = ScriptVersion.objects.filter(script=script).order_by("-script_version", "-script_iteration").first()
                script_data.append({
                    "id": script.id,
                    "slug": script.slug,
                    "script_name": script.script_name,
                    "script_description": script.script_description,
                    "modified_date": getattr(latest_version, "modified_date", None),
                    "created_by": getattr(latest_version, "created_by", None),
                })
            groups.append({
                "group_name": group.group_name,
                "description": group.description,
                "scripts": script_data,
            })
        ctx["groups"] = groups
        return ctx


# ------------------------------
# SCRIPT SUBMIT VIEW
# ------------------------------
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

            utils.validate_form(form=form, data=post, files=request.FILES)

            if form.errors:
                print("🔥 FORM VALIDATION FAILED:", form.errors)
                print("🚀 Received POST data:", post)
                print("📂 Received FILES data:", request.FILES)
                return JsonResponse({"valid": False, "errors": form.errors})

            version_pk = form.cleaned_data.get("scriptly_type")
            parser_pk = form.cleaned_data.get("scriptly_parser")
            script_version = ScriptVersion.objects.get(pk=version_pk)

            valid = utils.valid_user(script_version.script, user).get("valid")
            group_valid = utils.valid_user(script_version.script.script_group, user)["valid"]

            if not (valid and group_valid):
                return JsonResponse({
                    "valid": False,
                    "errors": {"__all__": ["Permission denied."]}
                })

            job = utils.create_scriptly_job(
                script_parser_pk=parser_pk,
                script_version_pk=version_pk,
                user=user,
                data=form.cleaned_data,
            )

            tasks = importlib.import_module(scriptly_settings.SCRIPTLY_CELERY_TASKS)
            tasks.run_scriptly_job.delay(job.id)

            return JsonResponse({
                "valid": True,
                "message": "Job submitted successfully",
                "job_id": job.id,
                "redirect": reverse("scriptly:scriptly_job_detail", kwargs={"job_id": job.id})
            })

        except Exception as e:
            return JsonResponse({
                "valid": False,
                "errors": {"__all__": [f"Unexpected error: {str(e)}"]}
            })

# ------------------------------
# JOB DETAIL VIEW
# ------------------------------
@csrf_exempt
@login_required
def scriptly_job_detail(request, job_id):
    job = get_object_or_404(ScriptlyJob, pk=job_id)
    output_files = utils.get_file_previews(job)

    return render(request, "scriptly/job_view.html", {
        "job": job,
        "output_files": output_files,
    })

# ------------------------------
# SEARCH JSON VIEWS
# ------------------------------
@method_decorator(login_required, name="dispatch")
class ScriptlyScriptSearchJSON(View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("query", "")  # Keep 'query' for consistency with your frontend
        if not query:
            return JsonResponse({"results": []})

        scripts = Script.objects.filter(
            Q(script_name__icontains=query) | Q(script_description__icontains=query),
            is_active=True
        )

        results = [{
            "id": script.id,
            "group_id": script.script_group.id,
            "name": script.script_name,
            "url": reverse("scriptly:script_group_detail", kwargs={"group_id": script.script_group.id}) + f"?script_id={script.id}"
        } for script in scripts]

        return JsonResponse({"results": results})

@method_decorator(login_required, name="dispatch")
class ScriptlyScriptSearchJSONHTML(View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "")
        scripts = Script.objects.filter(
            Q(script_name__icontains=query) | Q(script_description__icontains=query),
            is_active=True
        )
        return render(request, "scriptly/partials/script_search_results.html", {
            "scripts": scripts,
        })

# ------------------------------
# GENERIC SCRIPT VIEW
# ------------------------------
class ScriptlyScriptView(TemplateView):
    template_name = "scriptly/script_view.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        scripts = Script.objects.filter(is_active=True)
        ctx["scripts"] = scripts
        return ctx

# ------------------------------
# USER PROFILE VIEW
# ------------------------------
@method_decorator(login_required, name="dispatch")
class ScriptlyProfileView(TemplateView):
    template_name = "scriptly/profile.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        jobs = ScriptlyJob.objects.filter(user=self.request.user).order_by("-created_date")
        ctx["jobs"] = jobs
        return ctx
