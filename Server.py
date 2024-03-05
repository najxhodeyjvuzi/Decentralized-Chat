import os
import grpc
import json
import logging
from concurrent import futures

import MiniChat_pb2
import MiniChat_pb2_grpc

PATH = os.path.dirname(__file__)


class Routing:
    def __init__(self):
        self.object = {}

    def Find(self, request, context):
        if request.token not in self.object:
            return MiniChat_pb2.Reply(flag=False, socket=[])

        return MiniChat_pb2.Reply(flag=True, socket=self.object[request.token])

    def userLogin(self, request, context):
        self.object[request.token] = [request.socket]
        logging.info(f"User {request.token} login.")
        return MiniChat_pb2.Reply(flag=True, socket=[])

    def userLogout(self, request, context):
        self.object.pop(request.token)
        logging.info(f"User {request.token} logoff.")
        return MiniChat_pb2.Reply(flag=True, socket=[])

    def joinRoom(self, request, context):
        if request.token not in self.object:
            self.object[request.token] = []
            logging.info(f"Room {request.token} created by.")
        logging.info(f"Room {request.token} found.")
        self.object[request.token].append(request.socket)
        return MiniChat_pb2.Reply(flag=True, socket=[])

    def leaveRoom(self, request, context):
        self.object[request.token].remove(request.socket)
        if len(self.object[request.token]) == 0:
            self.object.pop(request.token)
            logging.info(f"Room {request.token} dismiss.")
        return MiniChat_pb2.Reply(flag=True, socket=[])


if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

    os.makedirs('ServerLog', exist_ok=True)
    log_file_path = './ServerLog/ServerLog.log'
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger('').addHandler(file_handler)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    MiniChat_pb2_grpc.add_RoutingServicer_to_server(Routing(), server)
    server.add_insecure_port("localhost:10001")
    server.start()
    logging.info(f"Server started, listening on port 10001.")
    logging.info(f"Press CTRL+C to stop.")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        server.stop(0)