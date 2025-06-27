from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from PIL import Image
from pydantic import BaseModel
from transformers import AutoModel

from mindtrace.core import Config
from mindtrace.registry import Registry


class ExampleModel(BaseModel):
    name: str
    value: int
    is_active: bool


def main():
    # Initialize the registry
    registry = Registry()

    # Register materializer for our custom Pydantic model
    # Use the actual type of the model for registration
    registry.register_materializer(
        f"{ExampleModel.__module__}.{ExampleModel.__name__}",
        "zenml.materializers.PydanticMaterializer"
    )

    # 1. Basic Python types
    # String
    registry.save("example:string", "Hello, World!")
    loaded_string = registry.load("example:string")
    print(f"Loaded string: {loaded_string}")

    # Integer
    registry.save("example:integer", 42)
    loaded_int = registry.load("example:integer")
    print(f"Loaded integer: {loaded_int}")

    # Float
    registry.save("example:float", 3.14159)
    loaded_float = registry.load("example:float")
    print(f"Loaded float: {loaded_float}")

    # Boolean
    registry.save("example:boolean", True)
    loaded_bool = registry.load("example:boolean")
    print(f"Loaded boolean: {loaded_bool}")

    # List
    registry.save("example:list", [1, 2, 3, 4, 5])
    loaded_list = registry.load("example:list")
    print(f"Loaded list: {loaded_list}")

    # Dictionary
    registry.save("example:dict", {"key1": "value1", "key2": 42})
    loaded_dict = registry.load("example:dict")
    print(f"Loaded dictionary: {loaded_dict}")

    # Tuple
    registry.save("example:tuple", (1, "two", 3.0))
    loaded_tuple = registry.load("example:tuple")
    print(f"Loaded tuple: {loaded_tuple}")

    # Set
    registry.save("example:set", {1, 2, 3, 4, 5})
    loaded_set = registry.load("example:set")
    print(f"Loaded set: {loaded_set}")

    # Bytes
    registry.save("example:bytes", b"Hello, World!")
    loaded_bytes = registry.load("example:bytes")
    print(f"Loaded bytes: {loaded_bytes}")

    # 2. File and Path handling
    # Create a temporary file
    temp_file = Path("temp_example.txt")
    temp_file.write_text("This is a test file")
    
    # Save the file path
    registry.save("example:file", temp_file)
    loaded_file = registry.load("example:file")
    print(f"Loaded file path: {loaded_file}")
    
    # Clean up
    temp_file.unlink()

    # 3. NumPy arrays
    # Create a NumPy array
    numpy_array = np.array([[1, 2, 3], [4, 5, 6]])
    registry.save("example:numpy", numpy_array)
    loaded_numpy = registry.load("example:numpy")
    print(f"Loaded NumPy array:\n{loaded_numpy}")

    # 4. PIL Images
    # Create a simple image
    image = Image.new('RGB', (100, 100), color='red')
    registry.save("example:image", image)
    loaded_image = registry.load("example:image")
    print(f"Loaded image size: {loaded_image.size}")

    # 5. PyTorch models and data
    # Create a simple PyTorch model
    model = torch.nn.Linear(10, 2)
    registry.save("example:pytorch:model", model)
    loaded_model = registry.load("example:pytorch:model")
    print(f"Loaded PyTorch model: {loaded_model}")

    # Create a PyTorch dataset
    dataset = torch.utils.data.TensorDataset(
        torch.randn(100, 10),
        torch.randint(0, 2, (100,))
    )
    registry.save("example:pytorch:dataset", dataset)
    loaded_dataset = registry.load("example:pytorch:dataset")
    print(f"Loaded PyTorch dataset length: {len(loaded_dataset)}")

    # 6. Hugging Face models and datasets
    # Load a small pre-trained model
    hf_model = AutoModel.from_pretrained("bert-base-uncased")
    registry.save("example:huggingface:model", hf_model)
    loaded_hf_model = registry.load("example:huggingface:model")
    print(f"Loaded Hugging Face model: {type(loaded_hf_model)}")

    # Create a simple dataset
    hf_dataset = Dataset.from_dict({
        "text": ["Hello", "World"],
        "label": [0, 1]
    })
    registry.save("example:huggingface:dataset", hf_dataset)
    loaded_hf_dataset = registry.load("example:huggingface:dataset")
    print(f"Loaded Hugging Face dataset: {loaded_hf_dataset}")

    # 7. Pydantic models
    pydantic_model = ExampleModel(name="test", value=42, is_active=True)
    registry.save("example:pydantic:model", pydantic_model)
    loaded_pydantic = registry.load("example:pydantic:model")
    print(f"Loaded Pydantic model: {loaded_pydantic}")

    # 8. Mindtrace Config
    config = Config(
        model_name="bert-base-uncased",
        model_batch_size=32,
        model_learning_rate=1e-4,
        training_epochs=10,
        training_early_stopping=True
    )
    registry.save("example:config", config)
    loaded_config = registry.load("example:config")
    print(f"Loaded Config:\n{loaded_config}")

    # List all saved objects
    print("\nAll saved objects:")
    for obj_name in registry.list_objects():
        versions = registry.list_versions(obj_name)
        print(f"{obj_name}: {versions}")

if __name__ == "__main__":
    main()
