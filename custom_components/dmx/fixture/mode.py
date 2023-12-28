import functools
from enum import Enum, auto
from itertools import product
from typing import Callable

from custom_components.dmx.fixture.matrix import Matrix


class ChannelOrder(Enum):
    perPixel = auto()
    perChannel = auto()


def matrix_pixel_order(axis0: int, axis1: int, axis2: int) -> Callable[[Matrix], (int, int, int)]:
    return lambda matrix: [matrix[x][y][z] for x, y, z in
                           sorted(product(matrix.dimensions()), key=lambda k: (k[axis2], k[axis1], k[axis0]))
                           ]


class RepeatFor(Enum):
    eachPixelABC = functools.partial(
        lambda matrix: [matrix[name] for name in sorted(matrix.pixelsByName.keys())]
    )
    eachPixelXYZ = matrix_pixel_order(0, 1, 2)
    eachPixelXZY = matrix_pixel_order(0, 2, 1)
    eachPixelYXZ = matrix_pixel_order(1, 0, 2)
    eachPixelYZX = matrix_pixel_order(1, 2, 0)
    eachPixelZXY = matrix_pixel_order(2, 0, 1)
    eachPixelZYX = matrix_pixel_order(2, 1, 0)
    eachPixelGroup = functools.partial(
        lambda matrix: [pixel for name in sorted(matrix.pixelGroups.keys()) for pixel in matrix.pixelGroups[name]]
    )


class MatrixChannelInsertBlock:
    def __init__(self, repeat_for: RepeatFor | list[str], order: ChannelOrder, template_channels: list[None | str]):
        self.repeat_for = repeat_for
        self.order = order
        self.template_channels = template_channels

    def __repr__(self):
        return "matrixChannels"


class Mode:
    def __init__(self, name: str, channels: list[None | str | MatrixChannelInsertBlock], short_name: str | None = None):
        assert channels

        self.name = name
        self.short_name = short_name
        self.channels = channels

    def __repr__(self):
        return self.name

    def __str__(self):
        return f"{self.name}: {self.channels}"
