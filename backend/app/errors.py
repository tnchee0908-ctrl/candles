"""Доменные ошибки. Их текст показывается пользователю как есть — вместо 500 Internal Server Error."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class Conflict(DomainError):
    status_code = 409
