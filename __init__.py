"""
Deployment management for KnightLab web application projects.

Add the pem file to your ssh agent:
    ssh-add <pemfile>

Set your AWS credentials in environment variables:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY

or in config files:
    /etc/boto.cfg, or
    ~/.boto

Note: Do not quote key strings in the config files.

You can find this information: 
- Login to AWS Management Console
- From 'Knight Lab' menu in upper-right corner, select 'Security Credentials'
- Access Key ID and Secret Access key are visible under 'Access Credentials'

For AWS (boto) config details, see:
    http://boto.readthedocs.org/en/latest/boto_config_tut.html#credentials

Set a WORKON_HOME environment variable.  This is the root directory for all
of your local virtual environments.  If you use virtualenvwrapper, this is 
already set for you. If not, then set it manually.
"""
import os
from os.path import abspath, dirname
import sys
import importlib
import shutil
import boto
from fabric.api import env, put, run, local, settings 
from fabric.context_managers import cd, lcd
from fabric.contrib.files import exists
from fabric.tasks import execute
from fabric.decorators import roles, runs_once, task
from .decorators import require_settings
from .utils import run_in_ve
from .utils import notice, warn, abort, path, do, confirm
from . import apache, aws, db
    
env.roledefs = {'app':[], 'work':[], 'pgis':[], 'mongo':[]}

env.s3cmd_cfg = path(dirname(dirname(abspath(__file__))), 
    'secrets', 's3cmd.cfg')
if not os.path.exists(env.s3cmd_cfg):
    abort("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'.")

def _run_in_ve_local(command):
    """
    Execute the command inside the local virtialenv.
    This is some hacky stuff that is only used in deploystatic.
    """
    cur_settings = env.settings
    loc()
    run_in_ve(command)
    globals()[cur_settings]()  

@require_settings(allow=['stg','prd'])
def _build_django_siteconf():
    chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
    secret_key = ''.join([choice(chars) for i in range(50)])
    run("""echo "SECRET_KEY='%s'" >> %s""" % (secret_key,
        os.path.join(env.project_path, 'core', 'settings', 'site.py')))


############################################################
# Environment
############################################################

def _setup_env(env_type):
    """Setup the working environment as appropriate for loc, stg, prd."""
    env.app_user = 'apps'
    env.repo_url = 'git@github.com:NUKnightLab/%(project_name)s.git' % env
    env.settings = env_type
    
    if env.settings == 'loc':
        env.doit = local    # run/local
        
        # base paths
        env.home_path = path('/Users', env.local_user)
        env.env_path = os.getenv('WORKON_HOME') or \
            _abort("You must set the WORKON_HOME environment variable to the" \
                " root directory for your virtual environments.")       
        env.project_path = path(os.path.dirname(os.path.abspath(__file__)), 
            env.project_name)
            
        # roledefs    
        env.roledefs = {
            'app': ['localhost'],
            'work': [],
            'pgis': ['localhost'],
            'mongo': ['localhost']
        }
    else:
        env.doit = run      # run/local

        # base paths
        env.home_path = path('/home', env.app_user)
        env.env_path = path(env.home_path, 'env')
        env.sites_path = path(env.home_path, 'sites')
        env.project_path = path(env.sites_path, env.project_name)
        
        # roledefs
        if not env.hosts:
            aws.lookup_ec2_instances()
    
    env.ssh_path = path(env.home_path, '.ssh')
    env.log_path = path(env.home_path, 'log', env.project_name)
    env.apache_path = path(env.home_path, 'apache')   
    env.ve_path = path(env.env_path, env.project_name)
    env.activate_path = path(env.ve_path, 'bin', 'activate') 
    env.conf_path = path(env.project_path, 'conf')
    env.data_path = path(env.project_path, 'data')

    # Load db module into env.db
    db.load_module()
    
@task
def prd():
    """Work on production environment."""
    _setup_env('prd')
    env.aws_storage_bucket = 'media.knightlab.com/%(project_name)s' % env
    
@task
def stg():
    """Work on staging environment."""
    _setup_env('stg')
    #env.aws_storage_bucket = 'media.knilab.com/%(project_name)s' % env
    env.aws_storage_bucket = 'test.knilab.com/%(project_name)s' % env
@task
def loc():
    """Work on local environment."""
    _setup_env('loc')    

############################################################
# Setup
############################################################

@require_settings(allow=['stg','prd'])
def _setup_ssh():
    with cd(env.ssh_path):
        if not exists('known_hosts'):
            aws.copy_from_s3('knightlab.ops', 'deploy/ssh/known_hosts',
                path(env.ssh_path, 'known_hosts'))
        if not exists('config'):
            aws.copy_from_s3('knightlab.ops', 'deploy/ssh/config',
                path(env.ssh_path, 'config'))
        if not exists('github.key'):
            aws.copy_from_s3('knightlab.ops', 'deploy/ssh/github.key',
                path(env.ssh_path, 'github.key'))
            with cd(env.ssh_path):
                run('chmod 0600 github.key')

@require_settings(allow=['stg','prd'])
def _setup_directories():
    run('mkdir -p %(sites_path)s' % env)
    run('mkdir -p %(log_path)s' %env)
    run('mkdir -p %(ve_path)s' % env)

@require_settings(allow=['stg','prd'])
def _clone_repo():
    """Clone the git repository."""
    run('git clone %(repo_url)s %(project_path)s' % env)

@require_settings(allow=['stg','prd'])
def _setup_virtualenv():
    """Create a virtualenvironment."""
    run('virtualenv -p %(python)s %(ve_path)s' % env)

@roles('app','work')
@require_settings(allow=['stg','prd'])
def _install_requirements():
    with cd(env.project_path):
        if exists('requirements.txt'):
            run_in_ve('pip install -r requirements.txt')
      
@task      
@roles('app','work')
@require_settings                    
def setup_project():
    """Setup project"""
    _setup_ssh()
    _setup_directories()
    _clone_repo()
    _setup_virtualenv()
    _build_django_siteconf()   
    _install_requirements()
   
@task
@require_settings
def setup_db(sample='n'):
    """Setup database."""
    execute(env.db.setup)
    execute(env.db.sync)
    execute(env.db.seed, sample=sample)      
    
@task
@require_settings                    
def setup(sample='n'):
    """Setup application deployment."""    
    execute(setup_project)
    execute(env.db.setup)
    execute(env.db.sync)
    execute(env.db.seed, sample=sample)      
    execute(apache.link_conf)
    
    
############################################################
# Deploy
############################################################

@task
@roles('app', 'work')    
@require_settings                    
def checkout():
    """Pull the latest code from github."""
    env.doit('cd %(project_path)s; git pull' % env)    

@task
@runs_once
@require_settings(allow=['prd','stg'], verbose=True)
def deploystatic(force='n'):
    """
    Sync local static files to S3.  Does not perform server operations.  
    Requires that the local git repository has no uncommitted changes.  
    If django flag is set, will use collectstatic to move assets into a
    temporary directory, which will then be synced.  Else, syncs the
    'static' directory within the project repository.
    """
    git_status = os.popen('git status').read()
    ready_status = '# On branch master\nnothing to commit'
 
    if not do(force) and not git_status.startswith(ready_status):    
        abort('You have uncommitted local code changes. ' \
            'Please commit and push changes before deploying to S3.')      

    print 'deploystatic to S3 ...'
    repo_dir = dirname(dirname(os.path.abspath(__file__)))
    
    if env.django:
        mod = importlib.import_module('.deploystatic_settings', 'fablib')       
        static_root = mod.STATIC_ROOT     
        
        if os.path.exists(static_root):
            shutil.rmtree(static_root)        
        _run_in_ve_local('python manage.py collectstatic ' + \
            '--pythonpath="%s" ' \
            '--settings=fablib.deploystatic_settings' % repo_dir)
    else:
        static_root = path(repo_dir, env.project_name, 'static')
            
    with lcd(repo_dir):
        local('fablib/bin/s3cmd --config=%s sync' \
                ' --rexclude ".*/\.[^/]*$"' \
                ' --delete-removed --acl-public' \
                ' %s/ s3://%s/' \
                % (env.s3cmd_cfg, static_root, env.aws_storage_bucket)) 
    
    if env.django and os.path.exists(static_root):
        shutil.rmtree(static_root)        
                         
 
@task  
@require_settings(allow=['prd','stg'], verbose=True)
def deploy(mro='y', requirements='y', static='y', restart='y'):
    """
    Deploy latest version of application to the server(s).
    """
    if do(mro):
        execute(apache.mrostart)
    execute(checkout)
    if do(requirements):
        execute(_install_requirements)
    if do(static):
        execute(deploystatic)
    if do(restart):
        if do(mro):
            execute(apache.mrostop)
        else:
            execute(apache.restart)
 
           
@roles('app', 'work')
@require_settings(allow=['prd','stg'], verbose=True)
def destroy_project():
    """Remove project environment."""
    warn('This will remove all %(project_name)s project files for' \
        ' %(settings)s on %(host)s.')
    if not confirm('Continue? (y/n)'):
        abort('Cancelling')

    execute(apache.unlink_conf)
    
    run('rm -rf %(project_path)s' % env) 
    run('rm -rf %(log_path)s' % env) 
    run('rm -rf %(ve_path)s' % env)

         
@task    
@require_settings
def destroy():
    """Remove project environment and databases."""
    execute(destroy_project)
    execute(env.db.destroy)
    

@task
def dump():
    """Dump env to stdout"""
    import pprint
    pprint.pprint(env)
