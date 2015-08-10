"""
File-related utilities
"""
import os
from fabric.api import local
from fabric.context_managers import hide
from fabric.utils import puts
from .utils import abort


def exists(path, required=False):
    """Does path exist?"""
    ret = os.path.exists(path)
    if not ret and required:
        abort('Could not find %s.' % path)
    return ret


def join(*args):
    """Join paths."""
    return os.path.join(*args)

    
def ls(d):
    """Get a directory listing."""
    with hide('commands'):
        return [join(d, f) for f in local("ls -1 %s" % d, 
            capture=True).splitlines()] 
      

def clean(path):
    """Delete contents of local path"""
    path = os.path.abspath(path)
    puts('clean: %s' % path)

    if exists(path): 
        with hide('commands'):
            result = local('file -b %s' % path, capture=True)

            if result == 'directory':
                for item in ls(path):
                    local('rm -rf %s' % item)         
            else:
                local('rm -rf %s' % path)


def makedirs(path, isfile=False):
    """Make directories in path"""
    if isfile:
        path = os.path.dirname(path)
    if not exists(path):
        with hide('commands'):
            local('mkdir -p %s' % path)


def relpath(root_path, path):
    """
    Get relative path from root_path.  This differs from os.path.relpath
    in that it will return an empty string if path == root_path.
    """
    if root_path == path:
        return ''
    return os.path.relpath(path, root_path)        
               