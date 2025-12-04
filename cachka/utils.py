import hashlib
import pickle
from typing import Tuple

def make_cache_key(func_name: str, args: Tuple, kwargs: dict) -> str:
    key_data = (func_name, args, tuple(sorted(kwargs.items())))
    return hashlib.sha256(
        pickle.dumps(key_data, protocol=pickle.HIGHEST_PROTOCOL)
    ).hexdigest()