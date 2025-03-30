class ParserFindTagException(Exception):
    """Вызывается, когда парсер не может найти тег."""
    pass


class VersionsNotFound(Exception):
    """Вызывается, когда не найдены версии Python"""
    pass
