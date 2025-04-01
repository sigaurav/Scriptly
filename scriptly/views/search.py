# scriptly/views/search.py
from django.http import JsonResponse
from django.views import View
from scriptly.models.core import Script

class ScriptlyScriptSearchJSON(View):
    def get(self, request):
        query = request.GET.get("q", "").strip()
        scripts = Script.objects.filter(script_name__icontains=query, is_active=True).select_related("script_group")
        results = []

        for script in scripts:
            try:
                url = script.latest_version.get_url()
                results.append({
                    "name": script.script_name,
                    "url": script.get_url(),
                })
            except Exception as e:
                # Optional: skip or log if a script doesn't have a group or version
                continue

        return JsonResponse({"results": results})
