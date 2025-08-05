import os
from typing import Optional, List, Union
import sys
import math
import time
import numpy as np
from functools import partial
from PIL import Image
import logging
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms

# from mtrix.models.backbones import Dinov2Backbone
# from mtrix.models.heads import LinearHead, ContrastiveHead, ClassSeverityLinearHead, LinearSeverityCrossEntropy, LinearSeverityHLGauss, ClassSeverityLoss
from mindtrace.automation.modelling.utils.transformations import ResizeSquareWithPaddingNormalize, ResizeSquareWithNormalize
import logging
logger = logging.getLogger(__name__)


class MigClassifier(nn.Module):
	def __init__(
     	self,
       	cls_to_idx_map: dict,
        loss_type: str = 'cross_entropy',
        head_type: str = 'linear',
        num_classification_layers: int = 1,
        classification_hidden_dim: int = 256,
        classification_dropout: float = 0.0,
        encoder_layers: Optional[Union[int, list[int]]] = [],
      	backbone_arch: str='dinov2_s_reg',
        load_pretrained: bool = True,
        adapter_mode: Optional[str] = None,
        adapter_rank: Optional[int] = None,
        adapter_dropout: Optional[float] = None,
        class_weights=None,
        only_cls_token=False,
		binary_anomaly_head: bool = False,
		drop_path_rate: float = 0.0,
		unfreeze_transformer_norm: bool = False,
		severity_head: bool = False,
		severity_head_type: str ='cross_entropy',
		class_severity_head: bool = False,
		embed_part_weld_id: bool = False,
		weld_map: dict = {},
		class_severity_loss_weight: float = 0.0,
		max_severity: int = 10,
		use_binary_conditioning: bool = False,
        **kwargs,
    ):
		super(MigClassifier, self).__init__()
		self.cls_to_idx_map = cls_to_idx_map
		self.idx_to_cls_map = {v: k for k, v in cls_to_idx_map.items()}
		self.num_classes = len(self.cls_to_idx_map.keys())
		self.encoder_layers = encoder_layers
		self.only_cls_token = only_cls_token
		self.embed_part_weld_id = embed_part_weld_id
		self.weld_map = weld_map
		self.class_severity_loss_weight = class_severity_loss_weight
		logger.info(f"Only cls token: {self.only_cls_token}")
		self.severity_head = severity_head
		self.class_severity_head = class_severity_head
		self.max_severity = max_severity
		extra_config = {}

		if self.class_severity_loss_weight > 0:
			self.cls_sev_loss = ClassSeverityLoss(class_weights)

		if drop_path_rate is not None and drop_path_rate > 0:
			extra_config['drop_path_rate'] = drop_path_rate
		if unfreeze_transformer_norm is not None:
			extra_config['unfreeze_transformer_norm'] = unfreeze_transformer_norm

		self.backbone = Dinov2Backbone(
      		arch_name=backbone_arch,
        	load_pretrained=load_pretrained,
			adapter_mode=adapter_mode,
			adapter_rank=adapter_rank,
			adapter_dropout=adapter_dropout,
			extra_config=extra_config,
		)

		if type(self.encoder_layers) is int:
			assert self.encoder_layers < len(self.backbone.blocks)
			self.encoder_layers = [i for i in range(len(self.backbone.blocks) - self.encoder_layers, len(self.backbone.blocks))]

		input_dim = self.backbone.embed_dim
		if self.embed_part_weld_id:
			self.weld_id_embedding = nn.Embedding(len(self.weld_map.keys()), self.backbone.embed_dim)
		# self.backbone = DinoAdapterBackbone(backbone_name = backbone_arch)
		if head_type== 'linear':
			logger.info(f"Initializing linear head for {self.num_classes} classes")
			self.head = LinearHead(
				input_dim = self.backbone.embed_dim,
				num_classes=self.num_classes,
				loss_type=loss_type,
				encoder_layers=self.encoder_layers,
				num_layers=num_classification_layers,
				hidden_dim=classification_hidden_dim,
				dropout=classification_dropout,
				weight=class_weights,
				only_cls_token=only_cls_token,
				additional_condition=embed_part_weld_id,
				use_binary_conditioning=use_binary_conditioning,
			)
		else:
			logger.info(f"Initializing contrastive head for {self.num_classes} classes")
			self.head = ContrastiveHead(
				input_dim = self.backbone.embed_dim,
				num_classes=self.num_classes,
				loss_type=loss_type,
				encoder_layers=self.encoder_layers,
				num_layers=num_classification_layers,
				hidden_dim=classification_hidden_dim,
				dropout=classification_dropout,
				only_cls_token=only_cls_token,
				additional_condition=embed_part_weld_id,
				use_binary_conditioning=use_binary_conditioning,
			)
		if binary_anomaly_head:
			logger.info(f"Initializing binary anomaly head")
			self.binary_anomaly_head = LinearHead(
				input_dim = self.backbone.embed_dim,
				num_classes=1,
				loss_type='binary_cross_entropy',
				encoder_layers=self.encoder_layers,
				num_layers=num_classification_layers,
				hidden_dim=classification_hidden_dim,
				dropout=classification_dropout,
				only_cls_token=only_cls_token,
				additional_condition=embed_part_weld_id,
			)
		if severity_head:
			logger.info(f"Initializing severity head of type: {severity_head_type}")

			if severity_head_type == 'cross_entropy':
				self.severity_head = LinearSeverityCrossEntropy(
					input_dim = self.backbone.embed_dim,
					num_classes=11,
					encoder_layers=self.encoder_layers,
					num_layers=num_classification_layers,
					hidden_dim=classification_hidden_dim,
					dropout=classification_dropout,
					only_cls_token=only_cls_token,
					use_binary_conditioning=use_binary_conditioning,
				)
			elif severity_head_type == 'hlgauss':
				self.severity_head = LinearSeverityHLGauss(
					input_dim = self.backbone.embed_dim,
					num_bins = 50,
					encoder_layers=self.encoder_layers,
					num_layers=num_classification_layers,
					hidden_dim=classification_hidden_dim,
					dropout=classification_dropout,
					only_cls_token=only_cls_token,
					additional_condition=embed_part_weld_id,
					use_binary_conditioning=use_binary_conditioning,
				)
			else:
				raise ValueError(f"Invalid severity head type: {severity_head_type}")

		if self.class_severity_head:
			logger.info(f"Initializing class severity head")
			self.class_severity_head = ClassSeverityLinearHead(
				input_dim = self.backbone.embed_dim,
				num_classes=self.num_classes,
				encoder_layers=self.encoder_layers,
				num_layers=num_classification_layers,
				hidden_dim=classification_hidden_dim,
				dropout=classification_dropout,
				only_cls_token=only_cls_token,
				use_binary_conditioning=use_binary_conditioning,
			)
		self.use_binary_conditioning = use_binary_conditioning

		if self.use_binary_conditioning:
			if not self.embed_part_weld_id:
				raise ValueError("use_binary_conditioning is True but embed_part_weld_id is False. Should be True if use_binary_conditioning is True.")
			logger.info(f"Using binary conditioning")

	def forward(self, x, masks=None, return_embedding=False, cond=None):
		if len(self.encoder_layers) > 0:
			x = self.backbone.get_intermediate_layers(x, n=self.encoder_layers, return_class_token=True)
		else:
			x = self.backbone(x, masks)

		if cond is not None:
			cond = self.weld_id_embedding(cond)
		output = {}

		if self.binary_anomaly_head:
			output['binary_logits'] = self.binary_anomaly_head(x, cond=cond)
			if self.use_binary_conditioning:  # Apply new logic based on the parameter
				binary_pred = torch.sigmoid(output['binary_logits'])
				cond = torch.cat([cond, binary_pred], dim=1) if cond is not None else binary_pred

		if return_embedding:
			logits, embeddings = self.head(x, return_embedding, cond=cond)
			output['logits'] = logits
			output['embeddings'] = embeddings
		else:
			output['logits'] = self.head.forward(x, cond=cond)

		if self.severity_head:
			output['severity_logits'] = self.severity_head(x, cond=cond)
		if self.class_severity_head:
			output['class_severity_logits'] = self.class_severity_head(x, cond=cond)
		return output

	def forward_with_loss(self, x, labels, masks=None, return_embedding=False, cond=None):
		if len(self.encoder_layers) > 0:
			x = self.backbone.get_intermediate_layers(x, n=self.encoder_layers, return_class_token=True)
		else:
			x = self.backbone(x, masks)
		if cond is not None:
			cond = self.weld_id_embedding(cond)

		multiclass_labels = labels['multiclass_target']
		output = {}

		if self.binary_anomaly_head:
			binary_labels = (multiclass_labels != 0).float().unsqueeze(1)  # 0 for healthy, 1 for anomaly
			binary_logits, binary_loss = self.binary_anomaly_head.forward_with_loss(x, binary_labels, cond=cond)
			output['binary_logits'] = binary_logits
			output['binary_loss'] = binary_loss
			if self.use_binary_conditioning:  # Apply new logic based on the parameter
				binary_pred = torch.sigmoid(binary_logits)
				cond = torch.cat([cond, binary_pred], dim=1) if cond is not None else binary_pred

		if return_embedding:
			logits, embedding, loss = self.head.forward_with_loss(x, multiclass_labels, return_embedding, cond=cond)
			output['logits'] = logits
			output['embeddings'] = embedding
			output['loss'] = loss
		else:
			logits, loss = self.head.forward_with_loss(x, multiclass_labels, cond=cond)
			output['logits'] = logits
			output['loss'] = loss

		if self.severity_head:
			severity_labels = labels['severity_target']
			severity_score_mask = labels['severity_score_mask']
			severity_logits, severity_loss = self.severity_head.forward_with_loss(x, severity_labels, severity_score_mask, cond=cond)
			output['severity_logits'] = severity_logits
			output['severity_loss'] = severity_loss

		if self.class_severity_head:
			severity_labels = labels['severity_target'] / self.max_severity
			severity_score_mask = labels['severity_score_mask']
			B = severity_labels.size(0)
			class_severity_labels = torch.zeros(B, self.num_classes, device=severity_labels.device)
			class_severity_labels.scatter_(1, multiclass_labels.unsqueeze(1), severity_labels.unsqueeze(1))
			class_severity_logits, class_severity_loss = self.class_severity_head.forward_with_loss(x, class_severity_labels, cond=cond)
			output['class_severity_logits'] = class_severity_logits
			output['class_severity_loss'] = class_severity_loss

		if self.class_severity_loss_weight > 0:
			loss = self.class_severity_loss_weight(y_true_class, y_pred_class, y_true_severity, y_pred_severity)
		return output

	def get_tta_imgs(self, imgs):
		return

	@torch.no_grad()
	def predict(self, x, masks=None, return_embedding=False, cond=None, use_tta=False):
		if len(self.encoder_layers) > 0:
			x = self.backbone.get_intermediate_layers(x, n=self.encoder_layers, return_class_token=True)
		else:
			x = self.backbone(x, masks)

		if cond is not None:
			cond = self.weld_id_embedding(cond)

		output = {}

		if self.binary_anomaly_head:
			binary_logits = self.binary_anomaly_head(x, cond=cond)
			binary_pred = torch.sigmoid(binary_logits)
			if self.use_binary_conditioning:  # Apply new logic based on the parameter
				cond = torch.cat([cond, binary_pred], dim=1)

		cls_idx, confs = self.head.predict(x, cond=cond)
		cls_idx = list(cls_idx.cpu().numpy())
		confs = list(confs.cpu().numpy())

		if self.binary_anomaly_head:
			binary_confs = list(binary_logits.cpu().numpy())
			binary_preds = (binary_pred.cpu().numpy() > 0.5).astype(int).flatten()

		if self.severity_head:
			severity_idx, severity_confs = self.severity_head.predict(x, cond=cond)
			severity_idx = list(severity_idx.cpu().numpy())
			severity_confs = list(severity_confs.cpu().numpy())

		if self.class_severity_head:
			predicted_classes, predicted_severities = self.class_severity_head.predict(x, cond=cond)
			predicted_classes = list(predicted_classes.cpu().numpy())
			predicted_severities = list(predicted_severities.cpu().numpy())

		outputs = {
			'multiclass_preds': [],
			'multiclass_confs': [],
			'binary_preds': [],
			'binary_confs': [],
			'severity_preds': [],
			'severity_confs': [],
			'class_severity_preds': [],
			'class_severity_scores': []
		}

		if return_embedding:
			if self.only_cls_token:
				outputs['embeddings'] = x.cls_tokens[-1]

		for idx, conf in zip(cls_idx, confs):
			outputs['multiclass_preds'].append(self.idx_to_cls_map[idx])
			outputs['multiclass_confs'].append(conf)

		if self.binary_anomaly_head:
			for pred, conf in zip(binary_preds, binary_confs):
				outputs['binary_preds'].append("Healthy" if pred == 0 else "Defective")
				outputs['binary_confs'].append(conf)

		if self.severity_head:
			for pred, conf in zip(severity_idx, severity_confs):
				outputs['severity_preds'].append(pred)
				outputs['severity_confs'].append(conf)

		if self.class_severity_head:
			for pred, conf in zip(predicted_classes, predicted_severities):
				outputs['class_severity_preds'].append(pred)
				outputs['class_severity_scores'].append(conf)

		return outputs

	def predict_topk(self, x, masks=None, cond=None):
		if len(self.encoder_layers) > 0:
			x = self.backbone.get_intermediate_layers(x, n=self.encoder_layers, return_class_token=True)
		else:
			x = self.backbone(x, masks)
		if cond is not None:
			cond = self.weld_id_embedding(cond)
		cls_idx, confs = self.head.predict_topk(x, k=2, cond=cond)
		cls_idx = list(cls_idx.cpu().numpy())
		confs = list(confs.cpu().numpy())
		outputs = []
		for idxs, confs in zip(cls_idx, confs):
			outputs.append([[self.idx_to_cls_map[idx], idx, conf] for idx, conf in zip(idxs, confs)])
		return outputs

	def get_last_attention_map(self, x, masks=None):
		return self.backbone.get_last_self_attention(x, masks)

	def _preprocess_images(self, images: List[Image.Image],image_size:int=448):
		transform = transforms.Compose([transforms.ToTensor(),
			# ResizeSquareWithPaddingNormalize(image_size, return_mask=False)
			ResizeSquareWithNormalize(image_size, return_mask=False)
		])
		images = [transform(image) for image in images]
		images = torch.stack(images)
		return images

	@torch.no_grad()
	def predict_batch(self, images: List[Image.Image], image_size: int = 448, masks=None, cond=None):
		if type(images) == list:
			batch_images = self._preprocess_images(images, image_size)
			batch_images = batch_images.to(self.backbone.cls_token.device)
		else:
			batch_images = images

		if len(self.encoder_layers) > 0:
			x = self.backbone.get_intermediate_layers(batch_images, n=self.encoder_layers, return_class_token=True)
		else:
			x = self.backbone(batch_images, masks)

		if cond is not None:
			if type(cond) == list:
				cond = torch.tensor(cond).to(self.backbone.cls_token.device)
			cond = self.weld_id_embedding(cond)


		if self.binary_anomaly_head:
			binary_logits = self.binary_anomaly_head(x, cond=cond)
			binary_pred = torch.sigmoid(binary_logits)
			if self.use_binary_conditioning:  # Apply new logic based on the parameter
				cond = torch.cat([cond, binary_pred], dim=1)

		cls_idx, confs = self.head.predict(x, cond=cond)
		cls_idx = list(cls_idx.cpu().numpy())
		confs = list(confs.cpu().numpy())

		if self.binary_anomaly_head:
			binary_confs = list(binary_logits.cpu().numpy())
			binary_preds = (binary_pred.cpu().numpy() > 0.5).astype(int).flatten()

		if self.severity_head:
			severity_idx, severity_confs = self.severity_head.predict(x, cond=cond)
			severity_idx = list((severity_idx.cpu().numpy() / 5))
			severity_confs = list(severity_confs.cpu().numpy())

		if self.class_severity_head:
			predicted_classes, predicted_severities = self.class_severity_head.predict(x, cond=cond)
			predicted_classes = list(predicted_classes.cpu().numpy())
			predicted_severities = list(predicted_severities.cpu().numpy())

		outputs = {
			'multiclass_preds': [],
			'multiclass_confs': [],
			'binary_preds': [],
			'binary_confs': [],
			'severity_preds': [],
			'severity_confs': [],
			'class_severity_preds': [],
			'class_severity_scores': []
		}

		for idx, conf in zip(cls_idx, confs):
			outputs['multiclass_preds'].append(self.idx_to_cls_map[idx])
			outputs['multiclass_confs'].append(conf)

		if self.binary_anomaly_head:
			for pred, conf in zip(binary_preds, binary_confs):
				outputs['binary_preds'].append("Healthy" if pred == 0 else "Defective")
				outputs['binary_confs'].append(conf)

		if self.severity_head:
			for pred, conf in zip(severity_idx, severity_confs):
				outputs['severity_preds'].append(pred)
				outputs['severity_confs'].append(conf)

		if self.class_severity_head:
			for pred, conf in zip(predicted_classes, predicted_severities):
				outputs['class_severity_preds'].append(pred)
				outputs['class_severity_scores'].append(conf)

		return outputs

	@classmethod
	def load_model(cls, model_path: str, device: str):
		try:
			model_pt = torch.load(model_path, map_location=device)
		except Exception as e:
			raise RuntimeError(f"Error loading model from {model_path}: {e}")
		model = cls(**model_pt['config'])
		model.load_state_dict(model_pt['state_dict'])
		model = model.eval()
		model = model.to(device)
		return model