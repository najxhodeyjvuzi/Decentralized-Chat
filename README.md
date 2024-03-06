# Decentralized-Chat
#### 分布式系统项目——去中心化的聊天系统

#### 概述

​	本次的去中心化聊天系统基于`python`和`grpc`进行搭建，虽然还有很多可以继续完善的功能，但是也基本实现了题目中包括一对一聊天，创建聊天房等功能，同时在一定程度上能够满足系统一致性的要求。

#### 环境

- unbutu 22.04.03 LTS
- python 3.10.12
- grpcio 1.59.2
- protobuf 4.25.0



#### 实现过程

系统的组织结构如下：

```shell
.
├── Client.py
├── MiniChat_pb2_grpc.py
├── MiniChat_pb2.py
├── MiniChat.proto
└── Server.py
```

首先定义定义通信接口，实现如下的`MiniChat.proto`文件并进行编译：

```protobuf
syntax = "proto3";

message Object {
    string token = 1;
    string socket = 2;
}

message Reply {
    bool flag = 1;
    repeated string socket = 2;
}

service Routing {
    rpc Find(Object) returns (Reply) {}
    rpc userLogin(Object) returns (Reply) {}
    rpc userLogout(Object) returns (Reply) {}
    rpc joinRoom(Object) returns (Reply) {}
    rpc leaveRoom(Object) returns (Reply) {}
}

message chatMessage {
    string message = 1;
}

message versionMessage {
    int32 version = 1;
}

service chat {
    rpc send_room(chatMessage) returns (Reply) {}
    rpc apply_for_room_history(Object) returns (chatMessage) {}
    rpc request_room_version(Object) returns (versionMessage) {}

    rpc send_personal(chatMessage) returns (Reply) {}
    rpc apply_for_personal_history(Object) returns (chatMessage) {}
    rpc request_personal_version(Object) returns (versionMessage) {}
}

```

对于上述的定义，有如下的解释：

- 消息类型：定义了`Object`，包含两个字段，`taken`记录用户或聊天房名称（身份），`socket`记录通信端口；定义了`chatMessage`，包含一个字段，即通信的内容。

- 服务接口：定义了`Reply`，包含两个字段，`flag`用于标志是否成功得到回复（在聊天系统中即找到需连接到的用户或聊天房），`socket`用于获取对象的通信端口。

- `Find`用于寻找对象；`userLogin`/`userLogout`实现用户登入/登出系统；`joinRoom`/`leaveRoom`实现用户进入/离开聊天房。

- `versionMessage`用于进行不同用户间的聊天记录版本信息交换，用于实现分布式系统一致性。

- `chat`类即进程交换信息的主要过程，包括群聊的信息交换选项，还有私聊的信息交换选项：`apply_history`用于用户向拥有更新的聊天记录的用户请求聊天记录，`request_version`则是请求版本号。每个用户登陆后，会向同属一个频道的所有对等方请求各自的消息记录版本，并选取最新的（将自己考虑在内）聊天记录进行同步。

  

将上面的`.proto`文件进行编译。

```shell
$ python3 -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. MiniChat.proto
```

可以得到`MiniChat_pb2.py`及`MiniChat_pb2_grpc.py`。基于这两份文件，我们进一步完成系统的实现。



然后我通过`Server.py`创建一个聊天系统的服务器：

```python
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

```

- 定义了`Routing`类，即对`.proto`文件中的`Routing`服务接口的实际实现，通过`.add_RoutingService_to_server`进行链接：成员`self.object`记录当前存在于系统中的对象，以及对象连接的所有通信端口。

```python
if __name__ == "__main__":
    # ……

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    MiniChat_pb2_grpc.add_RoutingServicer_to_server(Routing(), server)
    server.add_insecure_port("localhost:10001")
    server.start()

    try:
        while True:
            pass
    except KeyboardInterrupt:
        server.stop(0)
```

- `main`函数：将服务器运行在`localhost:10001`上，实现了用户登陆登出和聊天房创建等信息的显示，并将用户使用记录到本地。注意，聊天记录并不存放在服务器本地中。也就是说，服务器进程仅仅只起到**管理用户状态**的作用，实际上就相当于一个**用户代理**，用于**帮助各用户找到对方**，然后交由他们**各自进行通信**。



最后，我使用`Client.py`用于构建客户端，并完成了对`.proto`中`chat`服务的定义。

```python
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
```

在本地端口中的$[30000,40000]$中随机选取一个端口作为当前客户端运行和通信的端口，并与服务器通信，获取服务接口`stub`，用于实现功能，如上面的用户登陆功能。

```python
    port = random.randint(30000, 40000)
    socket = f"localhost:{port}"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    MiniChat_pb2_grpc.add_chatServicer_to_server(chat(), server)
    server.add_insecure_port(socket)
    server.start()
    # ……
    token = input("Input your nickname: ")
    channel = grpc.insecure_channel("localhost:10001")
    stub = MiniChat_pb2_grpc.RoutingStub(channel)
    
    stub.userLogin(
    	MiniChat_pb2.Object(
    		token=token, socket=socket))
```

然后，创建循环，用于实现用户功能。以聊天房功能为例，如下实现：

```python
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

        #--------------------------------------------------------------------------------------
        # 聊天记录一致性
        # 从同频道（若是私人聊天，则从对方和自己/若是聊天房，则从参与房间的所有对等方，以及自己本地）
        # 拉取可能会有不同版本的聊天记录 
        # 选取最新的聊天记录，并更新本地的聊天记录                                                           
        # 将聊天记录回显到终端窗口上
        #--------------------------------------------------------------------------------------
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
            # ……
            # 不是系统的主要组成部分，所以省略
            
        stub.leaveRoom(MiniChat_pb2.Object(token=target, socket=socket))
```

通过上面的实现，用户能够：

- 主观决定使用私人聊天或聊天房聊天。
- 加入（没有时创建）聊天房。
- 发送信息。
- 退出当前聊天，并进行下一次聊天。

个人对个人聊天实现类似，这里不再展示，建议之间参见源代码`Client.py`。同时，虽然每个实例都运行在本地上，但是每个用户的聊天记录都存放之余自己相关的目录下，可以近似看作客户端本地存放聊天记录。



#### 结果展示

1. ##### 支持一对一聊天 / 支持聊天房群聊

   可以分别创建一个`Server.py`实例，以及多个`Client.py`实例。

   我们登入用户a和b，用于测试一对一聊天联系。

   ```shell
   2024-01-13 22:13:41,554 - INFO - Server started, listening on port 39070.
   2024-01-13 22:13:41,554 - INFO - CTRL+C to exit.
   Input your nickname: a
   CHAT ROOM or PRIVATE CONNECTION with only 2 users [1/2]: 
   2
   Input the user you want to connect:
   b
   ```

   ![image-20240113221808704](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113221808704.png)

   可以看到，在一对一聊天中，a和b能够互相看到对方发送的信息，并且聊天记录也被保存在本地的目录中。关于本地聊天记录，在下面的分布式系统一致性部分中会做出更加详细的解释。

   然后登陆用户c，d，e用于测试聊天房群聊

   ```shell
   2024-01-13 22:19:26,079 - INFO - Server started, listening on port 35123.
   2024-01-13 22:19:26,079 - INFO - CTRL+C to exit.
   Input your nickname: e
   CHAT ROOM or PRIVATE CONNECTION with only 2 users [1/2]: 
   1
   Input the room name you want to enter:
   testroom
   2024-01-13 22:19:42,451 - INFO - Joined in 'testroom'.
   ```

   

   而在聊天房聊天中，另外两个人也能够看到某个人发送的信息，同样有本地聊天记录生成。

   ![image-20240113222157572](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113222157572.png)

   

   

2. ##### 能够满足实时性要求，如相应时间控制在10ms以内

   具体可见最后的性能测试，可以认为基本满足实时性。

   

3. ##### 通信方式采用RPC

   通信基于RPC进行。

   

4. ##### 支持分布式系统一致性

   在本次的项目中，使用了近似单调写来实现一致性。

   上面提到了各用户维护的本地聊天记录，他们的组织形式近似如下：

   ```shell
   ├── ChatFiles
   │   ├── a
   │   │   ├── a.log
   │   │   ├── ChatRoom
   │   │   │   └── testroom2
   │   │   │       ├── a-testroom2.log
   │   │   │       └── version.log
   │   │   └── Personal
   │   │       └── b
   │   │           ├── a-b.log
   │   │           └── version.log
   │   ├── b
   │   │   ├── b.log
   │   │   ├── ChatRoom
   │   │   │   └── testroom
   │   │   │       ├── b-testroom.log
   │   │   │       └── version.log
   │   │   └── Personal
   │   │       └── a
   │   │           ├── b-a.log
   │   │           └── version.log
   │   ├── c
   │   │   ├── ChatRoom
   │   │   │   └── testroom
   │   │   │       ├── c-testroom.log
   │   │   │       └── version.log
   │   │   └── c.log
   │   ├── d
   │   │   ├── ChatRoom
   │   │   │   └── testroom
   │   │   │       ├── d-testroom.log
   │   │   │       └── version.log
   │   │   └── d.log
   │   └── e
   │       ├── ChatRoom
   │       │   └── testroom
   │       │       ├── e-testroom.log
   │       │       └── version.log
   │       └── e.log
   ```

   可以看到，每个用户对应一个最上层目录，然后每个用户会维护一个`/Chatroom`和`/Personal`子目录，用于分别存放群聊记录和私聊记录。

   然后，在这两个子母录之下，又有各个以聊天对象为名创建的子目录。如对a用户来说，他有`/Chatroom/testroom2/a-testroom2.log`，说明他曾经加入过群聊`testroom2`，所以才生成了这一个聊天记录。同时，他私人和`b`有过会话，所以生成了`Personal/b/a-b.log`。

   另一个值得一提的就是`version.log`，因为这是我们实现一致性的关键。

   他的内容仅仅只是一个整数，如下，是`version.log`和`a-b.log`的对应关系：

   ![image-20240113223021674](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113223021674.png)

   不难看到，实际上`version.log`记录的就是聊天记录中的条数。

   当a或b两个人其中一人发送一条信息后，这个`version`都会增加1，聊天记录文件也会更新。

   上面的实现模块也有提到，为了保持各个用户聊天记录的一致，我们会在每个用户登陆的时候广播一个请求版本号的消息，并拉取一个最新的消息记录，在这个基础上进行消息的更新。

   由此，我们实现了一个比较简单的一致性。

   

5. ##### 具备一定的失效容错措施

   失效容错也可以利用上面所说到的聊天记录版本号来实现。

   存在几种失效的情形：

   1. 在私聊中，若连接未建立，但是其中一方已经开始发送信息时：

      系统会将发送信息的一方的消息缓存在本地，这样，当另一方上线后，就会自动拉取最新的记录，实现消息的同步。

      ![image-20240113223945417](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113223945417.png)

      如上图，b已经登陆，所以a能够连接到b，但是连接是单向的，b还没有建立与a的连接，所以他不能够收到来自a的信息。

      然后，我们令b与a进行连接。

      ![image-20240113224136169](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113224136169.png)

      这时可以看到，b离线时接收到的信息，已经通过信息拉取并显示在了屏幕上。消息版本也实现了同步

      ![image-20240113224327480](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113224327480.png)

      

   2. 在群聊中，可能会存在多个用户掉线的情况。但是，我们只要保证有一个用户仍然在线，那么肯定能实现各用户消息的回显和同步。

      考虑如下的情况：a，b，c三人创建了一个三人群聊房，他们已经进行了一段时间的对话。

      ![image-20240113225000405](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113225000405.png)

      但是某一时刻，b断线离开了聊天房，而c更是发生了`fail-stop`故障，本地的消息记录缓存也全部丢失（在这里是人为删除整个用户c的聊天记录，并将版本文件删除）。

      而在此期间，用户a依然在发言，但是b，c此时必然收不到，a所发送的消息只有他自己能够看到

      ![image-20240113225725913](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113225725913.png)

      但是，当b和c再次连接进入聊天房时，记录都会被同步。

      ![image-20240113225808114](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113225808114.png)

      可以知道我们的容错机制基本有效。

      

   3. 其实还有一阵容错机制待拓展，只是由于时间关系没能够在此次项目中实现，那就是聊天的重做和撤销。

      系统中，在维护用户各自的本地聊天记录时，我们还为各用户维护了一个系统状态日志，以及服务器的状态日志。

      ![image-20240113230202314](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113230202314.png)

      其实，我们可以扩展系统，将其用于检查点的设置，以及状态的回滚。

   

6. ##### 聊天数据分散存储

   参照上面的内容，可近似系统聊天记录在客户端本地进行存储，实际应该也是以这种思路进行实现。

   

#### 性能测试：

为了测试聊天系统通信的实时性能，下面做了几组测试：

1. 测试在3人群聊中，发送1000条信息的平均响应时间

   在群聊功能实现的代码段中，采用以下代码进行简单的消息发送和测试（用户测试也是类似的代码段，因此下面不再展示）：

   ```python
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
   ```

   可以看到，计算得到的平均时间约为0.00688s，即约6毫秒，响应时间小于10毫秒。

   ![image-20240113212033402](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113212033402.png)

   

2. 尝试在20人的群组中，发送1000条信息

   可以看到，当用户数增多的时候，一个用户发送的信息要保证到达多个用户时，所需要的时间就会变长。

   这是显然的，因为每轮发送的信息也是以数倍计算的。

   ![image-20240113213043305](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113213043305.png)

3. 尝试在单对单的聊天中，发送1000条信息

   平均响应时间是4毫秒。

   ![image-20240113214910769](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113214910769.png)

4. 尝试在单对单的聊天中，互相发送1000条信息

   可以看到平均的响应时间为6毫秒左右。

   ![image-20240113215159529](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113215159529.png)

   

5. 尝试在三个用户的群聊中，选取两个用户同时测试发送1000条信息：

   可以看到，响应时间也是有一定的降低，刚好在10毫秒左右。

   ![image-20240113213737391](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113213737391.png)

   另一个值得注意的实验结果是，可以看到下图所展示的消息记录次序，是严格一致的。

   这也可以说明在本次实验中采取的一致性操作是有起到作用的，才能维护各用户的消息记录一致。

   ![image-20240113214142560](C:\Users\13030\AppData\Roaming\Typora\typora-user-images\image-20240113214142560.png)

   

