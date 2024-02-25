from . import _context
from . import _key
from . import _register
#from ._memoize import Decorator as Memoize
#from ._rate_decorator import rate
#from ._register import Decorator as Register
#from ._throttle import Decorator as Throttle

Context = _context.Decorator.Top
Key = _key.Decorator.Top
Register = _register.Decorator.Top

#__all__ = [
#    'CLI',
#    'Memoize',
#    'Key',
#    'rate',
#    'Register',
#    'Throttle',
#]
