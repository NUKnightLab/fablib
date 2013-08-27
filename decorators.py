"""
Decorators
"""
from functools import update_wrapper
from fabric.api import env, require
from .utils import warn


def require_settings(fn=None, **kwargs):
    """
    Decorator preventing function from running unless env.settings is set.
    If not set, an error will be thrown via fabric.api.require().
    
    Available options:  
    
    allow:     Only run the function if env.settings is in this list.    
    verbose:   Output a warning to the user about skipped function.
    
    Examples:
    
    @require_settings
    def f():

    @require_settings(allow=['loc','stg'], verbose=True)
    def f():
    """ 
    allow = kwargs.pop('allow', None)
    verbose = kwargs.pop('verbose', False)   

    def decorator(func):
        def wrapper(*args, **kwargs):
            require('settings')
            if not allow or env.settings in allow:
                return func(*args, **kwargs)
            elif verbose:
                warn('Skipping "%s"' % func.__name__)
        return update_wrapper(wrapper, func)
        
    if fn:
        return decorator(fn)
    else:
        return decorator
