"""
Package for DB-related code.  

Each type of database should have a separate module in this package named 
according to the db backend module (e.g. 'mysql', 'postgis').  The name of
the backend module is dynamically loaded from a DATABASE attribute in your
project settings file (core.settings.[loc|stg|prd]).  The format of this
attribute follows the Django convention:
    
    DATABASES = {
        'default': {
            'ENGINE': '<package path>.<backend>'
            ...
        }
    }
    
    e.g.,
    
    DATABASES = {
        'default': {
            'ENGINE': 'django.contrib.gis.db.backends.postgis'
            ...
        }
    }
        
Each module should define these public methods:

    setup_env(conf)
        Set any db-specific variables in env
        
    setup()
        Create the project database and user.
        
    sync()
        Setup the database tables.  If this is a django project, then
        you should just import the sync method below.
    
    seed(sample='n')
        Seed the database with any necessary data.  If sample=y, then also
        attempt to seed with sample data.
    
    destroy():
        Remove the project database and user.
        
Related data files should be placed in a subdirectory named according to the 
module name:

    <project>/data/db/<module name>/seed/
    <project>/data/db/<module name>/sample/
"""
from fabric.api import env
from fabric.contrib.files import exists
from fabric.context_managers import cd
from fabric.decorators import roles, runs_once, task
import importlib
import sys
import re
from ..decorators import require_settings
from ..fos import join, ls
from ..utils import confirm, do, notice, run_in_ve, warn

class FablibDbTypeError(Exception):
    pass
    
@require_settings
def load_module():
    """Load the db module according to (core.settings.[loc|stg|prd])."""
    mod_name = 'core.settings.%(settings)s' % env
    
    try:
        importlib.import_module(mod_name)
        mod = sys.modules[mod_name]
        
        if not hasattr(mod, 'DATABASES'):
            raise FablibDbTypeError('no DATABASES in settings file')
            
        conf = mod.DATABASES.get('default', {})

        # Set common env variables
        env.db_name = conf.get('NAME', '')
        env.db_user = conf.get('USER', '')
        env.db_password = conf.get('PASSWORD', '')
        env.db_host = conf.get('HOST', '')
        
        # Load db-specific module
        engine = conf.get('ENGINE', '')
        m = re.match(r'.*\.(?P<db_type>[a-zA-Z0-9]+)$', engine)
        if not m:
            raise FablibDbTypeError('no DATABASES.ENGINE match')
            
        env.db_type = m.group('db_type')                
        env.db = importlib.import_module('.%(db_type)s' % env, 'fablib.db')
        notice('Loaded db module for %(db_type)s' % env)
        
        # Do db-specific setup
        env.db.setup_env(conf)
    except FablibDbTypeError, e:
        env.db_type = 'dummy'               
        env.db = importlib.import_module('.%(db_type)s' % env, 'fablib.db')
        warn('Could not determine db type (%s)' % e)
    except ImportError, e:
        env.db_type = 'dummy'               
        env.db = importlib.import_module('.%(db_type)s' % env, 'fablib.db')
        warn('Could not import settings module "%s": %s' % (mod_name, e))

@require_settings
def sync():
    """Sync the database using the Django syncdb command."""
    if env.django:
        with cd(env.project_path):
            run_in_ve('python manage.py syncdb ' \
                '--settings=core.settings.%(settings)s' % env)
           
@require_settings
def seed(sample='n'):
    """
    Seed the database.  Set sample=y to load sample data (default = n).
    Must be run from the app or work server to pipe data.
    """
    d = join(env.data_path, 'db', env.db_type, 'seed')   
    if exists(d):
        files = ls(d)     
        for f in files:
            env.db.pipe_data(f)                    
                        
    d = join(env.data_path, 'db', env.db_type, 'sample')
    if do(sample) and exists(d):
        files = ls(d)     
        print files   
        for f in files:
            env.db.pipe_data(f)

@task
@roles('app')
@runs_once
@require_settings
def setup(sample='n'):
    """Setup database and user."""
    env.db.setup()
    env.db.sync()
    env.db.seed(sample=sample)      

@task
@roles('app')
@runs_once
@require_settings
def destroy():
    """Remove the database and user."""
    warn('This will delete the "%(db_name)s" database and "%(db_user)s" ' \
         'database user for %(settings)s on %(db_host)s.')        
    if not confirm('Continue? (y/n) ' % env):
        abort('Aborting.')

    env.db.destroy()
