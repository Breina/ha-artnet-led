import re
from functools import reduce

from custom_components.dmx.fixture.exceptions import FixtureConfigurationError


class Pixel:
    def __init__(self, x: int, y: int, z: int, name: str | None = None):
        super().__init__()

        self.x = x
        self.y = y
        self.z = z
        self.name = name

    def __str__(self):
        if self.name:
            return self.name
        else:
            return f"({self.x},{self.y},{self.z})"

    def __repr__(self):
        return self.__str__()

    def match(self, pattern: str):
        return re.search(pattern, self.name)


def flatten(matrix: list[list[list[Pixel]]]) -> list[Pixel]:
    return reduce(list.__add__, reduce(list.__add__, matrix))


class PixelGroup:

    def __init__(self, name: str, pixels: list[Pixel]):
        super().__init__()
        self.name = name
        self.pixels = pixels

    def __str__(self):
        return f"{self.name}: {self.pixels.__str__()}"


class Matrix:
    def __init__(self, pixels: list[list[list[Pixel | None]]]):
        super().__init__()
        self.pixels = pixels

        self.zSize = len(pixels)
        self.ySize = len(pixels[0])
        self.xSize = len(pixels[0][0])

        self.pixelsByName = {}
        for yz_plane in self.pixels:
            for y_row in yz_plane:
                for pixel in y_row:
                    if pixel and pixel.name:
                        self.pixelsByName[pixel.name] = pixel

        self.pixelGroups = {}

    def __getitem__(self, __name):
        if isinstance(__name, str):
            return self.pixelsByName[__name]
        return self.pixels[__name]

    def group(self, name: str) -> PixelGroup:
        return self.pixelGroups[name]

    def create_group(self, name: str, ref) -> PixelGroup:
        if ref == "all":
            group = PixelGroup(name, [pixel for pixel in flatten(self.pixels) if pixel])
            self.pixelGroups[name] = group
            return group

        if isinstance(ref, dict):
            xSlice = self.map_to_slice(ref, "x", self.xSize)
            ySlice = self.map_to_slice(ref, "y", self.ySize)
            zSlice = self.map_to_slice(ref, "z", self.zSize)
            patterns = ref.get("name", [])

            flatPixels = flatten([[row[xSlice] for row in zy_plane[ySlice]] for zy_plane in self.pixels[zSlice]])

            flatPixels = [pixel for pixel in flatPixels
                          if pixel and all([pixel.match(pattern) for pattern in patterns])
                          ]

            group = PixelGroup(name, flatPixels)
            self.pixelGroups[name] = group
            return group

        if isinstance(ref, list):
            group = PixelGroup(name, list(map(lambda pixel_name: self[pixel_name], ref)))
            self.pixelGroups[name] = group
            return group

        raise FixtureConfigurationError(f"Pixel group {ref} is ill defined.")

    def map_to_slice(self, ref, axis: str, max_size: int):
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
                step = int(constraint[:constraint.index("n")])
                if "+" in constraint:
                    start = int(constraint[constraint.index("+") + 1:]) - 1
                else:
                    start = step - 1
            else:
                raise FixtureConfigurationError(f"Wtf is this kind of pixel group: {constraint}")

        return slice(start, stop, step)

    def __str__(self):
        return self.pixels.__str__()


def matrix_from_pixel_count(x_size: int, y_size: int, z_size: int) -> Matrix:
    return Matrix([[[Pixel(x, y, z, str((x + 1) + y * x_size + z * (x_size + y_size)))
                     for x in range(x_size)] for y in range(y_size)] for z in range(z_size)])


def matrix_from_pixel_names(pixels: list[list[list[str | None]]]) -> Matrix:
    zSize = len(pixels)
    ySize = len(pixels[0])
    xSize = len(pixels[0][0])

    for z in range(zSize):
        for y in range(ySize):
            for x in range(xSize):
                pixels[z][y][x] = Pixel(x, y, z, pixels[z][y][x]) if pixels[z][y][x] else None

    return Matrix(pixels)

# matrix = matrix_from_pixel_count(10, 3, 1)
# matrix = matrix_from_pixel_names([
#     [
#         [None, "Top", None],
#         ["Left", "Center", "Right"],
#         [None, "Bottom", None]
#     ]
# ])
# print(matrix["Center"])
# print(matrix.get_group("SOME NAME", { "x": ["3n+2"]}))
# print(matrix.get_group("SOME NAME", ["Center", "Bottom"]))
# print(flatten(matrix[::3][:][:]))
