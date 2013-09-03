"""
mysql
"""
import os
from fabric.api import env, settings, hide
from ..utils import abort, notice, warn
from . import BaseDatabase


class Database(BaseDatabase):
    def __init__(self, conf):
        super(Database, self).__init__(conf)    

        if env.settings == 'loc':
            self.root_user = conf.get('ROOT_USER', 'root')
            self.root_password = conf.get('ROOT_PASSWORD', '')
        else:
            self.root_user = conf.get('ROOT_USER', '')
            self.root_password = conf.get('ROOT_PASSWORD', '')
        
            if not self.root_user:
                abort('No "ROOT_USER" found in DATABASES settings')
            if not self.root_password:
                abort('No "ROOT_PASSWORD" found in DATABASES settings')

    def cmd(self, cmd, prefix='', **kwargs): 
        """
        Send command to mysql.
        """  
        s = prefix+' mysql -h {0.host} -u {0.root_user} '
        if self.root_password:
            s += ' -p"{0.root_password}" '
        s += cmd      
        return env.doit(s.format(self) % env, **kwargs)
        
    def db_exists(self, name):
        """
        Does the database exist?
        """
        with hide('warnings'), settings(warn_only=True):
            result = self.cmd('-e "SHOW DATABASES;" | grep "^%s$"' % name)
        return not result.failed
            
    def user_exists(self):
        """
        Does the user exist?
        """
        with hide('warnings'), settings(warn_only=True):
            result = self.cmd('-e ' \
                '"SELECT User FROM mysql.user;" | grep "^{0.user}$"')
        return not result.failed
       
    def pipe_data(self, file_path):
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
            self.cmd('{0.name}', prefix='%s %s |' % (cmd, file_path))
        else:            
            warn('Skipping file, unknown format (%s)' % file_path)      

    def dump_data(self, file_path):
        """
        Dump data from database to file.
        """    
        with hide('commands'):
            if env.settings == 'loc':
                result = self.cmd('-e "SHOW TABLES;" {0.name}', capture=True)
            else:
                result = self.cmd('-e "SHOW TABLES;" {0.name}')

        c = 'mysqldump -h {0.host} -u {0.user}'
        if env.password:
            c += ' -p"{0.password}" '        
       
        # Ignore django administrative tables     
        for line in result.splitlines():
            if line.startswith('+'):
                continue
            name = line.strip('| ') 
           
            if name.startswith('Tables_in_'):
                continue
            if name.startswith('auth_') or name.startswith('django_'):
                c += ' --ignore-table={0.name}.'+name
        
        env.doit((c+' {0.name} > '+file_path).format(self))
           
    def setup(self):
        """
        Create the project database and user.
        """    
        # Create the project database
        if self.db_exists(self.name):
            notice('Database "{0.name}" exists on host {0.host}'.format(self))
        else:
            notice('Creating db "{0.name}"'.format(self))
            self.cmd('-e "CREATE DATABASE {0.name};"')
         
        # Create the database user
        if self.user_exists():
            notice('Database user "{0.user}" exists on host {0.host}'.format(self))
        else:
            notice('Creating db user "{0.user}"'.format(self))
            if self.password:
                self.cmd('-e "CREATE USER \'{0.user}\' IDENTIFIED BY \'{0.password}\';"')        
            else:
                self.cmd('-e "CREATE USER \'{0.user}\';"')
            self.cmd('-e "GRANT ALL PRIVILEGES ON {0.name}.* TO \'{0.user}\';"') 
            self.cmd('-e "FLUSH PRIVILEGES;"')       
    
    def destroy(self):
        """
        Remove the database and user.
        """   
        if self.user_exists():
            notice('Dropping database user "{0.user}"'.format(self))
            self.cmd('-e "DROP USER \'{0.user}\';"')
        else:
            notice('Database user "{0.user}" does not exist'.format(self))        
    
        if self.db_exists(self.name):
            notice('Dropping database "{0.name}"'.format(self))
            self.cmd('-e "DROP DATABASE {0.name};"')
        else:
            notice('Database "{0.name}" does not exist'.format(self))    
        

    

