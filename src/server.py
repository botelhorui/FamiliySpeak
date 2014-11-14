from multiprocessing import Process, Pipe
from multiprocessing.connection import wait
import time
import socket
import collections
# my stuff
from my_connection import Listener


ClientId = collections.namedtuple("ClientId","id,nickname,player_address")

def clientid_from_client(client):   
    ci = ClientId(client.id,client.nickname,client.player_address)
    return ci

class Client:
    def __init__(self,conn,id):
        self.conn=conn
        self.id=id
        self.nickname=None
        self.player_address=None

    def fileno(self):
        return self.conn.fileno()

    def __repr__(self):
        return "<server.Client id={} nickname={} player_address={}>".format(self.id,self.nickname,self.player_address)

class Server:
    @classmethod
    def accept_poll(cls,left_conn,address):
        if address == None:
            address = (socket.gethostbyname(socket.gethostname()), 42000)

        with Listener(address, authkey=b'mimi') as listener:    
            print("[listener]accepting on ",address)
            while True:
                conn = listener.accept()
                left_conn.send(conn)

    def __init__(self,address):
        left_conn, right_conn = Pipe()
        Process(target=Server.accept_poll,args=(left_conn,address)).start()
        self._last_id=0

        #last statement:
        self.process_poll(right_conn)


    def create_id(self):
        i = self._last_id
        self._last_id += 1
        return i

    def process_poll(self,right_conn):
        clients_connected = self.clients_connected = []
        clients_logged = self.clients_logged = []
        while True:
            wait_lst = clients_connected + clients_logged + [right_conn]
            for c in wait(wait_lst):
                if c is right_conn:
                    conn = c.recv()
                    client = Client(conn,self.create_id())
                    clients_connected.append(client)
                    print("new client:",clients_connected[-1])
                    #broadcast change
                elif c in clients_connected:
                    try:
                        msg = c.conn.recv()
                    except (EOFError,ConnectionResetError):                        
                        clients_connected.remove(c)
                        print("[disconnected]",c)
                    else:
                        self.handle_rpc(c,msg)                  
                else:
                    try:
                        msg = c.conn.recv()
                    except (EOFError,ConnectionResetError):
                        self.logout(c)
                    else:
                        self.handle_rpc(c,msg)

    def handle_rpc(self,client,rpc):
        print("rpc:",client,rpc)
        func, *args = rpc
        func=getattr(self,func)
        args = [client] + args
        func(*args)

    def login(self,client,nickname,player_address):        
        client.nickname = nickname
        client.player_address=player_address

        self.clients_logged.append(client)
        self.clients_connected.remove(client)

        client_id = clientid_from_client(client)
        client.conn.send(client_id)
        self.update_clients()

    def logout(self,client):
        print("[disconnected]",client)
        self.clients_logged.remove(client)
        self.update_clients()   

    def update_clients(self):
        clients_ids = [clientid_from_client(c) for c in self.clients_logged]
        action = ["set_clients",clients_ids]
        for c in self.clients_logged:
            c.conn.send(action)

    def show_message(self,client,txt):
        action = ["show_message",client.nickname,txt]
        for c in self.clients_logged:
            if c is not client:
                c.conn.send(action)





if __name__ == "__main__":    
	aux = socket.gethostbyname_ex(socket.gethostname())
	ip_lst = aux[2]
	index, port = input("Choose an ip by index, and a port: index port\n{}".format(aux)).split()
	addr = (ip_lst[int(index)],int(port))
	print("Creating server using {} ...".format(addr))
	Server(addr)
