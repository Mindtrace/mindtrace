import numpy as np
import cv2

class LetterBox:
	"""
 	Resize image and padding for detection, instance segmentation, pose.
	Implementation taken from Ultralytics repository: https://github.com/ultralytics/ultralytics/data/augment.py
 	"""

	def __init__(self, new_shape=(640, 640), auto=False, scaleFill=False, scaleup=True, center=True, stride=32):
		"""Initialize LetterBox object with specific parameters."""
		self.new_shape = new_shape
		self.auto = auto
		self.scaleFill = scaleFill
		self.scaleup = scaleup
		self.stride = stride
		self.center = center  # Put the image in the middle or top-left
		self.ratio = None
		self.dw = None
		self.dh = None

	def __call__(self, image=None):
		"""Return updated labels and image with added border."""
		img = image
		shape = img.shape[:2]  # current shape [height, width]

		# Scale ratio (new / old)
		r = min(self.new_shape[0] / shape[0], self.new_shape[1] / shape[1])
		if not self.scaleup:  # only scale down, do not scale up (for better val mAP)
			r = min(r, 1.0)

		# Compute padding
		self.ratio = r, r  # width, height ratios
		new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
		dw, dh = self.new_shape[1] - new_unpad[0], self.new_shape[0] - new_unpad[1]  # wh padding
		if self.auto:  # minimum rectangle
			dw, dh = np.mod(dw, self.stride), np.mod(dh, self.stride)  # wh padding
		elif self.scaleFill:  # stretch
			dw, dh = 0.0, 0.0
			new_unpad = (self.new_shape[1], self.new_shape[0])
			self.ratio = self.new_shape[1] / shape[1], self.new_shape[0] / shape[0]  # width, height ratios

		if self.center:
			dw /= 2  # divide padding into 2 sides
			dh /= 2

		self.dw = dw
		self.dh = dh

		if shape[::-1] != new_unpad:  # resize
			img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
		top, bottom = int(round(dh - 0.1)) if self.center else 0, int(round(dh + 0.1))
		left, right = int(round(dw - 0.1)) if self.center else 0, int(round(dw + 0.1))
		img = cv2.copyMakeBorder(
			img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
		)  # add border
		return img