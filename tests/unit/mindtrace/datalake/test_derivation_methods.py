"""Unit tests for derivation methods in the Datalake class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from mindtrace.datalake import Datalake
from mindtrace.datalake.types import Datum


def create_mock_datum(data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, datum_id=None):
    """Create a mock Datum instance without requiring beanie initialization."""
    if datum_id is None:
        datum_id = "507f1f77bcf86cd799439011"

    mock_datum = MagicMock(spec=Datum)
    mock_datum.data = data
    mock_datum.registry_uri = registry_uri
    mock_datum.registry_key = registry_key
    mock_datum.derived_from = derived_from
    mock_datum.metadata = metadata or {}
    mock_datum.id = datum_id
    return mock_datum


class TestDerivationMethods:
    """Unit tests for derivation-related methods in Datalake."""

    @pytest.fixture
    def mock_database(self):
        """Mock database backend."""
        mock_db = AsyncMock()
        mock_db.initialize = AsyncMock()
        mock_db.find = AsyncMock()
        mock_db.get_raw_model = MagicMock(return_value=MagicMock(derived_from=MagicMock()))
        return mock_db

    @pytest.fixture
    def mock_registry(self):
        """Mock registry backend."""
        mock_registry = MagicMock()
        mock_registry.save = MagicMock()
        mock_registry.load = MagicMock()
        return mock_registry

    @pytest.fixture
    def datalake(self, mock_database, mock_registry):
        """Create Datalake instance with mocked database and patched Datum model."""

        class _MockDatum:
            def __init__(self, data=None, registry_uri=None, registry_key=None, derived_from=None, metadata=None, contract="default"):
                self.id = PydanticObjectId()
                self.data = data
                self.contract = contract
                self.registry_uri = registry_uri
                self.registry_key = registry_key
                self.derived_from = derived_from
                self.metadata = metadata or {}

        db_patcher = patch("mindtrace.datalake.datalake.MongoMindtraceODMBackend", return_value=mock_database)
        datum_patcher = patch("mindtrace.datalake.datalake.Datum", _MockDatum)
        registry_patcher = patch("mindtrace.datalake.datalake.Registry", return_value=mock_registry)
        db_patcher.start()
        datum_patcher.start()
        registry_patcher.start()
        try:
            instance = Datalake("mongodb://test:27017", "test_db")
            yield instance
        finally:
            datum_patcher.stop()
            registry_patcher.stop()
            db_patcher.stop()

    @pytest.mark.asyncio
    async def test_get_directly_derived_data_single_child(self, datalake, mock_database):
        """Test getting directly derived data with single child."""
        parent_id = PydanticObjectId()
        child_id = PydanticObjectId()

        mock_child = create_mock_datum(data={"child": "data"}, metadata={}, derived_from=parent_id, datum_id=child_id)
        mock_database.find.return_value = [mock_child]

        result = await datalake.get_directly_derived_data(parent_id)

        # Verify database query
        mock_database.find.assert_called_once()
        query_call = mock_database.find.call_args[0][0]
        # The query should be a dictionary with derived_from key
        expected_query = {"derived_from": parent_id}
        assert query_call == expected_query

        assert result == [child_id]

    @pytest.mark.asyncio
    async def test_get_directly_derived_data_multiple_children(self, datalake, mock_database):
        """Test getting directly derived data with multiple children."""
        parent_id = PydanticObjectId()
        child_ids = [PydanticObjectId() for _ in range(3)]

        mock_children = [
            create_mock_datum(data={"child": i}, metadata={}, derived_from=parent_id, datum_id=child_ids[i])
            for i in range(3)
        ]
        mock_database.find.return_value = mock_children

        result = await datalake.get_directly_derived_data(parent_id)

        assert result == child_ids

    @pytest.mark.asyncio
    async def test_get_directly_derived_data_no_children(self, datalake, mock_database):
        """Test getting directly derived data when no children exist."""
        parent_id = PydanticObjectId()
        mock_database.find.return_value = []

        result = await datalake.get_directly_derived_data(parent_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_directly_derived_data_database_error(self, datalake, mock_database):
        """Test error handling in get_directly_derived_data."""
        parent_id = PydanticObjectId()
        mock_database.find.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await datalake.get_directly_derived_data(parent_id)

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_linear_chain(self, datalake):
        """Test getting indirectly derived data in a linear chain A->B->C->D."""
        # Create IDs for chain: A -> B -> C -> D
        ids = [PydanticObjectId() for _ in range(4)]

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = [
                [ids[1]],  # A -> [B]
                [ids[2]],  # B -> [C]
                [ids[3]],  # C -> [D]
                [],  # D -> []
            ]

            result = await datalake.get_indirectly_derived_data(ids[0])

        # Should return all nodes in the chain
        assert set(result) == set(ids)
        assert mock_get_direct.call_count == 4

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_tree_structure(self, datalake):
        """Test getting indirectly derived data in a tree structure."""
        # Create tree: A -> [B, C], B -> [D, E], C -> [F]
        root_id = PydanticObjectId()
        child_ids = [PydanticObjectId() for _ in range(6)]  # B, C, D, E, F, G

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = [
                [child_ids[0], child_ids[1]],  # A -> [B, C]
                [child_ids[2], child_ids[3]],  # B -> [D, E]
                [child_ids[4]],  # C -> [F]
                [],  # D -> []
                [],  # E -> []
                [],  # F -> []
            ]

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should return all nodes in the tree
        expected_ids = [root_id] + child_ids[:5]  # A, B, C, D, E, F
        assert set(result) == set(expected_ids)
        assert mock_get_direct.call_count == 6

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_complex_graph(self, datalake):
        """Test getting indirectly derived data in a complex graph."""
        # Create graph: A -> [B, C], B -> [D], C -> [D, E], D -> [F], E -> [F]
        # This creates a diamond pattern with shared descendants
        root_id = PydanticObjectId()
        child_ids = [PydanticObjectId() for _ in range(5)]  # B, C, D, E, F

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = [
                [child_ids[0], child_ids[1]],  # A -> [B, C]
                [child_ids[2]],  # B -> [D]
                [child_ids[2], child_ids[3]],  # C -> [D, E]
                [child_ids[4]],  # D -> [F]
                [child_ids[4]],  # E -> [F]
                [],  # F -> []
            ]

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should return all unique nodes: A, B, C, D, E, F
        expected_ids = [root_id] + child_ids
        assert set(result) == set(expected_ids)
        assert mock_get_direct.call_count == 6

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_self_reference_prevention(self, datalake):
        """Test that self-references don't cause infinite loops."""
        root_id = PydanticObjectId()
        child_id = PydanticObjectId()

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = [
                [child_id],  # A -> [B]
                [root_id],  # B -> [A] (self-reference)
                [],  # A -> [] (already processed)
            ]

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should handle self-reference gracefully
        expected_ids = [root_id, child_id]
        assert set(result) == set(expected_ids)
        assert mock_get_direct.call_count == 2  # A -> [B], B -> [A], but A is already visited

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_empty_result(self, datalake):
        """Test getting indirectly derived data when no descendants exist."""
        root_id = PydanticObjectId()

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.return_value = []

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should return only the root node
        assert result == [root_id]
        assert mock_get_direct.call_count == 1

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_error_propagation(self, datalake):
        """Test that errors in get_directly_derived_data are propagated."""
        root_id = PydanticObjectId()

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = Exception("Derivation query error")

            with pytest.raises(Exception, match="Derivation query error"):
                await datalake.get_indirectly_derived_data(root_id)

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_breadth_first_order(self, datalake):
        """Test that breadth-first search order is maintained."""
        # Create tree: A -> [B, C], B -> [D], C -> [E]
        root_id = PydanticObjectId()
        child_ids = [PydanticObjectId() for _ in range(4)]  # B, C, D, E

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            mock_get_direct.side_effect = [
                [child_ids[0], child_ids[1]],  # A -> [B, C]
                [child_ids[2]],  # B -> [D]
                [child_ids[3]],  # C -> [E]
                [],  # D -> []
                [],  # E -> []
            ]

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should process in breadth-first order: A, then B,C, then D,E
        expected_ids = [root_id] + child_ids
        assert set(result) == set(expected_ids)

        # Verify call order (breadth-first)
        call_args = [call[0][0] for call in mock_get_direct.call_args_list]
        assert call_args[0] == root_id  # A
        assert call_args[1] == child_ids[0]  # B
        assert call_args[2] == child_ids[1]  # C
        assert call_args[3] == child_ids[2]  # D
        assert call_args[4] == child_ids[3]  # E

    @pytest.mark.asyncio
    async def test_get_indirectly_derived_data_large_tree(self, datalake):
        """Test performance with a larger tree structure."""
        # Create a tree with 3 levels: 1 -> 3 -> 9 nodes
        root_id = PydanticObjectId()
        level1_ids = [PydanticObjectId() for _ in range(3)]
        level2_ids = [PydanticObjectId() for _ in range(9)]

        with patch.object(datalake, "get_directly_derived_data") as mock_get_direct:
            # Root -> 3 children
            mock_get_direct.side_effect = [
                level1_ids,  # Root -> [L1_0, L1_1, L1_2]
                level2_ids[0:3],  # L1_0 -> [L2_0, L2_1, L2_2]
                level2_ids[3:6],  # L1_1 -> [L2_3, L2_4, L2_5]
                level2_ids[6:9],  # L1_2 -> [L2_6, L2_7, L2_8]
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                [],
                [],  # All L2 nodes have no children
            ]

            result = await datalake.get_indirectly_derived_data(root_id)

        # Should return all 13 nodes (1 + 3 + 9)
        expected_ids = [root_id] + level1_ids + level2_ids
        assert set(result) == set(expected_ids)
        assert len(result) == 13
        assert mock_get_direct.call_count == 13
