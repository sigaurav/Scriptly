from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, View
from django.http import JsonResponse
from django.db.models import Q
import importlib
from scriptly.tasks import submit_script
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
                latest_version = ScriptVersion.objects.filter(script=script).order_by("-script_version",
                                                                                      "-script_iteration").first()
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
        print("🟢 [DEBUG] ScriptlyScriptSubmitView POST called")
        print("📥 POST data:", post)
        print("📁 FILES data:", request.FILES)

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
                print("⛔ Permission denied")
                return JsonResponse({
                    "valid": False,
                    "errors": {"__all__": ["Permission denied."]}
                })

            job = utils.create_scriptly_job(
                script_parser_pk=parser_pk,
                script_version_pk=version_pk,
                user=user,
                data=form.cleaned_data,
                files=self.request.FILES
            )
            print("✅ Job created with ID:", job.id)

            # tasks = importlib.import_module(scriptly_settings.SCRIPTLY_CELERY_TASKS)
            submit_script.delay(scriptly_job=job.id)

            print("🚀 Task submitted to Celery")
            return JsonResponse({
                "valid": True,
                "message": "Your job was submitted successfully!",
                "job_id": job.id,
                "redirect": reverse("scriptly:user_results")
            })



        except Exception as e:

            print("💥 Exception caught:", str(e))

            return JsonResponse({

                "valid": False,

                "errors": {"__all__": [f"Unexpected error: {str(e)}"]},

                "redirect": None,

                "message": "Internal server error"

            })


# ------------------------------
# JOB DETAIL VIEW
# ------------------------------
@login_required
def scriptly_job_detail(request, job_id):
    job = get_object_or_404(ScriptlyJob, pk=job_id)
    output_files = utils.get_file_previews(job)

    print("🧪 output_files from get_file_previews:", output_files)
    return render(request, "scriptly/jobs/job_view.html", {
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
            "url": reverse("scriptly:script_group_detail",
                           kwargs={"group_id": script.script_group.id}) + f"?script_id={script.id}"
        } for script in scripts]

        return JsonResponse({"results": results})


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
