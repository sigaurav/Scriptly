# scriptly/views/search.py
from django.http import JsonResponse
from django.views import View
from scriptly.models.core import Script
from django.urls import reverse

class ScriptlyScriptSearchJSON(View):
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

            return JsonResponse({"results": result})

