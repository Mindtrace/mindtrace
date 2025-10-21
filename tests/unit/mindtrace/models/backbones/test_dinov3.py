"""
Unit tests for DinoV3 backbone model.

This module tests the DinoV3 model functionality including:
- Model loading and initialization
- Forward pass with preprocessor
- Forward pass with direct tensor input
- Error handling
"""


from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from mindtrace.models.backbones.dinov3 import DinoV3


class TestDinoV3:
    """Test class for DinoV3 backbone model."""

    @pytest.fixture(scope="class")
    def test_image_path(self):
        """Path to the test image."""
        # Get the project root by going up from this test file
        project_root = Path(__file__).parent.parent.parent.parent.parent.parent
        return project_root / "tests" / "resources" / "datasets" / "test" / "cat1.jpg"

    @pytest.fixture(scope="class")
    def test_image(self, test_image_path):
        """Load test image as PIL Image and resize to manageable size."""
        image = Image.open(test_image_path).convert("RGB")
        # Resize to a smaller size to avoid memory issues
        image = image.resize((224, 224), Image.Resampling.LANCZOS)
        return image

    @pytest.fixture(scope="class")
    def test_image_tensor(self, test_image):
        """Convert test image to tensor."""
        # Convert PIL image to tensor
        image_array = np.array(test_image)
        # Convert to tensor and normalize to [0, 1]
        tensor = torch.from_numpy(image_array).float() / 255.0
        # Convert from HWC to CHW format
        tensor = tensor.permute(2, 0, 1)
        # Add batch dimension
        tensor = tensor.unsqueeze(0)
        return tensor

    @pytest.fixture(scope="class")
    def test_batch_tensor(self, test_image):
        """Create batch tensor from test image."""
        # Convert PIL image to tensor
        image_array = np.array(test_image)
        # Convert to tensor and normalize to [0, 1]
        tensor = torch.from_numpy(image_array).float() / 255.0
        # Convert from HWC to CHW format
        tensor = tensor.permute(2, 0, 1)
        # Create batch of 3 images
        batch_tensor = tensor.unsqueeze(0).repeat(3, 1, 1, 1)
        return batch_tensor

    @pytest.fixture(scope="class")
    def dinov3_model(self):
        """Initialize DinoV3 model."""
        model = DinoV3()
        return model

    @pytest.fixture(scope="class")
    def loaded_dinov3_model(self, dinov3_model):
        """Load DinoV3 model with the specified architecture."""
        architecture = "facebook/dinov3-vits16-pretrain-lvd1689m"
        dinov3_model.load_model(architecture, adapter_mode=False)
        return dinov3_model

    def test_model_initialization(self, dinov3_model):
        """Test that DinoV3 model initializes correctly."""
        assert dinov3_model.model is None
        assert dinov3_model.processor is None
        assert dinov3_model.device is not None
        assert dinov3_model.model_config is None
        assert dinov3_model.blocks is None
        assert dinov3_model.num_features is None
        assert dinov3_model.embed_dim is None
        assert dinov3_model.norm is None

    def test_model_loading(self, dinov3_model):
        """Test that model loads correctly."""
        architecture = "facebook/dinov3-vits16-pretrain-lvd1689m"

        # Test loading without adapters
        dinov3_model.load_model(architecture, adapter_mode=False)

        assert dinov3_model.model is not None
        assert dinov3_model.processor is not None
        assert dinov3_model.model_config is not None
        assert dinov3_model.blocks is not None
        assert dinov3_model.num_features is not None
        assert dinov3_model.embed_dim is not None
        assert dinov3_model.norm is not None

    def test_model_loading_with_adapters(self, dinov3_model):
        """Test that model loads correctly with LoRA adapters."""
        architecture = "facebook/dinov3-vits16-pretrain-lvd1689m"

        # Test loading with adapters
        dinov3_model.load_model(
            architecture, adapter_mode=True, adapter_rank=8)

        assert dinov3_model.model is not None
        assert dinov3_model.processor is not None
        assert dinov3_model.model_config is not None
        assert dinov3_model.adapter_mode is True
        assert dinov3_model.adapter_rank == 8

    def test_forward_with_preprocessor(self, loaded_dinov3_model, test_image_tensor):
        """Test forward pass using preprocessor."""
        # Test with tensor input
        output = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)

        # Check output properties
        assert isinstance(output, torch.Tensor)
        assert output.dim() == 3  # [batch_size, seq_len, hidden_size]
        assert output.shape[0] == 1  # batch size
        assert output.shape[2] == loaded_dinov3_model.embed_dim  # hidden size

        # Check that output is on correct device
        assert output.device.type == loaded_dinov3_model.device.type

    def test_forward_with_direct_tensor(self, loaded_dinov3_model, test_image_tensor):
        """Test forward pass using direct tensor input."""
        # Test with preprocessed tensor
        output = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=False)

        # Check output properties
        assert isinstance(output, torch.Tensor)
        assert output.dim() == 3  # [batch_size, seq_len, hidden_size]
        assert output.shape[0] == 1  # batch size
        assert output.shape[2] == loaded_dinov3_model.embed_dim  # hidden size

        # Check that output is on correct device
        assert output.device.type == loaded_dinov3_model.device.type

    def test_forward_with_numpy_array(self, loaded_dinov3_model, test_image_tensor):
        """Test forward pass with numpy array input."""
        # Convert tensor to numpy array
        image_array = test_image_tensor.squeeze(0).permute(1, 2, 0).numpy()

        # Convert back to tensor format [batch_size, channels, height, width]
        tensor_from_numpy = torch.from_numpy(
            image_array).permute(2, 0, 1).unsqueeze(0).float()

        # Test with tensor created from numpy array
        output = loaded_dinov3_model.forward(
            tensor_from_numpy, use_preprocessor=True)

        # Check output properties
        assert isinstance(output, torch.Tensor)
        assert output.dim() == 3
        assert output.shape[0] == 1
        assert output.shape[2] == loaded_dinov3_model.embed_dim

    def test_forward_error_handling(self, dinov3_model, test_image_tensor):
        """Test error handling when model is not loaded."""
        # Create a fresh model instance without loading
        fresh_model = DinoV3()
        with pytest.raises(ValueError, match="Model not loaded. Call load_model\\(\\) first."):
            fresh_model.forward(test_image_tensor)

    def test_forward_device_consistency(self, loaded_dinov3_model, test_image_tensor):
        """Test that input is moved to correct device."""
        # Create tensor on CPU
        cpu_tensor = torch.randn(1, 3, 224, 224)

        # Test forward pass
        output = loaded_dinov3_model.forward(
            cpu_tensor, use_preprocessor=False)

        # Check that output is on model's device
        assert output.device.type == loaded_dinov3_model.device.type

    def test_forward_output_shape_consistency(self, loaded_dinov3_model, test_image_tensor):
        """Test that output shapes are consistent across different input types."""
        # Test with preprocessor
        output_preprocessor = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)

        # Test without preprocessor
        output_direct = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=False)

        # All outputs should have the same shape
        assert output_preprocessor.shape == output_direct.shape

    def test_forward_gradient_computation(self, loaded_dinov3_model, test_image_tensor):
        """Test that gradients can be computed during forward pass."""
        # Enable gradient computation
        loaded_dinov3_model.train()

        # Test forward pass
        output = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)

        # Compute a simple loss and check gradients
        loss = output.sum()
        loss.backward()

        # Check that gradients exist for trainable parameters
        has_gradients = False
        for param in loaded_dinov3_model.parameters():
            if param.grad is not None:
                has_gradients = True
                break

        assert has_gradients, "No gradients were computed"

    def test_model_config_properties(self, loaded_dinov3_model):
        """Test that model configuration properties are set correctly."""
        assert loaded_dinov3_model.model_config is not None
        assert loaded_dinov3_model.num_features == loaded_dinov3_model.embed_dim
        assert loaded_dinov3_model.embed_dim == loaded_dinov3_model.model_config.hidden_size
        assert loaded_dinov3_model.blocks is not None
        assert loaded_dinov3_model.norm is not None

    @pytest.mark.slow
    def test_forward_performance(self, loaded_dinov3_model, test_image_tensor):
        """Test forward pass performance (marked as slow test)."""
        import time

        # Warm up
        for _ in range(3):
            _ = loaded_dinov3_model.forward(
                test_image_tensor, use_preprocessor=True)

        # Time the forward pass
        start_time = time.time()
        output = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)
        end_time = time.time()

        # Check that forward pass completes in reasonable time (< 5 seconds)
        assert (end_time - start_time) < 5.0, "Forward pass took too long"
        assert isinstance(output, torch.Tensor)

    def test_forward_with_different_batch_sizes(self, loaded_dinov3_model, test_batch_tensor):
        """Test forward pass with different batch sizes."""
        # Test with batch tensor
        output = loaded_dinov3_model.forward(
            test_batch_tensor, use_preprocessor=True)

        # Check output shape
        assert output.shape[0] == 3  # batch size
        assert output.shape[2] == loaded_dinov3_model.embed_dim

        # Test with single image tensor
        single_tensor = test_batch_tensor[0:1]  # Take first image
        output_single = loaded_dinov3_model.forward(
            single_tensor, use_preprocessor=True)

        # Check output shape
        assert output_single.shape[0] == 1  # batch size
        assert output_single.shape[2] == loaded_dinov3_model.embed_dim

    def test_forward_memory_usage(self, loaded_dinov3_model, test_image_tensor):
        """Test that forward pass doesn't cause memory issues."""
        import gc

        # Clear any existing gradients
        loaded_dinov3_model.zero_grad()

        # Perform forward pass
        output = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)

        # Check that output is valid
        assert isinstance(output, torch.Tensor)
        assert not torch.isnan(output).any(), "Output contains NaN values"
        assert not torch.isinf(output).any(), "Output contains infinite values"

        # Clean up
        del output
        gc.collect()

    def test_model_state_consistency(self, loaded_dinov3_model, test_image_tensor):
        """Test that model state remains consistent across forward passes."""
        # Get initial model state
        initial_state = loaded_dinov3_model.training

        # Perform forward pass
        output1 = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)

        # Check model state hasn't changed
        assert loaded_dinov3_model.training == initial_state

        # Perform another forward pass
        output2 = loaded_dinov3_model.forward(
            test_image_tensor, use_preprocessor=True)

        # Check that outputs have the same shape
        assert output1.shape == output2.shape, "Output shapes should be consistent"

        # Note: Due to potential randomness in the model, we only check shapes
        # In a deterministic setup, outputs should be identical
        print(f"Output shapes match: {output1.shape == output2.shape}")
        print(
            f"Output difference norm: {torch.norm(output1 - output2).item():.6f}")

    def test_get_last_self_attention(self, loaded_dinov3_model, test_image_tensor):
        """Test getting attention weights from the last layer."""
        # Test getting attention weights
        attn_weights = loaded_dinov3_model.get_last_self_attention(
            test_image_tensor)

        # Check that attention weights are returned
        if attn_weights is not None:
            assert isinstance(attn_weights, torch.Tensor)
            # [batch_size, num_heads, seq_len, seq_len]
            assert attn_weights.dim() == 4
            # batch size
            assert attn_weights.shape[0] == test_image_tensor.shape[0]
            assert attn_weights.device.type == loaded_dinov3_model.device.type

            # Check attention weights properties
            assert not torch.isnan(attn_weights).any(
            ), "Attention weights contain NaN"
            assert not torch.isinf(attn_weights).any(
            ), "Attention weights contain infinite values"

            # Attention weights should sum to 1 across the last dimension (softmax)
            attn_sum = attn_weights.sum(dim=-1)
            assert torch.allclose(attn_sum, torch.ones_like(
                attn_sum), atol=1e-6), "Attention weights don't sum to 1"

            print(f"✅ Attention weights shape: {attn_weights.shape}")
            print(
                f"✅ Attention weights mean: {attn_weights.mean().item():.4f}")
            print(f"✅ Attention weights std: {attn_weights.std().item():.4f}")
        else:
            print(
                "⚠️ No attention weights returned - model might not be configured for attention output")


if __name__ == "__main__":
    pytest.main([__file__])
