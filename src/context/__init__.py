from functools import lru_cache
from context.config import ApiConfig


@lru_cache(maxsize=1)
def get_config() -> ApiConfig:
    return ApiConfig()


config = get_config()
