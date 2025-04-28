from __future__ import absolute_import
import os
import subprocess
import sys
import tarfile
import tempfile
import traceback
import zipfile
from threading import Thread

from django.utils.text import get_valid_filename
from django.core.files import File
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.apps import apps

from celery import app
from celery.schedules import crontab
from celery.signals import worker_process_init

from .backend import utils
from . import settings as scriptly_settings

try:
    from Queue import Empty, Queue
except ImportError:
    from queue import Empty, Queue

ON_POSIX = "posix" in sys.builtin_module_names

celery_app = app.app_or_default()


def enqueue_output(out, q):
    for line in iter(out.readline, b""):
        q.put(line.decode("utf-8"))
    try:
        out.close()
    except IOError:
        pass


def output_monitor_queue(queue, out):
    p = Thread(target=enqueue_output, args=(out, queue))
    p.start()
    return p


def update_from_output_queue(queue, out):
    lines = []
    while True:
        try:
            line = queue.get_nowait()
            lines.append(line)
        except Empty:
            break
    out += "".join(map(str, lines))
    return out


@worker_process_init.connect
def configure_workers(*args, **kwargs):
    import django
    django.setup()


def get_latest_script(script_version):
    script_path = script_version.script_path
    local_storage = utils.get_storage(local=True)
    script_exists = local_storage.exists(script_path.name)
    if not script_exists:
        local_storage.save(script_path.name, script_path.file)
        return True
    else:
        script_contents = local_storage.open(script_path.name).read()
        script_checksum = utils.get_checksum(buff=script_contents)
        if script_checksum != script_version.checksum:
            tf = tempfile.TemporaryFile()
            with tf:
                tf.write(script_contents)
                tf.seek(0)
                local_storage.delete(script_path.name)
                local_storage.save(script_path.name, tf)
                return True
    return False


def run_and_stream_command(command, cwd=None, job=None, stdout="", stderr=""):
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        bufsize=0,
    )

    qout, qerr = Queue(), Queue()
    pout = output_monitor_queue(qout, proc.stdout)
    perr = output_monitor_queue(qerr, proc.stderr)

    prev_std = (stdout, stderr)

    def check_output(job, stdout, stderr, prev_std):
        stdout = update_from_output_queue(qout, stdout)
        stderr = update_from_output_queue(qerr, stderr)
        if job and (stdout, stderr) != prev_std:
            job.update_realtime(stdout=stdout, stderr=stderr)
            prev_std = (stdout, stderr)
        return stdout, stderr, prev_std

    while proc.poll() is None or pout.is_alive() or perr.is_alive():
        stdout, stderr, prev_std = check_output(job, stdout, stderr, prev_std)

    try:
        proc.stdout.flush()
    except ValueError:
        pass
    stdout, stderr, prev_std = check_output(job, stdout, stderr, prev_std)
    return_code = proc.returncode
    return (stdout, stderr, return_code)


def setup_venv(virtual_environment, job=None, stdout="", stderr=""):
    venv_path = virtual_environment.get_install_path()
    venv_executable = virtual_environment.get_venv_python_binary()
    return_code = 0

    if not os.path.exists(venv_path):
        stdout += _("Setting up Virtual Environment\n########\n")
        venv_command = [
            virtual_environment.python_binary,
            "-m", "venv", venv_path,
            "--without-pip", "--system-site-packages",
        ]
        stdout, stderr, return_code = run_and_stream_command(
            venv_command, cwd=None, job=job, stdout=stdout, stderr=stderr
        )
        if return_code:
            raise Exception(_("VirtualEnv setup failed.\n{stdout}\n{stderr}").format(stdout=stdout, stderr=stderr))

        pip_setup = [venv_executable, "-m", "pip", "install", "-I", "pip"]
        stdout += _("Installing Pip\n########\n")
        stdout, stderr, return_code = run_and_stream_command(
            pip_setup, cwd=None, job=job, stdout=stdout, stderr=stderr
        )
        if return_code:
            raise Exception(_("Pip setup failed.\n{stdout}\n{stderr}").format(stdout=stdout, stderr=stderr))

    requirements = virtual_environment.requirements
    if requirements:
        with tempfile.NamedTemporaryFile(mode="w", prefix="requirements", suffix=".txt", delete=False) as reqs_txt:
            reqs_txt.write(requirements)
        venv_command = [venv_executable, "-m", "pip", "install", "-r", reqs_txt.name]
        stdout += _("Installing Requirements\n########\n")
        stdout, stderr, return_code = run_and_stream_command(
            venv_command, cwd=None, job=job, stdout=stdout, stderr=stderr
        )
        if return_code:
            raise Exception(_("Requirements setup failed.\n{stdout}\n{stderr}").format(stdout=stdout, stderr=stderr))
        os.remove(reqs_txt.name)

    stdout += _("Virtual Environment Setup Complete\n########\n")
    return (venv_executable, stdout, stderr, return_code)


@celery_app.task()
def submit_script(**kwargs):
    job_id = kwargs.pop("scriptly_job")
    resubmit = kwargs.pop("scriptly_resubmit", False)
    ScriptlyJob = apps.get_model("scriptly", "ScriptlyJob")

    job = ScriptlyJob.objects.get(pk=job_id)
    job.update_realtime(delete=True)
    stdout, stderr = "", ""

    try:
        virtual_environment = job.script_version.script.virtual_environment
        venv_executable = None
        if virtual_environment:
            venv_executable, stdout, stderr, return_code = setup_venv(
                virtual_environment, job, stdout, stderr
            )
            if return_code:
                raise Exception("Virtual env setup failed.\n{}\n{}".format(stdout, stderr))

        command = utils.get_job_commands(job=job, executable=venv_executable)
        if resubmit:
            job.pk = None

        cwd = job.get_output_path()
        abscwd = os.path.abspath(os.path.join(settings.MEDIA_ROOT, cwd))
        job.command = " ".join(command)
        job.save_path = cwd

        utils.mkdirs(abscwd)
        get_latest_script(job.script_version)

        job.status = ScriptlyJob.RUNNING
        job.save()

        stdout, stderr, return_code = run_and_stream_command(command, abscwd, job, stdout, stderr)

        job = ScriptlyJob.objects.get(pk=job_id)

        if len(os.listdir(abscwd)):
            tar_out = utils.get_available_file(abscwd, get_valid_filename(job.job_name), "tar.gz")
            with tarfile.open(tar_out, "w:gz") as tar:
                tar.add(abscwd, arcname=os.path.basename(abscwd))

            zip_out = utils.get_available_file(abscwd, get_valid_filename(job.job_name), "zip")
            zip = zipfile.ZipFile(zip_out, "w")
            arcname = os.path.splitext(os.path.split(zip_out)[1])[0]
            zip.write(abscwd, arcname=arcname)
            base_dir = os.path.split(zip_out)[0]
            for root, folders, filenames in os.walk(base_dir):
                for filename in filenames:
                    path = os.path.join(root, filename)
                    if path in [tar_out, zip_out]:
                        continue
                    try:
                        archive_name = path.replace(base_dir, "").lstrip(os.sep)
                        archive_name = os.path.join(arcname, archive_name)
                        zip.write(path, arcname=archive_name)
                    except Exception:
                        stderr += "{}\n{}".format(stderr, traceback.format_exc())
            try:
                zip.close()
            except Exception:
                stderr += "{}\n{}".format(stderr, traceback.format_exc())

            if scriptly_settings.SCRIPTLY_EPHEMERAL_FILES:
                for root, folders, files in os.walk(abscwd):
                    for filename in files:
                        filepath = os.path.join(root, filename)
                        s3path = os.path.join(root[root.find(cwd):], filename)
                        remote = utils.get_storage(local=False)
                        exists = remote.exists(s3path)
                        filesize = remote.size(s3path) if exists else 0
                        if not exists or (exists and filesize == 0):
                            if exists:
                                remote.delete(s3path)
                            remote.save(s3path, File(open(filepath, "rb")))

        utils.create_job_fileinfo(job)
        job.status = ScriptlyJob.COMPLETED if return_code == 0 else ScriptlyJob.FAILED
        job.update_realtime(delete=True)
    except Exception:
        stderr += "{}\n{}".format(stderr, traceback.format_exc())
        job.status = ScriptlyJob.ERROR

    job.stdout = stdout
    job.stderr = stderr
    job.save()
    return (stdout, stderr)


@celery_app.task()
def cleanup_scriptly_jobs(**kwargs):
    from django.utils import timezone
    ScriptlyJob = apps.get_model("scriptly", "ScriptlyJob")

    cleanup_settings = scriptly_settings.SCRIPTLY_JOB_EXPIRATION
    anon_settings = cleanup_settings.get("anonymous")
    now = timezone.now()

    if anon_settings:
        ScriptlyJob.objects.filter(user=None, created_date__lte=now - anon_settings).delete()

    user_settings = cleanup_settings.get("user")
    if user_settings:
        ScriptlyJob.objects.filter(user__isnull=False, created_date__lte=now - user_settings).delete()


@celery_app.task()
def cleanup_dead_jobs():
    ScriptlyJob = apps.get_model("scriptly", "ScriptlyJob")
    inspect = celery_app.control.inspect()
    worker_info = inspect.active()

    if not worker_info:
        return

    active_tasks = {
        task["id"] for worker, tasks in worker_info.items() for task in tasks
    }

    active_jobs = ScriptlyJob.objects.filter(status=ScriptlyJob.RUNNING)
    to_disable = {job.pk for job in active_jobs if job.celery_id not in active_tasks}
    ScriptlyJob.objects.filter(pk__in=to_disable).update(status=ScriptlyJob.FAILED)


celery_app.conf.beat_schedule.update({
    "cleanup-old-jobs": {
        "task": "scriptly.tasks.cleanup_scriptly_jobs",
        "schedule": crontab(hour=0, minute=0),
    },
    "cleanup-dead-jobs": {
        "task": "scriptly.tasks.cleanup_dead_jobs",
        "schedule": crontab(minute="*/10"),
    },
})
