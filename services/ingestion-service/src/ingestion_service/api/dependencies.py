from fastapi import Request

from messaging.kafka_producer import KafkaEventPublisher


def get_publisher(request: Request) -> KafkaEventPublisher:
    return request.app.state.publisher
