"""
postgres/postgis 

seed data:
    <project>/data/db/postgis/seed/
    
sample data:
    <project>/data/db/postgis/sample/
    
See _pipe_data() for acceptable formats and file-naming conventions.
"""
from fabric.api import env, settings, hide
from fabric.contrib.files import exists
from fabric.decorators import roles, runs_once
import os
from ..utils import notice, warn, abort, path, ls, do, confirm
from . import django_sync


def _psql(cmd, user='', prefix=''):
    c = ' psql -h %(db_host)s -U '+(user or env.db_root_user)+ ' '
    return env.doit((prefix+c+cmd) % env)

def _db_exists(db_name):
    with hide('warnings'), settings(warn_only=True):
        result = _psql('-l | grep "%s "' % db_name)
    return not result.failed
    
def _user_exists():
    with hide('warnings'), settings(warn_only=True):
        result = _psql('-c "SELECT rolname FROM pg_roles" %(db_name)s | grep "%(db_user)s"')    
    return not result.failed
    
def _pipe_data(file_path):
    """
    Pipe data from a file to the db.  Types of files:
    
    1.  Files created using pg_dump (full SQL statements).
    
    These are loaded by piping their contents directly to psql.
    
        any_name_is_fine.sql[.gz|.gzip|.zip|.Z]
    
    2.  Files created from psql using -c "SELECT..." (data only).
    
    These are loaded by piping their contains to to psql and having psql
    copy the data from STDIN using the COPY statement.  The table_name
    component of the filename MUST match the name of the table in the db.
    
        table_name.copy.[.gz|.gzip|.zip|.Z]
        
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
                 
    if ext == '.copy':
        (other, table_name) = os.path.split(other)
        _psql('-c "COPY %s FROM STDIN" buzz' % table_name, 
            user=env.db_user, prefix='%s %s |' % (cmd, file_path))
    elif ext == '.sql':
        _psql'%(db_name)s', 
            user=env.db_user, prefix='%s %s |' % (cmd, file_path))
    else:
        warn('Skipping file, unknown format (%s)' % file_path)  

def setup_env(conf):
    """Setup the working environment as appropriate for loc, stg, prd."""    
    if env.settings == 'loc':
        env.db_root_user = env.local_user
        env.postgis_root = '/usr/local/share/postgis'
    else:
        env.db_root_user = 'postgres'
        env.postgis_root = '/usr/share/postgresql/9.1/contrib/postgis-1.5'
        
@roles('app', 'work')  
@runs_once
def setup():
    """Create the project database and user."""
    created_db = False
    
    # Create the template database
    if _db_exists('template_postgis'):
        notice('Template database template_postgis already exists')
    else:
        notice('Creating template database template_postgis')
        env.doit('createdb -h %(db_host)s -U %(db_root_user)s template_postgis' % env)
        _psql('-f %(postgis_root)s/postgis.sql template_postgis')
        _psql('-f %(postgis_root)s/spatial_ref_sys.sql template_postgis')
       
    # Create the project database
    if _db_exists(env.db_name):
        notice('Database %(db_name)s already exists' % env)
    else:    
        notice('Creating database %(db_name)s from template' % env)
        env.doit('createdb -h %(db_host)s -U %(db_root_user)s -T template_postgis %(db_name)s' % env)
        created_db = True
        
    # Create the database user
    if _user_exists():
        if created_db:
            _psql('-c "' \
                'ALTER TABLE geometry_columns OWNER TO %(db_user)s;' \
                'ALTER TABLE spatial_ref_sys OWNER TO %(db_user)s;' \
                '" %(db_name)s')      
    else:
        notice('Creating database user %(db_user)s' % env)
        _psql('-c "' \
            'CREATE USER %(db_user)s;' \
            'GRANT ALL PRIVILEGES ON DATABASE %(db_name)s to %(db_user)s;' \
            'ALTER TABLE geometry_columns OWNER TO %(db_user)s;' \
            'ALTER TABLE spatial_ref_sys OWNER TO %(db_user)s;' \
            '" %(db_name)s')
    
@roles('app', 'work')
@runs_once
def sync():
    django_sync()

@roles('app', 'work')
@runs_once
def seed(sample='n'):
    """
    Seed the database.  Set sample=y to load sample data (default = n).
    Must be run from the app or work server to pipe data to psql.
    """
    d = path(env.data_path, 'db', 'postgis', 'seed')   
    if exists(d):
        files = ls(d)     
        for f in files:
            _pipe_data(f)                    
                        
    d = path(env.data_path, 'db', 'postgis', 'sample')
    if do(sample) and exists(d):
        files = ls(d)        
        for f in files:
            _pipe_data(f)
    
@roles('app', 'work')
@runs_once
def destroy():
    """Remove the database and user."""   
    warn('This will delete the %(db_name)s db and %(db_user)s user ' \
        'for %(settings)s on %(db_host)s.')        
    if not confirm('Continue? (y/n) ' % env):
        abort('Cancelling')
        
    if _user_exists():
        notice('Dropping user %(db_user)s' % env)
        _psql('-c "DROP OWNED BY %(db_user)s;DROP USER %(db_user)s;" %(db_name)s')
    else:
        notice('Database user %(db_user)s does not exist' % env)
    
    if _db_exists():
        notice('Dropping database %(db_name)s' % env)
        env.doit('dropdb -h %(host)s -U %(db_root_user)s %(db_name)s' % env)
    else:
        notice('Database %(db_name)s does not exist' % env)    
    

