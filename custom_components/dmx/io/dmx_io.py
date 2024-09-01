from typing import List, Callable


class Universe:
    def __init__(self):
        pass

    def register_channel_listener(self, channels: int | List[int],
                                  callback: Callable[[int], None]
                                  ) -> None:
        pass

    async def update_value(self, channel: int | List[int], value: int) -> None:
        print(f"Updating {channel} to {value}")
        pass
