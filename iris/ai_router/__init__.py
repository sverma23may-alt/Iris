"""AI Router backend architecture."""

from iris.ai_router.configuration import AIRouterConfiguration, RoutingMode
from iris.ai_router.provider import AIProvider
from iris.ai_router.registry import ProviderRegistry, register_provider_type
from iris.ai_router.response import AIResponse
from iris.ai_router.router import AIRouter

__all__ = [
    "AIProvider",
    "AIResponse",
    "AIRouter",
    "AIRouterConfiguration",
    "ProviderRegistry",
    "RoutingMode",
    "register_provider_type",
]
