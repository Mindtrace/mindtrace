"""Test services for providing external dependencies through Docker."""

import PIL
from PIL.Image import Image


def images_are_identical(image_1: Image, image_2: Image):
    if image_1.mode != image_2.mode:
        return False
    elif image_1.mode in ["1", "L"]:
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == ((0, 0))
    elif image_1.mode == "LA":
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == (
            (0, 0),
            (0, 0),
        )
    elif image_1.mode == "RGB":
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == (
            (0, 0),
            (0, 0),
            (0, 0),
        )
    elif image_1.mode == "RGBA":
        return PIL.ImageChops.difference(image_1, image_2).getextrema() == (
            (0, 0),
            (0, 0),
            (0, 0),
            (0, 0),
        )
    else:
        raise NotImplementedError(f"Unable to compare images of type {image_1.mode}.")


__all__ = ['images_are_identical']