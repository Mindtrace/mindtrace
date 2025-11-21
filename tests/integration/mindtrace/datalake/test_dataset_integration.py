"""Integration tests for the Dataset class."""

import pathlib

import pytest

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Dataset


class TestDatasetIntegration:
    """Integration tests for the Dataset class."""

    @pytest.mark.asyncio
    async def test_dataset_create_from_query_data_and_to_hf(self, datalake: Datalake, temp_registry_dir: str):
        """Test creating a Dataset from query_data, loading it, and converting to HuggingFace dataset."""
        # Use test images from disk
        test_dir = pathlib.Path(__file__).parent
        image1_path = test_dir / "test_image_red.png"
        image2_path = test_dir / "test_image_blue.png"
        image3_path = test_dir / "test_image_green.png"

        # Add image data to the datalake using registry storage (image files must be stored in registry)
        registry_uri = temp_registry_dir
        image_datum1 = await datalake.add_datum(
            data=image1_path,
            metadata={"type": "image", "project": "test_project"},
            contract="image",
            registry_uri=registry_uri,
        )
        image_datum2 = await datalake.add_datum(
            data=image2_path,
            metadata={"type": "image", "project": "test_project"},
            contract="image",
            registry_uri=registry_uri,
        )
        image_datum3 = await datalake.add_datum(
            data=image3_path,
            metadata={"type": "image", "project": "test_project"},
            contract="image",
            registry_uri=registry_uri,
        )

        # Create some label data with classification contract
        label_datum1 = await datalake.add_datum(
            data={"label": "cat", "confidence": 0.95},
            metadata={"type": "label"},
            contract="classification",
            derived_from=image_datum1.id,
        )
        label_datum2 = await datalake.add_datum(
            data={"label": "dog", "confidence": 0.87},
            metadata={"type": "label"},
            contract="classification",
            derived_from=image_datum2.id,
        )
        label_datum3 = await datalake.add_datum(
            data={"label": "bird", "confidence": 0.92},
            metadata={"type": "label"},
            contract="classification",
            derived_from=image_datum3.id,
        )

        assert label_datum1.id is not None
        assert label_datum2.id is not None
        assert label_datum3.id is not None

        # Use query_data to get datum_ids with transpose=True to get a dict
        query = [
            {"metadata.project": "test_project", "metadata.type": "image", "column": "image"},
            {"derived_from": "image", "metadata.type": "label", "column": "label"},
        ]
        datum_ids_dict = await datalake.query_data(query, transpose=True)

        # Type assertion for type checker
        assert isinstance(datum_ids_dict, dict)

        # Verify we got the expected structure
        assert "image" in datum_ids_dict
        assert "label" in datum_ids_dict
        image_ids: list = datum_ids_dict["image"]  # type: ignore
        label_ids: list = datum_ids_dict["label"]  # type: ignore
        assert isinstance(image_ids, list)
        assert isinstance(label_ids, list)
        assert len(image_ids) == 3
        assert len(label_ids) == 3

        # Convert the column-oriented dict to row-oriented list format
        # datum_ids_dict: {"image": [id1, id2, id3], "label": [label1, label2, label3]}
        # datum_ids_list: [{"image": id1, "label": label1}, {"image": id2, "label": label2}, ...]
        datum_ids_list = [
            {column: datum_ids_dict[column][i] for column in datum_ids_dict.keys()}  # type: ignore
            for i in range(len(image_ids))
        ]

        # Create a Dataset instance with the datum_ids
        dataset = Dataset(
            name="test_dataset",
            description="Integration test dataset",
            datum_ids=datum_ids_list,
        )

        # Insert the dataset into the database
        inserted_dataset = await datalake.dataset_database.insert(dataset)

        # Verify the dataset was inserted
        assert inserted_dataset.id is not None
        assert inserted_dataset.name == "test_dataset"
        assert inserted_dataset.description == "Integration test dataset"
        assert len(inserted_dataset.datum_ids) == 3
        assert all("image" in row for row in inserted_dataset.datum_ids)
        assert all("label" in row for row in inserted_dataset.datum_ids)

        # Test load() method
        loaded_data = await inserted_dataset.load(datalake)

        # Verify loaded_data structure (should be a list of dicts, same format as datum_ids)
        assert isinstance(loaded_data, list)
        assert len(loaded_data) == 3

        # Verify contracts were automatically detected and set
        assert "image" in inserted_dataset.contracts
        assert "label" in inserted_dataset.contracts
        assert inserted_dataset.contracts["image"] == "image"
        assert inserted_dataset.contracts["label"] == "classification"

        # Verify each row has the expected columns
        for row in loaded_data:
            assert "image" in row
            assert "label" in row
            # Verify the loaded images are PIL Images
            assert isinstance(row["image"], (pathlib.Path, pathlib.PosixPath))
            # Verify the loaded labels are dictionaries
            assert isinstance(row["label"], dict)
            assert "label" in row["label"]
            assert "confidence" in row["label"]

        # Test to_HF() method
        hf_dataset = await inserted_dataset.to_HF(datalake)

        # Verify it's a valid HuggingFace Dataset
        from datasets import IterableDataset as HFIterableDataset

        assert isinstance(hf_dataset, HFIterableDataset)

        # Verify we can iterate over the dataset
        row_count = 0
        for row in hf_dataset:
            assert "image" in row
            assert "label" in row
            # Verify image data is accessible (could be PIL Image or decoded format)
            assert row["image"] is not None
            # Verify label data structure
            assert isinstance(row["label"], dict)
            assert "label" in row["label"]
            assert "confidence" in row["label"]
            row_count += 1
        assert row_count == 3

        # Verify the dataset info is accessible
        assert hf_dataset.info is not None

        # Verify dataset features are properly defined based on contracts
        from datasets import Image as HFImage
        from datasets import Value

        assert hf_dataset.features is not None

        # Verify features exist for all columns
        assert "image" in hf_dataset.features
        assert "label" in hf_dataset.features

        # Image contract should map to Image feature type
        image_feature = hf_dataset.features["image"]
        assert isinstance(image_feature, HFImage), f"Expected Image feature, got {type(image_feature)}"

        # Classification contract should map to dict with label and confidence
        label_feature = hf_dataset.features["label"]
        assert isinstance(label_feature, dict), f"Expected dict feature for classification, got {type(label_feature)}"
        assert "label" in label_feature, "Classification feature should have 'label' key"
        assert "confidence" in label_feature, "Classification feature should have 'confidence' key"

        # Verify the Value types
        assert isinstance(label_feature["label"], Value), (
            f"Expected Value for label, got {type(label_feature['label'])}"
        )
        assert isinstance(label_feature["confidence"], Value), (
            f"Expected Value for confidence, got {type(label_feature['confidence'])}"
        )

        # Verify label is string type
        assert label_feature["label"].dtype == "string", (
            f"Expected string dtype for label, got {label_feature['label'].dtype}"
        )

        # Verify confidence is float type
        assert label_feature["confidence"].dtype == "float64" or label_feature["confidence"].dtype == "float32", (
            f"Expected float dtype for confidence, got {label_feature['confidence'].dtype}"
        )

        # Verify we can select columns
        image_only = hf_dataset.select_columns(["image"])
        for row in image_only:
            assert "image" in row
            assert row["image"] is not None
            assert "label" not in row

    @pytest.mark.asyncio
    async def test_dataset_contract_validation(self, datalake: Datalake, temp_registry_dir: str):
        """Test that dataset load() validates that all datums in a column have the same contract."""
        # Use test images from disk
        test_dir = pathlib.Path(__file__).parent
        image1_path = test_dir / "test_image_red.png"
        image2_path = test_dir / "test_image_blue.png"

        registry_uri = temp_registry_dir
        image_datum1 = await datalake.add_datum(
            data=image1_path, metadata={"type": "image"}, contract="image", registry_uri=registry_uri
        )
        # Create a second image with different contract (should fail)
        image_datum2 = await datalake.add_datum(
            data=image2_path, metadata={"type": "image"}, contract="default", registry_uri=registry_uri
        )

        # Create a dataset with mixed contracts
        # Type assertions to help the type checker understand IDs are not None
        assert image_datum1.id is not None
        assert image_datum2.id is not None
        dataset = Dataset(
            name="mixed_contracts_dataset",
            description="Dataset with mixed contracts",
            datum_ids=[
                {"image": image_datum1.id},
                {"image": image_datum2.id},
            ],
        )

        inserted_dataset = await datalake.dataset_database.insert(dataset)

        # Loading should raise ValueError because contracts don't match
        with pytest.raises(ValueError, match="All datums in a column must have the same contract"):
            await inserted_dataset.load(datalake)

    @pytest.mark.asyncio
    async def test_dataset_with_explicit_contracts(self, datalake: Datalake, temp_registry_dir: str):
        """Test creating a dataset with explicitly set contracts."""
        # Use test images from disk
        test_dir = pathlib.Path(__file__).parent
        image1_path = test_dir / "test_image_red.png"
        image2_path = test_dir / "test_image_blue.png"

        registry_uri = temp_registry_dir
        image_datum1 = await datalake.add_datum(
            data=image1_path, metadata={"type": "image"}, contract="image", registry_uri=registry_uri
        )
        image_datum2 = await datalake.add_datum(
            data=image2_path, metadata={"type": "image"}, contract="image", registry_uri=registry_uri
        )

        label_datum1 = await datalake.add_datum(
            data={"label": "cat", "confidence": 0.95}, metadata={"type": "label"}, contract="classification"
        )
        label_datum2 = await datalake.add_datum(
            data={"label": "dog", "confidence": 0.87}, metadata={"type": "label"}, contract="classification"
        )

        # Create dataset with explicit contracts
        # Type assertions to help the type checker understand IDs are not None
        assert image_datum1.id is not None
        assert image_datum2.id is not None
        assert label_datum1.id is not None
        assert label_datum2.id is not None
        dataset = Dataset(
            name="explicit_contracts_dataset",
            description="Dataset with explicit contracts",
            contracts={"image": "image", "label": "classification"},
            datum_ids=[
                {"image": image_datum1.id, "label": label_datum1.id},
                {"image": image_datum2.id, "label": label_datum2.id},
            ],
        )

        inserted_dataset = await datalake.dataset_database.insert(dataset)

        # Verify contracts are set
        assert inserted_dataset.contracts == {"image": "image", "label": "classification"}

        # Load should still work and validate
        loaded_data = await inserted_dataset.load(datalake)
        assert len(loaded_data) == 2

        # Contracts should still be set after load
        assert inserted_dataset.contracts == {"image": "image", "label": "classification"}

        # Test to_HF() with explicit contracts
        hf_dataset = await inserted_dataset.to_HF(datalake)

        # Verify features are correctly set based on explicit contracts
        from datasets import Image as HFImage
        from datasets import Value

        assert hf_dataset.features is not None
        assert "image" in hf_dataset.features
        assert "label" in hf_dataset.features

        # Image feature should be Image type
        assert isinstance(hf_dataset.features["image"], HFImage)

        # Classification feature should be dict with label and confidence
        label_feature = hf_dataset.features["label"]
        assert isinstance(label_feature, dict)
        assert "label" in label_feature
        assert "confidence" in label_feature
        assert isinstance(label_feature["label"], Value)
        assert isinstance(label_feature["confidence"], Value)
        assert label_feature["label"].dtype == "string"
        assert label_feature["confidence"].dtype in ["float64", "float32"]

    @pytest.mark.asyncio
    async def test_dataset_with_bbox_feature(self, datalake: Datalake, temp_registry_dir: str):
        """Test creating a Dataset with image, classification, and bbox features."""
        # Use test images from disk
        test_dir = pathlib.Path(__file__).parent
        image1_path = test_dir / "test_image_red.png"
        image2_path = test_dir / "test_image_blue.png"
        image3_path = test_dir / "test_image_green.png"

        # Add image data to the datalake using registry storage
        registry_uri = temp_registry_dir
        image_datum1 = await datalake.add_datum(
            data=image1_path,
            metadata={"type": "image", "project": "bbox_test"},
            contract="image",
            registry_uri=registry_uri,
        )
        image_datum2 = await datalake.add_datum(
            data=image2_path,
            metadata={"type": "image", "project": "bbox_test"},
            contract="image",
            registry_uri=registry_uri,
        )
        image_datum3 = await datalake.add_datum(
            data=image3_path,
            metadata={"type": "image", "project": "bbox_test"},
            contract="image",
            registry_uri=registry_uri,
        )

        # Create classification labels
        label_datum1 = await datalake.add_datum(
            data={"label": "cat", "confidence": 0.95},
            metadata={"type": "label"},
            contract="classification",
            derived_from=image_datum1.id,
        )
        label_datum2 = await datalake.add_datum(
            data={"label": "dog", "confidence": 0.87},
            metadata={"type": "label"},
            contract="classification",
            derived_from=image_datum2.id,
        )
        label_datum3 = await datalake.add_datum(
            data={"label": "bird", "confidence": 0.92},
            metadata={"type": "label"},
            contract="classification",
            derived_from=image_datum3.id,
        )

        assert label_datum1.id is not None
        assert label_datum2.id is not None
        assert label_datum3.id is not None

        # Create bbox data derived from images
        # Bbox data structure: {height: float, width: float, bbox: [[x1, y1, x2, y2], ...]}
        bbox_datum1 = await datalake.add_datum(
            data={"bbox": [[10.0, 20.0, 50.0, 60.0], [80.0, 30.0, 120.0, 70.0]]},
            metadata={"type": "bbox"},
            contract="bbox",
            derived_from=image_datum1.id,
        )
        bbox_datum2 = await datalake.add_datum(
            data={"bbox": [[15.0, 25.0, 55.0, 65.0]]},
            metadata={"type": "bbox"},
            contract="bbox",
            derived_from=image_datum2.id,
        )
        bbox_datum3 = await datalake.add_datum(
            data={"bbox": [[20.0, 30.0, 60.0, 70.0], [90.0, 40.0, 130.0, 80.0], [140.0, 50.0, 180.0, 90.0]]},
            metadata={"type": "bbox"},
            contract="bbox",
            derived_from=image_datum3.id,
        )
        assert bbox_datum1.id is not None
        assert bbox_datum2.id is not None
        assert bbox_datum3.id is not None

        # Use query_data to get datum_ids
        query = [
            {"metadata.project": "bbox_test", "metadata.type": "image", "column": "image"},
            {"derived_from": "image", "metadata.type": "label", "column": "label"},
            {"derived_from": "image", "metadata.type": "bbox", "column": "bbox"},
        ]
        datum_ids_dict = await datalake.query_data(query, transpose=True)

        # Type assertion for type checker
        assert isinstance(datum_ids_dict, dict)

        # Verify we got the expected structure
        assert "image" in datum_ids_dict
        assert "label" in datum_ids_dict
        assert "bbox" in datum_ids_dict
        image_ids: list = datum_ids_dict["image"]  # type: ignore
        label_ids: list = datum_ids_dict["label"]  # type: ignore
        bbox_ids: list = datum_ids_dict["bbox"]  # type: ignore
        assert isinstance(image_ids, list)
        assert isinstance(label_ids, list)
        assert isinstance(bbox_ids, list)
        assert len(image_ids) == 3
        assert len(label_ids) == 3
        assert len(bbox_ids) == 3

        # Convert to row-oriented format
        datum_ids_list = [
            {column: datum_ids_dict[column][i] for column in datum_ids_dict.keys()}  # type: ignore
            for i in range(len(image_ids))
        ]

        # Create a Dataset instance
        dataset = Dataset(
            name="bbox_dataset",
            description="Integration test dataset with bbox",
            datum_ids=datum_ids_list,
        )

        # Insert the dataset into the database
        inserted_dataset = await datalake.dataset_database.insert(dataset)

        # Verify the dataset was inserted
        assert inserted_dataset.id is not None
        assert inserted_dataset.name == "bbox_dataset"
        assert len(inserted_dataset.datum_ids) == 3
        assert all("image" in row for row in inserted_dataset.datum_ids)
        assert all("label" in row for row in inserted_dataset.datum_ids)
        assert all("bbox" in row for row in inserted_dataset.datum_ids)

        # Test load() method
        loaded_data = await inserted_dataset.load(datalake)

        # Verify loaded_data structure
        assert isinstance(loaded_data, list)
        assert len(loaded_data) == 3

        # Verify contracts were automatically detected and set
        assert "image" in inserted_dataset.contracts
        assert "label" in inserted_dataset.contracts
        assert "bbox" in inserted_dataset.contracts
        assert inserted_dataset.contracts["image"] == "image"
        assert inserted_dataset.contracts["label"] == "classification"
        assert inserted_dataset.contracts["bbox"] == "bbox"

        # Verify each row has the expected columns and data structure
        for row in loaded_data:
            assert "image" in row
            assert "label" in row
            assert "bbox" in row
            # Verify the loaded images are paths
            assert isinstance(row["image"], (pathlib.Path, pathlib.PosixPath))
            # Verify the loaded labels are dictionaries
            assert isinstance(row["label"], dict)
            assert "label" in row["label"]
            assert "confidence" in row["label"]
            # Verify the loaded bbox data structure
            assert isinstance(row["bbox"], dict)
            assert "bbox" in row["bbox"]
            assert isinstance(row["bbox"]["bbox"], list)
            for bbox_entry in row["bbox"]["bbox"]:
                assert isinstance(bbox_entry, list)
                assert len(bbox_entry) == 4
                assert all(isinstance(x, float) for x in bbox_entry)

        # Test to_HF() method
        hf_dataset = await inserted_dataset.to_HF(datalake)

        # Verify it's a valid HuggingFace Dataset
        from datasets import IterableDataset as HFIterableDataset

        assert isinstance(hf_dataset, HFIterableDataset)

        # Verify we can iterate over the dataset
        row_count = 0
        for row in hf_dataset:
            assert "image" in row
            assert "label" in row
            assert "bbox" in row
            # Verify image data is accessible
            assert row["image"] is not None
            # Verify label data structure
            assert isinstance(row["label"], dict)
            assert "label" in row["label"]
            assert "confidence" in row["label"]
            # Verify bbox data structure in HF dataset (only bbox list, not height/width)
            assert isinstance(row["bbox"], dict)
            assert "bbox" in row["bbox"]
            assert isinstance(row["bbox"]["bbox"], list)
            # Verify each bbox entry is a list of 4 floats
            for bbox_entry in row["bbox"]["bbox"]:
                assert isinstance(bbox_entry, list)
                assert len(bbox_entry) == 4
                assert all(isinstance(x, float) for x in bbox_entry)
            row_count += 1
        assert row_count == 3

        # Verify dataset features are properly defined
        from datasets import Image as HFImage
        from datasets import List as HFList
        from datasets import Sequence as HFSequence

        assert hf_dataset.features is not None
        assert "image" in hf_dataset.features
        assert "label" in hf_dataset.features
        assert "bbox" in hf_dataset.features

        # Image feature should be Image type
        image_feature = hf_dataset.features["image"]
        assert isinstance(image_feature, HFImage)

        # Classification feature should be dict with label and confidence
        label_feature = hf_dataset.features["label"]
        assert isinstance(label_feature, dict)
        assert "label" in label_feature
        assert "confidence" in label_feature

        # Bbox feature should be dict with bbox list
        bbox_feature = hf_dataset.features["bbox"]
        assert isinstance(bbox_feature, dict)
        assert "bbox" in bbox_feature
        # The bbox feature should be a List of Sequences of floats
        assert isinstance(bbox_feature["bbox"], (HFList, HFSequence))
