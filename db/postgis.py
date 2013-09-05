"""
postgres/postgis 
"""
import os
from fabric.api import env, settings, hide
from ..utils import abort, notice, warn
from . import BaseDatabase

class Database(BaseDatabase):
    def __init__(self, conf):
        super(Database, self).__init__(conf)     
        
        if env.settings == 'loc':
            self.root_user = env.local_user
            self.postgis_root = '/usr/local/share/postgis'
        else:
            self.root_user = 'postgres'
            self.postgis_root = '/usr/share/postgresql/9.1/contrib/postgis-1.5'
            
    def cmd(self, cmd, user='', prefix='', **kwargs):
        """
        Send command to psql.
        """
        if user:
            s = prefix+' psql -h {0.host} -U '+user+' '+cmd
        else:
            s = prefix+' psql -h {0.host} -U {0.root_user} '+cmd
        return env.doit((s.format(self)) % env)

    def db_exists(self, name):
        """
        Does the database exist?
        """
        with hide('warnings'), settings(warn_only=True):
            result = self.cmd('-l | grep "%s "' % name)
        return not result.failed
    
    def user_exists(self):
        """
        Does the user exist?
        """
        with hide('warnings'), settings(warn_only=True):
            result = self.cmd('-c "SELECT rolname FROM pg_roles" {0.name} | grep "{0.user}"')    
        return not result.failed
    
    def pipe_data(self, file_path):
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
            self.cmd('-c "COPY %s FROM STDIN" buzz' % table_name, 
                user=env.user, prefix='%s %s |' % (cmd, file_path))
        elif ext == '.sql':
            self.cmd('{0.name}', 
                user=self.user, prefix='%s %s |' % (cmd, file_path))
        else:
            warn('Skipping file, unknown format (%s)' % file_path)  
       
    def setup(self):
        """
        Create the project database and user.
        """
        created_db = False
    
        # Create the template database
        if self.db_exists('template_postgis'):
            notice('Template database template_postgis already exists')
        else:
            notice('Creating template database template_postgis')
            env.doit('createdb -h %{0.host} -U {0.root_user} template_postgis'.format(self))
            self.cmd('-f {0.postgis_root}/postgis.sql template_postgis')
            self.cmd('-f {0.postgis_root}/spatial_ref_sys.sql template_postgis')
       
        # Create the project database
        if self.db_exists(self.name):
            notice('Database "{0.name}" exists on host {0.host}'.format(self))
        else:    
            notice('Creating database {0.name} from template'.format(self))
            env.doit('createdb -h {0.host} -U {0.root_user} -T template_postgis {0.name}'.format(self))
            created_db = True
        
        # Create the database user
        if self.user_exists():
            notice('Database user "{0.user}" exists on host {0.host}'.format(self))
        else:
            notice('Creating db user "{0.user}"'.format(self))
            self.cmd('-c "' \
                'CREATE USER {0.user};' \
                'GRANT ALL PRIVILEGES ON DATABASE {0.name} to {0.user};' \
                '" {0.name}')
                
        if created_db:
            self.cmd('-c "' \
                'ALTER TABLE geometry_columns OWNER TO {0.user};' \
                'ALTER TABLE spatial_ref_sys OWNER TO {0.user};' \
                '" {0.name}')      
        
    def destroy(self):
        """
        Remove the database and user.
        """           
        if self.user_exists():
            notice('Dropping database user "{0.user}"'.format(self))
            self.cmd('-c "' \
                'DROP OWNED BY {0.user};' \
                'DROP USER {0.user};" {0.name}')
        else:
            notice('Database user "{0.user}" does not exist'.format(self))
    
        if self.db_exists(self.name):
            notice('Dropping database "{0.name}"'.format(self))
            env.doit('dropdb -h {0.host} -U {0.root_user} {0.name}'.format(self))
        else:
            notice('Database "{0.name}" does not exist'.format(self))    
    

