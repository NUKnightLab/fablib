"""
mongo
"""
import os
from fabric.api import env, settings, hide
from ..utils import abort, notice, warn
from . import BaseDatabase

class Database(BaseDatabase):
    def __init__(self, conf):
        super(Database, self).__init__(conf)        
 
    def cmd(self, cmd, prefix=''):
        """
        Send command to mongo.
        """
        s = prefix+' mongo -host {0.host} '+cmd
        return env.doit((s.format(self)) % env)

    def db_exists(self, name):
        with hide('warnings'), settings(warn_only=True):
            result = self.cmd('--eval ' \
                '"printjson(db.adminCommand(\'listDatabases\'));"' \
                ' | grep "\"%s\""' % name)
        return not result.failed
           
    def destroy(self):
        """
        Remove the database and user.
        """   
        if self.db_exists(self.name):
            notice('Dropping database "{0.name}"'.format(self))
            self.cmd('{0.name} --eval "printjson(db.dropDatabase())"')
        else:
            notice('Database "{0.name}" does not exist'.format(self))    

