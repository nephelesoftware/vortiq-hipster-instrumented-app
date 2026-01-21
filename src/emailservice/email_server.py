import grpc
from concurrent import futures
import time
import os

import demo_pb2
import demo_pb2_grpc
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from logger import getJSONLogger
logger = getJSONLogger('emailservice-server')

class EmailService(demo_pb2_grpc.EmailServiceServicer):
    def SendOrderConfirmation(self, request, context):
        email = request.email
        order = request.order
        logger.info('request received')
        return demo_pb2.Empty()

class HealthCheck(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)

    def Watch(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)

def serve():
    port = os.environ.get('PORT', '8080')
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    demo_pb2_grpc.add_EmailServiceServicer_to_server(EmailService(), server)
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
