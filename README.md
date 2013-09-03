### Setup

Add the AWS pem file to your ssh agent:

    ssh-add <pemfile>

Set your AWS credentials in environment variables `AWS_ACCESS_SECRET_KEY` and `AWS_SECRET_ACCESS_KEY`, or in one of these boto config files (do not quote key strings in these files):

    /etc/boto.cfg
    ~/.boto
    
Set a `WORKON_HOME` environment variable to the root directory of your local virtual environments.  If you use virtualenvwrapper, this is already set for you.  Else, set it manually.

It is assumed that all of your repositories are in a common directory and that you have checked out the `secrets` repository into that standard location.
    

### Usage

Each project should contain a `fabfile.py` at the top level of the project repository.  It should look like the following sample below.  Typically, you would only need to make sure that `env.django` is set to the proper value of `True` or `False` depending on whether or not your project uses django.

Once you have created your project `fabfile.py`, you can run `fab -l` to see the available Fabric commands.


    from os.path import abspath, basename, dirname, join
    import sys
    from fabric.api import env

    #
    # Project-specific settings, alter as needed
    #
    env.project_name = basename(dirname(__file__))
    env.django = True

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

    add_paths(project_path, repos_path)

    #
    # Import from fablib
    #
    from fablib import *

