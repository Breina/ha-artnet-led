"""
General exceptions that can occur within the integration.
"""

from homeassistant.exceptions import IntegrationError


class FixtureConfigurationError(IntegrationError):
    """
    Something being wrong with the fixture configuration itself.
    This is open-fixture-format related, not user-related.
    """

    def __init__(self, msg: str, *args):
        super().__init__(*args)
        self.msg = msg

    def __str__(self) -> str:
        return self.msg
