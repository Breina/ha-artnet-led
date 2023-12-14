from homeassistant.exceptions import IntegrationError


class FixtureConfigurationError(IntegrationError):
    def __init__(self, msg: str, *args):
        super().__init__(*args)
        self.msg = msg

    def __str__(self) -> str:
        return self.msg
