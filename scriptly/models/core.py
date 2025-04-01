from __future__ import absolute_import, print_function, unicode_literals
import os
import importlib
import json
import uuid
from io import IOBase

from autoslug import AutoSlugField
from django.db import models, transaction
from django.conf import settings
from django.core.cache import caches as django_cache
from django.core.exceptions import SuspiciousFileOperation
from django.contrib.auth.models import Group, User
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.text import get_valid_filename

from .. import settings as scriptly_settings
from ..backend import utils

# TODO: Handle cases where celery is not setup but specified to be used
tasks = importlib.import_module(scriptly_settings.SCRIPTLY_CELERY_TASKS)


class Project(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    scripts = models.ManyToManyField('Script', blank=True)

    def __str__(self):
        return self.name


class ScriptGroup(models.Model):
    """
    This is a group of scripts, it holds general information
    about a collection of scripts, and allows for custom descriptions

    """

    group_name = models.TextField()
    description = models.TextField(blank=True, null=True)
    slug = AutoSlugField(populate_from="group_name", unique=True)
    group_description = models.TextField(null=True, blank=True)
    group_order = models.SmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    user_groups = models.ManyToManyField(Group, blank=True)

    class Meta:
        app_label = "scriptly"
        verbose_name = _("script group")
        verbose_name_plural = _("script groups")

    def __str__(self):
        return self.group_name


class Script(models.Model):
    script_name = models.CharField(max_length=255)
    script_path = models.CharField(max_length=255)
    slug = AutoSlugField(populate_from="script_name", unique=True)
    # we create defaults for the script_group in the clean method of the model. We have to set it to null/blank=True
    # or else we will fail form validation before we hit the model.
    script_group = models.ForeignKey(
        "ScriptGroup", null=True, blank=True, on_delete=models.CASCADE
    )
    script_description = models.TextField(blank=True, null=True)
    documentation = models.TextField(blank=True, null=True)
    script_order = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    user_groups = models.ManyToManyField(Group, blank=True)
    ignore_bad_imports = models.BooleanField(
        default=False,
        help_text=_(
            "Ignore bad imports when adding scripts. This is useful if a script is under a virtual environment."
        ),
    )

    execute_full_path = models.BooleanField(
        default=True
    )  # use full path for subprocess calls
    save_path = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="By default save to the script name,"
                  " this will change the output folder.",
    )
    virtual_environment = models.ForeignKey(
        "VirtualEnvironment", on_delete=models.SET_NULL, null=True, blank=True
    )

    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "scriptly"
        verbose_name = _("script")
        verbose_name_plural = _("scripts")

    def __str__(self):
        return self.script_name

    def get_url(self):
        return reverse("scriptly:scriptly_home") + f"#script-{self.id}"

    @property
    def latest_version(self):
        return self.script_version.get(default_version=True)

    def clean(self):
        if self.script_group is None:
            group = (
                ScriptGroup.objects.filter(
                    group_name=scriptly_settings.SCRIPTLY_DEFAULT_SCRIPT_GROUP
                )
                .order_by("pk")
                .first()
            )
            if not group:
                group, created = ScriptGroup.objects.get_or_create(
                    group_name=scriptly_settings.SCRIPTLY_DEFAULT_SCRIPT_GROUP
                )
            self.script_group = group

    def get_previous_versions(self):
        return self.script_version.all().order_by("script_version", "script_iteration")


class ScriptVersion(models.Model):
    # when a script updates, increment this to keep old scripts that are cloned working. The downside is we get redundant
    # parameters, but even a huge site may only have a few thousand parameters to query though.
    script_version = models.CharField(
        max_length=50, help_text="The script version.", blank=True, default="1"
    )
    script_iteration = models.PositiveSmallIntegerField(default=1)
    script_path = models.FileField()
    default_version = models.BooleanField(default=False)
    script = models.ForeignKey(
        "Script", related_name="script_version", on_delete=models.CASCADE
    )
    checksum = models.CharField(max_length=40, blank=True)

    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='created_versions')
    modified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='modified_versions')

    error_messages = {
        "duplicate_script": _("This script already exists!"),
    }

    class Meta:
        app_label = "scriptly"
        verbose_name = _("script version")
        verbose_name_plural = _("script versions")
        get_latest_by = "-created_date"

    def __str__(self):
        return "{}({}: {})".format(
            self.script.script_name, self.script_version, self.script_iteration
        )

    def get_url(self):
        return reverse("scriptly:script_group_detail",
                       kwargs={"group_id": self.script.script_group.id}) + f"#script-{self.script.id}"

    def get_version_url(self):
        return reverse(
            "scriptly:scriptly_script",
            kwargs={
                "slug": self.script.slug,
                "script_version": self.script_version,
                "script_iteration": self.script_iteration,
            },
        )

    def get_script_path(self):
        print("📂 DEBUG script_path.name:", self.script_path.name) # To be deleted
        print("📂 DEBUG script_path.path:", self.script_path.path) # To be deleted

        local_storage = utils.get_storage(local=True)
        full_path = local_storage.path(self.script_path.name)
        print("📂 DEBUG resolved full_path:", full_path) # To be deleted

        return full_path if self.script.execute_full_path else os.path.split(full_path)[1]

    def get_parameters(self):
        return ScriptParameter.objects.filter(script_version=self).order_by(
            "param_order", "pk"
        )

import os
import uuid
import json
import time
from django.db import models, transaction
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.core.exceptions import SuspiciousFileOperation

from .. import settings as scriptly_settings
from ..backend import utils


class ScriptlyJob(models.Model):
    """
    This model serves to link the submitted jobs to a script submitted.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL
    )
    uuid = models.CharField(max_length=255, default=uuid.uuid4, unique=True)
    job_name = models.CharField(max_length=255)
    job_description = models.TextField(null=True, blank=True)
    stdout = models.TextField(null=True, blank=True)
    stderr = models.TextField(null=True, blank=True)

    COMPLETED = "completed"
    DELETED = "deleted"
    FAILED = "failed"
    ERROR = "error"
    RUNNING = "running"
    SUBMITTED = "submitted"

    TERMINAL_STATES = {COMPLETED, FAILED, ERROR}

    STATUS_CHOICES = (
        (COMPLETED, _("Completed")),
        (DELETED, _("Deleted")),
        (FAILED, _("Failed")),
        (ERROR, _("Error")),
        (RUNNING, _("Running")),
        (SUBMITTED, _("Submitted")),
    )

    status = models.CharField(max_length=255, default=SUBMITTED, choices=STATUS_CHOICES)
    save_path = models.CharField(max_length=255, blank=True, null=True)
    command = models.TextField()
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    script_version = models.ForeignKey("ScriptVersion", on_delete=models.CASCADE)

    error_messages = {
        "invalid_permissions": _("You are not authenticated to view this job."),
    }

    class Meta:
        app_label = "scriptly"
        verbose_name = _("scriptly job")
        verbose_name_plural = _("scriptly jobs")

    def __str__(self):
        return self.job_name

    def get_parameters(self):
        return (
            ScriptParameters.objects.select_related("parameter")
            .filter(job=self)
            .order_by("pk")
        )

    def execute_sync(self):
        import subprocess

        self.status = self.RUNNING
        self.save()

        try:
            script_path = self.script_version.get_script_path()
            print("🔍 Executing script at:", script_path)

            if not os.path.exists(script_path):
                raise FileNotFoundError(f"Script not found: {script_path}")

            command = ["python", script_path]
            params = self.get_parameters()
            for param in params:
                if param.value:
                    command.append(str(param.value))

            print("🛠 Command to run:", command)

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(script_path),  # ensure it runs in the script's dir
            )
            stdout, stderr = process.communicate()

            self.stdout = stdout.decode("utf-8")
            self.stderr = stderr.decode("utf-8")

            if process.returncode == 0:
                self.status = self.COMPLETED
                self.stdout += "\n✅ Job completed successfully."
            else:
                self.status = self.FAILED
                self.stderr += f"\n❌ Job failed with exit code {process.returncode}"

        except Exception as e:
            self.status = self.FAILED
            self.stderr = f"❌ Exception occurred: {str(e)}"

        self.save()
        return self.stdout

    def can_user_view(self, user):
        return self.user is None or (user.is_authenticated and self.user == user)

    @property
    def output_path(self):
        directories = [
            scriptly_settings.SCRIPTLY_FILE_DIR,
            get_valid_filename(
                self.user.username
                if self.user is not None and self.user.is_authenticated
                else "anonymous"
            ),
            get_valid_filename(
                self.script_version.script.slug
                if not self.script_version.script.save_path
                else self.script_version.script.save_path
            ),
            str(self.uuid),
        ]
        return os.path.join(*[i for i in directories if i])

    def get_output_path(self):
        path = self.output_path
        utils.mkdirs(os.path.join(settings.MEDIA_ROOT, path))
        return path

    def get_upload_path(self):
        path = self.output_path
        utils.mkdirs(os.path.join(settings.MEDIA_ROOT, path))
        return path

    def get_realtime_key(self):
        return "scriptlyjob_{}_rt".format(self.pk)

    def update_realtime(self, stdout="", stderr="", delete=False):
        scriptly_cache = scriptly_settings.SCRIPTLY_REALTIME_CACHE
        if not delete and scriptly_cache is None:
            self.stdout = stdout
            self.stderr = stderr
            self.save()
        elif scriptly_cache is not None:
            cache = django_cache[scriptly_cache]
            if delete:
                cache.delete(self.get_realtime_key())
            else:
                cache.set(
                    self.get_realtime_key(),
                    json.dumps({"stdout": stdout, "stderr": stderr}),
                )

    def get_realtime(self):
        scriptly_cache = scriptly_settings.SCRIPTLY_REALTIME_CACHE
        if scriptly_cache is not None:
            cache = django_cache[scriptly_cache]
            out = cache.get(self.get_realtime_key())
            if out:
                return json.loads(out)
        return {"stdout": self.stdout, "stderr": self.stderr}

    def get_stdout(self):
        if self.status not in ScriptlyJob.TERMINAL_STATES:
            rt = self.get_realtime().get("stdout")
            if rt:
                return rt
        return self.stdout

    def get_stderr(self):
        if self.status not in ScriptlyJob.TERMINAL_STATES:
            rt = self.get_realtime().get("stderr")
            if rt:
                return rt
        return self.stderr



class ScriptParameterGroup(models.Model):
    group_name = models.TextField()
    hidden = models.BooleanField(default=False)
    script_version = models.ManyToManyField("ScriptVersion")

    class Meta:
        app_label = "scriptly"
        verbose_name = _("script parameter group")
        verbose_name_plural = _("script parameter groups")

    def __str__(self):
        script_version = self.script_version.first()
        return "{}: {}".format(
            script_version.script.script_name
            if script_version
            else "No Script Assigned",
            self.group_name,
        )


class ScriptParser(models.Model):
    name = models.CharField(max_length=255, blank=True, default="")
    script_version = models.ManyToManyField("ScriptVersion")

    def __str__(self):
        script_version = self.script_version.first()
        return "{}: {}".format(
            script_version.script.script_name
            if script_version
            else "No Script Assigned",
            self.name,
        )


class ScriptParameter(models.Model):
    """
    This holds the parameter mapping for each script, and enforces uniqueness by each script via a FK.
    """

    parser = models.ForeignKey("ScriptParser", on_delete=models.CASCADE)
    script_version = models.ManyToManyField("ScriptVersion")
    short_param = models.CharField(max_length=255, blank=True)
    script_param = models.TextField()
    slug = AutoSlugField(populate_from="script_param", unique=True)
    is_output = models.BooleanField(default=None)
    required = models.BooleanField(default=False)
    choices = models.TextField(null=True, blank=True)
    choice_limit = models.CharField(max_length=10, null=True, blank=True)
    collapse_arguments = models.BooleanField(
        default=True,
        help_text=_(
            "Collapse separate inputs to a given argument to a single input (ie: --arg 1 --arg 2 becomes --arg 1 2)"
        ),
    )
    form_field = models.CharField(max_length=255)
    default = models.JSONField(null=True, blank=True)
    input_type = models.CharField(
        max_length=255,
        help_text=_(
            "The python type expected by the script (e.g. boolean, integer, file)."
        ),
    )
    custom_widget = models.ForeignKey(
        "ScriptlyWidget", null=True, blank=True, on_delete=models.SET_NULL
    )
    param_help = models.TextField(verbose_name=_("help"), null=True, blank=True)
    is_checked = models.BooleanField(default=False)
    hidden = models.BooleanField(default=False)
    parameter_group = models.ForeignKey(
        "ScriptParameterGroup", on_delete=models.CASCADE
    )
    param_order = models.SmallIntegerField(
        help_text=_("The order the parameter appears to the user."), default=0
    )

    class Meta:
        app_label = "scriptly"
        verbose_name = _("script parameter")
        verbose_name_plural = _("script parameters")

    @property
    def form_slug(self):
        return "{}-{}".format(self.parser.pk, self.slug)

    @property
    def multiple_choice(self):
        choice_limit = json.loads(self.choice_limit)
        if choice_limit is None:
            return False
        try:
            choice_limit = int(choice_limit)
        except ValueError:
            # it's not a set # of choices that is a max, it's either >=0, or >=1, which are the same for a front-end
            # since validation of >=0 or >=1 is performed outside of the form.
            return True
        else:
            return choice_limit > 1

    @property
    def max_choices(self):
        choice_limit = json.loads(self.choice_limit)
        if choice_limit is None:
            return 1
        try:
            choice_limit = int(choice_limit)
        except ValueError:
            # for this, it's either >=0 or >=1 so as many as they want.
            return -1
        else:
            return choice_limit

    def __str__(self):
        scripts = ", ".join([i.script.script_name for i in self.script_version.all()])
        return "{}: {}".format(scripts, self.script_param)


# TODO: find a better name for this class. Job parameter? SelectedParameter?
class ScriptParameters(models.Model):
    """
    This holds the actual parameters sent with the submission
    """

    # the details of the actual executed scripts
    job = models.ForeignKey("ScriptlyJob", on_delete=models.CASCADE)
    parameter = models.ForeignKey("ScriptParameter", on_delete=models.CASCADE)
    # we store a JSON dumped string in here to attempt to keep our types in order
    _value = models.TextField(db_column="value")

    BOOLEAN = "BooleanField"
    CHAR = "CharField"
    CHOICE = "ChoiceField"
    FILE = "FileField"
    FLOAT = "FloatField"
    INTEGER = "IntegerField"

    SCRIPTLY_FIELD_MAP = {
        BOOLEAN: lambda x: str(x).lower() == "true",
        CHAR: str,
        CHOICE: str,
        FLOAT: float,
        INTEGER: int,
    }

    class Meta:
        app_label = "scriptly"
        verbose_name = _("script parameters")

    def __str__(self):
        try:
            value = self.value
        except IOError:
            value = _("FILE NOT FOUND")
        except SuspiciousFileOperation:
            value = _("File outside of project")
        return "{}: {}".format(self.parameter.script_param, value)

    def get_subprocess_value(self):
        value = self.value
        if self.value is None:
            return None
        field = self.parameter.form_field
        param = self.parameter.short_param
        com = {"parameter": param, "script_parameter": self.parameter}
        if field == self.BOOLEAN:
            if value:
                return com
            else:
                del com["parameter"]
        if field == self.FILE:
            if self.parameter.is_output:
                try:
                    value = value.path
                except AttributeError:
                    value = utils.get_storage(local=True).path(value)
                    # trim the output path, we don't want to be adding our platform specific paths to the output
                    op = self.job.get_output_path()
                    # TODO : use os.path.sep
                    value = value[value.find(op) + len(op) + 1:]
            else:
                # make sure we have it locally otherwise download it
                if not utils.get_storage(local=True).exists(value.path):
                    new_path = utils.get_storage(local=True).save(value.path, value)
                    value = new_path
                else:
                    # return the string for processing
                    value = value.path
        try:
            float(value)
            value = str(value)
        except ValueError:
            pass
        com["value"] = str(value)
        return com

    def force_value(self, value):
        self._value = json.dumps(value)

    def recreate(self):
        # we want to change filefields to reflect whatever is the current job's path. This is currently used for
        # job resubmission
        value = json.loads(self._value)
        if value is not None:
            field = self.parameter.form_field
            if field == self.FILE:
                # we are perfectly fine using old input files instead of recreating them, so only check output files
                if self.parameter.is_output:
                    new_path = self.job.get_output_path()
                    new_root, new_id = os.path.split(new_path)
                    # we want to remove the root + the old job's pk
                    value = value[value.find(new_root) + len(new_root) + 1:]
                    value = value[value.find(os.path.sep) + 1:]
                    # we want to create a new path for the current job
                    path = os.path.join(
                        new_path, self.parameter.slug if not value else value
                    )
                    value = path
                    self._value = json.dumps(value)

    @property
    def value(self):
        value = json.loads(self._value)
        if value is not None:
            field = self.parameter.form_field
            if field == self.FILE:
                try:
                    with utils.get_storage_object(value, close=False) as value:
                        pass
                except IOError:
                    # this can occur when the storage object is not yet made for output
                    if self.parameter.is_output:
                        return value
                    raise IOError
        return value

    @value.setter
    def value(self, value):
        # coerce the value to the proper type and store as json to make it persistent as well as have json
        #  handle type conversion on the way back out
        field = self.parameter.form_field
        add_file = False
        checksum = None
        if field == self.CHAR:
            if value is None:
                value = None
            elif field == self.CHAR:
                if not value:
                    value = None
            else:
                value = self.SCRIPTLY_FIELD_MAP[field](value)
        elif field == self.INTEGER:
            value = (
                self.SCRIPTLY_FIELD_MAP[field](value)
                if isinstance(value, int) or str(value).isdigit()
                else None
            )
        elif field == self.BOOLEAN:
            if value is None or value is False:
                value = None
            if value:
                value = True
        elif field == self.FILE:
            if self.parameter.is_output:
                # make a fake object for it
                path = os.path.join(
                    self.job.get_output_path(),
                    self.parameter.slug if not value else value,
                )
                value = path
            else:
                if value:
                    local_storage = utils.get_storage(local=True)
                    current_path = local_storage.path(value.name)
                    checksum = utils.get_checksum(path=value)
                    path = utils.get_upload_path(current_path, checksum=checksum)
                    if hasattr(value, "size"):
                        filesize = value.size
                    elif issubclass(type(value), IOBase):
                        value.seek(0, 2)
                        filesize = value.tell()
                        value.seek(0)
                    else:
                        filesize = None
                    if not local_storage.exists(path) or (
                            filesize is not None and local_storage.size(path) != filesize
                    ):
                        local_path = local_storage.save(path, value)
                    else:
                        local_path = local_storage.path(path)
                        local_path = os.path.join(
                            os.path.split(path)[0], os.path.split(local_path)[1]
                        )
                    remote_storage = utils.get_storage(local=False)
                    if not remote_storage.exists(path) or (
                            filesize is not None and remote_storage.size(path) != filesize
                    ):
                        local_path = remote_storage.save(local_path, value)
                    add_file = True
                    value = local_path
        self._value = json.dumps(value)
        if add_file:
            # make a ScriptlyFile so the user can share it/etc.
            # get the system path for the file
            local_path = utils.get_storage(local=True).path(local_path)
            fileinfo = utils.get_file_info(local_path)
            # save ourself first, we have to do this because we are referenced in ScriptlyFile
            self.save()
            if checksum is None:
                checksum = utils.get_checksum(path=local_path)
            scriptly_file, file_created = ScriptlyFile.objects.get_or_create(
                checksum=checksum
            )
            if file_created:
                scriptly_file.filetype = fileinfo.get("type")
                scriptly_file.filepreview = fileinfo.get("preview")
                save_file = utils.get_storage().open(local_path)
                save_path = path
                scriptly_file.filepath.save(save_path, save_file, save=False)
                scriptly_file.filepath.name = save_path
                scriptly_file.save()

            UserFile.objects.get_or_create(
                job=self.job,
                system_file=scriptly_file,
                parameter=self,
                filename=os.path.split(local_path)[1],
            )


class UserFile(models.Model):
    filename = models.TextField()
    job = models.ForeignKey("ScriptlyJob", on_delete=models.CASCADE)
    system_file = models.ForeignKey("ScriptlyFile", on_delete=models.CASCADE)
    parameter = models.ForeignKey(
        "ScriptParameters", null=True, blank=True, on_delete=models.CASCADE
    )

    class Meta:
        app_label = "scriptly"

    def __str__(self):
        return "{}: {}".format(self.job.job_name, self.system_file)

    @property
    def filepath(self):
        return self.system_file.filepath


class ScriptlyFile(models.Model):
    filepath = models.FileField(max_length=500)
    filepreview = models.TextField(null=True, blank=True)
    filetype = models.CharField(max_length=255, null=True, blank=True)
    size_bytes = models.IntegerField(null=True)
    checksum = models.CharField(max_length=40, blank=True)

    class Meta:
        app_label = "scriptly"
        verbose_name = _("scriptly file")
        verbose_name_plural = _("scriptly files")

    def __str__(self):
        return self.filepath.name


class VirtualEnvironment(models.Model):
    name = models.CharField(
        max_length=25, help_text=_("The name of the virtual environment.")
    )
    python_binary = models.CharField(
        max_length=1024,
        help_text=_(
            'The binary to use for creating the virtual environment. Should be in your path (e.g. "python3" or "/usr/bin/python3")'
        ),
    )
    requirements = models.TextField(
        null=True,
        blank=True,
        help_text=_(
            'A list of requirements for the virtualenv. This gets passed directly to "pip install -r".'
        ),
    )
    venv_directory = models.CharField(
        max_length=1024,
        help_text=_("The directory to place the virtual environment under."),
    )

    class Meta:
        app_label = "scriptly"
        verbose_name = _("virtual environment")
        verbose_name_plural = _("virtual environments")

    def get_venv_python_binary(self):
        return os.path.join(
            self.get_install_path(),
            "Scripts" if scriptly_settings.IS_WINDOWS else "bin",
            "python.exe" if scriptly_settings.IS_WINDOWS else "python",
        )

    def get_install_path(self, ensure_exists=False):
        path = os.path.join(
            self.venv_directory,
            "".join(x for x in self.python_binary if x.isalnum()),
            self.name,
        )
        if ensure_exists:
            os.makedirs(path, exist_ok=True)
        return path

    def __str__(self):
        return self.name


def get_absolute_url(self):
    return reverse("scriptly:scriptly_script", kwargs={"slug": self.slug})
