import grpc
from concurrent import futures
import time
import os
import random

import demo_pb2
import demo_pb2_grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from logger import getJSONLogger
logger = getJSONLogger('recommendationservice')

class RecommendationService(demo_pb2_grpc.RecommendationServiceServicer):
    def ListRecommendations(self, request, context):
        max_responses = 5
        product_ids = [
            'OLJCESPC7Z', '66VCHSJNUP', '1YMWWN1N4O', 'L9ECAV7KIM',
            '2ZYFJ3GM2N', '0PUK6V6EV0', 'LS4PSXUNUM', '9SIQT8TOJO', '6E92ZMYYFZ'
        ]
        filtered = [p for p in product_ids if p not in request.product_ids]
        num = min(max_responses, len(filtered))
        indices = random.sample(range(len(filtered)), num) if filtered else []
        result = [filtered[i] for i in indices]
        logger.info('Recommending ' + str(len(result)) + ' products')
        return demo_pb2.ListRecommendationsResponse(product_ids=result)

class HealthCheck(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)

def serve():
    port = os.environ.get('PORT', '8080')
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    demo_pb2_grpc.add_RecommendationServiceServicer_to_server(RecommendationService(), server)
    health_pb2_grpc.add_HealthServicer_to_server(HealthCheck(), server)
    server.add_insecure_port('[::]:' + port)
    server.start()
    logger.info('starting server on port ' + port)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
