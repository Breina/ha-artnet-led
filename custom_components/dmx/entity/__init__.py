from homeassistant.exceptions import IntegrationError


class DmxRuntimeError(IntegrationError):

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __str__(self) -> str:
        return self.reason
