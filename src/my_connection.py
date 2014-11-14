# code based on multiprocessing.connection
import socket
import struct
import io
import pickle
import os

class AuthenticationError(Exception):
	def __init__(self,value=""):
		self.value=value

	def __str__(self):
		return repr(self.value)

class AuthenticationTimeout(socket.timeout):
	def __init__(self,value=""):
		self.value=value

	def __str__(self):
		return repr(self.value)

class Connection:
	def __init__(self, sock):
		self.sock = sock		
	
	def send(self,obj):
		self.send_bytes(pickle.dumps(obj))

	def recv(self):
		buf = self.recv_bytes()
		return pickle.loads(buf)

	def recv_bytes(self, maxsize=None):
		data = self.sock.recv(4)
		if len(data) == 0:
			raise EOFError
		size, = struct.unpack("!i",data)
		if maxsize is not None and size > maxsize:
			return None
		buf = io.BytesIO()
		remaining = size
		while remaining > 0:
			chunk = self.sock.recv(remaining)
			n = len(chunk)
			if n == 0:
				if remaining == size:
					raise EOFError
				else:
					raise OSError("got end of file during message")
			buf.write(chunk)
			remaining -= n
		return buf.getvalue()

	def send_bytes(self,buf):
		n = len(buf)
		header = struct.pack("!i",n)
		buf = header + buf
		remaining = len(buf)
		while True:
			n = self.sock.send(buf)
			remaining -= n
			if remaining == 0:
				break
			buf = buf[n:]		

	def close(self):
		self.sock.close()

	def __exit__(self, type, value, tb):
		self.close()

	def fileno(self):
		return self.sock.fileno()


class Listener:
	def __init__(self,address,authkey):
		""" assume adress is valid (ip,port) 
			and authkey is a bytes object"""
		self.sock = socket.socket()
		self.sock.bind(address)
		self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.sock.listen(5)
		self.authkey = authkey

	def accept(self):
		sock,addr = self.sock.accept()
		sock.settimeout(1)
		conn = Connection(sock)
		try:
			deliver_challenge(conn,self.authkey)
			answer_challenge(conn,self.authkey)
			conn.sock.settimeout(None)
			return conn
		except socket.timeout:
			raise AuthenticationTimeout()

	def close(self):
		self.sock.close()

	def fileno(self):
		return self.sock.fileno()

	def __exit__(self, type, value, tb):
		self.close()

	def __enter__(self):
		return self

def Client(address, authkey):
	s = socket.socket()
	s.connect(address)
	conn = Connection(s)
	answer_challenge(conn,authkey)
	deliver_challenge(conn,authkey)
	return conn
		

#
# Authentication stuff
#

MESSAGE_LENGTH = 20

CHALLENGE = b'#CHALLENGE#'
WELCOME = b'#WELCOME#'
FAILURE = b'#FAILURE#'

def deliver_challenge(conn, authkey):
	import hmac
	assert isinstance(authkey,bytes)
	message = os.urandom(MESSAGE_LENGTH)
	conn.send_bytes(CHALLENGE+message)
	digest = hmac.new(authkey, message, 'md5').digest()
	response = conn.recv_bytes(256)
	if response == digest:
		conn.send_bytes(WELCOME)
	else:
		conn.send_bytes(FAILURE)
		raise AuthenticationError()


def answer_challenge(conn, authkey):
    import hmac
    assert isinstance(authkey, bytes)
    message = conn.recv_bytes(256)         # reject large message
    assert message[:len(CHALLENGE)] == CHALLENGE, 'message = %r' % message
    message = message[len(CHALLENGE):]
    digest = hmac.new(authkey, message, 'md5').digest()
    conn.send_bytes(digest)
    response = conn.recv_bytes(256)        # reject large message
    if response != WELCOME:
    	raise AuthenticationError()


