import os

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "16379"))
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
GRPC_HOST = os.getenv("GRPC_HOST", "[::]")