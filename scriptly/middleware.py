from .models import APIKey
from . import settings as scriptly_settings


def api_key_login(get_response):
    def middleware(request):
        if not request.user.is_authenticated and scriptly_settings.SCRIPTLY_ENABLE_API_KEYS:
            auth_value = request.META.get("HTTP_AUTHORIZATION", "")
            if auth_value:
                try:
                    prefix, token = auth_value.split(" ")
                except ValueError:
                    pass
                else:
                    if prefix == "Bearer":
                        user = APIKey.get_user_by_key(token)
                        if user:
                            request.user = user

        return get_response(request)

    return middleware
