from django.urls import include, path
from django.contrib.auth.decorators import login_required
from scriptly.views import celery_results_view
from .views import celery_results_view
from scriptly.views.views import ScriptlyScriptSubmitView


from scriptly.views import (
    ScriptlyHomeView,
    ScriptlyScriptView,
    ScriptlyScriptSearchJSON,
    ScriptlyScriptSearchJSONHTML,
    UserResultsView,
    user_results_json,
    ScriptlyProfileView,
    scriptly_login,
    ScriptlyRegister,
    toggle_favorite,
)
from scriptly.views.home import home, script_group_detail

app_name = "scriptly"

urlpatterns = [
    path('', ScriptlyHomeView.as_view(), name='scriptly_home'),
    path('scripts/submit/', ScriptlyScriptSubmitView.as_view(), name='scriptly_submit_script'),
    path('jobs/results/<int:job_id>/', celery_results_view, name='celery_results'),
    # Script detail and execution
    path('scripts/<slug:slug>/', ScriptlyScriptView.as_view(), name='scriptly_script'),
    path('scripts/jobs/results/celery_results/<int:job_id>/', celery_results_view, name='celery_results'),
    path('scripts/jobs/results/status/<int:job_id>/', celery_results_view, name='job_status'),
    # Script search endpoints
    path("scripts/search/script/json", ScriptlyScriptSearchJSON.as_view(), name="scriptly_search_script_json"),
    path('scripts/search/jsonhtml', ScriptlyScriptSearchJSONHTML.as_view(), name='scriptly_search_script_jsonhtml'),


    # User results
    path('scripts/jobs/results/user', UserResultsView.as_view(), name='user_results'),
    path('scripts/jobs/results/user/json', user_results_json, name='user_results_json'),

    # Profile
    path('profile/', ScriptlyProfileView.as_view(), name='profile_home'),
    path('profile/<str:username>/', ScriptlyProfileView.as_view(), name='profile'),

    # Groups
    path('group/<int:group_id>/', login_required(script_group_detail), name='script_group_detail'),

    # Auth
    path('accounts/register/', ScriptlyRegister.as_view(), name='scriptly_register'),
    path('admin/login/', scriptly_login, name='scriptly_login'),

    # Favorites
    path('favorite/toggle', toggle_favorite, name='toggle_favorite'),

    # Internationalization
    path('i18n/', include('django.conf.urls.i18n')),
]