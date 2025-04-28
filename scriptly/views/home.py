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
    group = get_object_or_404(ScriptGroup, pk=group_id)
    scripts = Script.objects.filter(script_group=group, is_active=True)

    # Get selected script_id from GET param (hash is NOT used here)
    selected_script_id = request.GET.get("script_id")

    if selected_script_id:
        # Safely filter and avoid breaking if the ID is invalid
        scripts = scripts.filter(id=selected_script_id)

    script_data = []
    for script in scripts:
        try:
            default_version = ScriptVersion.objects.get(script=script, default_version=True)
            form_groups = utils.get_form_groups(script_version=default_version)
            print("🟢 Script:", script.script_name)
            print("🔎 Form groups returned:", form_groups)
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
        "selected_script_id": selected_script_id,  # Optional: can use this in template if needed
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
                'id': script.id,  # ✅ ADD THIS LINE
                'script_name': script.script_name,
                'slug': script.slug,
                'script_description': script.script_description or "No description.",
                'modified_date': version.modified_date if version else None,
                'created_by': version.created_by.username if version and version.created_by else "Unknown",
            })
        group.scripts = enriched_scripts

    return render(request, 'scriptly/home.html', {'groups': groups})

