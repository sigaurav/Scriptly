from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from scriptly.models import Script, ScriptGroup, ScriptVersion
from scriptly.backend import utils
from django.urls import reverse

@csrf_exempt
@login_required
def script_group_detail(request, group_id):
    if request.method == "POST":
        post = request.POST.copy()
        user = request.user if request.user.is_authenticated else None

        form = utils.get_master_form(
            pk=int(post.get("scriptly_type")),
            parser=int(post.get("scriptly_parser", 0))
        )

        utils.validate_form(form=form, data=post, files=request.FILES)

        if not form.errors:
            version_pk = form.cleaned_data.get("scriptly_type")
            parser_pk = form.cleaned_data.get("scriptly_parser")

            try:
                script_version = ScriptVersion.objects.get(pk=version_pk)
            except ScriptVersion.DoesNotExist:
                return JsonResponse({"valid": False, "errors": {"__all__": ["Script version not found."]}})

            valid = utils.valid_user(script_version.script, request.user).get("valid")
            group_valid = utils.valid_user(script_version.script.script_group, request.user).get("valid")

            if valid and group_valid:
                job = utils.create_scriptly_job(
                    script_parser_pk=parser_pk,
                    script_version_pk=version_pk,
                    user=user,
                    data=form.cleaned_data,
                )
                job.execute_sync()

                return JsonResponse({
                    "valid": True,
                    "job_id": job.id,
                    "redirect": reverse("scriptly:celery_results", kwargs={"job_id": job.id}),
                    "message": "Job completed successfully",
                })

        return JsonResponse({"valid": False, "errors": form.errors})

    # GET handler stays unchanged
    group = get_object_or_404(ScriptGroup, pk=group_id)
    scripts = Script.objects.filter(script_group=group, is_active=True)
    script_data = []

    for script in scripts:
        try:
            default_version = ScriptVersion.objects.get(script=script, default_version=True)
            form_groups = utils.get_form_groups(script_version=default_version)
            script_data.append({
                "id": script.id,
                "slug": script.slug,
                "script_name": script.script_name,
                "script_description": script.script_description,
                "modified_date": default_version.modified_date,
                "created_by": default_version.created_by,
                "form_action_url": reverse("scriptly:script_group_detail", kwargs={"group_id": group.id}),
                "parsers": form_groups["parsers"],
                "scriptly_form": form_groups["scriptly_form"],
            })
        except ScriptVersion.DoesNotExist:
            continue

    return render(request, "scriptly/script_group_detail.html", {
        "group": group,
        "scripts": script_data,
    })


@login_required
def home(request):
    groups = ScriptGroup.objects.prefetch_related('script_set').all()
    for group in groups:
        scripts = Script.objects.filter(script_group=group, is_active=True)
        enriched_scripts = []
        for script in scripts:
            try:
                version = ScriptVersion.objects.get(script=script, default_version=True)
            except ScriptVersion.DoesNotExist:
                version = None
            enriched_scripts.append({
                'script_name': script.script_name,
                'slug': script.slug,
                'script_description': script.script_description or "No description.",
                'modified_date': version.modified_date if version else None,
                'created_by': version.created_by.username if version and version.created_by else "Unknown",
            })
        group.scripts = enriched_scripts

    return render(request, 'scriptly/home.html', {'groups': groups})

