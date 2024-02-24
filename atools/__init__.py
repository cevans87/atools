from ._cli import Decorator as CLI
from ._key import Decorator as Key
from ._memoize import Decorator as Memoize
from ._rate_decorator import rate
from ._register import Decorator as Register
from ._throttle import Decorator as Throttle

__all__ = [
    'CLI',
    'Memoize',
    'Key',
    'rate',
    'Register',
    'Throttle',
]
