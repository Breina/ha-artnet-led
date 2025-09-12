"""
The matrix stores `Pixels`, which contain information that is used for
templating channels.
"""

import re
from dataclasses import dataclass
from typing import Any

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

    def __str__(self) -> str:
        if self.name:
            return self.name
        return f"({self.x + 1},{self.y + 1},{self.z + 1})"

    def __repr__(self) -> str:
        return self.__str__()

    def match(self, pattern: str) -> re.Match[str] | None:
        """
        Regex match a pixel name.
        :param pattern: The regex pattern that is matched against the pixel name
        :return: The regex Match object
        """
        if self.name is None:
            return None
        return re.search(pattern, self.name)


def flatten(matrix: list[list[list[Pixel | None]]]) -> list[Pixel | None]:
    """
    Flatten a 3D list into a 1D list.
    :param matrix: The 3D list.
    :return: The 1D list.
    """
    # Use a more explicit approach for better type safety
    result: list[Pixel | None] = []
    for z_plane in matrix:
        for y_row in z_plane:
            result.extend(y_row)
    return result


@dataclass
class PixelGroup:
    """
    Pixels can also be grouped if a fixture allows control in different fine
    grades, like fourths or halves of a light bar.
    """

    name: str
    pixels: list[Pixel]

    def __str__(self) -> str:
        return f"{self.name}: {self.pixels.__str__()}"


class Matrix:
    """
    God class for matrix / pixel operations.
    """

    def __init__(self, pixels: list[list[list[Pixel | None]]]) -> None:
        super().__init__()
        self.pixels = pixels

        self.z_size: int = len(pixels)
        self.y_size: int = len(pixels[0])
        self.x_size: int = len(pixels[0][0])

        self.pixels_by_name: dict[str, Pixel] = {}
        for yz_plane in self.pixels:
            for y_row in yz_plane:
                for pixel in y_row:
                    if pixel and pixel.name:
                        self.pixels_by_name[pixel.name] = pixel

        self.pixel_groups: dict[str, PixelGroup] = {}

    def __getitem__(self, name: str | int) -> Pixel | list[list[list[Pixel | None]]] | list[list[Pixel | None]]:
        if isinstance(name, str):
            return self.pixels_by_name[name]
        return self.pixels[name]

    def dimensions(self) -> tuple[int, int, int]:
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

    def define_group(self, name: str, ref: str | dict[str, Any] | list[str]) -> PixelGroup:
        """
        Defines a new pixel group.
        :param name: The name of the new pixel group.
        :param ref: The reference, which follows the matrix structure docs;
                    https://github.com/OpenLightingProject/open-fixture-library/blob/master/docs/fixture-format.md#matrix-structure
        :return: The newly created pixel group.
        """
        if ref == "all":
            # Filter out None pixels for PixelGroup which expects list[Pixel]
            pixels: list[Pixel] = [pixel for pixel in flatten(self.pixels) if pixel is not None]
            group = PixelGroup(name, pixels)
            self.pixel_groups[name] = group
            return group

        if isinstance(ref, dict):
            x_slice = self.__map_to_slice(ref, "x")
            y_slice = self.__map_to_slice(ref, "y")
            z_slice = self.__map_to_slice(ref, "z")
            patterns = ref.get("name", [])

            flat_pixels = flatten([[row[x_slice] for row in zy_plane[y_slice]] for zy_plane in self.pixels[z_slice]])

            # Filter out None pixels and apply pattern matching, ensuring we get list[Pixel]
            filtered_pixels: list[Pixel] = [
                pixel
                for pixel in flat_pixels
                if pixel is not None and all(pixel.match(pattern) for pattern in patterns)
            ]

            group = PixelGroup(name, filtered_pixels)
            self.pixel_groups[name] = group
            return group

        if isinstance(ref, list):
            # Ensure we get Pixel objects, not other types from __getitem__
            group_pixels: list[Pixel] = []
            for pixel_name in ref:
                pixel = self[pixel_name]
                if isinstance(pixel, Pixel):
                    group_pixels.append(pixel)
            group = PixelGroup(name, group_pixels)
            self.pixel_groups[name] = group
            return group

        raise FixtureConfigurationError(f"Pixel group {ref} is ill defined.")

    @staticmethod
    def __map_to_slice(ref: dict[str, Any], axis: str) -> slice:
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
                start = int(constraint[constraint.index("+") + 1 :]) - 1 if "+" in constraint else step - 1
            else:
                raise FixtureConfigurationError(f"Wtf is this kind of pixel group: {constraint}")

        return slice(start, stop, step)

    def __str__(self) -> str:
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

    # Create new matrix with proper typing to avoid in-place modification issues
    pixel_matrix: list[list[list[Pixel | None]]] = []

    for z in range(z_size):
        z_plane: list[list[Pixel | None]] = []
        for y in range(y_size):
            y_row: list[Pixel | None] = []
            for x in range(x_size):
                pixel_name = pixels[z][y][x]
                y_row.append(Pixel(x, y, z, pixel_name) if pixel_name else None)
            z_plane.append(y_row)
        pixel_matrix.append(z_plane)

    return Matrix(pixel_matrix)
