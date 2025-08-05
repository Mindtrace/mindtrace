import math
from torchvision.transforms import v2
from torchvision import transforms
from torchvision.transforms.v2 import functional as F
import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2
import numpy as np
import torch
from PIL import Image, ImageOps
import random

def channel_shuffle(image, **kwargs):
    channels = np.arange(image.shape[2])
    np.random.shuffle(channels)
    return image[:, :, channels]

class ResizeSquareWithPaddingNormalize:
    """
    ResizeSquareWithPadding(size)

    A PyTorch-style image transformation class for resizing images to a square with padding.

    Args:
        size (int): The desired size of the square after resizing and padding.

    Returns:
        torch.Tensor: The resized image tensor.

    Example:
        transform = transforms.Compose([
            # ... other transformations ...
            toTensor(),
            ResizeSquareWithPadding(size=256),
        ])
    Note:
        This transformation is designed to be applied at the end of the image transformations
        to ensure that the final image is a square with padding.
    """

    def __init__(self, size, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], return_mask=True):
        """
        Initialize the ResizeSquareWithPadding transformation.

        Args:
            size (int): The desired size of the square after resizing.
        """
        self.size = size
        self.mean = mean
        self.std = std
        self.return_mask = return_mask
        self.normalize = transforms.Normalize(mean=self.mean, std=self.std)

    def __call__(self, img_tensor,normalize=True,interpolation=F.InterpolationMode.BILINEAR):
        """
        Apply the ResizeSquareWithPadding transformation to the input image tensor.

        Args:
            img_tensor (torch.Tensor): The input image tensor.

        Returns:
            torch.Tensor: The resized image tensor.
        """
        # Get the original width and height of the image
        _, height, width = img_tensor.shape

        # Calculate new size while preserving the aspect ratio
        if width > height:
            new_width = self.size
            new_height = int(self.size * height / width)
        else:
            new_height = self.size
            new_width = int(self.size * width / height)

        # Resize the image
        if img_tensor.ndim==2:
            img_tensor = img_tensor.unsqueeze(0)

        img_tensor = F.resize(img_tensor, [new_height, new_width], antialias=True,interpolation=interpolation)

        # Calculate padding needed to make the image square
        padding_width = max(0, (self.size - new_width) / 2)
        delta_left, delta_right = math.ceil(padding_width), math.floor(padding_width)
        padding_height = max(0, (new_width - new_height) / 2)
        delta_top, delta_bottom = math.ceil(padding_height), math.floor(padding_height)

        # Padding values for left, top, right, and bottom
        padding = [delta_left, delta_top, delta_right, delta_bottom]

        # Apply padding
        img = F.pad(img_tensor, padding, fill=0, padding_mode="constant")

        mask = torch.ones_like(img_tensor)
        mask = F.pad(mask, padding, fill=0, padding_mode='constant')
        if normalize:
            img = self.normalize(img)

        if self.return_mask:
            return img, mask
        else:
            return img

class ResizeSquareWithNormalize:
    """
    ResizeSquareWithoutPadding(size)

    A PyTorch-style image transformation class for resizing images to a square with padding.

    Args:
        size (int): The desired size of the square after resizing and padding.

    Returns:
        torch.Tensor: The resized image tensor.

    Example:
        transform = transforms.Compose([
            # ... other transformations ...
            toTensor(),
            ResizeSquareWithNormalize(size=256),
        ])
    Note:
        This transformation is designed to be applied at the end of the image transformations
        to ensure that the final image is a square with padding.
    """

    def __init__(self, size, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], return_mask=True):
        """
        Initialize the ResizeSquareWithPadding transformation.

        Args:
            size (int): The desired size of the square after resizing.
        """
        self.size = size
        self.mean = mean
        self.std = std
        self.return_mask = return_mask
        self.normalize = transforms.Normalize(mean=self.mean, std=self.std)

    def __call__(self, img_tensor,normalize=True,interpolation=F.InterpolationMode.BILINEAR):
        """
        Apply the ResizeSquare transformation to the input image tensor.

        Args:
            img_tensor (torch.Tensor): The input image tensor.

        Returns:
            torch.Tensor: The resized image tensor.
        """
        # Get the original width and height of the image
        # Resize the image
        if img_tensor.ndim==2:
            img_tensor = img_tensor.unsqueeze(0)
        img = F.resize(img_tensor, [self.size, self.size], antialias=True,interpolation=interpolation)


        mask = torch.ones_like(img)

        if normalize:
            img = self.normalize(img)
            # img = self.normalize(img)

        if self.return_mask:
            return img, mask
        else:
            return img

class RandomResizeTransform:
    def __init__(self, size, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], return_mask=True):
        self.resize_transform1 = ResizeSquareWithPaddingNormalize(size=size, mean=mean, std=std, return_mask=return_mask)
        self.resize_transform2 = ResizeSquareWithNormalize(size=size, mean=mean, std=std, return_mask=return_mask)
        self.return_mask = return_mask

    def __call__(self, image):
        if random.random() < 0.5:
            return self.resize_transform1(image)
        else:
            return self.resize_transform2(image)

class AlbumentationsGeometricTransforms:
    def __init__(self):
        self.transform = A.Compose([
            # A.Rotate(limit=(0, 90), p=0.5),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.Affine(scale=(0.9, 1.1), translate_percent=(0.01, 0.05), rotate=(0, 0), shear=(-5, 5), p=0.5),  # Mild affine transform
            # A.Lambda(image=self.center_crop, p=0.5),
        ], additional_targets={'weld_segmentation': 'mask', 'defect_segmentation': 'mask'})

    def center_crop(self, image, **kwargs):
        height, width = image.shape[:2]
        crop_percent = random.uniform(0, 0.15)

        crop_height = int(height * (1 - crop_percent))
        crop_width = int(width * (1 - crop_percent))

        start_y = (height - crop_height) // 2
        start_x = (width - crop_width) // 2

        return image[start_y:start_y+crop_height, start_x:start_x+crop_width]

    def __call__(self, img=None, weld_mask=None, defect_mask=None, mask=None):
        inputs = {}
        inputs['image'] = np.array(img)

        if weld_mask is not None:
            weld_mask = np.array(weld_mask)
            inputs['weld_segmentation'] = weld_mask

        if defect_mask is not None:
            defect_mask = np.array(defect_mask)
            inputs['defect_segmentation'] = defect_mask

        augmented = self.transform(**inputs)

        img_np = augmented['image']
        img = Image.fromarray(img_np).convert('RGB')
        img = ImageOps.exif_transpose(img)

        if weld_mask is not None:
            weld_mask = augmented['weld_segmentation']
        if defect_mask is not None:
            defect_mask = augmented['defect_segmentation']

        if weld_mask is not None and defect_mask is not None:
            return img, weld_mask, defect_mask
        elif weld_mask is not None:
            return img, weld_mask
        elif defect_mask is not None:
            return img, defect_mask
        else:
            return img,None

geometric_transforms =  AlbumentationsGeometricTransforms()

# Geometric transformations
geometric_transforms1 = v2.Compose(
    [
        v2.RandomHorizontalFlip(p=0.5),
        v2.RandomVerticalFlip(p=0.5),
    ]
)

color_space_transforms = v2.Compose(
    [
        v2.RandomChoice(
            [
                v2.RandomAdjustSharpness(sharpness_factor=0.75, p=0.15),  # Increased sharpness factor, reduced probability
                # v2.RandomAutocontrast(p=0.15),  # Reduced probability
                v2.RandomEqualize(p=0.15),  # Reduced probability
            ]
        ),
        v2.RandomApply([v2.Grayscale(num_output_channels=3)], p=0.2),  # Reduced probability
        # v2.RandomApply([A.Lambda(image=channel_shuffle)], p=0.2),  # Reduced probability
        v2.RandomApply(
            [v2.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1, hue=0.05)],  # Reduced intensity
            p=0.3  # Reduced probability
        )
    ]
)

noise_transforms = v2.Compose(
    [
        v2.RandomChoice(
            [
                #v2.RandomChoice(
                #    [
                #        v2.RandomPosterize(bits=2, p=0.5),
                #        v2.RandomPosterize(bits=3, p=0.5),
                #    ]
                #),
                v2.RandomApply(
                    [
                        v2.GaussianBlur(kernel_size=(5, 9), sigma=(0.1, 5.0)),
                    ],
                    p=0.5,
                ),
            ]
        )
    ]
)