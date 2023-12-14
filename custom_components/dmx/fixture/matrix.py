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

        self.xSize = len(pixels)
        self.ySize = len(pixels[0])
        self.zSize = len(pixels[0][0])

        self.pixelsByName = {}
        for xy_plane in self.pixels:
            for y_row in xy_plane:
                for pixel in y_row:
                    if pixel and pixel.name:
                        self.pixelsByName[pixel.name] = pixel

    def __getitem__(self, __name):
        if isinstance(__name, str):
            return self.pixelsByName[__name]
        return self.pixels[__name]

    def get_group(self, name: str, ref) -> PixelGroup:
        if ref == "all":
            return PixelGroup(name, flatten(self.pixels))

        if isinstance(ref, dict):
            xSlice = self.map_to_slice(ref, "x", self.xSize)
            ySlice = self.map_to_slice(ref, "y", self.ySize)
            zSlice = self.map_to_slice(ref, "z", self.zSize)
            return PixelGroup(name, flatten(self.pixels[xSlice][ySlice][zSlice]))

        pass

    def map_to_slice(self, ref, axis: str, max_size: int):
        if axis not in ref:
            return slice(None)

        constraints = ref[axis]
        start = 0
        stop = None
        step = 1

        for constraint in constraints:
            if constraint.startswith("<="):
                stop = int(constraint[2:]) + 1
            elif constraint.startswith(">="):
                start = int(constraint[2:])
            elif constraint.startswith("="):
                exact = int(constraint[1:])
                start = exact
                stop = exact + 1
            elif "n" in constraint:
                step = int(constraint[:constraint.index("n")])
                if "+" in constraint:
                    start = int(constraint[constraint.index("+") + 1:])
                else:
                    start = 0
            else:
                raise FixtureConfigurationError(f"Wtf is this kind of pixel group: {constraint}")

        return slice(start, stop, step)


#                 XYZ constraints are <=5, =5, >=5,
#                 3n (divisible by 3),
#                 3n+1 (divisible by 3 with remainder 1),
#                   even (≙ 2n) and odd (≙ 2n+1). Name constraints are regular expressions.

def matrix_from_pixel_count(x_size: int, y_size: int, z_size: int) -> Matrix:
    return Matrix([[[Pixel(x, y, z) for z in range(z_size)] for y in range(y_size)] for x in range(x_size)])


def matrix_from_pixel_names(pixels: list[list[list[str | None]]]) -> Matrix:
    xSize = len(pixels)
    ySize = len(pixels[0])
    zSize = len(pixels[0][0])

    for x in range(xSize):
        for y in range(ySize):
            for z in range(zSize):
                pixels[x][y][z] = Pixel(x, y, z, pixels[x][y][z]) if pixels[x][y][z] else None

    return Matrix(pixels)


# matrix = matrix_from_pixel_count(10, 3, 1)
matrix = matrix_from_pixel_names([
    [
      [ None,  "Top",     None  ],
      ["Left", "Center", "Right"],
      [ None,  "Bottom",  None  ]
    ]
  ])
print(matrix["Center"])
# print(matrix.get_group("SOME NAME", { "x": ["3n+2"]}))
# print(flatten(matrix[::3][:][:]))
