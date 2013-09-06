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
            
Each module should define a class named Database that inherits from the
BaseDatabase class below.  Override class methods as needed.
        
Related data files should be placed in a subdirectory named according to the 
module name:

    <project>/data/db/<module name>/seed/
    <project>/data/db/<module name>/sample/
"""
import importlib
import sys
import re
from fabric.api import env
from fabric.context_managers import cd
from fabric.decorators import roles, runs_once, task
from ..decorators import require_settings
from ..fos import exists, join, ls
from ..utils import abort, confirm, do, notice, run_in_ve, warn


class BaseDatabase(object):
    """
    Base class for engine-specific Database classes.
    """
    def __init__(self, conf):
        """
        Set db-specific vars from DATABASES configuration.
        """
        self.type = self.__module__.split('.')[-1]
        self.name = conf.get('NAME', '')
        self.user = conf.get('USER', '')
        self.password = conf.get('PASSWORD', '')
        self.host = conf.get('HOST', '')  
          
    def pipe_data(self, file_path):
        """
        Pipe data form file to database.
        """
        warn('Skipping file, unsupported format (%s)' % file_path)      
              
    def dump_data(self, file_path):
        """
        Dump data from database to file_path
        """  
        warn('%s.dump_data not implemeneted' % self.type)  
        
    def setup(self):
        """
        Create the project database and user.
        """
        warn('%s.setup not implemeneted' % self.type)  
       
    def sync(self):
        """
        Setup database tables (e.g. django sync)
        """
        if env.django:
            with cd(env.project_path):
                run_in_ve('python manage.py syncdb ' \
                    '--settings=core.settings.%(settings)s' % env)

    def seed(self, sample='n'):
        """
        Seed the database.  Set sample=y to load sample data (default = n).
        Must be run from app/work server to pipe data.
         """
        d = join(env.data_path, 'db', env.db.type, 'seed')   
        if exists(d):
            files = ls(d)     
            for f in files:
                env.db.pipe_data(f)                    
                        
        d = join(env.data_path, 'db', env.db.type, 'sample')
        if do(sample) and exists(d):
            files = ls(d)     
            for f in files:
                env.db.pipe_data(f)
              
    def destroy(self):
        """
        Destroy the project database and user.
        """
        warn('%s.destroy not implemeneted' % self.type) 


class FablibDbTypeError(Exception):
    pass

    
@require_settings
def load():
    """Load the db module according to (core.settings.[loc|stg|prd])."""
    mod_name = 'core.settings.%(settings)s' % env
    
    try:
        settings_mod = importlib.import_module(mod_name)
        
        if not hasattr(settings_mod, 'DATABASES'):
            raise FablibDbTypeError('no DATABASES in settings file')
            
        conf = settings_mod.DATABASES.get('default', {})
       
        # Load db-specific module
        engine = conf.get('ENGINE', '')
        m = re.match(r'.*?(?P<db_type>[a-zA-Z0-9]+)$', engine)
        if not m:
            raise FablibDbTypeError('no DATABASES.ENGINE match')
           
        db_type = m.group('db_type')  
        db_mod = importlib.import_module('.%s' % db_type, 'fablib.db')
          
        notice('Loaded db module for %s' % db_type)
                
        env.db = db_mod.Database(conf)
    except FablibDbTypeError, e:
        env.db = BaseDatabase({})
        warn('Could not determine db type (%s)' % e)
    except ImportError, e:
        env.db = BaseDatabase({})
        warn('Could not import settings module "%s": %s' % (mod_name, e))

#
# Tasks
#

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
    warn('This will delete the "{0.name}" database and "{0.user}" ' \
         'database user on {0.host}.'.format(env.db))        
    if not confirm('Continue? (y/n) '):
        abort('Aborting.')

    env.db.destroy()

@task
@roles('app')
@runs_once
@require_settings
def dump(type='', filename='data.sql'):
    """Dump data from database. Set type=sample|seed."""
    if type not in ['sample', 'seed']:
        abort('Invalid data type "%s", expected "sample" or "seed"' % type)
    file_path = join(env.data_path, 'db', env.db.type, type, filename)
    
    notice('Dumping data to "%s"' % file_path)    
    if exists(file_path):
        if not confirm('Overwrite existing file? (y/n) '):
            abort('Aborting.')
            
    env.db.dump_data(file_path)
    

