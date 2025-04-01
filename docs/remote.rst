Remote File Systems
===================

Scriptly has been tested on heroku with S3 as a file storage system.
Settings for this can be seen in the user\_settings.py, which give you a
starting point for a non-local server. In short, you need to change your
storage settings like such:

STATICFILES\_STORAGE = DEFAULT\_FILE\_STORAGE =
'scriptly.scriptlystorage.CachedS3BotoStorage' SCRIPTLY\_EPHEMERAL\_FILES = True
