"""
This module contains mode related functions and classes, as per matrix-format.
"""

import functools
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto, member
from itertools import product
from typing import Any


class ChannelOrder(Enum):
    """
    ChannelOrder enum, defines how to loop through template channels and pixels.
    Names match fixture format exactly.
    """

    # pylint: disable=invalid-name
    perPixel = auto()  # noqa: N815
    perChannel = auto()  # noqa: N815


def matrix_pixel_order(axis0: int, axis1: int, axis2: int) -> Callable[[Any], list[Any]]:
    """
    Loops through all pixels, ordered by axis.
    :param axis0: The order [0, 2] in which to sort the x-axis.
    :param axis1: The order [0, 2] in which to sort the y-axis.
    :param axis2: The order [0, 2] in which to sort the z-axis.
    :return: A lambda taking in a matrix and returning an ordered list of pixels
    """
    return lambda matrix: [
        matrix[x][y][z]
        for z, y, x in sorted(product(*map(range, matrix.dimensions())), key=lambda k: (k[axis2], k[axis1], k[axis0]))
    ]


class RepeatFor(Enum):
    """
    A repeatFor enum containing partial function which can be called upon for
    repeating pixels of a matrix, as defined by the matrix format.
    Names match fixture format exactly.
    """

    # pylint: disable=invalid-name
    eachPixelABC = member(  # noqa: N815
        functools.partial(lambda matrix: [matrix[name] for name in sorted(matrix.pixels_by_name.keys())])
    )
    eachPixelXYZ = member(functools.partial(matrix_pixel_order(0, 1, 2)))  # noqa: N815
    eachPixelXZY = member(functools.partial(matrix_pixel_order(0, 2, 1)))  # noqa: N815
    eachPixelYXZ = member(functools.partial(matrix_pixel_order(1, 0, 2)))  # noqa: N815
    eachPixelYZX = member(functools.partial(matrix_pixel_order(1, 2, 0)))  # noqa: N815
    eachPixelZXY = member(functools.partial(matrix_pixel_order(2, 0, 1)))  # noqa: N815
    eachPixelZYX = member(functools.partial(matrix_pixel_order(2, 1, 0)))  # noqa: N815
    eachPixelGroup = member(  # noqa: N815
        functools.partial(
            lambda matrix: [
                pixel for name in sorted(matrix.pixel_groups.keys()) for pixel in matrix.pixel_groups[name].pixels
            ]
        )
    )


@dataclass
class MatrixChannelInsertBlock:
    """
    Data class containing an insert block as defined by the matrix format.
    """

    repeat_for: RepeatFor | list[str]
    order: ChannelOrder
    template_channels: list[None | str]

    def __repr__(self) -> str:
        return "matrixChannels"


@dataclass
class Mode:
    """
    Mode class as defined by the matrix format.
    """

    name: str
    channels: list[None | str | MatrixChannelInsertBlock]
    short_name: str | None = None

    def __post_init__(self) -> None:
        if self.short_name is None:
            self.short_name = self.name

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return f"{self.name}: {self.channels}"
