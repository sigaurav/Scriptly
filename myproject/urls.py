from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.shortcuts import redirect
from scriptly.views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home.home, name='scriptly_home'),
    path('group/<int:group_id>/', home.script_group_detail, name='script_group_detail'),
    path('scripts/', include(('scriptly.urls', 'scriptly'), namespace='scriptly')),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='scriptly/registration/login.html'),
         name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='scriptly:scriptly_login'), name='logout'),
]
