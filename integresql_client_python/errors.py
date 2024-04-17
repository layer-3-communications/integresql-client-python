__all__ = [
    "DatabaseDiscarded",
    "IntegreSQLError",
    "ManagerNotReady",
    "TemplateAlreadyInitialized",
    "TemplateNotFound",
]


class IntegreSQLError(Exception):
    pass


class TemplateAlreadyInitialized(IntegreSQLError):
    pass


class ManagerNotReady(IntegreSQLError):
    pass


class TemplateNotFound(IntegreSQLError):
    pass


class DatabaseDiscarded(IntegreSQLError):
    pass
