import pickle
import socket
import time
import pyaudio
import collections
from multiprocessing import *
from multiprocessing.connection import wait
import array
import audioop

import bisect
## mine
from server import ClientId
from head import Statistics
import lowcfe

"""
an audio sample, sent by client_id, and a bytes objects on length CHUNK*SAMPWITH
"""
Sample = collections.namedtuple("Sample","client_id,play_time,data")

mytime = time.perf_counter
mytime()

# AUDIO DEFINITIONS
SAMPWIDTH = 2 # bytes in a sample
FORMAT = 8 #get_format_from_width(2)
NCHANNELS = 1
FRAMERATE = 8000 # samples per second
CHUNK_DURATION = 0.01
CHUNK = 80


p = pyaudio.PyAudio()
open_out_args={
	"format":FORMAT,
	"channels":NCHANNELS,
	"rate":FRAMERATE,
	"output":True,
	"frames_per_buffer":CHUNK
}
open_out=lambda:p.open(**open_out_args)

open_in_args={
	"format":FORMAT,
	"channels":NCHANNELS,
	"rate":FRAMERATE,
	"input":True,
	"frames_per_buffer":CHUNK
}
open_in=lambda:p.open(**open_in_args)


DRAW_RATE = 1


class Streamer:
	def __init__(self,client_pipe,out_sock,stats): 
		#set argument variables       
		self.client_pipe=client_pipe
		self.stats=stats
		self.sock = out_sock

		#set stream_loop variables
		self.client_id=None        
		self.clients_ids = []
		
		self.stream = open_in()
		self.play_time = 1			

		self.run()

	def handle_rpc(self):
		if not self.client_pipe.poll():
			return
		rpc = self.client_pipe.recv()
		func, *args = rpc
		func=getattr(self,func)
		print("[streamer] rpc {}".format(rpc))
		func(*args)

	def set_client_id(self,client_id):
		self.client_id=client_id

	def set_clients(self,clients_ids):
		self.clients_ids=clients_ids

	def stop(self):
		self.keep_looping=False

	def run(self):
		self.keep_looping=True
		try:
			while self.keep_looping:
				self.handle_rpc()
				self.stream_loop()
		except KeyboardInterrupt:
			pass
		finally:
			print("[streamer] cleaning")
			self.sock.close()
			self.stream.stop_stream()
			print("[streamer] exit")

	def stream_loop(self):
		data = self.stream.read(CHUNK)

		with self.stats.produced.get_lock():
			self.stats.produced.value+=len(data)

		if len(self.clients_ids) == 0:
			return

		if not self.client_id:
			return

		sample = Sample(self.client_id,self.play_time,data)
		self.play_time+=1
		payload=pickle.dumps(sample)
		total_sent = 0
		for ci in self.clients_ids:
			total_sent += self.sock.sendto(payload,ci.player_address)

		with self.stats.sent.get_lock():
			self.stats.sent.value+=total_sent

class Player:
	def __init__(self,client_pipe,sock,stats):
		#set argument variables        
		self.client_pipe=client_pipe
		self.stats=stats
		self.sock = sock	
		self.sock.settimeout(0.0)

		#set receive/play variables
		self.streams = {}
		self.deadline = mytime() + CHUNK_DURATION

		# setup dedicated process to play samples and block while playing...
		samples_in, self.samples_pipe = Pipe()
		self._player = Process(target=stream_play_loop,args=(samples_in,self.stats))
		
		self._player.start()
		# final statement
		self.run()

	def handle_rpc(self):
		if not self.client_pipe.poll():
			return
		rpc = self.client_pipe.recv()
		func, *args = rpc
		func=getattr(self,func)
		print("[player] rpc {}".format(rpc))
		func(*args)

	def set_clients(self,clients_ids):
		keys = list(self.streams.keys())
		for client_id in clients_ids:
			if client_id in keys:				
				keys.remove(client_id)
			else:
				self.streams[client_id]=Stream()

		for k in keys:
			del self.streams[k]

	def stop(self):
		self.keep_looping=False

	def run(self):
		self.keep_looping=True
		try:
			while self.keep_looping:
				self.handle_rpc()
				self.play_loop()			
		except KeyboardInterrupt:
			pass
		finally:
			print("[player] cleaning")			
			self.samples_pipe.send([])
			self._player.join()
			self.sock.close()
			print("[player] exit")


	def play_loop(self):
		
		if not self.streams: # should we discard packets?			
			self.clear_socket()			
			return

		l = 0	
		total_rejected = 0
		#Receive frames while, previous one is playing
		total_received = 0
		while True:
			if mytime() > self.deadline:
				self.deadline += CHUNK_DURATION
				break

			total_rejected+=l				
			try:
				payload, addr = self.sock.recvfrom(2048)
				l = len(payload)
			except socket.timeout:
				continue
			except BlockingIOError:
				continue				

			try:
				sample = pickle.loads(payload)
			except pickle.UnpicklingError:
				continue

			# Filtering phase
			try:
				stream = self.streams[sample.client_id]
			except KeyError:
				continue # discard samples from unknown users

			if sample.play_time < stream.play_time:
				continue # discard old samples

			if sample.play_time in [s.play_time for s in stream.play_list]:
				continue # discard duplicate samples

			stream.insert_sample(sample)        
			total_received += len(payload)
			l = 0

		with self.stats.rejected.get_lock():
			self.stats.rejected.value+=total_rejected

		with self.stats.received.get_lock():
			self.stats.received.value+=total_received

		#produce frame
		lst = [stream.get_play_sample() for stream in self.streams.values()]
		self.samples_pipe.send(lst)

	def clear_socket(self):
		total_rejected=0
		try:
			while True:
				_ = self.sock.recvfrom(2048)
				total_rejected+=len(_[1])
		except socket.timeout:
			pass
		except BlockingIOError:
			pass
		with self.stats.rejected.get_lock():
			self.stats.rejected.value+=total_rejected


def stream_play_loop(samples_in,stats):
	#stream from pyaudio
	stream = open_out()
	try:
		while True:					
			#lst = samples_in.get()		
			lst = samples_in.recv()	
			if not lst:
				break
			out = lst[0]
			lst = lst[1:]
			
			for d in lst:
				out = audioop.add(out,d,SAMPWIDTH)			
			stream.write(out)
			with stats.played.get_lock():
				stats.played.value += len(out)	
	except KeyboardInterrupt:
		pass			
	finally:
		stream.close()

class Stream:
	def __init__(self):
		self.play_time=-1
		#list of samples
		self.play_list=[]		
		#low complexity frame erasure concealment
		self.fec = lowcfe.LowcFE()

	def insert_sample(self,sample):
			#insert the sample in the stream playlist in order
			keys = [x.play_time for x in self.play_list]
			bl = bisect.bisect_left(keys,sample.play_time)
			self.play_list.insert(bl,sample)

	def get_play_sample(self):
		data = None
		if self.play_list:			
			sample = self.play_list.pop(0)			
			data = self.fec.add_to_history(sample.data)
			self.play_time = sample.play_time
		else:
			# erasure
			data = self.fec.dofe()
			#data = b'\x00'*2*CHUNK
		return data

	def __repr__(self):
		return "<voip.Stream play_time={} len(play_list)={}>"\
				.format(self.play_time,len(self.play_list))



if __name__=="__main__":
	print("VOIP TEST:")
	# PRINT CONSTANTS
	d = locals().copy()
	for k,v in d.items():
		if not k.startswith("_") and k.isupper():
			print("{} = {}".format(k,v))
	choice = input("streamer(s) or player(p) or benchmark(b)?")	
	if choice == "s":
		sci = ClientId(0,"test_streamer",None)
		left,right = Pipe()
		left.send(["set_client_id",sci])
		ip,port = input("player: ip port\n").split()
		paddr = (ip,int(port))
		pci = ClientId(1,"test_player",paddr)
		left.send(["set_clients",[pci]])
		print("Streaming mic to {} ...".format(paddr))		
		Streamer(right,None)
	elif choice == "p" or choice == "b":
		import socket		
		aux = socket.gethostbyname_ex(socket.gethostname())
		ip_lst = aux[2]
		if choice == "p":
			index, port = input("Choose an ip by index, and a port: index port\n{}".format(aux)).split()
			paddr = (ip_lst[int(index)],int(port))
		else:
			paddr = ("127.0.0.1",0)		
		sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
		sock.bind(paddr)
		left,right = Pipe()
		sci = ClientId(0,"test_streamer",None)
		left.send(["set_clients",[sci]])
		print("Playing from {} ...".format(paddr))
		Player(right,sock,None)
