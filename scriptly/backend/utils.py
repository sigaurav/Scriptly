from __future__ import absolute_import
import json
import errno
import os
import re
import sys
import traceback
from collections import OrderedDict, defaultdict
from contextlib import contextmanager
import hashlib
import uuid
from django.conf import settings as scriptly_settings

# Python2.7 encoding= support
from io import open
from itertools import chain
from operator import itemgetter
from pkg_resources import parse_version

from clinto.parser import Parser
from clinto.parsers.constants import SPECIFY_EVERY_PARAM
from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import transaction
from django.db.utils import OperationalError
from django.core.files.storage import default_storage
from django.core.files import File
from django.forms import FileField
from django.http import QueryDict
from django.utils.datastructures import MultiValueDict
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from .. import errors
from .. import settings as scriptly_settings


def sanitize_name(name):
    return name.replace(" ", "_").replace("-", "_")


def sanitize_string(value):
    return value.replace('"', '\\"')


def ensure_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def flatten(value):
    new_list = []
    for element in value:
        if isinstance(element, list):
            new_list.extend(flatten(element))
        else:
            new_list.append(element)
    return new_list


def get_storage(local=True):
    if scriptly_settings.SCRIPTLY_EPHEMERAL_FILES:
        storage = default_storage.local_storage if local else default_storage
    else:
        storage = default_storage
    return storage


def purge_output(job=None):
    from ..models import UserFile

    # cleanup the old files, we need to be somewhat aggressive here.
    local_storage = get_storage(local=True)
    for user_file in UserFile.objects.filter(job=job):
        if user_file.parameter is None or user_file.parameter.parameter.is_output:
            system_file = user_file.system_file
            matching_files = UserFile.objects.filter(system_file=system_file).exclude(
                job=user_file.job
            )
            # nothing else references this file, delete it
            if matching_files.count() == 0:
                scriptly_file = system_file.filepath.name
                # this will delete the default file -- which if we are using an ephemeral file system will be the
                # remote instance
                system_file.filepath.delete(False)
                system_file.delete()
                # check our local storage and remove it if it is there as well
                path = local_storage.path(scriptly_file)
                if local_storage.exists(path):
                    local_storage.delete(path)
            # delete all copies this user has of this file.
            user_file.delete()


def get_job_commands(job=None, executable=None):
    script_version = job.script_version
    script_path = script_version.get_script_path()
    command = [executable if executable else sys.executable, script_path]

    parameters = job.get_parameters()
    print("🧩 DEBUG get_job_commands: job.get_parameters() length =", len(parameters))
    for param in parameters:
        print("  - param:", param.parameter.script_param, "| value:", param.value)

    base_parameters = [p for p in parameters if not p.parameter.parser.name]
    command_parameters = [p for p in parameters if p.parameter.parser.name]

    added_parsers = set()

    for param in chain(base_parameters, command_parameters):
        script_param = param.parameter
        # Add subparser if needed
        if script_param.parser and script_param.parser.pk not in added_parsers:
            added_parsers.add(script_param.parser.pk)
            if script_param.parser.name:
                command.append(script_param.parser.name)

        value = param.value

        short_param = script_param.short_param
        print(f"🧪 Final value added for {script_param.slug}: {value}")
        if value in (None, '', []):
            continue

        # Ensure the value is a string or a list of strings
        try:
            if isinstance(value, list):
                value = [str(v) for v in value]
            else:
                value = str(value)
        except Exception as e:
            print(f"⚠️ Skipping parameter {script_param.slug} due to conversion error: {e}")
            continue

        if short_param:
            command.append(short_param)

        if isinstance(value, list):
            command.extend([str(v) for v in value])
        else:
            command.append(str(value))


    print("📦 JOB PARAMETER DEBUG START")
    for param in job.get_parameters():
        print(f"🔸 param.slug={param.parameter.slug}")
        print(f"🔸 param.short_param={param.parameter.short_param}")
        print(f"🔸 param.value={param.value}")
        print(f"🔸 is_output={param.parameter.is_output}")
        print("-----")
    print("📦 JOB PARAMETER DEBUG END")

    print("🧪 Final constructed command:", command)
    return command




@transaction.atomic
def create_scriptly_job(user=None, script_version_pk=None, script_parser_pk=None, data=None, files=None):
    from ..models import ScriptlyJob, ScriptParameter, ScriptParameters, ScriptVersion
    from .utils import get_storage, get_upload_path

    script_version = ScriptVersion.objects.select_related("script").get(pk=script_version_pk)

    if script_parser_pk is None:
        script_parsers = list(script_version.scriptparser_set.all())
        if len(script_parsers) == 1:
            script_parser_pk = script_parsers[0].pk
        elif len(script_parsers) > 1:
            raise Exception("Multiple subparsers found but no parser selected.")

    data = data or {}
    print("💥 CLEANED DATA RECEIVED:", data)

    job = ScriptlyJob(
        user=user,
        job_name=data.pop("job_name", None),
        job_description=data.pop("job_description", None),
        script_version=script_version,
    )
    job.save()

    parameters = OrderedDict([
        (param.form_slug, param)
        for param in ScriptParameter.objects.select_related("parser")
        .filter(script_version=script_version)
        .filter(Q(parser_id=script_parser_pk) | Q(parser__name=""))
        .order_by("param_order", "pk")
    ])

    print("🧩 PARAMETER COUNT:", len(parameters))

    for form_slug, param in parameters.items():
        print(f"🔹 Checking param: {param.script_param} ({param.slug}), parser={param.parser_id}")

        if param.parser_id and param.parser_id != script_parser_pk:
            print(f"⛔ Skipping {param.slug}: parser mismatch")
            continue

        uploaded_file = files.getlist(form_slug)[0] if files and form_slug in files else None
        print(f"📥 File: {uploaded_file}")

        final_value = None

        try:
            if uploaded_file:
                storage = get_storage(local=False)
                upload_path = get_upload_path(uploaded_file)
                saved_path = storage.save(upload_path, File(uploaded_file))
                final_value = storage.path(saved_path)

                print(f"✅ Saved file for {param.slug} at {final_value}")
                print(f"📁 File exists: {os.path.exists(final_value)}")
            else:
                val = data.get(form_slug)
                val = val[0] if isinstance(val, list) else val
                if not val:
                    print(f"⚠️ No usable value for {form_slug}")
                    continue
                final_value = val
                print(f"✅ Saved non-file value for {param.slug}: {final_value}")

            # ⚠️ Bypass the value setter to avoid `.name` attribute issues
            ScriptParameters.objects.create(
                job=job,
                parameter=param,
                _value=json.dumps(final_value)
            )

        except Exception as e:
            print(f"💥 Error saving parameter {form_slug}: {e}")

    print(f"🎉 Job {job.id} created successfully with parameters.")
    return job



def get_master_form(script_version=None, pk=None, parser=None):
    from ..forms.factory import DJ_FORM_FACTORY

    return DJ_FORM_FACTORY.get_master_form(
        script_version=script_version, pk=pk, parser=parser
    )


def get_form_groups(script_version=None, initial_dict=None, render_fn=None):
    from ..forms.factory import DJ_FORM_FACTORY

    return DJ_FORM_FACTORY.get_group_forms(
        script_version=script_version, initial_dict=initial_dict, render_fn=render_fn
    )


def validate_form(form=None, data=None, files=None):
    form.add_scriptly_fields()
    form.data = data if data is not None else {}
    form.files = files if files is not None else {}
    form.is_bound = True
    form.full_clean()

    # for cloned jobs, because we do not open a file selection window again in the browser, the pointer to files will just be a list
    # like ['', filename]. We need to remap these to previously submitted files and merge with any new files provided.
    to_delete = []
    for field in data:
        if isinstance(form.fields.get(field), FileField):
            # if we have a value set, reassert this
            new_values = (
                list(filter(lambda x: x, data.getlist(field)))
                if isinstance(data, (MultiValueDict, QueryDict))
                else ensure_list(data.get(field))
            )
            cleaned_values = []
            for new_value in new_values:
                if field not in files and (
                    field not in form.cleaned_data
                    or (
                        new_value
                        and (
                            form.cleaned_data[field] is None
                            or not [j for j in form.cleaned_data[field] if j]
                        )
                    )
                ):
                    # this is a previously set field, so a cloned job
                    if new_value is not None:
                        cleaned_values.append(get_storage(local=False).open(new_value))
                    to_delete.append(field)
            if cleaned_values:
                form.cleaned_data[field] = cleaned_values
    for field in to_delete:
        if field in form.errors:
            del form.errors[field]

    # Now append any new files into our cleaned form data
    for field in files or {}:
        v = (
            files.getlist(field)
            if isinstance(files, (MultiValueDict, QueryDict))
            else files[field]
        )
        if field in form.cleaned_data:
            cleaned = ensure_list(form.cleaned_data[field])
            form.cleaned_data[field] = list(set(cleaned).union(set(v)))


def get_current_scripts():
    from ..models import ScriptVersion

    try:
        scripts = ScriptVersion.objects.count()
    except OperationalError:
        # database not initialized yet
        return

    # get the scripts with default version
    scripts = ScriptVersion.objects.select_related("script").filter(
        default_version=True
    )
    # scripts we need to figure out the default version for some reason
    non_default_scripts = ScriptVersion.objects.filter(default_version=False).exclude(
        script__in=[i.script for i in scripts]
    )
    script_versions = defaultdict(list)
    for sv in non_default_scripts:
        try:
            version_string = parse_version(str(sv.script_version))
        except Exception:
            sys.stderr.write(
                "Error converting script version:\n{}".format(traceback.format_exc())
            )
            version_string = sv.script_version
        script_versions[sv.script.script_name].append(
            (version_string, sv.script_iteration, sv)
        )
        [
            script_versions[i].sort(key=itemgetter(0, 1, 2), reverse=True)
            for i in script_versions
        ]
    scripts = [i.script for i in scripts]
    if script_versions:
        for script_version_info in script_versions.values():
            new_scripts = ScriptVersion.objects.select_related("script").filter(
                pk__in=[i[2].pk for i in script_version_info]
            )
            scripts.extend([i.script for i in new_scripts])
    return scripts


@contextmanager
def get_storage_object(path, local=False, close=True):
    storage = get_storage(local=local)
    obj = storage.open(path)
    obj.url = storage.url(path)
    obj.path = storage.path(path)
    yield obj
    if close:
        obj.close()


def add_scriptly_script(
    script_version=None,
    script_path=None,
    group=None,
    script_name=None,
    set_default_version=True,
    ignore_bad_imports=False,
    user=None,  # ✅ NEW
):

    # There is a class called 'Script' which contains the general information about a script. However, that is not where the file details
    # of the script lie. That is the ScriptVersion model. This allows the end user to tag a script as a favorite/etc. and set
    # information such as script descriptions/names that do not constantly need to be updated with every version change. Thus,
    # a ScriptVersion stores the file info and such.
    from ..models import (
        Script,
        ScriptGroup,
        ScriptParser,
        ScriptParameter,
        ScriptParameterGroup,
        ScriptVersion,
    )

    # if we are adding through the admin, at this point the file will be saved already and this method will be receiving
    # the scriptversion object. Otherwise, we are adding through the managementment command. In this case, the file will be
    # a location and we need to setup the Script and ScriptVersion in here.
    # check if the script exists
    print("DEBUG: user passed to add_scriptly_script =", user) # To be deleted later
    script_path = script_path or script_version.script_path.name
    script_name = script_name or (
        script_version.script.script_name
        if script_version
        else os.path.basename(os.path.splitext(script_path)[0])
    )
    with get_storage_object(script_path) as so:
        checksum = get_checksum(buff=so.read())
    existing_version = None
    try:
        existing_version = ScriptVersion.objects.get(
            checksum=checksum, script__script_name=script_name
        )
    except ObjectDoesNotExist:
        pass
    except MultipleObjectsReturned:
        # This exists because previous versions did not enforce a checksum, so multiple scriptverisons are
        # possible with the same checksum.
        existing_version = (
            ScriptVersion.objects.filter(
                checksum=checksum, script__script_name=script_name
            )
            .order_by("script_version", "script_iteration")
            .last()
        )
    # If script_verison is None, it likely came from `addscript`
    if existing_version is not None and (
        script_version is None or existing_version != script_version
    ):
        return {
            "valid": False,
            "errors": ScriptVersion.error_messages["duplicate_script"],
            "script": existing_version,
        }

    local_storage = get_storage(local=True)
    if script_version is not None:
        # we are updating the script here or creating it through the admin

        # we need to move the script to the scriptly scripts directory now
        # handle remotely first, because by default scripts will be saved remotely if we are using an
        # ephemeral file system
        old_name = script_version.script_path.name
        new_name = os.path.normpath(
            os.path.join(scriptly_settings.SCRIPTLY_SCRIPT_DIR, old_name)
            if not old_name.startswith(scriptly_settings.SCRIPTLY_SCRIPT_DIR)
            else old_name
        )

        current_storage = get_storage(local=not scriptly_settings.SCRIPTLY_EPHEMERAL_FILES)
        current_file = current_storage.open(old_name)
        if current_storage.exists(new_name):
            new_name = current_storage.get_available_name(new_name)
        new_path = current_storage.save(new_name, current_file)

        # remove the old file
        if old_name != new_name:
            current_file.close()
            current_storage.delete(old_name)
            current_file = current_storage.open(new_path)

        script_version._rename_script = True
        script_version.script_path.name = new_name
        script_version.save()

        # download the script locally if it doesn't exist
        if not local_storage.exists(new_path):
            new_path = local_storage.save(new_path, current_file)

        # Close the old file if it is not yet
        if not current_file.closed:
            current_file.close()

        with get_storage_object(new_path, local=True) as so:
            script = so.path
        with local_storage.open(new_path) as local_handle:
            local_file = local_handle.name
    else:
        # we got a path, if we are using a remote file system, it will be located remotely by default
        # make sure we have it locally as well
        if scriptly_settings.SCRIPTLY_EPHEMERAL_FILES:
            remote_storage = get_storage(local=False)
            with remote_storage.open(script_path) as remote_file:
                local_file = local_storage.save(script_path, remote_file)
        else:
            with local_storage.open(script_path) as local_handle:
                local_file = local_handle.name
        with get_storage_object(local_file, local=True) as so:
            script = so.path
    if isinstance(group, ScriptGroup):
        group = group.group_name
    if group is None:
        group = "Scriptly Scripts"
    basename, extension = os.path.splitext(script)
    filename = os.path.split(basename)[1]

    parser = Parser(
        script_name=filename,
        script_path=local_storage.path(local_file),
        ignore_bad_imports=ignore_bad_imports,
    )
    if not parser.valid:
        return {
            "valid": False,
            "errors": errors.ParserError(parser.error),
        }
    # make our script
    script_schema = parser.get_script_description()
    script_group, created = ScriptGroup.objects.get_or_create(group_name=group)
    version_string = script_schema.get("version")
    if version_string is None:
        version_string = "1"
    try:
        parse_version(version_string)
    except Exception:
        sys.stderr.write(
            "Error parsing version, defaulting to 1. Error message:\n {}".format(
                traceback.format_exc()
            )
        )
        version_string = "1"
    if script_version is None:
        # we are being loaded from the management command, create/update our script/version
        script_kwargs = {
            "script_group": script_group,
            "script_name": script_name or script_schema["name"],
            "ignore_bad_imports": ignore_bad_imports,
        }
        version_kwargs = {
            "script_version": version_string,
            "script_path": local_file,
            "default_version": set_default_version,
            "checksum": checksum,
        }
        # does this script already exist in the database?
        script_created = Script.objects.filter(**script_kwargs).count() == 0
        if script_created:
            # we are creating it, add the description if we can
            script_kwargs.update({"script_description": script_schema["description"]})
            scriptly_script = Script(**script_kwargs)
            scriptly_script._script_cl_creation = True
            scriptly_script.save()
            version_kwargs.update({"script_iteration": 1, "default_version": True})
        else:
            # we're updating it
            scriptly_script = Script.objects.get(**script_kwargs)
            if not scriptly_script.script_description and script_schema["description"]:
                scriptly_script.script_description = script_schema["description"]
                scriptly_script.save()
            # check if we have the version in our script version
            current_versions = ScriptVersion.objects.filter(
                script=scriptly_script, script_version=version_string
            )
            if current_versions.count() == 0:
                next_iteration = 1
            else:
                # get the largest iteration and add 1 to it
                next_iteration = (
                    sorted([i.script_iteration for i in current_versions])[-1] + 1
                )
            # disable older versions
            if set_default_version:
                ScriptVersion.objects.filter(script=scriptly_script).update(
                    default_version=False
                )
            version_kwargs.update({"script_iteration": next_iteration})
        version_kwargs.update({"script": scriptly_script})
        script_version = ScriptVersion(**version_kwargs)
        script_version._script_cl_creation = True
        script_version.checksum = checksum

        if user:
            script_version.created_by = user

        script_version.save()
    else:
        # we are being created/updated from the admin
        scriptly_script = script_version.script
        if not scriptly_script.script_description:
            scriptly_script.script_description = script_schema["description"]
        if not scriptly_script.script_name:
            scriptly_script.script_name = script_name or script_schema["name"]
        past_versions = ScriptVersion.objects.filter(
            script=scriptly_script, script_version=version_string
        ).exclude(pk=script_version.pk)
        if len(past_versions) == 0:
            script_version.script_version = version_string
            script_version.default_version = True
        script_version.script_iteration = past_versions.count() + 1
        # Make all old versions non-default
        if set_default_version:
            ScriptVersion.objects.filter(script=scriptly_script).update(
                default_version=False
            )
        script_version.default_version = True
        script_version.checksum = checksum
        scriptly_script.save()
        script_version.save()

    # make our parameters
    parameter_index = 0
    for parser_name, parser_inputs in script_schema["inputs"].items():
        parsers = ScriptParser.objects.filter(
            name=parser_name, script_version__script=scriptly_script
        ).distinct()
        if len(parsers):
            parser = parsers.first()
        else:
            parser = ScriptParser.objects.create(
                name=parser_name,
            )
            parser.save()
        parser.script_version.add(script_version)

        for param_group_info in parser_inputs:
            param_group_name = param_group_info.get("group")

            param_groups = ScriptParameterGroup.objects.filter(
                group_name=param_group_name, script_version__script=scriptly_script
            ).distinct()

            # TODO: There should only ever be one, should probably do a harder enforcement of this.
            if len(param_groups):
                param_group = param_groups.first()
            else:
                param_group = ScriptParameterGroup.objects.create(
                    group_name=param_group_name,
                )
                param_group.save()
            param_group.script_version.add(script_version)

            for param in param_group_info.get("nodes"):
                # TODO: fix 'file' to be global in argparse
                # ✅ Corrected is_output detection logic:
                # Positional arguments (no "param") are always treated as INPUTS, not outputs.
                # Determine if parameter is an output
                if param.get("upload", True) is True:
                    is_out = False  # It's an input
                elif param.get("upload", True) is False:
                    is_out = True  # Explicit output
                elif param.get("param") is None:
                    is_out = False  # Positional → assume input
                else:
                    # Fallback guess: if it's a file and not uploaded, it's probably output
                    is_out = param.get("type") == "file"

                # ✅ Corrected form_field ("model") assignment logic:
                if param.get("type") == "file":
                    if is_out:
                        param["model"] = "CharField"  # Outputs stay CharField (for file path storage)
                    else:
                        param["model"] = "FileField"  # Inputs must be FileField for file uploads
                elif param.get("type") in ("str", "string", None):
                    param["model"] = "CharField"
                elif param.get("type") in ("bool", "boolean"):
                    param["model"] = "BooleanField"
                elif param.get("type") in ("int", "integer"):
                    param["model"] = "IntegerField"
                elif param.get("type") in ("float", "double"):
                    param["model"] = "FloatField"
                else:
                    # Fallback for unknown types
                    param["model"] = "CharField"

                script_param_kwargs = {
                    "short_param": param["param"],
                    "script_param": param["name"],
                    "is_output": is_out,
                    "required": param.get("required", False),
                    "form_field": param["model"],
                    "input_type": param.get("type"),
                    "choices": json.dumps(param.get("choices")),
                    "choice_limit": json.dumps(param.get("choice_limit", 1)),
                    "param_help": param.get("help"),
                    "is_checked": param.get("checked", False),
                    # parameter_group': param_group,
                    "collapse_arguments": SPECIFY_EVERY_PARAM
                    not in param.get("param_action", set()),
                }
                default_value = param.get("value")
                if "value" not in param:
                    script_param_kwargs["default__isnull"] = True
                else:
                    script_param_kwargs["default"] = default_value

                parameter_index += 1

                # This indicates the parameter is a positional argument. If these are changed between script versions,
                # the script can break. Therefore, we have to add an additional filter on the parameter order that
                # keyword arguments can ignore.
                if not param["param"]:
                    script_param_kwargs["param_order"] = parameter_index
                script_params = (
                    ScriptParameter.objects.filter(**script_param_kwargs)
                    .filter(
                        script_version__script=scriptly_script,
                        parameter_group__group_name=param_group_name,
                        parser__name=parser_name,
                    )
                    .distinct()
                )

                if not script_params:
                    script_param_kwargs["parser"] = parser
                    script_param_kwargs["parameter_group"] = param_group
                    if "param_order" not in script_param_kwargs:
                        script_param_kwargs["param_order"] = parameter_index

                    script_param, created = ScriptParameter.objects.get_or_create(
                        **script_param_kwargs
                    )
                    script_param.script_version.add(script_version)
                else:
                    # If we are here, the script parameter exists and has not changed since the last update. We can simply
                    # point the new script at the old script parameter. This lets us clone old scriptversions and have their
                    # parameters still auto populate.
                    script_param = script_params[0]
                    if "param_order" not in script_param_kwargs:
                        script_param.param_order = parameter_index
                    script_param.script_version.add(script_version)
                    script_param.save()

    return {
        "valid": True,
        "errors": None,
        "script": script_version,
    }


def valid_user(obj, user):
    ret = {"valid": False, "error": "", "display": ""}
    from ..models import Script

    groups = obj.user_groups.all()

    if scriptly_settings.SCRIPTLY_ALLOW_ANONYMOUS or user.is_authenticated:
        if isinstance(obj, Script):
            from itertools import chain

            groups = list(chain(groups, obj.script_group.user_groups.all()))
        if (
            not user.is_authenticated
            and scriptly_settings.SCRIPTLY_ALLOW_ANONYMOUS
            and len(groups) == 0
        ):
            ret["valid"] = True
        elif groups:
            ret["error"] = _("You are not permitted to use this script")
        if not groups and obj.is_active:
            ret["valid"] = True
        if obj.is_active:
            if set(list(user.groups.all())) & set(list(groups)):
                ret["valid"] = True
    ret["display"] = "disabled" if scriptly_settings.SCRIPTLY_SHOW_LOCKED_SCRIPTS else "hide"
    return ret


def mkdirs(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def get_upload_path(file_or_path, checksum=None):
    # file_or_path can be a path string or file object
    if hasattr(file_or_path, 'read'):
        # file-like object, not saved yet — hash its contents
        file_or_path.seek(0)
        data = file_or_path.read()
        checksum = hashlib.sha256(data).hexdigest()
        file_or_path.seek(0)
        filename = getattr(file_or_path, 'name', str(uuid.uuid4()))
        filename = os.path.basename(filename)
    else:
        # full path already exists (e.g., during archival)
        filename = os.path.basename(file_or_path)
        if checksum is None:
            with open(file_or_path, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()

    return os.path.join(
        scriptly_settings.SCRIPTLY_FILE_DIR,
        checksum[:2],
        checksum[-2:],
        checksum,
        filename
    )


def get_file_info(filepath):
    # returns info about the file
    filetype, preview = False, None
    tests = [("tabular", test_delimited), ("fasta", test_fastx), ("image", test_image)]
    while not filetype and tests:
        ptype, pmethod = tests.pop()
        filetype, preview = pmethod(filepath)
        filetype = ptype if filetype else filetype
    preview = None if not filetype else preview
    filetype = None if not filetype else filetype
    try:
        json_preview = json.dumps(preview)
    except Exception:
        sys.stderr.write(
            "Error encountered in file preview:\n {}\n".format(traceback.format_exc())
        )
        json_preview = json.dumps(None)
    return {"type": filetype, "preview": json_preview}


def test_image(filepath):
    import imghdr

    return imghdr.what(filepath) is not None, None


def test_delimited(filepath):
    import csv

    with open(filepath, "r", newline="") as csv_file:
        try:
            dialect = csv.Sniffer().sniff(csv_file.read(1024 * 16), delimiters=",\t")
        except Exception as e:
            return False, None
        csv_file.seek(0)
        reader = csv.reader(csv_file, dialect)
        rows = []
        try:
            for index, entry in enumerate(reader):
                rows.append(entry)

        except Exception as e:
            return False, None

        # If > 10 rows, generate preview by slicing top and bottom 5
        # ? this might not be a great idea for massive files
        if len(rows) > 10:
            rows = rows[:5] + [None] + rows[-5:]
        # FIXME: This should be more intelligent:
        # for small files (<1000 rows?) we should take top and bottom preview 10
        # for large files we should give up and present top 10 (11)
        # same rules should apply to columns: this will require us to discard them as they're read

    return True, rows


def test_fastx(filepath):
    # if we can be delimited by + or > we're maybe a fasta/q
    with open(filepath, encoding="latin-1") as fastx_file:
        sequences = OrderedDict()
        seq = []
        header = ""
        found_caret = False
        for row_index, row in enumerate(fastx_file, 1):
            if row_index > 30:
                break
            if not row.strip():
                continue
            if not found_caret and row[0] != ">":
                if row[0] == ";":
                    continue
                break
            elif not found_caret and row[0] == ">":
                found_caret = True
            if row and row[0] == ">":
                if seq:
                    sequences[header] = "".join(seq)
                    seq = []
                header = row
            elif row:
                # we bundle the fastq stuff in here since it's just a visual
                seq.append(row)
        if seq and header:
            sequences[header] = "".join(seq)
        if sequences:
            rows = []
            [rows.extend([i, v]) for i, v in sequences.items()]
            return True, rows
    return False, None


# ... (imports and utility methods unchanged)

def create_job_fileinfo(job):
    from ..models import ScriptlyFile, UserFile
    from django.conf import settings
    import shutil

    parameters = job.get_parameters()
    files = []
    local_storage = get_storage(local=True)

    group_name = job.script_version.script.script_group.group_name
    script_name = job.script_version.script.script_name
    output_dir = os.path.join("media", group_name, script_name)

    abs_output_dir = os.path.join(settings.MEDIA_ROOT, output_dir)
    mkdirs(abs_output_dir)

    output_files_for_job = []

    for field in parameters:
        try:
            if field.parameter.form_field == "FileField":
                value = field.value
                if value is None:
                    continue

                if isinstance(value, str):
                    if local_storage.exists(value):
                        value_file = local_storage.open(value)
                        if not get_storage(local=False).exists(value):
                            get_storage(local=False).save(value, File(value_file))
                        value = File(value_file)
                    else:
                        field.force_value(None)
                        try:
                            with transaction.atomic():
                                field.save()
                        except Exception:
                            sys.stderr.write("{}\n".format(traceback.format_exc()))
                        continue

                d = {"parameter": field, "file": value, "size_bytes": value.size}
                if field.parameter.is_output:
                    original_filename = os.path.basename(value.name)
                    new_rel_path = os.path.join(output_dir, original_filename)
                    new_abs_path = os.path.join(settings.MEDIA_ROOT, new_rel_path)

                    shutil.copy(value.file.name, new_abs_path)
                    d["checksum"] = get_checksum(path=new_abs_path)
                    output_files_for_job.append(new_rel_path)

                files.append(d)
        except ValueError:
            continue

    for d in files:
        try:
            filepath = d["file"].name
            checksum = d.get("checksum", get_checksum(path=filepath))
            scriptly_file, _ = ScriptlyFile.objects.get_or_create(
                checksum=checksum,
                defaults={
                    "filepath": filepath,
                    "filetype": "output" if d["parameter"].parameter.is_output else "input",
                    "filepreview": "",
                    "size_bytes": d["size_bytes"],
                },
            )

            UserFile.objects.get_or_create(
                job=job,
                parameter=d["parameter"],
                system_file=scriptly_file,
                filename=os.path.basename(filepath),
            )
        except Exception:
            sys.stderr.write(
                "Error saving file info for {}:\n{}".format(filepath, traceback.format_exc())
            )
            continue

    # ✅ Unconditional fallback always runs
    fallback_dir = os.path.join(settings.MEDIA_ROOT, job.get_output_path())
    print("🔎 Scanning fallback folder:", fallback_dir)

    if os.path.exists(fallback_dir):
        for root, dirs, files in os.walk(fallback_dir):
            for filename in files:
                if filename.endswith((".tar.gz", ".zip")):
                    continue
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, settings.MEDIA_ROOT).replace("\\", "/")
                print("✅ Found fallback output file:", rel_path)
                output_files_for_job.append(rel_path)

    print("📦 Final output files for job:", output_files_for_job)

    if output_files_for_job:
        job.output_files = output_files_for_job
        job.save()
        print("✅ Saved job.output_files")



def get_checksum(path=None, buff=None, extra=None):
    import hashlib

    BLOCKSIZE = 65536
    hasher = hashlib.sha1()
    if extra:
        if isinstance(extra, (list, tuple)):
            for i in extra:
                hasher.update(str(i).encode("utf-8"))
        elif isinstance(extra, str):
            hasher.update(extra)
    if buff is not None:
        hasher.update(buff)
    elif path is not None:
        if isinstance(path, str):
            with open(path, "rb") as afile:
                buf = afile.read(BLOCKSIZE)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = afile.read(BLOCKSIZE)
        else:
            start = path.tell()
            path.seek(0)
            buf = path.read(BLOCKSIZE)
            while len(buf) > 0:
                hasher.update(buf)
                buf = path.read(BLOCKSIZE)
            path.seek(start)
    return hasher.hexdigest()


def get_available_file(cwd, name, ext):
    "Returns an available filename"
    out = os.path.join(cwd, name)
    index = 0
    while os.path.exists("{}.{}".format(out, ext)):
        index += 1
        out = os.path.join(cwd, "{}_{}".format(name, index))
    return "{}.{}".format(out, ext)


def get_grouped_file_previews(files):
    groups = {"all": []}
    for file_info in files:
        system_file = file_info.system_file

        filedict = {
            "id": file_info.id,
            "object": file_info,
            "name": file_info.filename,
            "preview": json.loads(system_file.filepreview)
            if system_file.filepreview
            else None,
            "url": get_storage(local=False).url(system_file.filepath.name),
            "slug": file_info.parameter.parameter.script_param
            if file_info.parameter
            else None,
            "basename": os.path.basename(system_file.filepath.name),
            "filetype": system_file.filetype,
            "size_bytes": system_file.size_bytes,
        }
        try:
            groups[system_file.filetype].append(filedict)
        except KeyError:
            groups[system_file.filetype] = [filedict]
        if system_file.filetype != "all":
            groups["all"].append(filedict)
    return groups


def get_file_previews(job):
    output_files = job.output_files or []
    print("🧪 [DEBUG] job.output_files =", output_files)

    if not output_files:
        return {}

    return {
        "Output": [{
            "preview_type": "download",
            "filepath": path,
            "url": os.path.join(settings.MEDIA_URL, path).replace("\\", "/"),
            "filename": os.path.basename(path),
        } for path in output_files]
    }



def get_file_previews_by_ids(ids):
    from ..models import UserFile

    files = UserFile.objects.filter(pk__in=ids)
    return get_grouped_file_previews(files)


def normalize_query(
    query_string,
    findterms=re.compile(r'"([^"]+)"|(\S+)').findall,
    normspace=re.compile(r"\s{2,}").sub,
):
    """
    Split the query string into individual keywords, discarding spaces
    and grouping quoted words together.

    >>> normalize_query('  some random  words "with   quotes  " and   spaces')
    ['some', 'random', 'words', 'with quotes', 'and', 'spaces']
    """

    return [normspace(" ", (t[0] or t[1]).strip()) for t in findterms(query_string)]


def get_query(query_string, search_fields):
    """
    Returns a query as a combination of Q objects that query the specified
    search fields.
    """

    query = None  # Query to search for every search term
    terms = normalize_query(query_string)
    for term in terms:
        or_query = None  # Query to search for a given term in each field
        for field_name in search_fields:
            q = Q(**{"%s__icontains" % field_name: term})
            if or_query is None:
                or_query = q
            else:
                or_query = or_query | q
        if query is None:
            query = or_query
        else:
            query = query & or_query

    if query is None:
        query = Q()

    return query


def tokenize_html_attributes(attributes):
    kv_parser = re.compile(r'(?P<key>\w+)=(?<!\\)"(?P<value>.+?)(?<!\\)"')
    for match in kv_parser.finditer(attributes):
        yield (match.group("key"), match.group("value"))
