"""
mongo

seed data:
    <project>/data/db/mongo/seed/
    
sample data:
    <project>/data/db/mongo/sample/
    
See pipe_data() for acceptable formats and file-naming conventions.
"""
from fabric.api import env, settings, hide
from fabric.contrib.files import exists
import os
from ..utils import notice, warn
from . import sync, seed


def _mongo(cmd, prefix=''):
    c = ' mongo -host %(db_host)s '
    return env.doit((prefix+c+cmd) % env)

def _db_exists():
    with hide('warnings'), settings(warn_only=True):
        result = _mongo('--eval ' \
            '"printjson(db.adminCommand(\'listDatabases\'));"' \
            ' | grep "\"%(db_name)s\""')
    return not result.failed

def _user_exists():
    return False
       
def pipe_data(file_path):
    """
    Pipe data from a file to the db.  Valid types of files:
    
    (none)
    """    
    warn('Skipping file, unsupported format (%s)' % file_path)      

def setup_env(conf):
    """Setup the working environment as appropriate for loc, stg, prd."""  
    pass
     
def setup():
    """Create the project database and user.""" 
    pass
    
def destroy():
    """Remove the database and user."""   
    if _db_exists():
        notice('Dropping database "%(db_name)s"' % env)
        _mongo('%(db_name)s --eval "printjson(db.dropDatabase())"')
    else:
        notice('Database "%(db_name)s" does not exist' % env)    

