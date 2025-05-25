from django.urls import include, path
from django.contrib.auth.decorators import login_required
from scriptly.views.views import scriptly_job_detail
from scriptly.views.views import ScriptlyScriptSubmitView
from scriptly.views.authentication import ScriptlyLoginView
from django.contrib.auth.views import LogoutView


from scriptly.views import (
    ScriptlyHomeView,
    ScriptlyScriptSearchJSON,
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
    path('submit/', ScriptlyScriptSubmitView.as_view(), name='scriptly_submit_script'),
    # Script search endpoints
    path("search/script/json", ScriptlyScriptSearchJSON.as_view(), name="scriptly_search_script_json"),

    # User results
    path('jobs/results/user', login_required(UserResultsView.as_view()), name='user_results'),
    path('jobs/results/user/json', user_results_json, name='user_results_json'),

    # Profile
    path('profile/', ScriptlyProfileView.as_view(), name='profile_home'),
    path('profile/<str:username>/', ScriptlyProfileView.as_view(), name='profile'),

    # Groups
    path('group/<int:group_id>/', login_required(script_group_detail), name='script_group_detail'),

    # Auth
    path('accounts/register/', ScriptlyRegister.as_view(), name='scriptly_register'),
    # Favorites
    path('favorite/toggle', toggle_favorite, name='toggle_favorite'),

    # Internationalization
    path('i18n/', include('django.conf.urls.i18n')),
    path("jobs/results/celery_results/<int:job_id>/", scriptly_job_detail, name="scriptly_job_detail"),
    path('accounts/login/', ScriptlyLoginView.as_view(), name='scriptly_login'),
    path('accounts/logout/', LogoutView.as_view(next_page='scriptly:scriptly_login'), name='logout'),


]