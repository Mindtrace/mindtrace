from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np
import torch
from peft import LoraConfig, get_peft_model
from torch import Tensor, nn
from transformers import AutoImageProcessor, AutoModel

from mindtrace.models.base.transformer_backbone_base import TransformerBackboneBase


@dataclass
class DinoV3Output:
    """
    Outputs of the DinoV3 Backbone
    """

    cls_tokens: Tensor | Tuple[Tensor] | None = None
    patch_tokens: Tensor | Tuple[Tensor] | None = None
    masks: Tensor | None = None
    pos_embed: Tensor | None = None


class DinoV3(nn.Module, TransformerBackboneBase):
    def __init__(self):
        super().__init__()
        self.model = None
        self.processor = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_config = None
        self.blocks = None
        self.num_features = None
        self.embed_dim = None
        self.norm = None
        self.adapter_mode = None
        self.adapter_rank = None
        self.adapter_dropout = None

    def load_model(
        self, architecture: str, adapter_mode: bool = True, adapter_rank: int = 16, adapter_dropout: float = 0.1
    ):
        """
        Load the DinoV3 model with the specified architecture and adapter configuration.

        Args:
            architecture: The model architecture name (e.g., "facebook/dinov2-base")
            adapter_mode: Whether to use LoRA adapters
            adapter_rank: LoRA rank for adapter layers
            adapter_dropout: Dropout rate for LoRA layers
        """
        self.adapter_mode = adapter_mode
        self.adapter_rank = adapter_rank
        self.adapter_dropout = adapter_dropout

        # Load processor
        self.processor = AutoImageProcessor.from_pretrained(architecture)

        if adapter_mode:
            print("Loading model with LoRA adapters")
            lora_config = LoraConfig(
                r=adapter_rank,
                lora_alpha=16,
                # Usually attention layers
                target_modules=["k_proj", "q_proj", "v_proj"],
                lora_dropout=adapter_dropout,
                bias="none",
                task_type="FEATURE_EXTRACTION",
            )

            # Add LoRA modules to the model
            self.model = get_peft_model(AutoModel.from_pretrained(architecture, output_attentions=True), lora_config)
            print(self.model.print_trainable_parameters())
        else:
            print("Loading model without adapters")
            self.model = AutoModel.from_pretrained(architecture, output_attentions=True)

        # Move model to device and set up configuration
        self.model = self.model.to(self.device)
        self.model_config = self.model.config
        self.blocks = self.model.layer
        self.num_features = self.embed_dim = self.model_config.hidden_size
        self.norm = nn.LayerNorm(self.model_config.hidden_size, eps=self.model_config.layer_norm_eps).to(self.device)

        # Enable gradient computation for normalization layers
        if adapter_mode:
            for blk in self.model.layer:
                for param in blk.norm1.parameters():
                    param.requires_grad = True
                for param in blk.norm2.parameters():
                    param.requires_grad = True

    def forward(self, x: torch.Tensor, use_preprocessor: bool = True) -> torch.Tensor:
        """
        Forward pass through the DinoV3 model.

        Args:
            x: Input tensor (image) - shape [batch_size, channels, height, width] or [batch_size, height, width, channels]
            use_preprocessor: Whether to use the preprocessor or use input tensor directly

        Returns:
            Final hidden states from the last layer
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")

        # Move input tensor to device
        x = x.to(self.device)

        if use_preprocessor:
            inputs = self.processor(images=x, return_tensors="pt")
            # shape: [batch_size, 3, 224, 224]
            pixel_values = inputs["pixel_values"]
            pixel_values = pixel_values.to(self.device)
            pixel_values = pixel_values.to(self.model.embeddings.patch_embeddings.weight.dtype)
            hidden_states = self.model.embeddings(pixel_values, bool_masked_pos=None)
        else:
            # Use input tensor directly
            pixel_values = x.to(self.model.embeddings.patch_embeddings.weight.dtype)
            hidden_states = self.model.embeddings(pixel_values, bool_masked_pos=None)

        position_embeddings = self.model.rope_embeddings(pixel_values)

        # Pass through all layers
        for layer_module in self.model.layer:
            layer_head_mask = None
            layer_output = layer_module(
                hidden_states,
                attention_mask=layer_head_mask,
                position_embeddings=position_embeddings,
            )
            # Handle both single output and tuple output
            if isinstance(layer_output, tuple):
                hidden_states, _ = layer_output
            else:
                hidden_states = layer_output

        # Apply final normalization
        output = self.norm(hidden_states)

        return output

    def get_intermediate_layers(self, x: torch.Tensor, num_layers: int, use_preprocessor: bool = True) -> DinoV3Output:
        """
        Get intermediate layer outputs from the DinoV3 model.

        Args:
            x: Input tensor (image) - shape [batch_size, channels, height, width] or [batch_size, height, width, channels]
            num_layers: Number of layers to extract from the end
            use_preprocessor: Whether to use the preprocessor or use input tensor directly

        Returns:
            DinoV3Output containing cls_tokens and patch_tokens
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")

        # Move input tensor to device
        x = x.to(self.device)

        if use_preprocessor:
            inputs = self.processor(images=x, return_tensors="pt")
            # shape: [batch_size, 3, 224, 224]
            pixel_values = inputs["pixel_values"]
            pixel_values = pixel_values.to(self.device)
            pixel_values = pixel_values.to(self.model.embeddings.patch_embeddings.weight.dtype)
            hidden_states = self.model.embeddings(pixel_values, bool_masked_pos=None)
        else:
            # Use input tensor directly
            pixel_values = x.to(self.model.embeddings.patch_embeddings.weight.dtype)
            hidden_states = self.model.embeddings(pixel_values, bool_masked_pos=None)

        position_embeddings = self.model.rope_embeddings(pixel_values)

        layer_outputs = []

        for i, layer_module in enumerate(self.model.layer):
            layer_head_mask = None
            layer_output = layer_module(
                hidden_states,
                attention_mask=layer_head_mask,
                position_embeddings=position_embeddings,
            )
            # Handle both single output and tuple output
            if isinstance(layer_output, tuple):
                hidden_states, _ = layer_output
            else:
                hidden_states = layer_output

            # Collect outputs from the last num_layers
            if self.model_config.num_hidden_layers - i <= num_layers:
                layer_outputs.append(hidden_states)

        # Apply normalization to all outputs
        normalized_outputs = [self.norm(op) for op in layer_outputs]

        # Extract cls tokens and patch tokens
        cls_tokens_per_layer = [out[:, 0] for out in normalized_outputs]
        patch_tokens_per_layer = [out[:, self.model_config.num_register_tokens + 1 :, :] for out in normalized_outputs]

        return DinoV3Output(cls_tokens=cls_tokens_per_layer, patch_tokens=patch_tokens_per_layer)

    def get_last_self_attention(self, x, masks=None):
        """
        Get the attention weights from the last layer using hooks.

        Args:
            x: Input tensor (image)
            masks: Optional attention masks

        Returns:
            Attention weights tensor from the last layer
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")

        # Store attention weights
        attention_weights = None

        def attention_hook(module, input, output):
            nonlocal attention_weights
            # The attention module returns (attn_output, attn_weights)
            if isinstance(output, tuple) and len(output) == 2:
                attention_weights = output[1]
            else:
                # If output is not a tuple, we need to manually compute attention weights
                # This happens when the layer doesn't return attention weights
                attention_weights = None

        # Register hook on the last layer's attention module
        last_layer = self.model.layer[-1]
        hook_handle = last_layer.attention.register_forward_hook(attention_hook)

        try:
            x = x.to(self.device)
            inputs = self.processor(images=x, return_tensors="pt")
            pixel_values = inputs["pixel_values"]  # shape: [1, 3, 224, 224]

            pixel_values = pixel_values.to(self.model.embeddings.patch_embeddings.weight.dtype)
            hidden_states = self.model.embeddings(pixel_values, bool_masked_pos=None)
            position_embeddings = self.model.rope_embeddings(pixel_values)

            # Forward pass through all layers
            for i, layer_module in enumerate(self.model.layer):
                layer_head_mask = None
                hidden_states = layer_module(
                    hidden_states,
                    attention_mask=layer_head_mask,
                    position_embeddings=position_embeddings,
                )

        finally:
            # Remove the hook
            hook_handle.remove()

        return attention_weights

    def get_last_self_attention_monkey_patch(self, x, masks=None):
        """
        Alternative approach: Monkey patch the last layer to return attention weights.

        Args:
            x: Input tensor (image)
            masks: Optional attention masks

        Returns:
            Attention weights tensor from the last layer
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")

        # Store the original forward method
        last_layer = self.model.layer[-1]
        original_forward = last_layer.forward

        # Store attention weights
        attention_weights = None

        def patched_forward(hidden_states, attention_mask=None, position_embeddings=None):
            nonlocal attention_weights
            # Attention with residual connection
            residual = hidden_states
            hidden_states = last_layer.norm1(hidden_states)
            hidden_states, attn_weights = last_layer.attention(
                hidden_states,
                attention_mask=attention_mask,
                position_embeddings=position_embeddings,
            )
            attention_weights = attn_weights  # Store for return
            hidden_states = last_layer.layer_scale1(hidden_states)
            hidden_states = last_layer.drop_path(hidden_states) + residual

            # MLP with residual connection
            residual = hidden_states
            hidden_states = last_layer.norm2(hidden_states)
            hidden_states = last_layer.mlp(hidden_states)
            hidden_states = last_layer.layer_scale2(hidden_states)
            hidden_states = last_layer.drop_path(hidden_states) + residual

            return hidden_states

        try:
            # Apply the monkey patch
            last_layer.forward = patched_forward

            x = x.to(self.device)
            inputs = self.processor(images=x, return_tensors="pt")
            pixel_values = inputs["pixel_values"]  # shape: [1, 3, 224, 224]

            pixel_values = pixel_values.to(self.model.embeddings.patch_embeddings.weight.dtype)
            hidden_states = self.model.embeddings(pixel_values, bool_masked_pos=None)
            position_embeddings = self.model.rope_embeddings(pixel_values)

            # Forward pass through all layers
            for i, layer_module in enumerate(self.model.layer):
                layer_head_mask = None
                hidden_states = layer_module(
                    hidden_states,
                    attention_mask=layer_head_mask,
                    position_embeddings=position_embeddings,
                )

        finally:
            # Restore the original forward method
            last_layer.forward = original_forward

        return attention_weights

    def plot_attention_map(self, x: torch.Tensor, predictions=None, patch_size=16):
        """
        Visualizes attention on the image by concatenating them horizontally.

        Args:
            x (torch.Tensor): Input image, should be of shape (1, C, H, W).
            predictions (str, optional): Text prediction to overlay on the image.
            patch_size (int): Patch size used in the model (default: 16 for DINOv3).

        Returns:
            numpy.ndarray: Concatenated image with attention map, shape (H, W, C).
        """

        def unnormalize_image(image_tensor):
            """Unnormalize image tensor assuming ImageNet normalization."""
            # ImageNet normalization: mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
            mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
            std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

            if image_tensor.device != mean.device:
                mean = mean.to(image_tensor.device)
                std = std.to(image_tensor.device)

            return image_tensor * std + mean

        def show_cam_on_image(image, heatmap):
            """Overlay attention heatmap on the original image."""
            # Convert heatmap to float and normalize
            heatmap = heatmap.astype(np.float32) / 255.0
            image = image.astype(np.float32) / 255.0

            # Blend the images
            cam = heatmap + image
            cam = cam / np.max(cam)

            return (cam * 255).astype(np.uint8)

        def add_prediction_text(image, predictions):
            """Add prediction text to the bottom of the image."""
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            font_color = (255, 255, 255)  # White color
            font_thickness = 1
            text_size = cv2.getTextSize(predictions, font, font_scale, font_thickness)[0]

            # Extend the image at the bottom
            padding = 20  # Extra padding above and below the text
            extended_img = np.zeros((image.shape[0] + text_size[1] + 2 * padding, image.shape[1], 3), dtype=np.uint8)

            # Copy the original image to the top of the extended image
            extended_img[: image.shape[0], :, :] = image

            # Fill the extended part with black color
            extended_img[image.shape[0] :, :, :] = 0

            # Calculate position for centered text at the bottom
            text_x = (extended_img.shape[1] - text_size[0]) // 2
            text_y = image.shape[0] + text_size[1] + padding

            # Add the text
            cv2.putText(
                extended_img, predictions, (text_x, text_y), font, font_scale, font_color, font_thickness, cv2.LINE_AA
            )

            return extended_img

        # Main function logic
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")

        # Ensure input is 4D tensor (batch, channels, height, width)
        if x.dim() == 3:
            x = x.unsqueeze(0)

        # Get attention weights
        attention_map = self.get_last_self_attention(x)

        if attention_map is None:
            raise ValueError("Could not extract attention weights")

        # Convert to numpy if needed
        if isinstance(attention_map, torch.Tensor):
            attention_map = attention_map.detach().cpu().numpy()

        # Calculate feature map dimensions
        w_featmap = x.shape[-2] // patch_size
        h_featmap = x.shape[-1] // patch_size

        # Average over the heads
        nh = attention_map.shape[1]

        # For DINOv3, extract attention from CLS token (skip first 5 tokens)
        if "dinov3" in str(type(self.model)).lower():
            attentions = attention_map[0, :, 0, 5:].reshape(nh, -1)
        else:
            attentions = attention_map[0, :, 0, 1:].reshape(nh, -1)

        # Calculate actual patch dimensions from attention size
        num_patches = attentions.shape[1]
        actual_patch_size = int(np.sqrt(num_patches))

        if actual_patch_size * actual_patch_size != num_patches:
            # Try to find reasonable dimensions
            for i in range(1, int(np.sqrt(num_patches)) + 1):
                if num_patches % i == 0:
                    h_featmap = i
                    w_featmap = num_patches // i
                    break
        else:
            h_featmap = w_featmap = actual_patch_size

        attentions = attentions.reshape(nh, h_featmap, w_featmap)

        # Interpolate attention map to original image size
        attentions_tensor = torch.from_numpy(attentions).unsqueeze(0)
        attentions_resized = torch.nn.functional.interpolate(attentions_tensor, scale_factor=patch_size, mode="nearest")
        attentions_resized = attentions_resized.mean(dim=1)  # Average over heads

        # Normalize attention map
        attentions_norm = (
            ((attentions_resized - attentions_resized.min()) / (attentions_resized.max() - attentions_resized.min()))[0]
            .cpu()
            .numpy()
        )

        # Convert image to numpy and denormalize
        image_np = unnormalize_image(x).squeeze(0).permute(1, 2, 0).cpu().numpy()
        image_np = (image_np * 255).astype(np.uint8)

        # Apply colormap to attention
        heatmap = cv2.applyColorMap(np.uint8(attentions_norm * 255), cv2.COLORMAP_JET)

        # Overlay attention on image
        out_img = show_cam_on_image(image_np, heatmap)

        # Add prediction text if provided
        if predictions:
            out_img = add_prediction_text(out_img, predictions)

        return out_img
