import json
import runpy
from pathlib import Path

from src.anomaly_detector import AnomalyDetector
from src.aiops_pipeline import run_pipeline
from src.event_consumer import EventConsumer
from src.event_producer import EventProducer
from src.event_topic import EventTopic


def test_normal_record_is_not_anomaly():
    detector = AnomalyDetector()

    record = {
        "timestamp": "2026-09-20T10:00:00",
        "service": "payment-service",
        "response_time_ms": 120,
        "cpu_percent": 42,
        "memory_percent": 51,
        "log_level": "INFO",
        "message": "Payment request processed successfully"
    }

    assert detector.detect(record) is None


def test_anomalous_record_is_detected():
    detector = AnomalyDetector()

    record = {
        "timestamp": "2026-09-20T10:05:00",
        "service": "payment-service",
        "response_time_ms": 610,
        "cpu_percent": 75,
        "memory_percent": 70,
        "log_level": "ERROR",
        "message": "Payment service timeout"
    }

    event = detector.detect(record)

    assert event is not None
    assert event["type"] == "ANOMALY"


def test_warning_log_creates_anomaly_reason():
    detector = AnomalyDetector()

    record = {
        "timestamp": "2026-09-20T11:00:00",
        "service": "auth-service",
        "response_time_ms": 100,
        "cpu_percent": 40,
        "memory_percent": 30,
        "log_level": "WARNING",
        "message": "Subscription warning"
    }

    event = detector.detect(record)

    assert event is not None
    assert "Warning log detected" in event["reasons"]


def test_producer_publishes_event():
    topic = EventTopic("anomaly-events")
    producer = EventProducer(topic)

    event = {
        "type": "ANOMALY",
        "service": "payment-service"
    }

    assert producer.publish(event)
    assert len(topic.get_messages()) == 1


def test_producer_rejects_empty_event():
    topic = EventTopic("anomaly-events")
    producer = EventProducer(topic)

    assert producer.publish(None) is False
    assert producer.publish({}) is False
    assert topic.get_messages() == []


def test_consumer_receives_event():
    topic = EventTopic("anomaly-events")
    producer = EventProducer(topic)
    consumer = EventConsumer(topic)

    event = {
        "type": "ANOMALY",
        "service": "payment-service"
    }

    producer.publish(event)
    messages = consumer.consume()

    assert len(messages) == 1
    assert messages[0]["service"] == "payment-service"


def test_event_topic_clear_removes_messages():
    topic = EventTopic("anomaly-events")
    topic.publish({"service": "alpha"})
    topic.publish({"service": "beta"})

    topic.clear()

    assert topic.get_messages() == []


def test_run_pipeline_reads_and_processes_records(tmp_path):
    file_path = tmp_path / "service_data.json"
    file_path.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-09-20T10:00:00",
                    "service": "payment-service",
                    "response_time_ms": 120,
                    "cpu_percent": 42,
                    "memory_percent": 51,
                    "log_level": "INFO",
                    "message": "Payment request processed successfully"
                },
                {
                    "timestamp": "2026-09-20T10:05:00",
                    "service": "auth-service",
                    "response_time_ms": 600,
                    "cpu_percent": 90,
                    "memory_percent": 90,
                    "log_level": "WARNING",
                    "message": "auth latency spike"
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run_pipeline(str(file_path))

    assert result["records_processed"] == 2
    assert len(result["anomalies_detected"]) == 1
    assert result["anomalies_detected"][0]["service"] == "auth-service"
    assert len(result["events_consumed"]) == 1
    assert result["events_consumed"][0]["service"] == "auth-service"


def test_aiops_pipeline_script_entrypoint_runs():
    script_path = Path(__file__).resolve().parents[1] / "src" / "aiops_pipeline.py"

    runpy.run_path(str(script_path), run_name="__main__")
