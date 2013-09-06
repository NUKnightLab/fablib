"""
Dynamic site utilities
"""
from random import choice
from fabric.api import env, run, local 
from fabric.context_managers import cd
from fabric.decorators import roles
from . import aws
from .fos import exists, join
from .utils import run_in_ve

def setup_ssh():
    ssh_path = join(env.home_path, '.ssh')
    with cd(ssh_path):
        if not exists('known_hosts'):
            aws.copy_from_s3('knightlab.ops', 'deploy/ssh/known_hosts',
                join(ssh_path, 'known_hosts'))
        if not exists('config'):
            aws.copy_from_s3('knightlab.ops', 'deploy/ssh/config',
                join(ssh_path, 'config'))
        if not exists('github.key'):
            aws.copy_from_s3('knightlab.ops', 'deploy/ssh/github.key',
                join(ssh_path, 'github.key'))
            with cd(ssh_path):
                run('chmod 0600 github.key')

def setup_directories():
    run('mkdir -p %(sites_path)s' % env)
    run('mkdir -p %(log_path)s' % env)
    run('mkdir -p %(ve_path)s' % env)

def setup_virtualenv():
    """Create a virtualenvironment."""
    run('virtualenv -p %(python)s %(ve_path)s' % env)

@roles('app', 'work') 
def build_django_siteconf():
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
    secret_key = ''.join([choice(chars) for i in range(50)])
    run("""echo "SECRET_KEY='%s'" >> %s""" % (secret_key,
        join(env.project_path, 'core', 'settings', 'site.py')))

@roles('app', 'work')
def install_requirements():
    with cd(env.project_path):
        if exists('requirements.txt'):
            run_in_ve('pip install -r requirements.txt')



    

