"""Integration tests for the Dataset class."""

import pytest
from PIL import Image as PILImage

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Dataset


class TestDatasetIntegration:
    """Integration tests for the Dataset class."""

    @pytest.mark.asyncio
    async def test_dataset_create_from_query_data_and_to_hf(self, datalake: Datalake, temp_registry_dir: str):
        """Test creating a Dataset from query_data, loading it, and converting to HuggingFace dataset."""
        # Create some test data
        # First, create some images
        image1 = PILImage.new("RGB", (100, 100), color="red")
        image2 = PILImage.new("RGB", (100, 100), color="blue")
        image3 = PILImage.new("RGB", (100, 100), color="green")

        # Add image data to the datalake using registry storage (PIL Images cannot be stored directly in MongoDB)
        registry_uri = temp_registry_dir
        image_datum1 = await datalake.add_datum(
            data=image1, metadata={"type": "image", "project": "test_project"}, registry_uri=registry_uri
        )
        image_datum2 = await datalake.add_datum(
            data=image2, metadata={"type": "image", "project": "test_project"}, registry_uri=registry_uri
        )
        image_datum3 = await datalake.add_datum(
            data=image3, metadata={"type": "image", "project": "test_project"}, registry_uri=registry_uri
        )

        # Create some label data
        label_datum1 = await datalake.add_datum(
            data={"label": "cat", "confidence": 0.95}, metadata={"type": "label"}, derived_from=image_datum1.id
        )
        label_datum2 = await datalake.add_datum(
            data={"label": "dog", "confidence": 0.87}, metadata={"type": "label"}, derived_from=image_datum2.id
        )
        label_datum3 = await datalake.add_datum(
            data={"label": "bird", "confidence": 0.92}, metadata={"type": "label"}, derived_from=image_datum3.id
        )

        # Use query_data to get datum_ids with transpose=True to get a dict
        query = [
            {"metadata.project": "test_project", "metadata.type": "image", "column": "image"},
            {"derived_from": "image", "metadata.type": "label", "column": "label"},
        ]
        datum_ids_dict = await datalake.query_data(query, transpose=True)

        # Verify we got the expected structure
        assert "image" in datum_ids_dict
        assert "label" in datum_ids_dict
        assert len(datum_ids_dict["image"]) == 3
        assert len(datum_ids_dict["label"]) == 3

        # Create a Dataset instance with the datum_ids
        dataset = Dataset(
            name="test_dataset",
            description="Integration test dataset",
            datum_ids=datum_ids_dict,
        )

        # Insert the dataset into the database
        inserted_dataset = await datalake.dataset_database.insert(dataset)

        # Verify the dataset was inserted
        assert inserted_dataset.id is not None
        assert inserted_dataset.name == "test_dataset"
        assert inserted_dataset.description == "Integration test dataset"
        assert len(inserted_dataset.datum_ids["image"]) == 3
        assert len(inserted_dataset.datum_ids["label"]) == 3

        # Test load() method
        loaded_data = await inserted_dataset.load(datalake)

        # Verify loaded_data structure
        assert "image" in loaded_data
        assert "label" in loaded_data
        assert len(loaded_data["image"]) == 3
        assert len(loaded_data["label"]) == 3

        # Verify the loaded images are PIL Images
        for img in loaded_data["image"]:
            assert isinstance(img, PILImage.Image)

        # Verify the loaded labels are dictionaries
        for label in loaded_data["label"]:
            assert isinstance(label, dict)
            assert "label" in label
            assert "confidence" in label

        # Test to_HF() method
        hf_dataset = await inserted_dataset.to_HF(datalake)

        # Verify it's a valid HuggingFace Dataset
        from datasets import Dataset as HuggingFaceDataset

        assert isinstance(hf_dataset, HuggingFaceDataset)

        # Verify the dataset has the expected columns
        assert "image" in hf_dataset.column_names
        assert "label" in hf_dataset.column_names

        # Verify the dataset has the expected number of rows
        assert len(hf_dataset) == 3

        # Verify we can access data from the dataset
        first_row = hf_dataset[0]
        assert "image" in first_row
        assert "label" in first_row

        # Verify the image column was cast correctly (should be Image feature type)
        # The Image feature type should have decode attribute
        assert "image" in hf_dataset.features
        # Check that the image feature is an Image feature
        from datasets import Image as HFImage

        assert isinstance(hf_dataset.features["image"], HFImage)

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

        # Verify we can access specific indices
        assert hf_dataset[0] is not None
        assert hf_dataset[1] is not None
        assert hf_dataset[2] is not None

        # Verify the dataset info is accessible
        assert hf_dataset.info is not None

        # Verify dataset features are properly defined
        assert hf_dataset.features is not None
        assert "image" in hf_dataset.features
        assert "label" in hf_dataset.features

        # Verify we can select columns
        image_only = hf_dataset.select_columns(["image"])
        assert "image" in image_only.column_names
        assert len(image_only) == 3

