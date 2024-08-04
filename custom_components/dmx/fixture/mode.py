"""
This module contains mode related functions and classes, as per matrix-format.
"""

import functools
from dataclasses import dataclass
from enum import Enum, auto
from itertools import product


class ChannelOrder(Enum):
    """
    ChannelOrder enum, defines how to loop through template channels and pixels.
    Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    perPixel = auto()
    perChannel = auto()


def matrix_pixel_order(axis0: int, axis1: int, axis2: int):
    """
    Loops through all pixels, ordered by axis.
    :param axis0: The order [0, 2] in which to sort the x-axis.
    :param axis1: The order [0, 2] in which to sort the y-axis.
    :param axis2: The order [0, 2] in which to sort the z-axis.
    :return: A lambda taking in a matrix and returning an ordered list of pixels
    """
    return lambda matrix: [matrix[x][y][z] for z, y, x in
                           sorted(product(*map(range, matrix.dimensions())),
                                  key=lambda k: (k[axis2], k[axis1], k[axis0])
                                  )
                           ]


class RepeatFor(Enum):
    """
    A repeatFor enum containing partial function which can be called upon for
    repeating pixels of a matrix, as defined by the matrix format.
    Names match fixture format exactly.
    """
    # pylint: disable=invalid-name
    eachPixelABC = functools.partial(
        lambda matrix: [matrix[name] for name in
                        sorted(matrix.pixels_by_name.keys())
                        ])
    eachPixelXYZ = functools.partial(matrix_pixel_order(0, 1, 2))
    eachPixelXZY = functools.partial(matrix_pixel_order(0, 2, 1))
    eachPixelYXZ = functools.partial(matrix_pixel_order(1, 0, 2))
    eachPixelYZX = functools.partial(matrix_pixel_order(1, 2, 0))
    eachPixelZXY = functools.partial(matrix_pixel_order(2, 0, 1))
    eachPixelZYX = functools.partial(matrix_pixel_order(2, 1, 0))
    eachPixelGroup = functools.partial(
        lambda matrix: [pixel
                        for name in sorted(matrix.pixel_groups.keys())
                        for pixel in matrix.pixel_groups[name].pixels
                        ]
    )


@dataclass
class MatrixChannelInsertBlock:
    """
    Data class containing an insert block as defined by the matrix format.
    """
    repeat_for: RepeatFor | list[str]
    order: ChannelOrder
    template_channels: list[None | str]

    def __repr__(self):
        return "matrixChannels"


@dataclass
class Mode:
    """
    Mode class as defined by the matrix format.
    """
    name: str
    channels: list[None | str | MatrixChannelInsertBlock]
    short_name: str | None = None

    def __repr__(self):
        return self.name

    def __str__(self):
        return f"{self.name}: {self.channels}"
