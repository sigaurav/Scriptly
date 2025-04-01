from django.template import Context
from django.test import TestCase

from ..django_compat import get_template_from_string
from ..templatetags import scriptly_tags
from .. import settings as scriptly_settings
from .factories import UserFactory


class TemplateTagsTestCase(TestCase):
    def test_get_scriptly_setting(self):
        # test that get_scriptly_setting works as expected
        self.assertEqual(
            scriptly_tags.get_scriptly_setting("SCRIPTLY_SITE_NAME"),
            scriptly_settings.SCRIPTLY_SITE_NAME,
        )
        # test that get_scriptly_setting works following a change
        scriptly_settings.SCRIPTLY_SITE_NAME = "TEST_SITE"
        self.assertEqual(
            scriptly_tags.get_scriptly_setting("SCRIPTLY_SITE_NAME"),
            scriptly_settings.SCRIPTLY_SITE_NAME,
        )

    def test_gravatar(self):
        t = get_template_from_string(
            "{% load scriptly_tags %}{% gravatar user.email 64 %}"
        )
        user = UserFactory()
        self.assertEqual(
            t.render(Context({"user": user})),
            "http://www.gravatar.com/avatar/d10ca8d11301c2f4993ac2279ce4b930?s=64",
        )
