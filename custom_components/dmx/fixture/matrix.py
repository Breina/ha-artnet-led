"""
The matrix stores `Pixels`, which contain information that is used for
templating channels.
"""

import re
from dataclasses import dataclass
from functools import reduce

from custom_components.dmx.fixture.exceptions import FixtureConfigurationError


class Pixel:
    """
    A pixel is a unit in a matrix, which can be templated into template channels
    """

    def __init__(self, x: int, y: int, z: int, name: str | None = None):
        super().__init__()

        self.x = x
        self.y = y
        self.z = z
        self.name = name

    def __str__(self):
        if self.name:
            return self.name
        return f"({self.x + 1},{self.y + 1},{self.z + 1})"

    def __repr__(self):
        return self.__str__()

    def match(self, pattern: str) -> re.Match[str] | None:
        """
        Regex match a pixel name.
        :param pattern: The regex pattern that is matched against the pixel name
        :return: The regex Match object
        """
        return re.search(pattern, self.name)


def flatten(matrix: list[list[list[Pixel | None]]]) -> list[Pixel | None]:
    """
    Flatten a 3D list into a 1D list.
    :param matrix: The 3D list.
    :return: The 1D list.
    """
    return reduce(list.__add__, reduce(list.__add__, matrix))


@dataclass
class PixelGroup:
    """
    Pixels can also be grouped if a fixture allows control in different fine
    grades, like fourths or halves of a light bar.
    """

    name: str
    pixels: list[Pixel]

    def __str__(self):
        return f"{self.name}: {self.pixels.__str__()}"


class Matrix:
    """
    God class for matrix / pixel operations.
    """

    def __init__(self, pixels: list[list[list[Pixel | None]]]):
        super().__init__()
        self.pixels = pixels

        self.z_size = len(pixels)
        self.y_size = len(pixels[0])
        self.x_size = len(pixels[0][0])

        self.pixels_by_name = {}
        for yz_plane in self.pixels:
            for y_row in yz_plane:
                for pixel in y_row:
                    if pixel and pixel.name:
                        self.pixels_by_name[pixel.name] = pixel

        self.pixel_groups = {}

    def __getitem__(self, name):
        if isinstance(name, str):
            return self.pixels_by_name[name]
        return self.pixels[name]

    def dimensions(self) -> (int, int, int):
        """
        Returns a tuple containing the 3 dimensions of the 3D matrix.
        :return: x-size, y-size, z-size integers
        """
        return self.x_size, self.y_size, self.z_size

    def group(self, name: str) -> PixelGroup:
        """
        Returns a pixel group.
        :param name: The name of the pixel group.
        :return: The pixel group
        """
        return self.pixel_groups[name]

    def define_group(self, name: str, ref: str | dict | list) -> PixelGroup:
        """
        Defines a new pixel group.
        :param name: The name of the new pixel group.
        :param ref: The reference, which follows the matrix structure docs;
                    https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/fixture-format.md#matrix-structure
        :return: The newly created pixel group.
        """
        if ref == "all":
            group = PixelGroup(name, [pixel for pixel in flatten(self.pixels) if pixel])
            self.pixel_groups[name] = group
            return group

        if isinstance(ref, dict):
            x_slice = self.__map_to_slice(ref, "x")
            y_slice = self.__map_to_slice(ref, "y")
            z_slice = self.__map_to_slice(ref, "z")
            patterns = ref.get("name", [])

            flat_pixels = flatten([[row[x_slice] for row in zy_plane[y_slice]] for zy_plane in self.pixels[z_slice]])

            flat_pixels = [
                pixel for pixel in flat_pixels if pixel and all(pixel.match(pattern) for pattern in patterns)
            ]

            group = PixelGroup(name, flat_pixels)
            self.pixel_groups[name] = group
            return group

        if isinstance(ref, list):
            group = PixelGroup(name, [self[pixel_name] for pixel_name in ref])
            self.pixel_groups[name] = group
            return group

        raise FixtureConfigurationError(f"Pixel group {ref} is ill defined.")

    @staticmethod
    def __map_to_slice(ref, axis: str) -> slice:
        if axis not in ref:
            return slice(None)

        constraints = ref[axis]
        start = 0
        stop = None
        step = 1

        for constraint in constraints:
            if constraint == "odd":
                constraint = "2n+1"
            elif constraint == "even":
                constraint = "2n"

            if constraint.startswith("<="):
                stop = int(constraint[2:])
            elif constraint.startswith(">="):
                start = int(constraint[2:]) - 1
            elif constraint.startswith("="):
                exact = int(constraint[1:])
                start = exact - 1
                stop = exact
            elif "n" in constraint:
                step = int(constraint[: constraint.index("n")])
                if "+" in constraint:
                    start = int(constraint[constraint.index("+") + 1 :]) - 1
                else:
                    start = step - 1
            else:
                raise FixtureConfigurationError(f"Wtf is this kind of pixel group: {constraint}")

        return slice(start, stop, step)

    def __str__(self):
        return self.pixels.__str__()


def matrix_from_pixel_count(x_size: int, y_size: int, z_size: int) -> Matrix:
    """
    Creates a new matrix from dimensions.
    :param x_size: The size of the matrix' x-dimension.
    :param y_size: The size of the matrix' y-dimension.
    :param z_size: The size of the matrix' z-dimension.
    :return: The newly created matrix
    """
    return Matrix(
        [
            [
                [Pixel(x, y, z, str((x + 1) + y * x_size + z * (x_size + y_size))) for x in range(x_size)]
                for y in range(y_size)
            ]
            for z in range(z_size)
        ]
    )


def matrix_from_pixel_names(pixels: list[list[list[str | None]]]) -> Matrix:
    """
    Creates a new matrix from pixel names.
    :param pixels: The 3D-list of pixel names (or None)
    :return: The newly created matrix
    """
    z_size = len(pixels)
    y_size = len(pixels[0])
    x_size = len(pixels[0][0])

    for z in range(z_size):
        for y in range(y_size):
            for x in range(x_size):
                pixels[z][y][x] = Pixel(x, y, z, pixels[z][y][x]) if pixels[z][y][x] else None

    return Matrix(pixels)
