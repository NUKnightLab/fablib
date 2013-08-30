"""
File-related utilities
"""
import os
from fabric.api import env, local, run
from fabric.context_managers import hide
import fabric.contrib.files
from fabric.utils import puts

def clean(path):
    """Delete contents of path"""
    path = os.path.abspath(path)
    puts('clean: %s' % path)

    if exists(path): 
        with hide('commands'):
            if env.settings == 'loc':
                result = local('file -b %s' % path, capture=True)
            else:
                result = run('file -b %s' % path)

            if result == 'directory':
                for item in ls(path):
                    env.doit('rm -rf %s' % item)         
            else:
                env.doit('rm -rf %s' % path)
                
def exists(path, required=False):
    """Does path exist?"""
    if env.settings == 'loc':   
        ret = os.path.exists(path)
    else:
        ret = fabric.contrib.files.exists(path)    
    if not ret and required:
        abort('Could not find %s.' % path)
    return ret
      
def ls(d):
    """Get a directory listing."""
    with hide('commands'):
        if env.settings == 'loc':
            return [join(d, f) for f in local("ls -1 %s" % d, 
                capture=True).splitlines()] 
        return [join(d, f) for f in run("ls -1 %s" % d).splitlines()] 

def join(*args):
    """Join paths."""
    return os.path.join(*args)

def makedirs(path, isfile=False):
    """Make directories in path"""
    if isfile:
        path = os.path.dirname(path)
    if not exists(path):
        with hide('commands'):
            env.doit('mkdir -p %s' % path)

def relpath(root_path, path):
    """
    Get relative path from root_path.  This differs from os.path.relpath in
    that it will return an empty string if path == root_path.
    """
    if root_path == path:
        return ''
    return os.path.relpath(path, root_path)        
               