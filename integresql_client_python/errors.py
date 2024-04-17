__all__ = [
    "BadDatabaseID",
    "DatabaseDiscarded",
    "DatabaseInUse",
    "IntegreSQLError",
    "ManagerNotReady",
    "NotFound",
    "TemplateAlreadyInitialized",
    "TemplateNotFound",
]


class IntegreSQLError(Exception):
    pass


class BadDatabaseID(IntegreSQLError):
    pass


class DatabaseInUse(IntegreSQLError):
    pass


class TemplateAlreadyInitialized(IntegreSQLError):
    pass


class ManagerNotReady(IntegreSQLError):
    pass


class TemplateNotFound(IntegreSQLError):
    pass


class DatabaseDiscarded(IntegreSQLError):
    pass


class NotFound(IntegreSQLError):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
