from unittest.mock import MagicMock, patch

import pydantic
import pytest
from pika.exceptions import ChannelClosedByBroker, ConnectionClosedByBroker, UnroutableError

from mindtrace.jobs.rabbitmq.client import RabbitMQClient


class DummyModel(pydantic.BaseModel):
    foo: str = "bar"


class DummyChannel(MagicMock):
    def exchange_declare(self, *args, **kwargs):
        pass

    def queue_declare(self, *args, **kwargs):
        pass

    def queue_bind(self, *args, **kwargs):
        pass

    def queue_purge(self, *args, **kwargs):
        pass

    def queue_delete(self, *args, **kwargs):
        pass

    def exchange_delete(self, *args, **kwargs):
        pass

    def basic_publish(self, *args, **kwargs):
        pass


def make_client():
    dc = DummyChannel()
    with patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.connect"):
        with patch("mindtrace.jobs.rabbitmq.connection.RabbitMQConnection.get_channel", return_value=dc):
            client = RabbitMQClient(host="localhost", port=5671, username="user", password="password")
            client.logger = MagicMock()
            client.channel = dc
            client.connection.get_channel = MagicMock(return_value=dc)
            client.connection.count_queue_messages = MagicMock(return_value=42)
            client.create_connection = MagicMock(return_value=dc)
            return client


def test_declare_exchange_already_exists():
    client = make_client()
    client.channel.exchange_declare = MagicMock(return_value=None)
    result = client.declare_exchange(exchange="ex")
    assert result["status"] == "success"
    assert "already exists" in result["message"]


def test_declare_exchange_channel_closed_then_success():
    client = make_client()
    client.channel.exchange_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), None])
    result = client.declare_exchange(exchange="ex")
    assert result["status"] == "success"
    assert "declared successfully" in result["message"]


def test_declare_exchange_channel_closed_then_exception():
    client = make_client()
    client.channel.exchange_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), Exception("fail")])
    with pytest.raises(RuntimeError):
        client.declare_exchange(exchange="ex")


def test_declare_exchange_other_exception():
    client = make_client()
    client.channel.exchange_declare = MagicMock(side_effect=Exception("fail"))
    with pytest.raises(RuntimeError):
        client.declare_exchange(exchange="ex")


def test_declare_queue_already_exists():
    client = make_client()
    client.channel.queue_declare = MagicMock(return_value=None)
    result = client.declare_queue("q")
    assert result["status"] == "success"
    assert "already exists" in result["message"]


def test_declare_queue_channel_closed_force_false():
    client = make_client()
    client.channel.queue_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed")])
    client.channel.exchange_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed")])
    with pytest.raises(ValueError):
        client.declare_queue("q", force=False)


def test_declare_queue_channel_closed_force_true():
    client = make_client()
    client.channel.queue_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), None])
    client.channel.exchange_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), None])
    client.channel.queue_bind = MagicMock(return_value=None)
    result = client.declare_queue("q", force=True)
    assert result["status"] == "success"
    assert "declared successfully" in result["message"]


def test_declare_queue_channel_closed_force_true_still_fails():
    client = make_client()
    client.channel.queue_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), Exception("fail")])
    client.channel.exchange_declare = MagicMock()
    client.channel.queue_bind = MagicMock(return_value=None)
    result = client.declare_queue("q", force=True)
    assert result["status"] == "error"
    assert "Failed to declare queue" in result["message"]


def test_declare_queue_channel_max_priority():
    client = make_client()
    client.channel.queue_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), None])
    client.channel.exchange_declare = MagicMock(side_effect=None)
    client.channel.queue_bind = MagicMock(return_value=None)
    result = client.declare_queue("q", max_priority=10)
    assert result["status"] == "success"
    assert "declared and bound to exchange" in result["message"]


def test_declare_queue_channel_exchange_provided():
    client = make_client()
    client.channel.queue_declare = MagicMock(side_effect=[ChannelClosedByBroker(406, "closed"), None])
    client.channel.exchange_declare = MagicMock(side_effect=None)
    client.channel.queue_bind = MagicMock(return_value=None)
    result = client.declare_queue("q", exchange="ex")
    assert result["status"] == "success"
    assert "declared and bound to exchange 'ex'" in result["message"]


def test_declare_queue_other_exception():
    client = make_client()
    client.channel.queue_declare = MagicMock(side_effect=Exception("fail"))
    result = client.declare_queue("q")
    assert result["status"] == "error"
    assert "Unexpected error" in result["message"]


def test_publish_success():
    client = make_client()
    client.channel.basic_publish = MagicMock(return_value=None)
    dummy = DummyModel()
    job_id = client.publish("q", dummy)
    assert isinstance(job_id, str)


def test_publish_unroutable():
    client = make_client()
    client.channel.basic_publish = MagicMock(side_effect=UnroutableError([]))
    dummy = DummyModel()
    with pytest.raises(UnroutableError):
        client.publish("q", dummy)


def test_publish_channel_closed():
    client = make_client()
    client.channel.basic_publish = MagicMock(side_effect=ChannelClosedByBroker(406, "closed"))
    dummy = DummyModel()
    with pytest.raises(ChannelClosedByBroker):
        client.publish("q", dummy)


def test_publish_connection_closed():
    client = make_client()
    client.channel.basic_publish = MagicMock(side_effect=ConnectionClosedByBroker(320, "closed"))
    dummy = DummyModel()
    with pytest.raises(ConnectionClosedByBroker):
        client.publish("q", dummy)


def test_publish_other_exception():
    client = make_client()
    client.channel.basic_publish = MagicMock(side_effect=Exception("fail"))
    dummy = DummyModel()
    with pytest.raises(Exception):
        client.publish("q", dummy)


def test_clean_queue_success():
    client = make_client()
    client.channel.queue_purge = MagicMock(return_value=None)
    result = client.clean_queue("q")
    assert result["status"] == "success"


def test_clean_queue_channel_closed():
    client = make_client()
    client.channel.queue_purge = MagicMock(side_effect=ChannelClosedByBroker(406, "closed"))
    with pytest.raises(ConnectionError):
        client.clean_queue("q")


def test_delete_queue_success():
    client = make_client()
    client.channel.queue_delete = MagicMock(return_value=None)
    result = client.delete_queue("q")
    assert result["status"] == "success"


def test_delete_queue_channel_closed():
    client = make_client()
    client.channel.queue_delete = MagicMock(side_effect=ChannelClosedByBroker(406, "closed"))
    with pytest.raises(ConnectionError):
        client.delete_queue("q")


def test_count_exchanges_success():
    client = make_client()
    client.channel.exchange_declare = MagicMock(return_value=MagicMock())
    result = client.count_exchanges(exchange="ex")
    assert result is not None


def test_count_exchanges_channel_closed():
    client = make_client()
    client.channel.exchange_declare = MagicMock(side_effect=ChannelClosedByBroker(406, "closed"))
    with pytest.raises(ConnectionError):
        client.count_exchanges(exchange="ex")


def test_delete_exchange_success():
    client = make_client()
    client.channel.exchange_delete = MagicMock(return_value=None)
    result = client.delete_exchange(exchange="ex")
    assert result["status"] == "success"


def test_delete_exchange_channel_closed():
    client = make_client()
    client.channel.exchange_delete = MagicMock(side_effect=ChannelClosedByBroker(406, "closed"))
    with pytest.raises(ConnectionError):
        client.delete_exchange(exchange="ex")


def test_move_to_dlq_logs():
    client = make_client()
    client.logger.info = MagicMock()
    dummy = DummyModel()
    result = client.move_to_dlq("src", "dlq", dummy, "err")
    assert result is None
    client.logger.info.assert_called()


def test_count_queue_messages_delegates():
    client = make_client()
    result = client.count_queue_messages("q")
    assert result == 42
