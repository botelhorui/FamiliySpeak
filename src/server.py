from multiprocessing import Process, Pipe, Event
from multiprocessing.connection import wait
import time
import socket
import collections
import sys
# my stuff
from my_connection import Listener, AuthenticationError, AuthenticationTimeout
import upnp


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
	def accept_poll(cls,left_conn,event,address):
		try:
			with Listener(address, authkey=b'mimi') as listener: 
				print("[listener] accepting on ", address) 
				while True:
					try:
						if event.is_set():
							return
						conn = listener.accept()
						left_conn.send(conn)
					except socket.timeout:
						continue
					except AuthenticationTimeout:
						print(sys.exc_info()[0])
						continue                    
					except AuthenticationError:                    
						print( sys.exc_info()[0])
						continue
		except KeyboardInterrupt:
			print("[listener] Caught KeyboardInterrupt, terminating")
			event.set()


	def __init__(self,address):
		left_conn, right_conn = Pipe()
		event = Event()
		listener_proc = Process(target=Server.accept_poll,args=(left_conn,event,address),name='Listener')
		listener_proc.start()
		self._last_id=0

		#last statement:
		try: 
			self.process_poll(right_conn)
		except KeyboardInterrupt:
			print("[server] Caught KeyboardInterrupt, terminating")
			event.set()

			

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



if __name__=="__main__":
	aux = socket.gethostbyname_ex(socket.gethostname())
	ip_lst=aux[2]
	while True:
		s = input("Choose an ip by index, and a port:\n{}\nindex port\n".format(ip_lst))
		if(s==""):
			continue
		try:
			spl = s.split()
			index = int(spl[0])
			port = int(spl[1])
			break
		except ValueError:
			pass
		except IndexError:
			pass

	local_ip = ip_lst[index]
	print("Using local_ip:{} port:{}".format(local_ip,port))
	found_router = False
	try:				
		external_ip = upnp.get_external_ip(local_ip)
		found_router = True
		print("[Server] got external_ip: ",external_ip)
	except upnp.MyException:
		external_ip = local_ip
		found_router = False
		print("[Server] not behind router")

	if found_router:
		PORT_RANGE_MIN = port
		PORT_RANGE_MAX = 52001		
		for port in range(PORT_RANGE_MIN,PORT_RANGE_MAX):
			print("Trying to open port {} (TCP)".format(port))
			try:			
				print("Router doesnt have the port open")						
				upnp.open_port(port,"TCP")
				break #no exception means we are safe																
			except upnp.MyException as e:
				print("Failed opening upnp port {} :".format(port))
				print(e)
			time.sleep(0.5)			

		if port == PORT_RANGE_MAX-1:
			raise RuntimeError('No port available')

	addr = (local_ip,port)
	print("Creating server using:")
	print("external ip:{}:{}".format(external_ip,port))
	print("local ip   :{}:{}".format(local_ip,port))
	try:
		Server(addr)
	finally:
		try:
			upnp.DeletePortMapping(port,"TCP")
		except MyException:
			pass