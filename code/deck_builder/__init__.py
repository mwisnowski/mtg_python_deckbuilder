__all__ = ['DeckBuilder']


def __getattr__(name):
    # Lazy-load DeckBuilder to avoid side effects during import of submodules
    if name == 'DeckBuilder':
        from .builder import DeckBuilder
        return DeckBuilder
    raise AttributeError(name)
