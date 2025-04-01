from django.contrib import admin
from django.urls import path, include
from scriptly.views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home.home, name='scriptly_home'),
    path('group/<int:group_id>/', home.script_group_detail, name='script_group_detail'),
    path('scripts/', include(('scriptly.urls', 'scriptly'), namespace='scriptly')),  # ✅ Now Django knows 'scriptly' is a namespace

]
