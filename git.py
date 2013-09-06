import os
import re
from fabric.api import env, local, run
from fabric.context_managers import cd, lcd
from fabric.decorators import roles
from fabric.operations import prompt
from fabric.utils import puts
from .utils import abort, warn


_ready_status = '# On branch master\nnothing to commit'

_not_ready_msg = '' \
    'You have uncommitted local code changes. ' \
    'Please commit and push changes before deploying.'

 
def check_clean(force=False):   
    git_status = os.popen('git status').read()
    if not force and not git_status.startswith(_ready_status):    
        abort(_not_ready_msg)      

@roles('app', 'work') 
def checkout():
    """Pull the latest code from github."""
    run('cd %(project_path)s; git pull' % env)    

@roles('app', 'work') 
def clone_repo():
    """Clone the git repository."""
    run('git clone %(repo_url)s %(project_path)s' % env)

def tags():
    """Get list of current tags"""
    if env.settings == 'loc':
        with lcd(env.project_path):
            tags = local('cd %(project_path)s;git tag' % env, capture=True)
    else:
        with cd(env.project_path):
            tags = run('cd %(project_path)s;git tag' % env)      
    if tags:
        return [x.strip() for x in tags.strip().split('\n')]
    return []
 
def last_tag():
    """Get the last version tag"""
    re_num = re.compile('[^0-9.]')
    tag_list = sorted([map(int, re_num.sub('', t).split('.')) for t in tags()])
    if tag_list:
        return '.'.join(map(str, tag_list[-1]))
    return None  

def prompt_tag(msg, unique=False):
    """Prompt user for a version tag.  Pass unique=True to require a new one."""
    tag_list = tags()
    puts('This project has the following tags:')
    puts(tag_list)
        
    while True:
        version = prompt("%s: " % msg).strip()      
        if unique:
            if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', version):
                warn('Invalid version number, must be in the format:' \
                    ' major.minor.revision')
            elif version in tag_list:
                warn('Invalid version number, tag already exists')
            else:
                break   
        elif not version in tag_list:
            warn('You must enter an existing version')
        else:
            break
         
    return version   

def push_tag(version):
    """Create and push a tag"""
    with lcd(env.project_path):
        local('git tag %s' % version)
        local('git push origin %s' % version)    

def delete_tag(version):
    """Delete and push a tag"""
    with lcd(env.project_path):
        local('git tag -d %s' % version)
        local('git push origin :refs/tags/%s' % version)    
    
    
        
               
    