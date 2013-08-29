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
import shutil
from fabric.api import env, put, run, local, settings, hide
from fabric.context_managers import cd, lcd
from fabric.tasks import execute
from fabric.decorators import roles, runs_once, task
from fabric.operations import prompt
from .decorators import require_settings
from .fos import clean, exists, join
from .utils import notice, warn, abort, do, confirm, run_in_ve
from . import aws, git
    

env.roledefs = {'app':[], 'work':[], 'pgis':[], 'mongo':[]}

# Path to s3cmd.cnf in secrets repository
env.s3cmd_cfg = join(dirname(dirname(abspath(__file__))), 
    'secrets', 's3cmd.cfg')
if not os.path.exists(env.s3cmd_cfg):
    abort("Could not find 's3cmd.cfg' repository at '%(s3cmd_cfg)s'.")

# STATIC or DYNAMIC? look for config.json
config_json_path = join(dirname(dirname(os.path.abspath(__file__))), 
            env.project_name, 'config.json')  

STATIC = os.path.exists(config_json_path)
DYNAMIC = not STATIC


@task
def dump():
    """Dump env to stdout"""
    import pprint
    pprint.pprint(env)

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
        env.home_path = join('/Users', env.local_user)
        env.env_path = os.getenv('WORKON_HOME') or \
            _abort("You must set the WORKON_HOME environment variable to the" \
                " root directory for your virtual environments.")       
        env.sites_path = dirname(dirname(os.path.abspath(__file__)))
        env.project_path = join(env.sites_path, env.project_name)
        
        env.roledefs = {'app': ['localhost'], 'work': []}
    else:
        env.doit = run      # run/local

        # base paths
        env.home_path = join('/home', env.app_user)
        env.env_path = join(env.home_path, 'env')
        env.sites_path = join(env.home_path, 'sites')
        env.project_path = join(env.sites_path, env.project_name)
        
        if not env.hosts:
            aws.lookup_ec2_instances()
    
    env.log_path = join(env.home_path, 'log', env.project_name)
    env.apache_path = join(env.home_path, 'apache')   
    env.ve_path = join(env.env_path, env.project_name)
    env.activate_path = join(env.ve_path, 'bin', 'activate') 
    env.data_path = join(env.project_path, 'data')
    
    if STATIC:
        env.build_path = join(env.project_path, 'build')
        env.source_path = join(env.project_path, 'source')           
    else:
        # Load db module into env.db
        db.load_module()

def _run_in_ve_local(command):
    """
    Execute the command inside the local virtialenv.
    This is some hacky stuff that is only used in deploystatic.
    """
    cur_settings = env.settings
    loc()
    run_in_ve(command)
    globals()[cur_settings]()  

def s3cmd_sync(src_path, bucket):
    """Sync local directory with S3 bucket"""
    repo_dir = dirname(dirname(os.path.abspath(__file__)))
    
    with lcd(repo_dir):
        local('fabfile/bin/s3cmd --config=%s sync' \
                ' --rexclude ".*/\.[^/]*$"' \
                ' --delete-removed --acl-public' \
                ' %s/ s3://%s/' \
                % (env.s3cmd_cfg, src_path, bucket)
            )
  
############################################################
# Dynamic sites
############################################################
if DYNAMIC:
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
        #env.aws_storage_bucket = 'media.knilab.com/%(project_name)s' % env
        env.aws_storage_bucket = 'test.knilab.com/%(project_name)s' % env
    @task
    def loc():
        """Work on local environment."""
        _setup_env('loc')    

    @task      
    @roles('app','work')
    @require_settings(allow=['stg','prd'])                    
    def setup_project():
        """Setup project environment"""
        ec2.setup_ssh()
        ec2.setup_directories()
        git.clone_repo()
        ec2.setup_virtualenv()
        ec2.build_django_siteconf()   
        ec2.install_requirements()

    @task
    @roles('app','work')
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

        print 'deploystatic to S3 ...'
        repo_dir = dirname(dirname(os.path.abspath(__file__)))
    
        if env.django:
            static_root = collectstatic_settings.STATIC_ROOT     
        
            if os.path.exists(static_root):
                shutil.rmtree(static_root)        
            _run_in_ve_local('python manage.py collectstatic ' + \
                '--pythonpath="%s" ' \
                '--settings=fablib.collectstatic_settings' % repo_dir)
        else:
            static_root = join(repo_dir, env.project_name, 'static')
    
        s3cmd_sync(static_root, env.aws_storage_bucket)
            
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
        git.checkout()
        if do(requirements):
            execute(_install_requirements)
        if do(static):
            execute(deploy_static)
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
        execute(db.destroy)
        
############################################################
# Static sites
############################################################
else:
    from . import static
        
    _setup_env('loc')      
    _config = static.load_config()

    # Path to cdn deployment
    env.cdn_path = abspath(join(env.sites_path, 'cdn.knightlab.com', 
        'app', 'libs', _config['name']))
    
    @task
    def debug():
        """Setup debug settings"""
        warn('DEBUG IS ON:')
        _config['deploy']['bucket'] = 'test.knilab.com'
        _config['version'] = '0.0.0'
     
        print 'deploy.bucket:', _config['deploy']['bucket']
        print 'version:', _config['version']
        print 'version tagging is OFF'
        print ''
    
        if do(prompt("Continue? (y/n): ").strip()):
            abort('Aborting.')       
        env.debug = True
            
    @task
    def serve():
        """Run the development server"""
        with lcd(join(env.project_path)):
            local('python website/app.py')
     
    @task
    def build():
        """Build version"""   
        # Get build config
        if not 'build' in _config:
            abort('Could not find "build" in config file')
      
        # Determine version
        if not 'version' in _config:
            _config['version'] = git.last_tag()
        if not _config['version']:
            abort('No available version tag')      
    
        notice('Building version %(version)s...' % _config)

        # Clean build directory
        static.clean(env.build_path)

        for key, param in _config['build'].iteritems():
            getattr(sys.modules[__name__], key)(_config, param)
           
    @task
    def stage():
        """Build version, copy to local cdn repository, tag last commit"""    
        if not 'stage' in _config:
            abort('Could not find "stage" in config file')

        # Make sure cdn exists
        exists(dirname(env.cdn_path), required=True)
    
        # Ask user for a new version
        if not env.debug:
            _config['version'] = git.prompt_tag()     
  
        build()
    
        cdn_path = join(env.cdn_path, _config['version'])
        clean(cdn_path)
    
        for r in _config['stage']:
            static.copy([{
                "src": r['src'],
                 "dst": cdn_path, "regex": r['regex']
            }])
        
        if not env.debug:
            with lcd(env.project_path):
                local('git tag %(version)s' % _config)
                local('git push origin %(version)s' % _config)           
    
    @task
    def stage_latest():
        """Copy version to latest within local cdn repository"""
        if 'version' in _config:
            version = _config['version']
        else:
            tag_list = git.tags()
            puts('This project has the following tags:')
            puts(tag_list)
    
            while True:
                version = prompt("Which version to stage as 'latest'? ").strip()        
                if not version in tag_list:
                    warn('You must enter an existing version')
                else:
                    break
    
        notice('stage_latest: %s' % version)
    
        # Make sure version has been staged
        version_cdn_path = join(env.cdn_path, version)
        if not os.path.exists(version_cdn_path): 
            abort("Version '%s' has not been staged" % version)
      
        # Stage version as latest           
        latest_cdn_path = join(env.cdn_path, 'latest')
        clean(latest_cdn_path)
        static.copy([{"src": version_cdn_path, "dst": latest_cdn_path}])


    @task
    def deploy():
        """Deploy to S3 bucket"""
        if not 'deploy' in CONFIG:
            abort('Could not find "deploy" in config file')
    
        # Do we need to build anything here?!?     
    
        template_path = join(env.project_path, 'website', 'templates')
        deploy_path = join(env.project_path, 'build', 'website')
    
        static.clean(deploy_path)
    
        # render templates and run usemin
        static.render_templates(template_path, deploy_path)   
        static.usemin([deploy_path])
    
        # copy static files
        static.copy([{
            "src": join(env.project_path, 'website', 'static'),
            "dst": join(deploy_path, 'static')
        }])
    
        # additional copy?
        if 'copy' in _config['deploy']:
            static.copy(_config['deploy']['copy'])
   
        # sync to S3
        s3cmd_sync(deploy_path, _config['deploy']['bucket'])
 
       
       
@task
@roles('app')
def test(force='n'):
    git.prompt_tag()
                  
      
