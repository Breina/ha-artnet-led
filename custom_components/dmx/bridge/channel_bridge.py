import logging
from array import array
from typing import Optional, Callable, Collection, Union, Type, List, Literal

from pyartnet import Channel, BaseUniverse
from pyartnet.fades import FadeBase, LinearFade

log = logging.getLogger('pyartnet.Channel')

class ChannelBridge:

    def __init__(self, channel: Channel):
        self.__channel = channel
        self.callback_values_updated: Optional[Callable[[array[int]], None]] = None

    def _apply_output_correction(self):
        self.__channel._apply_output_correction()

    def get_values(self) -> List[int]:
        return self.__channel.get_values()

    def set_values(self, values: Collection[Union[int, float]]):
        return self.__channel.set_values(values)

    def to_buffer(self, buf: bytearray):
        return self.__channel.to_buffer(buf)

    def add_fade(self, values: Collection[Union[int, FadeBase]], duration_ms: int,
                 fade_class: Type[FadeBase] = LinearFade):
        return self.__channel.add_fade(values, duration_ms, fade_class)

    def set_fade(self, values: Collection[Union[int, FadeBase]], duration_ms: int,
                 fade_class: Type[FadeBase] = LinearFade):
        return self.__channel.set_fade(values, duration_ms, fade_class)

    def __await__(self):
        return self.__channel.__await__()

    def __repr__(self):
        return self.__channel.__repr__()

    def set_output_correction(self, func: Optional[Callable[[float, int], float]]) -> None:
        self.__channel.set_output_correction(func)

    @property
    def _start(self):
        return self.__channel._start

    @property
    def _width(self):
        return self.__channel._width

    @property
    def _stop(self):
        return self.__channel._stop

    @property
    def _byte_size(self):
        return self.__channel._byte_size

    @property
    def _byte_order(self):
        return self.__channel._byte_order

    @property
    def _value_max(self):
        return self.__channel._value_max

    @property
    def _buf_start(self):
        return self.__channel._buf_start

    @property
    def _parent_universe(self):
        return self.__channel._parent_universe

    @property
    def _parent_node(self):
        return self.__channel._parent_node

    @property
    def _current_fade(self):
        return self.__channel._current_fade

    @property
    def callback_fade_finished(self):
        return self.__channel.callback_fade_finished

    @property
    def _correction_current(self):
        return self.__channel._correction_current

    @property
    def _values_raw(self):
        return self.__channel._values_raw

    @property
    def _values_act(self):
        return self.__channel._values_act

    @callback_fade_finished.setter
    def callback_fade_finished(self, value):
        self.__channel.callback_fade_finished = value

    @_correction_current.setter
    def _correction_current(self, value):
        self.__channel._correction_current = value

    @_values_raw.setter
    def _values_raw(self, value):
        self.__channel._values_raw = value

    @_values_act.setter
    def _values_act(self, value):
        self.__channel._values_act = value

    def from_buffer(self, buf: bytearray):
        byte_order = self.__channel._byte_order
        byte_size = self.__channel._byte_size

        # TODO reverse correction not supported yet
        # correction = self.__channel._correction_current
        # value_max = self.__channel._value_max

        start_index = self.__channel._start - 1
        end_index = self.__channel._stop

        byte_chunks = self.__chunks(buf[start_index:end_index], byte_size)

        values_act = array(
            'i', [int.from_bytes(byte_chunk, byte_order, signed=False)
                  for byte_chunk in byte_chunks
                  if len(byte_chunk) == byte_size]
        )
        values_act = values_act + array(values_act.typecode, [-1] * (len(self.__channel._values_act) - len(values_act)))

        changed = False
        for act_value_index, act_value in enumerate(values_act):
            if act_value == -1:
                log.warning(f"Channel {start_index + act_value_index} was updated externally, but is part of an "
                            f"incomplete {byte_size} byte number. This is very likely unintended by the external "
                            f"controller.")
                break

            if self.__channel._values_act[act_value_index] == act_value:
                continue

            self.__channel._values_act[act_value_index] = act_value
            changed = True

        if not changed:
            return

        # TODO reverse correction not supported yet
        # values_raw = [round(correction.reverse_correct(val, value_max)) for val in values_act]
        values_raw = [val for val in values_act]
        for raw_value_index, raw_value in enumerate(values_raw):
            self.__channel._values_raw[raw_value_index] = raw_value

        if self.callback_values_updated is not None:
            self.callback_values_updated(self.__channel._values_raw)

    @staticmethod
    def __chunks(lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]