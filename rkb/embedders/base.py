"""Base embedder functionality and factory function."""


from rkb.core.interfaces import EmbedderInterface

# Registry of available embedders
_EMBEDDER_REGISTRY: dict[str, type[EmbedderInterface]] = {}


def register_embedder(name: str, embedder_class: type[EmbedderInterface]) -> None:
    """Register an embedder class.

    Args:
        name: Name to register the embedder under
        embedder_class: Embedder class implementing EmbedderInterface
    """
    _EMBEDDER_REGISTRY[name] = embedder_class


def get_embedder(name: str, **kwargs) -> EmbedderInterface:
    """Get an embedder instance by name.

    Args:
        name: Name of the embedder to get
        **kwargs: Configuration parameters for the embedder

    Returns:
        Configured embedder instance

    Raises:
        ValueError: If embedder name is not registered
    """
    if name not in _EMBEDDER_REGISTRY:
        available = list(_EMBEDDER_REGISTRY.keys())
        raise ValueError(f"Unknown embedder '{name}'. Available: {available}")

    embedder_class = _EMBEDDER_REGISTRY[name]
    return embedder_class(**kwargs)


def list_embedders() -> list[str]:
    """List all registered embedder names.

    Returns:
        List of registered embedder names
    """
    return list(_EMBEDDER_REGISTRY.keys())
