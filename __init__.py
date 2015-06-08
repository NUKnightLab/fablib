"""
Deployment management for KnightLab web application projects.
Read the README.
"""
import os
from os.path import abspath, dirname
import sys
import shutil
from datetime import datetime
from fabric.api import env, put, run, local, settings, hide
from fabric.context_managers import cd, lcd
from fabric.tasks import execute
from fabric.decorators import roles, runs_once, task
from fabric.operations import prompt
from fabric.utils import puts
from .decorators import require_settings, require_static_settings
from .fos import clean, exists, join
from .utils import notice, warn, abort, do, confirm, run_in_ve
from . import aws, git, static

   
env.debug = False 
env.python = 'python2.7'
env.roledefs = {'app':[], 'work':[], 'pgis':[], 'mongo':[], 'search':[]}
env.app_user = 'apps'
env.branch = 'master'       # DEFAULT BRANCH

if not 'django' in env:
    env.django = False

if not 'conf_dir' in env:
    env.conf_dir = 'conf'

if not 'requirements_file' in env:
    env.requirements_file = 'requirements.txt'
    
#
# Set path to s3cmd.cnf in secrets repository
#
env.s3cmd_cfg = join(dirname(dirname(abspath(__file__))), 
    'secrets', 's3cmd.cfg')
if not os.path.exists(env.s3cmd_cfg):
    warn("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'." \
         "  You will not be able to deploy.")
#
# Load config.json from project directory?
#
_config = None
DYNAMIC = True  # dynamic or static website?


if not 'project_name' in env:
    abort('You must set env.project_name in your fabfile')
try:
    config_json_path = join(dirname(dirname(os.path.abspath(__file__))), 
            env.project_name, 'config.json')  
    _config = static.load_config(config_json_path)
    notice('Loaded config @ %s' % config_json_path)
        
    DYNAMIC = 'deploy' not in _config
except IOError:
    notice('No config @ %s' % config_json_path)
    
############################################################
# Environment
############################################################

def _setup_env(env_type):
    """Setup the working environment as appropriate for loc, stg, prd."""
    env.repo_url = 'git@github.com:NUKnightLab/%(project_name)s.git' % env
    env.settings = env_type
    
    if env.settings == 'loc':
        env.doit = local    # run/local
        env.roledefs = {
            'app': ['localhost'], 
            'work': [], 
            'pgis':['localhost'], 
            'mongo': ['localhost'],
            'search': [], 
        }
        
        # base paths
        env.home_path = os.path.expanduser('~')
        env.env_path = os.getenv('WORKON_HOME')
        env.sites_path = dirname(dirname(os.path.abspath(__file__)))
        if not env.env_path:
            warn("You should set the WORKON_HOME environment variable to the" \
                " root directory for your virtual environments.")
            env.env_path = env.sites_path
    else:
        env.doit = run      # run/local
        env.roledefs = {
            'app': [], 
            'work': [], 
            'pgis': [], 
            'mongo': [], 
            'search': []
        }

        # base paths
        env.home_path = join('/home', env.app_user)
        env.env_path = join(env.home_path, 'env')
        env.sites_path = join(env.home_path, 'sites')
        
        if not env.hosts:
            aws.lookup_ec2_instances()
    
    env.project_path = join(env.sites_path, env.project_name)
    env.log_path = join(env.home_path, 'log', env.project_name)
    env.apache_path = join(env.home_path, 'apache')   
    env.ve_path = join(env.env_path, env.project_name)
    env.activate_path = join(env.ve_path, 'bin', 'activate') 
    env.data_path = join(env.project_path, 'data')
    
    if DYNAMIC:
        # Load db module into env.db
        db.load()


def _run_in_ve_local(command):
    """
    Execute the command inside the local virtualenv.
    This is some hacky stuff that is only used in deploystatic.
    """
    cur_settings = env.settings    
    loc()
    run_in_ve(command)
    globals()[cur_settings]()  


def _s3cmd_put(src_path, bucket):
    """Copy local directory to S3 bucket"""
    repo_dir = dirname(dirname(os.path.abspath(__file__)))
    
    with lcd(repo_dir):
        local('fablib/bin/s3cmd --config=%s put' \
                ' --rexclude ".*/\.[^/]*$"' \
                ' --acl-public' \
                ' --add-header="Cache-Control:max-age=300"' \
                ' -r %s/ s3://%s/' \
                % (env.s3cmd_cfg, src_path, bucket))
   
def _s3cmd_sync(src_path, bucket):
    """Sync local directory with S3 bucket"""
    repo_dir = dirname(dirname(os.path.abspath(__file__)))
     
    with lcd(repo_dir):
        local('fablib/bin/s3cmd --config=%s sync' \
                ' --rexclude ".*/\.[^/]*$"' \
                ' --delete-removed --acl-public' \
                ' --add-header="Cache-Control:max-age=300"' \
                ' %s/ s3://%s/' \
                % (env.s3cmd_cfg, src_path, bucket))
  
  
def _confirm_branch():
    if env.branch != 'master':
        if not do(prompt("You are deploying branch '%(branch)s'.  Continue? (y/n): " % env).strip()):
            abort('Aborting.')
  

############################################################
# Dynamic web sites deployed to ec2
############################################################
if not _config or 'deploy' not in _config:
    from . import apache, db, ec2
    from . import collectstatic_settings

    @task
    def prd():
        """Work on production environment."""
        _setup_env('prd')
        env.aws_storage_bucket = 'media.knightlab.com/%(project_name)s' % env
    
    @task
    def stg():
        """Work on staging environment."""
        _setup_env('stg')
        env.aws_storage_bucket = 'media.knilab.com/%(project_name)s' % env

    @task
    def loc():
        """Work on local environment."""
        _setup_env('loc')    

    @task
    @require_settings(allow=['stg','prd'])                    
    def setup_by_host():
        """Setup project environment, pass host argument (ignore roles)"""
        ec2.setup_ssh()
        ec2.setup_directories()
        git.clone_repo()
        ec2.setup_virtualenv()
        if env.django:
            ec2.build_django_siteconf()   
        ec2.install_requirements()
                 
    @task
    @roles('app','work')
    @require_settings(allow=['stg','prd'])                    
    def setup_project():
        """Setup project environment"""
        ec2.setup_ssh()
        ec2.setup_directories()
        git.clone_repo()
        ec2.setup_virtualenv()
        if env.django:
            ec2.build_django_siteconf()   
        ec2.install_requirements()

    @task
    @require_settings
    def setup(sample='n'):
        """Setup deployment."""    
        execute(setup_project)
        execute(db.setup, sample=sample)     
        execute(apache.link_conf)

    @task
    @runs_once
    @require_settings(allow=['prd','stg'], verbose=True)
    def deploy_static(force='n'):
        """
        Sync local static files to S3.  Does not perform server operations.  
        If django flag is set, will use collectstatic to move assets into a
        temporary directory, which will then be synced.  Else, syncs the
        'static' directory within the project repository.
        """
        git.check_clean(force=do(force))

        print 'deploying static media to S3 ...'
        repo_dir = dirname(dirname(os.path.abspath(__file__)))
    
        if env.django:
            static_root = collectstatic_settings.STATIC_ROOT     
        
            if os.path.exists(static_root):
                shutil.rmtree(static_root)   
                   
            # Make it so that fablib module itself is not loaded        
            #_run_in_ve_local('python manage.py collectstatic' \
            #    ' --pythonpath="%s"' \
            #    ' --settings=fablib.collectstatic_settings' \
            #    % repo_dir)
            _run_in_ve_local('python manage.py collectstatic' \
                ' --pythonpath="%s/fablib"' \
                ' --settings=collectstatic_settings' \
                % repo_dir)
        else:
            static_root = join(repo_dir, env.project_name, 'static')
            
        _s3cmd_sync(static_root, env.aws_storage_bucket)
            
        if env.django and os.path.exists(static_root):
            shutil.rmtree(static_root)        

    @task
    @require_settings(allow=['prd','stg'], verbose=True)
    def deploy(mro='y', requirements='n', static='y', restart='y', force='n'):
        """Deploy latest version of application to the server(s)."""
        _confirm_branch()
                
        if do(mro):
            execute(apache.mrostart)
        execute(git.checkout)
        if do(requirements):
            execute(ec2.install_requirements)
        if do(static):
            execute(deploy_static, force=force)
        if do(restart):
            if do(mro):
                execute(apache.mrostop)
            else:
                execute(apache.restart)

    @task
    @roles('app', 'work')
    @require_settings(allow=['prd','stg'], verbose=True)
    def destroy_project():
        """Remove project environment."""
        warn('This will remove all %(project_name)s project files for' \
            ' %(settings)s on %(host)s.')
        if not confirm('Continue? (y/n) '):
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
        execute(db.destroy)
        
############################################################
# Static websites deployed to S3
############################################################
else:        
    @task 
    def undeploy(env_type):
        """Delete website from S3 bucket.  Specify stg|prd as argument."""
        _setup_env('loc') 

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
        
        repo_dir = dirname(dirname(os.path.abspath(__file__)))
     
        with lcd(repo_dir):
            local('fablib/bin/s3cmd --config=%s del -r --force s3://%s/' \
                % (env.s3cmd_cfg, bucket))

    @task
    def render(env_type):   
        """Render templates (deploy except for actual sync with S3)"""
        _setup_env('loc') 
        
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

        # render templates and run usemin
        if 'deploy_context' in _config['deploy'][env_type]:
            deploy_context = _config['deploy'][env_type]['deploy_context']
        else:
            deploy_context = {}
            
        # sometimes we need this path append to import app from website
        # in render_templates, dunno why:
        sys.path.append(_config['project_path'])
        
        static.render_templates(template_path, deploy_path, deploy_context)   
        static.usemin(_config, [deploy_path], usemin_context)

        # copy static files
        static.copy(_config, [{
            "src": join(_config['project_path'], 'website', 'static'),
            "dst": join(deploy_path, 'static')
        }])

        # additional copy?
        if 'copy' in _config['deploy'][env_type]:
            static.copy(_config, _config['deploy'][env_type]['copy'])

    @task 
    def put(env_type):
        """Put (copy) website to S3 bucket.  Specify stg|prd as argument."""
        render(env_type)
        
        bucket = _config['deploy'][env_type]['bucket']
        notice('copying to %s' % bucket)
           
        # copy to S3
        deploy_path = join(_config['project_path'], 'build', 'website')
        _s3cmd_put(deploy_path, bucket)
             
    @task
    def deploy(env_type):
        """Deploy website to S3 bucket.  Specify stg|prd as argument."""  
        
        render(env_type)
                         
        bucket = _config['deploy'][env_type]['bucket']
        notice('deploying to %s' % bucket)
   
        # sync to S3
        deploy_path = join(_config['project_path'], 'build', 'website')
        _s3cmd_sync(deploy_path, bucket)
         

############################################################
# JS libraries
############################################################

if _config:
    # Set env.cdn_path = path to cdn repository   
    env.cdn_path = abspath(join(_config['root_path'], 'cdn.knightlab.com',
        'app', 'libs', _config['name']))
             
    @task
    def debug():
        """Setup debug settings to test deployment"""
        warn('DEBUG IS ON:')
        _config['deploy']['bucket'] = 'test.knilab.com'

        print 'deploy.bucket:', _config['deploy']['bucket']
        print ''

        if not do(prompt("Continue? (y/n): ").strip()):
            abort('Aborting.')       
        env.debug = True

    @task
    def build():       
        """Build version"""   
        _setup_env('loc')

        # Get build config
        if not 'build' in _config:
            abort('Could not find "build" in config file')
      
        # Check version
        if not 'version' in _config:
            _config['version'] = datetime.utcnow().strftime('%Y-%m-%d-%H-%M-%S')
            warn('Using development version value "%(version)s"' % _config)
            if not do(prompt("Continue? (y/n): ").strip()):
                abort('Aborting.')      
    
        notice('Building version %(version)s...' % _config)

        # Clean build directory
        clean(_config['build_path'])
        
        for key, param in _config['build'].iteritems():
            getattr(static, key)(_config, param)
            #getattr(sys.modules[__name__], 'fablib.static.%s' % key)(_config, param)

    @task
    def stage():
        """Build/commit/tag/push version, copy to local cdn repository"""    
        _setup_env('loc')

        if not 'stage' in _config:
            abort('Could not find "stage" in config file')

        # Make sure cdn exists
        exists(dirname(env.cdn_path), required=True)
    
        # Ask user for a new version
        _config['version'] = git.prompt_tag('Enter a new version number: ',
            unique=True) 
             
        # Build version   
        build()
        
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

    @task
    def stage_dev():
        """
        Build and copy to local cdn repository as 'dev' version       
        No tagging/committing/etc/
        """    
        _setup_env('loc')
        
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
                
    @task
    def stage_latest():
        """Copy version to latest within local cdn repository"""
        _setup_env('loc')

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
    
@task
def branch(name):
    """Specify a branch other than master"""
    env.branch = name
    
@task
def serve(ssl='n', port='5000'):
    """Run the development server"""
    if not 'project_path' in env:
        _setup_env('loc')

    opts = ' -p '+port
    if do(ssl):
        opts += ' -s'    
        
    with lcd(join(env.project_path)):
        if env.django:
            local('python manage.py runserver')
        elif DYNAMIC:
            if int(port) < 1024:
                local('sudo python api.py'+opts)
            else:
                local('python api.py'+opts)                
        else:    
            if int(port) < 1024:
                local('sudo python website/app.py'+opts)     
            else:
                local('python website/app.py'+opts)
                                        
@task
def dump():
    """Dump env and config (if applicable) to stdout"""
    import pprint
    pprint.pprint(env)
    
    if _config:
        print '\n', _config
  
