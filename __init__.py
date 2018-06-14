"""
Deployment management for KnightLab web application projects.
Read the README.
"""
import os
from os.path import abspath, dirname
import sys
from datetime import datetime
import zipfile
import zlib
from fabric.api import env, put, local, settings, hide
from fabric.context_managers import lcd
from fabric.decorators import task
from fabric.operations import prompt
from fabric.tasks import execute
from .fos import clean, exists, join
from .utils import notice, warn, abort, do, confirm
from . import aws, git, static


if not 'project_name' in env:
    abort('You must set env.project_name in your fabfile')


#
# Set to parent directory of repositories
#
env.sites_path = dirname(dirname(abspath(__file__)))


#
# Set path to s3cmd.cnf in secrets repository
#
env.s3cmd_cfg = join(env.sites_path, 'secrets', 's3cmd.cfg')

#
# Load config.json from project directory?
#
_config = None

config_json_path = join(env.sites_path, env.project_name, 'config.json')
try:
    _config = static.load_config(config_json_path)
    notice('Loaded config @ %s' % config_json_path)
except IOError:
    notice('No config found @ %s' % config_json_path)


def _setup_env():
    """Setup the local working environment."""
    env.home_path = os.path.expanduser('~')
    env.env_path = os.getenv('WORKON_HOME')

    if not env.env_path:
        warn("You should set the WORKON_HOME environment variable to" \
             " the root directory for your virtual environments.")
        env.env_path = env.sites_path

    env.project_path = join(env.sites_path, env.project_name)
    env.ve_path = join(env.env_path, env.project_name)
    env.activate_path = join(env.ve_path, 'bin', 'activate')


def _s3cmd_put(src_path, bucket):
    """Copy local directory to S3 bucket"""
    if not os.path.exists(env.s3cmd_cfg):
        abort("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'." % env)

    with lcd(env.sites_path):
        local('fablib/bin/s3cmd --config=%s put' \
                ' --rexclude ".*/\.[^/]*$"' \
                ' --acl-public' \
                ' --add-header="Cache-Control:max-age=300"' \
                ' -r %s/ s3://%s/' \
                % (env.s3cmd_cfg, src_path, bucket))


def _s3cmd_sync(src_path, bucket):
    """Sync local directory with S3 bucket"""

    if not os.path.exists(env.s3cmd_cfg):
        abort("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'." % env)

    with lcd(env.sites_path):
        local('fablib/bin/s3cmd --config=%s sync' \
                ' --rexclude ".*/\.[^/]*$"' \
                ' --delete-removed --acl-public' \
                ' --add-header="Cache-Control:max-age=300"' \
                ' --no-preserve' \
                ' %s/ s3://%s/' \
                % (env.s3cmd_cfg, src_path, bucket))



############################################################
# JS libraries
############################################################
if _config:

    # Set env.cdn_path = path to cdn repository
    env.cdn_path = abspath(join(_config['root_path'],
        'cdn.knightlab.com', 'app', 'libs', _config['name']))


    def _make_zip(file_path):
        notice('Creating zip file: %s' % file_path)
        with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as f_zip:
            for r in _config['stage']:
                static.add_zip_files(f_zip, _config, [{
                    "src": r['src'],
                    "dst": _config['name'], "regex": r['regex']}])


    @task
    def build():
        """Build lib version"""
        _setup_env()

        # Get build config
        if not 'build' in _config:
            abort('Could not find "build" in config file')

        # Check version
        if not 'version' in _config:
            _config['version'] = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
            warn('Using development version value "%(version)s"' % _config)

        notice('Building version %(version)s...' % _config)

        # Clean build directory
        clean(_config['build_path'])

        # Build it
        for key, param in _config['build'].iteritems():
            getattr(static, key)(_config, param)


    @task
    def stage():
        """Build/commit/tag/push lib version, copy to local cdn repo"""
        _setup_env()

        if not 'stage' in _config:
            abort('Could not find "stage" in config file')

        # Make sure cdn exists
        exists(dirname(env.cdn_path), required=True)

        # Ask user for a new version
        _config['version'] = git.prompt_tag('Enter a new version number',
            unique=True)

        # Build version
        # use execute to allow for other implementations of 'build'
        execute('build')

        # Commit/push/tag
        with lcd(env.project_path):
            with settings(warn_only=True):
                local('git add build')
            # support builds where there's no change; sometimes comes up when
            # reusing a tag because of an unexpected problem
            with settings(warn_only=True):
                msg = local('git commit -m "Release %(version)s"' % _config,capture=True)
                if 'nothing to commit' in msg:
                    warn(msg)
                    warn('continuing anyway')
                elif not msg.startswith('[master'):
                    abort("Unexpected result: %s" % msg)
            local('git push')

            git.push_tag(_config['version'])

        # Copy to local CDN repository
        cdn_path = join(env.cdn_path, _config['version'])
        clean(cdn_path)

        for r in _config['stage']:
            static.copy(_config, [{
                "src": r['src'],
                "dst": cdn_path, "regex": r['regex']}])

        # Create zip file in local CDN repository
        _make_zip(join(cdn_path, '%(name)s.zip' % _config))


    @task
    def stage_dev():
        """
        Build lib and copy to local cdn repository as 'dev' version
        No tagging/committing/etc/
        """
        _setup_env()

        if not 'stage' in _config:
            abort('Could not find "stage" in config file')

        # Make sure cdn exists
        exists(dirname(env.cdn_path), required=True)

        # Build version
        build()

        # Copy to local CDN repository
        cdn_path = join(env.cdn_path, 'dev')
        clean(cdn_path)

        for r in _config['stage']:
            static.copy(_config, [{
                "src": r['src'],
                "dst": cdn_path, "regex": r['regex']}])

        # Create zip file in local CDN repository
        _make_zip(join(cdn_path, '%(name)s.zip' % _config))


    @task
    def stage_latest():
        """Copy lib version to latest within local cdn repo"""
        _setup_env()

        if 'version' in _config:
            version = _config['version']
        else:
            version = git.prompt_tag('Which version to stage as "latest"?')

        notice('stage_latest: %s' % version)

        # Make sure version has been staged
        version_cdn_path = join(env.cdn_path, version)
        if not os.path.exists(version_cdn_path):
            abort("Version '%s' has not been staged" % version)

        # Stage version as latest
        latest_cdn_path = join(env.cdn_path, 'latest')
        clean(latest_cdn_path)
        static.copy(_config, [{
            "src": version_cdn_path, "dst": latest_cdn_path}])


    @task
    def untag():
        """Delete a tag (in case of error)"""
        version = git.prompt_tag('Which tag to delete?')
        if not version:
            abort('No available version tag')
        git.delete_tag(version)


############################################################
# Static websites deployed to S3
############################################################
if _config and 'deploy' in _config:

    @task
    def undeploy(env_type):
        """Delete website from S3 bucket.  Specify stg|prd as argument."""
        _setup_env()

        # Activate local virtual environment (for render_templates+flask?)
        local('. %s' % env.activate_path)

        if not os.path.exists(env.s3cmd_cfg):
            abort("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'.")

        if not env_type in _config['deploy']:
            abort('Could not find "%s" in "deploy" in config file' % env_type)

        if not "bucket" in _config['deploy'][env_type]:
            abort('Could not find "bucket" in deploy.%s" in config file' % env_type)

        bucket = _config['deploy'][env_type]['bucket']

        warn('YOU ARE ABOUT TO DELETE EVERYTHING IN %s' % bucket)
        if not do(prompt("Are you ABSOLUTELY sure you want to do this? (y/n): ").strip()):
            abort('Aborting.')

        with lcd(env.sites_path):
            local('fablib/bin/s3cmd --config=%s del -r --force s3://%s/' \
                % (env.s3cmd_cfg, bucket))


    @task
    def render(env_type):
        """Render templates (deploy except for actual sync with S3)"""
        _setup_env()

        # Activate local virtual environment (for render_templates+flask?)
        local('. %s' % env.activate_path)

        if not os.path.exists(env.s3cmd_cfg):
            abort("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'.")

        if not env_type in _config['deploy']:
            abort('Could not find "%s" in "deploy" in config file' % env_type)

        if not "bucket" in _config['deploy'][env_type]:
            abort('Could not find "bucket" in deploy.%s" in config file' % env_type)

        if 'usemin_context' in _config['deploy'][env_type]:
            usemin_context = _config['deploy'][env_type]['usemin_context']
        else:
            usemin_context = None

        template_path = join(_config['project_path'], 'website', 'templates')
        deploy_path = join(_config['project_path'], 'build', 'website')

        clean(deploy_path)

        # Render templates and run usemin
        if 'deploy_context' in _config['deploy'][env_type]:
            deploy_context = _config['deploy'][env_type]['deploy_context']
        else:
            deploy_context = {}

        # Sometimes we need this path append to import app from website
        # in render_templates, dunno why:
        sys.path.append(_config['project_path'])

        static.render_templates(template_path, deploy_path, deploy_context)
        static.usemin(_config, [deploy_path], usemin_context)

        # Copy static files
        static.copy(_config, [{
            "src": join(_config['project_path'], 'website', 'static'),
            "dst": join(deploy_path, 'static')
        }])

        # Additional copy?
        if 'copy' in _config['deploy'][env_type]:
            static.copy(_config, _config['deploy'][env_type]['copy'])


    @task
    def put(env_type):
        """Put (copy) website to S3 bucket.  Specify stg|prd as argument."""
        render(env_type)

        bucket = _config['deploy'][env_type]['bucket']
        notice('copying to %s' % bucket)

        # Copy to S3
        deploy_path = join(_config['project_path'], 'build', 'website')
        _s3cmd_put(deploy_path, bucket)


    @task
    def deploy(env_type):
        """Deploy website to S3 bucket.  Specify stg|prd as argument."""
        render(env_type)

        bucket = _config['deploy'][env_type]['bucket']
        notice('deploying to %s' % bucket)

        # Sync to S3
        deploy_path = join(_config['project_path'], 'build', 'website')
        _s3cmd_sync(deploy_path, bucket)


@task
def serve(ssl='n', port='5000'):
    """Run the development server"""
    if not 'project_path' in env:
        _setup_env()

    opts = ' -p '+port
    if do(ssl):
        opts += ' -s'

    with lcd(join(env.project_path)):
        if exists(join(env.project_path, 'manage.py')):
            local('python manage.py runserver')
        elif _config and 'deploy' in _config:
            if int(port) < 1024:
                local('sudo python website/app.py'+opts)
            else:
                local('python website/app.py'+opts)
        else:
            if int(port) < 1024:
                local('sudo python api.py'+opts)
            else:
                local('python api.py'+opts)


@task
def dump():
    """Dump env and config (if applicable) to stdout"""
    import pprint
    import json

    notice('dumping env...')
    pprint.pprint(env)

    if _config:
        notice('dumping config...')
        print _config
