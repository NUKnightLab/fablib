"""
mysql

seed data:
    <project>/data/db/mysql/seed/
    
sample data:
    <project>/data/db/mysql/sample/
    
See pipe_data() for acceptable formats and file-naming conventions.
"""
from fabric.api import env, settings, hide
from fabric.contrib.files import exists
import os
from ..utils import notice, warn
from . import sync, seed


def _mysql(cmd, user= '', prefix=''):
    c = ' mysql -h %(db_host)s -u '+(user or env.db_root_user)+' '
    if env.db_password:
        c += '-p"%(db_password)s" '
    return env.doit((prefix+c+cmd) % env)

def _db_exists():
    with hide('warnings'), settings(warn_only=True):
        result = _mysql('-e "SHOW DATABASES;" | grep "^%(db_name)s$"')
    return not result.failed

def _user_exists():
    with hide('warnings'), settings(warn_only=True):
        result = _mysql('-e "SELECT User FROM mysql.user;" | grep "^%(db_user)s$"')
    return not result.failed
       
def pipe_data(file_path):
    """
    Pipe data from a file to the db.  Valid types of files:
    
    1.  Files created using mysqldump (full SQL statements)

    These are loaded by piping their contents directly to mysql.
    
        any_name_is_fine.sql[.gz|.gzip|.zip|.Z]   

    Files that do not follow these naming conventions are skipped.
    """    
    (other, ext) = os.path.splitext(file_path)
    ext = ext.lower()
    if ext.lower() in ('.gz', '.gzip', '.zip', '.Z'):
        cmd = 'gunzip -c'
        (other, ext) = os.path.splitext(other) 
        ext = ext.lower()  
    else:
        cmd = 'cat'
    
    if ext == '.sql':
        _mysql('%(db_name)s', 
            user=env.db_user, prefix='%s %s |' % (cmd, file_path))
    else:
        warn('Skipping file, unknown format (%s)' % file_path)      

def setup_env(conf):
    """Setup the working environment as appropriate for loc, stg, prd."""  
    #
    # TO DO: SET A ROOT USER FOR REALS
    #
    if env.settings == 'loc':
        env.db_root_user = 'root'
    else:
        env.db_root_user = 'root'
 
def setup():
    """
    Create the project database and user.
    """    
    # Create the project database
    if _db_exists():
        notice('Database "%(db_name)s" exists on host %(db_host)s' % env)
    else:
        notice('Creating db "%(db_name)s"' % env)
        _mysql('-e "CREATE DATABASE %(db_name)s;"')
         
    # Create the database user
    if _user_exists():
        notice('Database user "%(db_user)s" exists on host %(db_host)s' % env)
    else:
        notice('Creating db user "%(db_user)s"' % env)
        _mysql('-e "CREATE USER \'%(db_user)s\'@\'%%\';"')
        _mysql('-e "GRANT ALL PRIVILEGES ON %(db_name)s.* TO \'%(db_user)s\'@\'%%\';"')        
    
def destroy():
    """Remove the database and user."""   
    if _user_exists():
        notice('Dropping user "%(db_user)s"' % env)
        _mysql('-e "DROP USER \'%(db_user)s\';"')
    else:
        notice('Database user "%(db_user)s" does not exist' % env)        
    
    if _db_exists():
        notice('Dropping database "%(db_name)s"' % env)
        _mysql('-e "DROP DATABASE %(db_name)s;"')
    else:
        notice('Database "%(db_name)s" does not exist' % env)    

