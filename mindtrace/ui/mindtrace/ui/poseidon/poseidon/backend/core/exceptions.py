class BackendError(Exception):
    """Base exception for backend errors."""
    pass

class UserAlreadyExistsError(BackendError):
    pass

class UserNotFoundError(BackendError):
    pass

class OrganizationNotFoundError(BackendError):
    pass

class InvalidCredentialsError(BackendError):
    pass 