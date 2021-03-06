#python modules
from multiprocessing.connection import wait
from multiprocessing import Process, Pipe, Manager, Value
import re
import traceback
import socket
import time
import logging
import datetime

#my modules
from my_connection import Client
import gui
import upnp
import voip
from server import ClientId
from head import Statistics
from logging_setup import logging_setup

logging_setup()



def string_to_ip(s):
	m = re.search("(.+?):(\d+)",s)
	return (m.group(1),int(m.group(2)))

class MyClient:
	def __init__(self):
		self.procs =[]			
		self.connections = []		
		self.keep_looping = True
		self.closed=False

		#setup statistics variables
		self.stats = Statistics(
			sent=Value("i",0),
			received=Value("i",0),
			produced=Value("i",0),
			played=Value("i",0),
			rejected=Value("i",0)
			)
		#create gui process
		self.gui_pipe, gui_end = Pipe()
		p = Process(target=gui.MyAppWindow,name="GUI-Process",args=(gui_end,self.stats))
		p.start()
		self.procs.append(p)
		self.connections.append(self.gui_pipe)

		self.streamer_pipe=None
		self.player_pipe=None

		self.player_port=None



		# LAST STATEMENTTTTTTTTTTTTTTT

		self.run()

	def setup_voip(self):
		local_ip = self.localip
		found_router = False
		try:				
			external_ip = upnp.get_external_ip(self.localip)
			found_router = True
			logging.debug("[client] got external_ip: "+external_ip)
		except upnp.MyException:
			external_ip = local_ip
			found_router = False
			logging.debug("[client] not behind router")

		sock = None
		port = 0
		PORT_RANGE_MIN = 42001
		PORT_RANGE_MAX = 42101		
		for port in range(PORT_RANGE_MIN,PORT_RANGE_MAX):
			logging.debug("Trying to create player using port {}".format(port))
			try:
				#try to obtain the port port
				sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
				local_address = (local_ip,port)
				sock.bind(local_address)
				if found_router:
					try:										
						upnp.open_port(port,"UDP")
						logging.debug("Door opened!!!")
						break #no exception means we are safe						
					except upnp.MyException as e:
						logging.debug("Failed opening upnp port {} :".format(port))
						logging.debug(e)
					sock.close()
					sock = None
				else:
					break
				time.sleep(0.5)
			except OSError as e:
				logging.debug("Failed opening socket port")
				logging.debug(e)				
				if sock:
					sock.close()			

		if port == PORT_RANGE_MAX-1:
			raise RuntimeError('No port available')
		self.player_port=port
		logging.debug("created player on local_ip: {} external_ip: {} port: {} in UDP".format(local_ip,external_ip,port))

		self.player_address = (external_ip,port)
		#create player process
		self.player_pipe,player_end=Pipe()
		p=Process(target=voip.Player,name="Player-Process",args=(player_end,sock,self.stats))
		p.start()
		self.procs.append(p)


		out_sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
		out_sock.bind((local_ip,0))
		logging.debug("created streamer on local_ip: {} external_ip: {} port: {} in UDP".format(local_ip,external_ip,out_sock.getsockname()[1]))
		#create streamer process
		self.streamer_pipe,streamer_end=Pipe()
		p = Process(target=voip.Streamer,name="Streamer-Process",args=(streamer_end,out_sock,self.stats))
		p.start()
		self.procs.append(p)


	def handle_rpc(self,c,rpc):
		logging.debug("[client]({})rpc {}".format(c,rpc))
		func, *args = rpc
		func=getattr(self,func)
		func(*args)

	def run(self):
		try:
			while self.keep_looping:
				for conn in wait(self.connections):
					try:
						msg = conn.recv()
					except EOFError:
						self.connections.remove(conn)
					except ConnectionResetError:
						pass
					else:
						if conn is self.gui_pipe:
							c="GUI"
						elif conn is self.server_conn:
							c="Server"
						else:
							c=conn
						self.handle_rpc(c,msg)


						if not self.keep_looping:
							break
				#if not all([p.is_alive() for p in self.procs]):
				#	self.keep_looping=False
		finally:
			self.close()


	#called by gui
	def login(self,server,nickname,localip):
		try:
			server = string_to_ip(server)
			self.localip = localip
			self.setup_voip()
			self.server_conn = Client(server,authkey=b"mimi")
			action = ["login",nickname,self.player_address]
			self.server_conn.send(action)
			self.client_id = self.server_conn.recv()
			if self.client_id != None:
				self.connections.append(self.server_conn)
				self.streamer_pipe.send(["set_client_id",self.client_id])
				self.gui_pipe.send(["connecting_successfull"])
			else:
				self.gui_pipe.send(["connecting_failed"])
		except Exception as e:
			#todo send error to gui
			logging.debug(traceback.format_exc())
			action = ["connecting_failed"]
			self.gui_pipe.send(action)		
		
	#called by server
	def set_clients(self,clients_ids):
		nicks = [ci.nickname for ci in clients_ids]
		txt = "\n".join(nicks)
		action = ["set_clients",txt]
		self.gui_pipe.send(action)	
		lst = [ci for ci in clients_ids if ci != self.client_id and ci.player_address != None]
		action = ["set_clients",lst]
		self.streamer_pipe.send(action)
		self.player_pipe.send(action)

	#called by server
	def show_message(self,client,txt):
		msg = "{}:{}".format(client,txt)
		action = ["show_message",msg]
		self.gui_pipe.send(action)

	#called by gui
	def send_message(self,txt):
		self.show_message(self.client_id.nickname,txt)
		msg = "{}:{}".format(self.client_id.nickname,txt)
		action = ["show_message",txt]
		self.server_conn.send(action)

	#called by gui
	def close(self):
		self.keep_looping = False
		if self.closed:
			return
		logging.debug("[client] closing")
		self.closed=True
		action = ["stop"]
		try:
			if self.streamer_pipe:
				self.streamer_pipe.send(action)
		finally:
			try:
				if self.player_pipe:
					self.player_pipe.send(action)
			finally:
				if self.gui_pipe:
					self.gui_pipe.send(action)
		
		for p in self.procs:
			p.join() #TODO BLOCKS:..
		for c in self.connections:
			c.close()
		logging.debug("[client] finished closing")
		# clear streamer and player processes




if __name__ == "__main__":
	MyClient()
