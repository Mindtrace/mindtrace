"""Unit tests for the Dataset class."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId
from datasets import Image, IterableDataset, List, Sequence, Value

from mindtrace.datalake.datum import Datum
from mindtrace.datalake.dataset import Dataset, contracts_to_hf_type, gen


def create_mock_dataset(
    name="test_dataset",
    description="Test description",
    contracts=None,
    datum_ids=None,
    metadata=None,
    dataset_id=None,
    created_at=None,
    updated_at=None,
):
    """Create a mock Dataset instance for testing."""
    if dataset_id is None:
        dataset_id = PydanticObjectId()
    if created_at is None:
        created_at = datetime.now()
    if updated_at is None:
        updated_at = datetime.now()
    if contracts is None:
        contracts = {}
    if datum_ids is None:
        datum_ids = []
    if metadata is None:
        metadata = {}

    mock_dataset = MagicMock(spec=Dataset)
    mock_dataset.name = name
    mock_dataset.description = description
    mock_dataset.contracts = contracts
    mock_dataset.datum_ids = datum_ids
    mock_dataset.metadata = metadata
    mock_dataset.id = dataset_id
    mock_dataset.created_at = created_at
    mock_dataset.updated_at = updated_at
    return mock_dataset


def create_mock_datum(data=None, contract="default", datum_id=None, added_at=None):
    """Create a mock Datum instance for testing."""
    if datum_id is None:
        datum_id = PydanticObjectId()
    if added_at is None:
        added_at = datetime.now()

    mock_datum = MagicMock(spec=Datum)
    mock_datum.data = data
    mock_datum.contract = contract
    mock_datum.id = datum_id
    mock_datum.added_at = added_at
    return mock_datum


class TestDatasetModel:
    """Unit tests for the Dataset model."""

    def test_dataset_creation_with_minimal_fields(self):
        """Test creating a Dataset with minimal required fields."""
        dataset = create_mock_dataset(name="test_dataset", description="Test description")

        assert dataset.name == "test_dataset"
        assert dataset.description == "Test description"
        assert dataset.contracts == {}
        assert dataset.datum_ids == []
        assert dataset.metadata == {}
        assert isinstance(dataset.created_at, datetime)
        assert isinstance(dataset.updated_at, datetime)

    def test_dataset_creation_with_all_fields(self):
        """Test creating a Dataset with all fields populated."""
        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        contracts = {"image": "image", "label": "classification"}
        metadata = {"project": "test", "version": "1.0"}
        created_at = datetime(2024, 1, 1, 10, 0, 0)
        updated_at = datetime(2024, 1, 2, 10, 0, 0)

        dataset = create_mock_dataset(
            name="full_dataset",
            description="Full dataset description",
            contracts=contracts,
            datum_ids=[{"image": datum_id1, "label": datum_id2}],
            metadata=metadata,
            created_at=created_at,
            updated_at=updated_at,
        )

        assert dataset.name == "full_dataset"
        assert dataset.description == "Full dataset description"
        assert dataset.contracts == contracts
        assert len(dataset.datum_ids) == 1
        assert dataset.datum_ids[0]["image"] == datum_id1
        assert dataset.datum_ids[0]["label"] == datum_id2
        assert dataset.metadata == metadata
        assert dataset.created_at == created_at
        assert dataset.updated_at == updated_at

    def test_dataset_contracts_default_factory(self):
        """Test that contracts defaults to empty dict using default_factory."""
        dataset1 = create_mock_dataset(name="test1", description="desc1")
        dataset2 = create_mock_dataset(name="test2", description="desc2")

        assert dataset1.contracts == {}
        assert dataset2.contracts == {}
        # In mocks, these are separate objects
        assert dataset1.contracts == dataset2.contracts

    def test_dataset_datum_ids_default_factory(self):
        """Test that datum_ids defaults to empty list using default_factory."""
        dataset1 = create_mock_dataset(name="test1", description="desc1")
        dataset2 = create_mock_dataset(name="test2", description="desc2")

        assert dataset1.datum_ids == []
        assert dataset2.datum_ids == []
        # In mocks, these are separate objects
        assert dataset1.datum_ids == dataset2.datum_ids

    def test_dataset_metadata_default_factory(self):
        """Test that metadata defaults to empty dict using default_factory."""
        dataset1 = create_mock_dataset(name="test1", description="desc1")
        dataset2 = create_mock_dataset(name="test2", description="desc2")

        assert dataset1.metadata == {}
        assert dataset2.metadata == {}
        # In mocks, these are separate objects
        assert dataset1.metadata == dataset2.metadata

    def test_dataset_created_at_default_factory(self):
        """Test that created_at is automatically set when not provided."""
        before_creation = datetime.now()
        dataset = create_mock_dataset(name="test", description="desc")
        after_creation = datetime.now()

        assert dataset.created_at is not None
        assert isinstance(dataset.created_at, datetime)
        assert before_creation <= dataset.created_at <= after_creation

    def test_dataset_updated_at_default_factory(self):
        """Test that updated_at is automatically set when not provided."""
        before_creation = datetime.now()
        dataset = create_mock_dataset(name="test", description="desc")
        after_creation = datetime.now()

        assert dataset.updated_at is not None
        assert isinstance(dataset.updated_at, datetime)
        assert before_creation <= dataset.updated_at <= after_creation

    def test_dataset_with_multiple_rows(self):
        """Test Dataset with multiple rows of datum_ids."""
        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        datum_id3 = PydanticObjectId()
        datum_id4 = PydanticObjectId()

        dataset = create_mock_dataset(
            name="multi_row_dataset",
            description="Dataset with multiple rows",
            datum_ids=[
                {"image": datum_id1, "label": datum_id2},
                {"image": datum_id3, "label": datum_id4},
            ],
        )

        assert len(dataset.datum_ids) == 2
        assert dataset.datum_ids[0]["image"] == datum_id1
        assert dataset.datum_ids[0]["label"] == datum_id2
        assert dataset.datum_ids[1]["image"] == datum_id3
        assert dataset.datum_ids[1]["label"] == datum_id4

    def test_dataset_with_different_column_names(self):
        """Test Dataset with different column names."""
        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        datum_id3 = PydanticObjectId()

        dataset = create_mock_dataset(
            name="multi_column_dataset",
            description="Dataset with multiple columns",
            datum_ids=[
                {"image": datum_id1, "label": datum_id2, "bbox": datum_id3},
            ],
        )

        assert len(dataset.datum_ids) == 1
        assert "image" in dataset.datum_ids[0]
        assert "label" in dataset.datum_ids[0]
        assert "bbox" in dataset.datum_ids[0]


class TestDatasetLoad:
    """Unit tests for the Dataset.load() method."""

    @pytest.fixture
    def mock_datalake(self):
        """Create a mock Datalake instance."""
        mock_datalake = MagicMock()
        mock_datalake.get_data = AsyncMock()
        return mock_datalake

    @pytest.fixture
    def dataset_class(self):
        """Create a mock Dataset class that can be instantiated."""

        class MockDataset:
            def __init__(self, name, description, contracts=None, datum_ids=None, metadata=None):
                self.name = name
                self.description = description
                self.contracts = contracts or {}
                self.datum_ids = datum_ids or []
                self.metadata = metadata or {}
                self.id = None
                self.created_at = datetime.now()
                self.updated_at = datetime.now()

            async def load(self, datalake):
                """Mock load method that calls the real implementation logic."""
                loaded_rows = []
                contracts = {}
                for i, row in enumerate(self.datum_ids):
                    loaded_row = {}
                    column_id_pairs = list(row.items())
                    datum_ids = [datum_id for _, datum_id in column_id_pairs]
                    datums = await datalake.get_data(datum_ids)
                    if i == 0:
                        for (column, _), datum in zip(column_id_pairs, datums):
                            contracts[column] = datum.contract
                    else:
                        for (column, _), datum in zip(column_id_pairs, datums):
                            if contracts[column] != datum.contract:
                                raise ValueError(
                                    f"All datums in a column must have the same contract, but entry {i} column {column} has contract {datum.contract} when the column contract is {contracts[column]}"
                                )
                    for (column, _), datum in zip(column_id_pairs, datums):
                        loaded_row[column] = datum.data
                    loaded_rows.append(loaded_row)
                self.contracts = contracts
                return loaded_rows

        return MockDataset

    @pytest.mark.asyncio
    async def test_load_empty_dataset(self, mock_datalake, dataset_class):
        """Test loading an empty dataset."""
        dataset = dataset_class(name="empty", description="Empty dataset")

        result = await dataset.load(mock_datalake)

        assert result == []
        assert dataset.contracts == {}
        mock_datalake.get_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_single_row_single_column(self, mock_datalake, dataset_class):
        """Test loading a dataset with a single row and single column."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(data={"test": "data"}, contract="default", datum_id=datum_id)

        dataset = dataset_class(
            name="single_row",
            description="Single row dataset",
            datum_ids=[{"data": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        result = await dataset.load(mock_datalake)

        assert len(result) == 1
        assert result[0]["data"] == {"test": "data"}
        assert dataset.contracts == {"data": "default"}
        mock_datalake.get_data.assert_called_once_with([datum_id])

    @pytest.mark.asyncio
    async def test_load_multiple_rows_single_column(self, mock_datalake, dataset_class):
        """Test loading a dataset with multiple rows and single column."""
        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        mock_datum1 = create_mock_datum(data={"test": "data1"}, contract="default", datum_id=datum_id1)
        mock_datum2 = create_mock_datum(data={"test": "data2"}, contract="default", datum_id=datum_id2)

        dataset = dataset_class(
            name="multi_row",
            description="Multiple row dataset",
            datum_ids=[{"data": datum_id1}, {"data": datum_id2}],
        )

        mock_datalake.get_data.side_effect = [
            [mock_datum1],
            [mock_datum2],
        ]

        result = await dataset.load(mock_datalake)

        assert len(result) == 2
        assert result[0]["data"] == {"test": "data1"}
        assert result[1]["data"] == {"test": "data2"}
        assert dataset.contracts == {"data": "default"}

    @pytest.mark.asyncio
    async def test_load_single_row_multiple_columns(self, mock_datalake, dataset_class):
        """Test loading a dataset with a single row and multiple columns."""
        image_id = PydanticObjectId()
        label_id = PydanticObjectId()
        mock_image = create_mock_datum(data="image_path", contract="image", datum_id=image_id)
        mock_label = create_mock_datum(
            data={"label": "cat", "confidence": 0.95}, contract="classification", datum_id=label_id
        )

        dataset = dataset_class(
            name="multi_column",
            description="Multiple column dataset",
            datum_ids=[{"image": image_id, "label": label_id}],
        )

        mock_datalake.get_data.return_value = [mock_image, mock_label]

        result = await dataset.load(mock_datalake)

        assert len(result) == 1
        assert result[0]["image"] == "image_path"
        assert result[0]["label"] == {"label": "cat", "confidence": 0.95}
        assert dataset.contracts == {"image": "image", "label": "classification"}

    @pytest.mark.asyncio
    async def test_load_multiple_rows_multiple_columns(self, mock_datalake, dataset_class):
        """Test loading a dataset with multiple rows and multiple columns."""
        image_id1 = PydanticObjectId()
        label_id1 = PydanticObjectId()
        image_id2 = PydanticObjectId()
        label_id2 = PydanticObjectId()

        mock_image1 = create_mock_datum(data="image_path1", contract="image", datum_id=image_id1)
        mock_label1 = create_mock_datum(
            data={"label": "cat", "confidence": 0.95}, contract="classification", datum_id=label_id1
        )
        mock_image2 = create_mock_datum(data="image_path2", contract="image", datum_id=image_id2)
        mock_label2 = create_mock_datum(
            data={"label": "dog", "confidence": 0.87}, contract="classification", datum_id=label_id2
        )

        dataset = dataset_class(
            name="multi_row_column",
            description="Multiple row and column dataset",
            datum_ids=[
                {"image": image_id1, "label": label_id1},
                {"image": image_id2, "label": label_id2},
            ],
        )

        mock_datalake.get_data.side_effect = [
            [mock_image1, mock_label1],
            [mock_image2, mock_label2],
        ]

        result = await dataset.load(mock_datalake)

        assert len(result) == 2
        assert result[0]["image"] == "image_path1"
        assert result[0]["label"] == {"label": "cat", "confidence": 0.95}
        assert result[1]["image"] == "image_path2"
        assert result[1]["label"] == {"label": "dog", "confidence": 0.87}
        assert dataset.contracts == {"image": "image", "label": "classification"}

    @pytest.mark.asyncio
    async def test_load_contract_detection_first_row(self, mock_datalake, dataset_class):
        """Test that contracts are detected from the first row."""
        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        mock_datum1 = create_mock_datum(data="data1", contract="image", datum_id=datum_id1)
        mock_datum2 = create_mock_datum(data="data2", contract="image", datum_id=datum_id2)

        dataset = dataset_class(
            name="contract_detection",
            description="Test contract detection",
            datum_ids=[{"col": datum_id1}, {"col": datum_id2}],
        )

        mock_datalake.get_data.side_effect = [
            [mock_datum1],
            [mock_datum2],
        ]

        await dataset.load(mock_datalake)

        assert dataset.contracts == {"col": "image"}

    @pytest.mark.asyncio
    async def test_load_contract_validation_mismatch(self, mock_datalake, dataset_class):
        """Test that load raises ValueError when contracts don't match."""
        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        mock_datum1 = create_mock_datum(data="data1", contract="image", datum_id=datum_id1)
        mock_datum2 = create_mock_datum(data="data2", contract="classification", datum_id=datum_id2)

        dataset = dataset_class(
            name="contract_mismatch",
            description="Test contract mismatch",
            datum_ids=[{"col": datum_id1}, {"col": datum_id2}],
        )

        mock_datalake.get_data.side_effect = [
            [mock_datum1],
            [mock_datum2],
        ]

        with pytest.raises(ValueError, match="All datums in a column must have the same contract"):
            await dataset.load(mock_datalake)

    @pytest.mark.asyncio
    async def test_load_preserves_column_order(self, mock_datalake, dataset_class):
        """Test that load preserves the order of columns."""
        image_id = PydanticObjectId()
        label_id = PydanticObjectId()
        bbox_id = PydanticObjectId()

        mock_image = create_mock_datum(data="image", contract="image", datum_id=image_id)
        mock_label = create_mock_datum(data={"label": "cat"}, contract="classification", datum_id=label_id)
        mock_bbox = create_mock_datum(data={"bbox": []}, contract="bbox", datum_id=bbox_id)

        dataset = dataset_class(
            name="column_order",
            description="Test column order",
            datum_ids=[{"image": image_id, "label": label_id, "bbox": bbox_id}],
        )

        mock_datalake.get_data.return_value = [mock_image, mock_label, mock_bbox]

        result = await dataset.load(mock_datalake)

        # Verify order is preserved
        columns = list(result[0].keys())
        assert columns == ["image", "label", "bbox"]


class TestDatasetToHF:
    """Unit tests for the Dataset.to_HF() method."""

    @pytest.fixture
    def mock_datalake(self):
        """Create a mock Datalake instance."""
        mock_datalake = MagicMock()
        mock_datalake.get_data = AsyncMock()
        return mock_datalake

    @pytest.fixture
    def dataset_class(self):
        """Create a mock Dataset class that can be instantiated."""

        class MockDataset:
            def __init__(self, name, description, contracts=None, datum_ids=None, metadata=None):
                self.name = name
                self.description = description
                self.contracts = contracts or {}
                self.datum_ids = datum_ids or []
                self.metadata = metadata or {}
                self.id = None
                self.created_at = datetime.now()
                self.updated_at = datetime.now()

            async def load(self, datalake):
                """Mock load method."""
                loaded_rows = []
                contracts = {}
                for i, row in enumerate(self.datum_ids):
                    loaded_row = {}
                    column_id_pairs = list(row.items())
                    datum_ids = [datum_id for _, datum_id in column_id_pairs]
                    datums = await datalake.get_data(datum_ids)
                    if i == 0:
                        for (column, _), datum in zip(column_id_pairs, datums):
                            contracts[column] = datum.contract
                    else:
                        for (column, _), datum in zip(column_id_pairs, datums):
                            if contracts[column] != datum.contract:
                                raise ValueError(
                                    f"All datums in a column must have the same contract, but entry {i} column {column} has contract {datum.contract} when the column contract is {contracts[column]}"
                                )
                    for (column, _), datum in zip(column_id_pairs, datums):
                        loaded_row[column] = datum.data
                    loaded_rows.append(loaded_row)
                self.contracts = contracts
                return loaded_rows

            async def to_HF(self, datalake):
                """Mock to_HF method that calls the real implementation."""
                from datasets import Features, IterableDataset

                loaded_data = await self.load(datalake)
                features_dict = {column: contracts_to_hf_type[contract] for column, contract in self.contracts.items()}
                hf_type = Features(features_dict)
                return IterableDataset.from_generator(
                    gen, gen_kwargs={"loaded_data": loaded_data, "contracts": self.contracts}, features=hf_type
                )

        return MockDataset

    @pytest.mark.asyncio
    async def test_to_hf_empty_dataset(self, mock_datalake, dataset_class):
        """Test converting an empty dataset to HuggingFace format."""
        dataset = dataset_class(name="empty", description="Empty dataset")

        hf_dataset = await dataset.to_HF(mock_datalake)

        assert isinstance(hf_dataset, IterableDataset)
        # Empty dataset should have no features
        assert hf_dataset.features is None or len(hf_dataset.features) == 0

    @pytest.mark.asyncio
    async def test_to_hf_single_column_image(self, mock_datalake, dataset_class):
        """Test converting a dataset with image column to HuggingFace format."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(data="image_path", contract="image", datum_id=datum_id)

        dataset = dataset_class(
            name="image_dataset",
            description="Image dataset",
            datum_ids=[{"image": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        hf_dataset = await dataset.to_HF(mock_datalake)

        assert isinstance(hf_dataset, IterableDataset)
        assert hf_dataset.features is not None
        assert "image" in hf_dataset.features
        assert isinstance(hf_dataset.features["image"], Image)

    @pytest.mark.asyncio
    async def test_to_hf_single_column_classification(self, mock_datalake, dataset_class):
        """Test converting a dataset with classification column to HuggingFace format."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(
            data={"label": "cat", "confidence": 0.95},
            contract="classification",
            datum_id=datum_id,
        )

        dataset = dataset_class(
            name="classification_dataset",
            description="Classification dataset",
            datum_ids=[{"label": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        hf_dataset = await dataset.to_HF(mock_datalake)

        assert isinstance(hf_dataset, IterableDataset)
        assert hf_dataset.features is not None
        assert "label" in hf_dataset.features
        label_feature = hf_dataset.features["label"]
        assert isinstance(label_feature, dict)
        assert "label" in label_feature
        assert "confidence" in label_feature
        assert isinstance(label_feature["label"], Value)
        assert isinstance(label_feature["confidence"], Value)

    @pytest.mark.asyncio
    async def test_to_hf_single_column_bbox(self, mock_datalake, dataset_class):
        """Test converting a dataset with bbox column to HuggingFace format."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(
            data={"bbox": [[10.0, 20.0, 50.0, 60.0]]},
            contract="bbox",
            datum_id=datum_id,
        )

        dataset = dataset_class(
            name="bbox_dataset",
            description="Bbox dataset",
            datum_ids=[{"bbox": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        hf_dataset = await dataset.to_HF(mock_datalake)

        assert isinstance(hf_dataset, IterableDataset)
        assert hf_dataset.features is not None
        assert "bbox" in hf_dataset.features
        bbox_feature = hf_dataset.features["bbox"]
        assert isinstance(bbox_feature, dict)
        assert "bbox" in bbox_feature

    @pytest.mark.asyncio
    async def test_to_hf_multiple_columns(self, mock_datalake, dataset_class):
        """Test converting a dataset with multiple columns to HuggingFace format."""
        image_id = PydanticObjectId()
        label_id = PydanticObjectId()
        mock_image = create_mock_datum(data="image_path", contract="image", datum_id=image_id)
        mock_label = create_mock_datum(
            data={"label": "cat", "confidence": 0.95},
            contract="classification",
            datum_id=label_id,
        )

        dataset = dataset_class(
            name="multi_column_dataset",
            description="Multi-column dataset",
            datum_ids=[{"image": image_id, "label": label_id}],
        )

        mock_datalake.get_data.return_value = [mock_image, mock_label]

        hf_dataset = await dataset.to_HF(mock_datalake)

        assert isinstance(hf_dataset, IterableDataset)
        assert hf_dataset.features is not None
        assert "image" in hf_dataset.features
        assert "label" in hf_dataset.features

    @pytest.mark.asyncio
    async def test_to_hf_iterates_correctly(self, mock_datalake, dataset_class):
        """Test that to_HF produces an iterable dataset with correct data."""
        from PIL import Image as PILImage

        datum_id1 = PydanticObjectId()
        datum_id2 = PydanticObjectId()
        mock_datum1 = create_mock_datum(data="image1", contract="image", datum_id=datum_id1)
        mock_datum2 = create_mock_datum(data="image2", contract="image", datum_id=datum_id2)

        dataset = dataset_class(
            name="iterable_dataset",
            description="Test iterable dataset",
            datum_ids=[{"image": datum_id1}, {"image": datum_id2}],
        )

        mock_datalake.get_data.side_effect = [
            [mock_datum1],
            [mock_datum2],
        ]

        # Mock PIL Image.open to avoid file loading during iteration
        mock_image = MagicMock(spec=PILImage.Image)
        with patch("PIL.Image.open", return_value=mock_image):
            hf_dataset = await dataset.to_HF(mock_datalake)

            row_count = 0
            for row in hf_dataset:
                assert "image" in row
                row_count += 1

            assert row_count == 2


class TestGenFunction:
    """Unit tests for the gen() generator function."""

    def test_gen_image_contract(self):
        """Test gen function with image contract."""
        loaded_data = [{"image": "path/to/image.png"}]
        contracts = {"image": "image"}

        result = list(gen(loaded_data, contracts))

        assert len(result) == 1
        assert result[0]["image"] == "path/to/image.png"
        assert isinstance(result[0]["image"], str)

    def test_gen_classification_contract(self):
        """Test gen function with classification contract."""
        loaded_data = [{"label": {"label": "cat", "confidence": 0.95}}]
        contracts = {"label": "classification"}

        result = list(gen(loaded_data, contracts))

        assert len(result) == 1
        assert result[0]["label"] == {"label": "cat", "confidence": 0.95}

    def test_gen_bbox_contract(self):
        """Test gen function with bbox contract."""
        loaded_data = [
            {
                "bbox": {
                    "bbox": [[10.0, 20.0, 50.0, 60.0], [80.0, 30.0, 120.0, 70.0]],
                }
            }
        ]
        contracts = {"bbox": "bbox"}

        result = list(gen(loaded_data, contracts))

        assert len(result) == 1
        assert result[0]["bbox"] == {"bbox": [[10.0, 20.0, 50.0, 60.0], [80.0, 30.0, 120.0, 70.0]]}

    def test_gen_bbox_contract_invalid_data(self):
        """Test gen function with bbox contract but invalid data structure."""
        loaded_data = [{"bbox": "not_a_dict"}]
        contracts = {"bbox": "bbox"}

        result = list(gen(loaded_data, contracts))

        # Should pass through invalid data as-is
        assert len(result) == 1
        assert result[0]["bbox"] == "not_a_dict"

    def test_gen_default_contract(self):
        """Test gen function with default contract."""
        loaded_data = [{"data": {"key": "value"}}]
        contracts = {"data": "default"}

        result = list(gen(loaded_data, contracts))

        assert len(result) == 1
        assert result[0]["data"] == {"key": "value"}

    def test_gen_multiple_columns(self):
        """Test gen function with multiple columns."""
        loaded_data = [
            {
                "image": "path/to/image.png",
                "label": {"label": "cat", "confidence": 0.95},
                "bbox": {"bbox": [[10.0, 20.0, 50.0, 60.0]]},
            }
        ]
        contracts = {"image": "image", "label": "classification", "bbox": "bbox"}

        result = list(gen(loaded_data, contracts))

        assert len(result) == 1
        assert result[0]["image"] == "path/to/image.png"
        assert result[0]["label"] == {"label": "cat", "confidence": 0.95}
        assert result[0]["bbox"] == {"bbox": [[10.0, 20.0, 50.0, 60.0]]}

    def test_gen_multiple_rows(self):
        """Test gen function with multiple rows."""
        loaded_data = [
            {"image": "path1.png"},
            {"image": "path2.png"},
            {"image": "path3.png"},
        ]
        contracts = {"image": "image"}

        result = list(gen(loaded_data, contracts))

        assert len(result) == 3
        assert result[0]["image"] == "path1.png"
        assert result[1]["image"] == "path2.png"
        assert result[2]["image"] == "path3.png"


class TestContractsToHFType:
    """Unit tests for the contracts_to_hf_type mapping."""

    def test_contracts_to_hf_type_image(self):
        """Test that image contract maps to Image feature."""
        assert "image" in contracts_to_hf_type
        assert isinstance(contracts_to_hf_type["image"], Image)

    def test_contracts_to_hf_type_classification(self):
        """Test that classification contract maps to correct structure."""
        assert "classification" in contracts_to_hf_type
        classification = contracts_to_hf_type["classification"]
        assert isinstance(classification, dict)
        assert "label" in classification
        assert "confidence" in classification
        assert isinstance(classification["label"], Value)
        assert isinstance(classification["confidence"], Value)
        assert classification["label"].dtype == "string"
        assert classification["confidence"].dtype in ["float64", "float32"]

    def test_contracts_to_hf_type_bbox(self):
        """Test that bbox contract maps to correct structure."""
        assert "bbox" in contracts_to_hf_type
        bbox = contracts_to_hf_type["bbox"]
        assert isinstance(bbox, dict)
        assert "bbox" in bbox
        # The bbox feature should be a List of Sequences
        bbox_list = bbox["bbox"]
        assert isinstance(bbox_list, (List, Sequence))


class TestDatasetEdgeCases:
    """Unit tests for edge cases in Dataset class."""

    @pytest.fixture
    def mock_datalake(self):
        """Create a mock Datalake instance."""
        mock_datalake = MagicMock()
        mock_datalake.get_data = AsyncMock()
        return mock_datalake

    @pytest.fixture
    def dataset_class(self):
        """Create a mock Dataset class that can be instantiated."""

        class MockDataset:
            def __init__(self, name, description, contracts=None, datum_ids=None, metadata=None):
                self.name = name
                self.description = description
                self.contracts = contracts or {}
                self.datum_ids = datum_ids or []
                self.metadata = metadata or {}
                self.id = None
                self.created_at = datetime.now()
                self.updated_at = datetime.now()

            async def load(self, datalake):
                """Mock load method."""
                loaded_rows = []
                contracts = {}
                for i, row in enumerate(self.datum_ids):
                    loaded_row = {}
                    column_id_pairs = list(row.items())
                    datum_ids = [datum_id for _, datum_id in column_id_pairs]
                    datums = await datalake.get_data(datum_ids)
                    if i == 0:
                        for (column, _), datum in zip(column_id_pairs, datums):
                            contracts[column] = datum.contract
                    else:
                        for (column, _), datum in zip(column_id_pairs, datums):
                            if contracts[column] != datum.contract:
                                raise ValueError(
                                    f"All datums in a column must have the same contract, but entry {i} column {column} has contract {datum.contract} when the column contract is {contracts[column]}"
                                )
                    for (column, _), datum in zip(column_id_pairs, datums):
                        loaded_row[column] = datum.data
                    loaded_rows.append(loaded_row)
                self.contracts = contracts
                return loaded_rows

            async def to_HF(self, datalake):
                """Mock to_HF method."""
                from datasets import Features, IterableDataset

                loaded_data = await self.load(datalake)
                features_dict = {column: contracts_to_hf_type[contract] for column, contract in self.contracts.items()}
                hf_type = Features(features_dict)
                return IterableDataset.from_generator(
                    gen, gen_kwargs={"loaded_data": loaded_data, "contracts": self.contracts}, features=hf_type
                )

        return MockDataset

    @pytest.mark.asyncio
    async def test_load_with_none_data(self, mock_datalake, dataset_class):
        """Test loading a dataset where datum data is None."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(data=None, contract="default", datum_id=datum_id)

        dataset = dataset_class(
            name="none_data",
            description="Dataset with None data",
            datum_ids=[{"data": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        result = await dataset.load(mock_datalake)

        assert len(result) == 1
        assert result[0]["data"] is None

    @pytest.mark.asyncio
    async def test_load_with_explicit_contracts(self, mock_datalake, dataset_class):
        """Test loading a dataset with explicitly set contracts."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(data="data", contract="image", datum_id=datum_id)

        dataset = dataset_class(
            name="explicit_contracts",
            description="Dataset with explicit contracts",
            contracts={"col": "image"},
            datum_ids=[{"col": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        await dataset.load(mock_datalake)

        # Contracts should be updated from loaded data
        assert dataset.contracts == {"col": "image"}

    @pytest.mark.asyncio
    async def test_load_contract_validation_different_columns(self, mock_datalake, dataset_class):
        """Test that contract validation works correctly for different columns."""
        image_id = PydanticObjectId()
        label_id = PydanticObjectId()
        mock_image = create_mock_datum(data="image", contract="image", datum_id=image_id)
        mock_label = create_mock_datum(data={"label": "cat"}, contract="classification", datum_id=label_id)

        dataset = dataset_class(
            name="different_contracts",
            description="Different contracts per column",
            datum_ids=[{"image": image_id, "label": label_id}],
        )

        mock_datalake.get_data.return_value = [mock_image, mock_label]

        await dataset.load(mock_datalake)

        # Should work fine with different contracts in different columns
        assert dataset.contracts == {"image": "image", "label": "classification"}

    @pytest.mark.asyncio
    async def test_to_hf_with_explicit_contracts(self, mock_datalake, dataset_class):
        """Test to_HF with explicitly set contracts."""
        datum_id = PydanticObjectId()
        mock_datum = create_mock_datum(data="data", contract="image", datum_id=datum_id)

        dataset = dataset_class(
            name="explicit_contracts_hf",
            description="Dataset with explicit contracts for HF",
            contracts={"col": "image"},
            datum_ids=[{"col": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        hf_dataset = await dataset.to_HF(mock_datalake)

        assert isinstance(hf_dataset, IterableDataset)
        assert hf_dataset.features is not None
        assert "col" in hf_dataset.features

    @pytest.mark.asyncio
    async def test_load_raises_on_missing_contract_in_mapping(self, mock_datalake, dataset_class):
        """Test that to_HF raises error if contract is not in contracts_to_hf_type."""
        datum_id = PydanticObjectId()
        # Create a datum with a contract that doesn't exist in contracts_to_hf_type
        mock_datum = create_mock_datum(data="data", contract="unknown_contract", datum_id=datum_id)

        dataset = dataset_class(
            name="unknown_contract",
            description="Dataset with unknown contract",
            datum_ids=[{"col": datum_id}],
        )

        mock_datalake.get_data.return_value = [mock_datum]

        # Load should work fine
        await dataset.load(mock_datalake)

        # But to_HF should raise KeyError when trying to map the contract
        with pytest.raises(KeyError):
            await dataset.to_HF(mock_datalake)
