FabLib is a suite of tools created to help with KnightLab software development and deployment. After we made it, we realized that there is already something on [pypi with the same name](https://pypi.python.org/pypi/fablib), but we didn't really create it for general use anyway.

We're making the repository public mostly so that people who want to work on our javascript code can use it to build the javascript and CSS files the same way that we do.

### Installing

KnightLab projects are written to assume that this directory is "alongside" directories (checked out git repositories) that use it. Gradually, we'll probably switch to using PIP SSH urls to make it available as an install, but for now, you may need to clone it accordingly.

### Requirements

 [Node.js](http://nodejs.org)
 
 [LESS](http://lesscss.org)
 
    # npm install less -g
  
 [UglifyJS](https://github.com/mishoo/UglifyJS2)
 
    # npm install uglify-js -g 

If you're just using this because it's needed by StoryMapJS or another javascript project, you don't need to read further.

### Setup

Add the AWS pem file to your ssh agent:

    ssh-add <pemfile>

Set your AWS credentials in environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, or in one of these boto config files (do not quote key strings in these files):

    /etc/boto.cfg
    ~/.boto
    
Set a `WORKON_HOME` environment variable to the root directory of your local virtual environments.  If you use virtualenvwrapper, this is already set for you.  Else, set it manually.

It is assumed that all of your repositories are in a common directory and that you have checked out the `secrets` repository into that standard location.
    

### Usage

Each project should contain a `fabfile.py` at the top level of the project repository.  It should look like the following sample below.  

Once you have created your project `fabfile.py`, you can run `fab -l` to see the available Fabric commands.


    from os.path import abspath, basename, dirname, join
    import sys
    from fabric.api import env

    #
    # Project-specific settings, alter as needed
    #
    env.project_name = basename(dirname(__file__))

    #
    # Add paths
    #
    def add_paths(*args):
        """Make paths are in sys.path."""
        for p in args:
            if p not in sys.path:
                sys.path.append(p)
 
    project_path = dirname(abspath(__file__))
    repos_path = dirname(project_path)
    website_path = join(project_path, 'website') # static websites only

    add_paths(project_path, repos_path, website_path)

    #
    # Import from fablib
    #
    from fablib import *

