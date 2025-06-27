"""Example demonstrating thread safety usage with the Registry class.

This script shows how to safely use the Registry class in a multi-threaded environment, including concurrent saves, 
loads, and mixed operations.
"""

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from mindtrace.registry import Registry


def save_models(registry: Registry, model_id: int) -> None:
    """Save a model and its metadata in a thread-safe manner."""
    # Simulate some model training/preparation
    time.sleep(0.1)  # Simulate work
    
    # Save the model and its metadata
    model_data = {
        "weights": [0.1 * model_id, 0.2 * model_id],
        "metadata": {"accuracy": 0.8 + 0.01 * model_id}
    }
    registry.save(f"model:{model_id}", model_data)
    print(f"Saved model:{model_id}")


def load_and_evaluate(registry: Registry, model_id: int) -> Dict[str, Any]:
    """Load a model and evaluate it in a thread-safe manner."""
    # Load the model
    model_data = registry.load(f"model:{model_id}")
    
    # Simulate evaluation
    time.sleep(0.1)  # Simulate work
    
    # Return evaluation results
    return {
        "model_id": model_id,
        "accuracy": model_data["metadata"]["accuracy"],
        "weights": model_data["weights"]
    }


def update_model_metadata(registry: Registry, model_id: int) -> None:
    """Update model metadata in a thread-safe manner."""
    # Load current model data
    model_data = registry.load(f"model:{model_id}")
    
    # Update metadata
    model_data["metadata"]["last_updated"] = time.time()
    model_data["metadata"]["update_count"] = model_data["metadata"].get("update_count", 0) + 1
    
    # Save updated model
    registry.save(f"model:{model_id}", model_data)
    print(f"Updated metadata for model:{model_id}")


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a registry in a temporary directory
        registry = Registry(registry_dir=temp_dir)
        
        print("Starting thread safety demonstration...")
        
        # Example 1: Concurrent model saving
        print("\n1. Concurrent model saving:")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(save_models, registry, i) for i in range(5)]
            for future in as_completed(futures):
                future.result()  # Wait for completion
        
        # Example 2: Concurrent model loading and evaluation
        print("\n2. Concurrent model loading and evaluation:")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(load_and_evaluate, registry, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]
            
            # Print evaluation results
            for result in sorted(results, key=lambda x: x["model_id"]):
                print(f"Model {result['model_id']}: Accuracy = {result['accuracy']:.3f}")
        
        # Example 3: Mixed operations (save, load, update)
        print("\n3. Mixed operations (save, load, update):")
        def mixed_operation(i: int) -> None:
            if i % 3 == 0:
                # Save new model
                save_models(registry, i + 5)
            elif i % 3 == 1:
                # Load and evaluate existing model
                result = load_and_evaluate(registry, i - 1)
                print(f"Evaluated model {result['model_id']}")
            else:
                # Update metadata
                update_model_metadata(registry, i - 2)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(mixed_operation, i) for i in range(5)]
            for future in as_completed(futures):
                future.result()
        
        # Example 4: Dictionary-like interface with threads
        print("\n4. Dictionary-like interface with threads:")
        def dict_operation(i: int) -> None:
            # Save using dictionary syntax
            registry[f"config:{i}"] = {"param1": i, "param2": i * 2}
            # Load using dictionary syntax
            config = registry[f"config:{i}"]
            print(f"Loaded config:{i}: {config}")
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(dict_operation, i) for i in range(3)]
            for future in as_completed(futures):
                future.result()
        
        # Clean up
        print("\nCleaning up...")
        registry.clear()
        
        # Wait a moment to ensure all operations are complete
        time.sleep(0.1)

        assert len(registry) == 0
    

if __name__ == "__main__":
    main()
