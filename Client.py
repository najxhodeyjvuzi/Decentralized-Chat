import grpc
import logging
import random
import os
import time
from concurrent import futures
import threading

import MiniChat_pb2
import MiniChat_pb2_grpc


class chat:
    def __init__(self):
        self.lock = threading.Lock()

    # 向群聊房中的用户发送信息
    def send_room(self, request, context):
        with self.lock:
            with open(room_version_file_dir,'r+') as version_file:
                content = version_file.read().strip()
                version_file.seek(0)
                if content:
                    version_file.write(f"{int(content)+1}")
                else:
                    version_file.write("1")

            logging.info(request.message)
            return MiniChat_pb2.Reply(flag=True, socket=[])
    
    # 请求群聊房最新的聊天记录
    def apply_for_room_history(self,request, context):
        with self.lock:
            with open(Room_chatfile_path,'r') as chat_histroy:
                return MiniChat_pb2.chatMessage(message = chat_histroy.read().strip())
            
    # 请求各用户的聊天记录版本号
    def request_room_version(self, request, context):
        with self.lock:
            if os.path.exists(room_version_file_dir):
                with open(room_version_file_dir, 'r') as version_file:
                    content = version_file.read().strip()
                    if content:
                        return MiniChat_pb2.versionMessage(version = int(content))
                    else:
                        return MiniChat_pb2.versionMessage(version = 0)
            else:
                return MiniChat_pb2.versionMessage(version = 0)
            
    # 发送私聊信息
    def send_personal(self, request, context):
        with self.lock:
            if not "personal_version_file_dir" in globals():
                return MiniChat_pb2.Reply(flag=True, socket=[])
            with open(personal_version_file_dir,'r+') as version_file:
                content = version_file.read().strip()
                version_file.seek(0)
                if content:
                    version_file.write(f"{int(content)+1}")
                else:
                    version_file.write("1")

            logging.info(request.message)
            return MiniChat_pb2.Reply(flag=True, socket=[])
        
    # 请求历史记录
    def apply_for_personal_history(self,request, context):
        with self.lock:
            with open(Personal_chatfile_path,'r') as chat_histroy:
                return MiniChat_pb2.chatMessage(message = chat_histroy.read().strip())
            
    # 请求聊天记录版本
    # 这里需要相较聊天房需要进行一个特殊处理
    # 既判断 版本管理文件-version_file 是否已经存在
    def request_personal_version(self, request, context):
        with self.lock:
            if not "personal_version_file_dir" in globals():
                return MiniChat_pb2.versionMessage(version = 0)
            if os.path.exists(personal_version_file_dir):
                with open(personal_version_file_dir, 'r') as version_file:
                    content = version_file.read().strip()
                    if content:
                        return MiniChat_pb2.versionMessage(version = int(content))
                    else:
                        return MiniChat_pb2.versionMessage(version = 0)
            else:
                return MiniChat_pb2.versionMessage(version = 0)
            

if __name__ == "__main__":

    # 日志格式的设置
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

    # 为客户分配端口
    port = random.randint(30000, 40000)
    socket = f"localhost:{port}"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))

    # 定义类，和grpc对接
    MiniChat_pb2_grpc.add_chatServicer_to_server(chat(), server)
    
    # 与服务器联系
    server.add_insecure_port(socket)
    server.start()

    logging.info(f"Server started, listening on port {port}.")
    logging.info(f"CTRL+C to exit.")
    
    # 用户注册登陆
    token = input("Input your nickname: ")
    channel = grpc.insecure_channel("localhost:10001")
    stub = MiniChat_pb2_grpc.RoutingStub(channel)

    # 设置主日志路径
    log_filename = f"{token}.log"
    dir_name = 'ChatFiles/'+f"{token}"

    
    os.makedirs(dir_name, exist_ok=True)
    user_file_path = os.path.join(dir_name,log_filename)

    os.makedirs(dir_name, exist_ok=True)
    user_file_path = os.path.join(dir_name,log_filename)
    file_handler = logging.FileHandler(user_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger('').addHandler(file_handler)


    stub.userLogin(
        MiniChat_pb2.Object(
            token=token, socket=socket))

    try:
        while True:
            option = input("CHAT ROOM or PRIVATE CONNECTION with only 2 users [1/2]: \n")

            # 群聊功能
            if option == "1":
                target = input("Input the room name you want to enter:\n")
                sockets = stub.Find(
                    MiniChat_pb2.Object(token=target, socket=socket))

                Room_chatfile_name = f"{token}-{target}.log"
                Room_chatfile_dir = f"ChatFiles/{token}/ChatRoom/{target}"

                if not sockets.flag:
                    if not os.path.exists(Room_chatfile_dir):
                        logging.info(f"A new room \'{target}\' is created by you.")
                else:
                    logging.info(f"Joined in \'{target}\'.")

                stub.joinRoom(MiniChat_pb2.Object(
                    token=target, socket=socket))

                # 切换聊天记录日志，用logging
                os.makedirs(Room_chatfile_dir, exist_ok=True)
                Room_chatfile_path = os.path.join(Room_chatfile_dir, Room_chatfile_name)
                Room_file_handler = logging.FileHandler(Room_chatfile_path)
                Room_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                logging.getLogger('').removeHandler(file_handler)
                logging.getLogger('').addHandler(Room_file_handler)

                #------------------------------------------------------------------------------------------------------
                # 聊天记录一致性
                # 从同频道（若是私人聊天，则从对方和自己/若是聊天房，则从参与房间的所有对等方，以及自己本地）拉取可能会有不同版本的聊天记录 
                # 选取最新的聊天记录，并更新本地的聊天记录                                                                    
                # 将聊天记录回显到终端窗口上
                #------------------------------------------------------------------------------------------------------
                sockets = stub.Find(
                    MiniChat_pb2.Object(token=target, socket=socket))
                
                # 如果是新建的聊天，那么就需要新建版本号文件 version.log
                # 并将版本号设置成0
                room_version_file_dir = f"ChatFiles/{token}/ChatRoom/{target}/version.log"
                if os.path.exists(room_version_file_dir):
                    with open(room_version_file_dir, 'r+') as version_file:
                        content = version_file.read().strip()
                        if content:
                            version = int(content)
                        else:
                            version = 0
                else:
                    version = 0

                # 群聊背景下
                # 广播寻找拥有最新的聊天记录的用户
                # 然后向该名用户拉取最新的聊天记录副本
                max_version = version
                request_object = socket

                for soc in sockets.socket:
                    with grpc.insecure_channel(soc) as chatChannel:
                        chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                        version = chatStub.request_room_version(MiniChat_pb2.Object(token = target, socket = socket)).version
                        if version > max_version:
                            max_version = version
                            request_object = soc

                with open(room_version_file_dir,'w+') as version:
                    version.write(f"{max_version}")

                if request_object != socket:
                    with grpc.insecure_channel(request_object) as chatChannel:
                        chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                        with open(Room_chatfile_path,'w+') as chatfile:
                            chatfile.write(chatStub.apply_for_room_history(MiniChat_pb2.Object(token = target, socket = socket)).message)

                # 将聊天记录先全部显示一遍，再开始进行聊天
                with open(Room_chatfile_path,'r') as chatfile:
                    print(chatfile.read())
                
                #------------------------------------------------------------------------

                # 监听循环，用于对用户的输入进行反应
                # 将消息发送给同频用户
                while True:

                    message = input(
                        'Input message (\'quit\' to quit): \n')
                    if message == "quit":
                        logging.getLogger('').removeHandler(Room_file_handler)
                        logging.getLogger('').addHandler(file_handler)
                        logging.info(f"-----Chat disconnect!-----")
                        break
                    sockets = stub.Find(
                        MiniChat_pb2.Object(token=target, socket=socket))
                    for soc in sockets.socket:
                        with grpc.insecure_channel(soc) as chatChannel:
                            chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                            chatStub.send_room(MiniChat_pb2.chatMessage(
                                message=f"{token}: {message}"))
                            
                    # 性能测试部分
                    # 以输入信息 ‘test' 表示开始
                    if (message == "test"):
                        logging.info(f"-----test start!-----")
                        sockets = stub.Find(
                            MiniChat_pb2.Object(token=target, socket=socket))
                        
                        total_time = 0

                        for i in range(1,1000):
                            start_time = time.time()
                            for soc in sockets.socket:
                                msg = str(i)
                                with grpc.insecure_channel(soc) as chatChannel:
                                    chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                                    chatStub.send_room(MiniChat_pb2.chatMessage(
                                        message=f"{token}: {msg}"))
                            end_time = time.time()
                            total_time += end_time - start_time
                        
                        total_time /= 1000
                        print(total_time)
                        logging.info(f"-----test ended!-----")

                    
                
                stub.leaveRoom(MiniChat_pb2.Object(token=target, socket=socket))

            # 私聊功能
            if option == '2':
                target = input("Input the user you want to connect:\n")
                sockets = stub.Find(
                    MiniChat_pb2.Object(token=target, socket=socket))
                if not sockets.flag:
                    logging.error(f"No such user.")
                    continue
                else:
                    logging.info(f"Connected to user \'{target}\'")
                
                # 切换聊天记录日志
                Personal_chatfile_name = f"{token}-{target}.log"
                Personal_chatfile_dir = f"ChatFiles/{token}/Personal/{target}"
                os.makedirs(Personal_chatfile_dir, exist_ok=True)
                Personal_chatfile_path = os.path.join(Personal_chatfile_dir, Personal_chatfile_name)
                Personal_file_handler = logging.FileHandler(Personal_chatfile_path)
                Personal_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                logging.getLogger('').removeHandler(file_handler)
                logging.getLogger('').addHandler(Personal_file_handler)

                # 验证并获取聊天记录版本号
                personal_version_file_dir = f"ChatFiles/{token}/Personal/{target}/version.log"
                if os.path.exists(personal_version_file_dir):
                    with open(personal_version_file_dir, 'r+') as version_file:
                        content = version_file.read().strip()
                        if content:
                            version = int(content)
                        else:
                            version = 0
                else:
                    version = 0

                # 群聊背景下
                # 广播寻找拥有最新的聊天记录的用户
                # 然后向该名用户拉取最新的聊天记录副本
                max_version = version
                request_object = socket

                sockets = stub.Find(
                    MiniChat_pb2.Object(token=target, socket=socket))
                    
                for soc in sockets.socket:
                    with grpc.insecure_channel(soc) as chatChannel:
                        chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                        version = chatStub.request_personal_version(MiniChat_pb2.Object(token = token, socket = socket)).version
                        if version > max_version:
                            max_version = version
                            request_object = soc

                with open(personal_version_file_dir,'w+') as version:
                    version.write(f"{max_version}")

                if request_object != socket:
                    with grpc.insecure_channel(request_object) as chatChannel:
                        chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                        with open(Personal_chatfile_path,'w+') as chatfile:
                            chatfile.write(chatStub.apply_for_personal_history(MiniChat_pb2.Object(token = target, socket = socket)).message)

                # 将聊天记录先全部显示一遍，再开始进行聊天
                with open(Personal_chatfile_path,'r') as chatfile:
                    print(chatfile.read())

                while True:
                    message = input(
                        'Input message (\'quit\' to quit): \n')
                    if message == "quit":
                        logging.getLogger('').removeHandler(Personal_file_handler)
                        logging.getLogger('').addHandler(file_handler)
                        logging.info(f"-----Chat disconnect!-----")
                        break

                    if message =='test':
                        logging.info(f"-----test start!-----")
                        sockets = stub.Find(
                            MiniChat_pb2.Object(token=target, socket=socket))
                        
                        total_time = 0

                        for i in range(1,1000):
                            start_time = time.time()
                            msg = str(i)
                            with grpc.insecure_channel(socket) as chatChannel:
                                chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                                chatStub.send_personal(MiniChat_pb2.chatMessage(
                                    message=f"{token}: {msg}"))
                                
                            for soc in sockets.socket:
                                with grpc.insecure_channel(soc) as chatChannel:
                                    chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                                    chatStub.send_personal(MiniChat_pb2.chatMessage(
                                        message=f"{token}: {msg}"))
                                
                            end_time = time.time()
                            total_time += end_time - start_time
                        
                        total_time /= 1000
                        print(total_time)
                        logging.info(f"-----test ended!-----")
                        continue

                    sockets = stub.Find(
                        MiniChat_pb2.Object(token=target, socket=socket))
                    
                    with grpc.insecure_channel(socket) as chatChannel:
                        chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                        chatStub.send_personal(MiniChat_pb2.chatMessage(
                            message=f"{token}: {message}"))
                    
                    for soc in sockets.socket:
                        with grpc.insecure_channel(soc) as chatChannel:
                            chatStub = MiniChat_pb2_grpc.chatStub(chatChannel)
                            chatStub.send_personal(MiniChat_pb2.chatMessage(
                                message=f"{token}: {message}"))
                            
                logging.getLogger('').removeHandler(Personal_file_handler)
                

    except KeyboardInterrupt:
        stub.userLogout(MiniChat_pb2.Object(token=token, socket=socket))
        exit(0)
    except:
        stub.userLogout(MiniChat_pb2.Object(token=token, socket=socket))