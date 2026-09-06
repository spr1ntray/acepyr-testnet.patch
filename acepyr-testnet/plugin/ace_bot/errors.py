from __future__ import annotations


class SoftError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class BlockedError(SoftError):
    pass
