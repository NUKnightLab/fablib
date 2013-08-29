"""
Apache-related utilities
"""
from fabric.api import env, run
from fabric.contrib.files import exists
from fabric.decorators import roles, task
from .decorators import require_settings
from .fos import join
from .utils import do, symlink


APACHE_CONF_NAME = 'apache' # inside conf/stg, conf/prd
APACHE_MAINTENANCE_CONF_NAME = 'apache.maintenance'


@roles('app')
@require_settings(allow=['stg','prd'])
def link_conf(maint=False):
    if maint:
        link_file = APACHE_MAINTENANCE_CONF_NAME
    else:
        link_file = APACHE_CONF_NAME
    apache_conf = join(env.project_path, 'conf', env.settings, link_file)
    if exists(apache_conf):
        run('mkdir -p %(apache_path)s' % env)
        link_path = join(env.apache_path, env.project_name)
        symlink(apache_conf, link_path)

@roles('app')
@require_settings(allow=['stg','prd'])
def unlink_conf(maint=False):
    link_path = join(env.apache_path, env.project_name)
    if exists(link_path):
        run('rm %s' % link_path)

@task
@roles('app')    
@require_settings(allow=['stg','prd'])                    
def start():
    """Start apache.  Uses init.d instead of apachectl for fabric."""
    run('sudo /etc/init.d/apache2 start')

@task
@roles('app')    
@require_settings(allow=['stg','prd'])                    
def stop(graceful='y'):
    """Stop apache.  Set graceful=n for immediate stop (default = y)."""
    if do(graceful):
        run('sudo /usr/sbin/apache2ctl graceful-stop')
    else:
        run('sudo /usr/sbin/apache2ctl stop')

@task
@roles('app')    
@require_settings(allow=['stg','prd'])                    
def restart(graceful='y'):
    """Restart apache.  Set graceful=n for immediate restart (default = y)."""
    if do(graceful):
        run('sudo /usr/sbin/apache2ctl graceful')
    else:
        run('sudo /usr/sbin/apache2ctl restart')

@task
@roles('app')
@require_settings(allow=['stg','prd'])                    
def mrostart():
    """Start maintenance mode (maintenance/repair/operations)."""
    link_conf(maint=True)
    restart()

    
@task
@roles('app')
@require_settings(allow=['stg','prd'])                    
def mrostop():
    """End maintenance mode."""
    link_conf()
    restart()
