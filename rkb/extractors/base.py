"""Base extractor functionality and factory function."""


from rkb.core.interfaces import ExtractorInterface

# Registry of available extractors
_EXTRACTOR_REGISTRY: dict[str, type[ExtractorInterface]] = {}


def register_extractor(name: str, extractor_class: type[ExtractorInterface]) -> None:
    """Register an extractor class.

    Args:
        name: Name to register the extractor under
        extractor_class: Extractor class implementing ExtractorInterface
    """
    _EXTRACTOR_REGISTRY[name] = extractor_class


def get_extractor(name: str, **kwargs) -> ExtractorInterface:
    """Get an extractor instance by name.

    Args:
        name: Name of the extractor to get
        **kwargs: Configuration parameters for the extractor

    Returns:
        Configured extractor instance

    Raises:
        ValueError: If extractor name is not registered
    """
    if name not in _EXTRACTOR_REGISTRY:
        available = list(_EXTRACTOR_REGISTRY.keys())
        raise ValueError(f"Unknown extractor '{name}'. Available: {available}")

    extractor_class = _EXTRACTOR_REGISTRY[name]
    return extractor_class(**kwargs)


def list_extractors() -> list[str]:
    """List all registered extractor names.

    Returns:
        List of registered extractor names
    """
    return list(_EXTRACTOR_REGISTRY.keys())
