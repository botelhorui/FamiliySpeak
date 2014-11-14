import re
import socket
import urllib.request
import logging
from time import time,clock
import os

#logging.basicConfig(level=logging.DEBUG,format="[%(levelname)s]%(message)s")

# function...

if os.name == "nt":
	time = clock

#meme reference
what_time_is_it=time()

milli_time = lambda: time()*1000

def default_ip():
	return socket.gethostbyname(socket.gethostname())

def stopwatch():
	s = milli_time()
	return lambda: "{:.2f}".format(milli_time()-s)

upnp_broadcast_address = ("239.255.255.250",1900)

class NoUpnpDeviceFoundError(Exception):
	def __init__(self,value=""):
		self.value=value

	def __str__(self):
		return repr(self.value)

class IgdXmlError(Exception):
	def __init__(self,value=""):
		self.value=value

	def __str__(self):
		return repr(self.value)

class SoapActionException(Exception):
	pass

class SoapActionTimeOut(SoapActionException):
	def __init__(self,value):
		self.value=value

	def __str__(self):
		return repr(self.value)

class SoapActionError(SoapActionException):
	def __init__(self,value="",error_code="000",error_description="Unspecified"):
		self.value=""
		self.error_code=error_code
		self.error_description=error_description

	def __str__(self):
		if self.value == "":
			txt = "error_code:{} error_description:{}".format(self.error_code,self.error_description)
			return txt
		return repr(self.value)

def get_html_content(payload):
	"""Example
	"""
	#POST /tkds39boc1z/IGD/upnp/control/igd/wanipc_2_1_1 HTTP/1.0
	#Host: 192.168.1.254:8000
	#Content-Type: text/xml; charset="utf-8"
	#Content-Length: 622
	#Soapaction: "urn:schemas-upnp-org:service:WANIPConnection:1#AddPortMapping"\r\n
	#\r\n	
	pattern = b"Content-Length:\s*(\d+)"
	match = re.search(pattern,payload,flags=re.IGNORECASE)
	length =  int(match.group(1))
	return payload[-length:]


def check_action_error(payload):
	#HTTP/1.0 200 OK
	#Connection: close
	#Server: Thomson TG 784n 10.2.2.8 UPnP/1.0 (58-98-35-56-36-3A)
	#Content-Length: 305
	#Content-Type: text/xml; charset="utf-8"
	#EXT:
	pattern = b"HTTP.*?(\d\d\d)\s(\S)+"
	match = re.search(pattern,payload,flags=re.IGNORECASE)
	html_code = int(match.group(1))
	html_txt = match.group(2)
	if html_code == 200:
		return
	#check if the payload encoding is uft-8
	pattern = b"Content-Type:\s*text/xml;\s*charset=\s*\"utf-8\""
	if not re.search(pattern,payload,flags=re.IGNORECASE):
		raise SoapActionError("html header content-type is not valid")
	pattern = b"Content-Length:\s*(\d+)"
	match = re.search(pattern,payload,flags=re.IGNORECASE)
	length =  int(match.group(1))
	xml = payload[-length:].decode()
	pattern = "<errorCode[^>]*?>\s*?(\d+)\s*?</errorCode>"
	match = re.search(pattern,xml,flags=re.IGNORECASE)
	if not match:
		raise SoapActionError("Error getting SOAP error code")
	error_code = match.group(1)
	pattern = "<errorDescription[^>]*?>([\s\S]*?)</errorDescription>"
	match = re.search(pattern,xml,flags=re.IGNORECASE)
	error_description = ""
	if match:
		error_description = match.group(1)		
	raise SoapActionError(error_code = error_code,error_description=error_description)


def print_query_response(query,response):
	if type(query) == bytes:
		query = query.decode()

	if type(response) == bytes:
		response = response.decode()
	logging.debug("\nQUERY: \n" + query + "\nRESPONSE: \n" + response)


def send_rcv_udp_packet(msg,max_tries = 8,max_time_waited=250, ip=default_ip()):
	with socket.socket(type=socket.SOCK_DGRAM) as s:
		s.bind((ip,0))
		logging.debug("sending udp from: {}".format(s.getsockname()))		
		data = msg.encode()
		total_time_waited=0
		for t in range(max_tries):
			logging.debug("Send/Receive try ({}/{})".format(t+1,max_tries))	
			s.sendto(data,upnp_broadcast_address)			
			sw = stopwatch()		
			logging.debug("sent {} bytes to {}".format(len(data),upnp_broadcast_address))
			timeout=5		
			time_waited=0
			one_second=1000
			while True:
				s.settimeout(timeout/one_second)
				try:			
					packet = s.recvfrom(4096)
					if packet[0] != b'':					
						nb = len(packet[0])
						ra = packet[1]
						logging.debug("received udp packet: bytes:{} from:{} after {}ms".format(nb,ra,sw()))		
						yield packet
					else:
						logging.debug("received a packet with 0 bytes! omg omg :O")								
				except socket.timeout:
					logging.debug("recv timeout at {}ms sw:{}ms".format(timeout,sw()))
					time_waited += timeout
					if time_waited > max_time_waited:
						logging.debug("maximum timeout reached")
						break
					timeout *= 2
			total_time_waited += time_waited	
		logging.debug("total time timeout {}ms".format(total_time_waited))

def search_device(ip = default_ip()):	
	"""DESCRIPTION	finds network's gateway that supports upnp information

	:returns: (gateway's address, url of the IGD.xml)
	"""		
	logging.debug("search_device start")
	#message defined in the upnp protocol
	m_search="""M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nST:upnp:rootdevice\r\nMAN:"ssdp:discover"\r\nMX:1\r\n\r\n"""

	"""
	Example of search response
		where we will get the url for IGD.xml
	"""
	#HTTP/1.1 200 OK
	#CACHE-CONTROL:max-age=1800
	#EXT:
	#LOCATION:http://192.168.1.254:8000/tkds39boc1z/IGD/upnp/IGD.xml
	#SERVER:Thomson TG 784n 10.2.2.8 UPnP/1.0 (58-98-35-56-36-3A)
	#ST:upnp:rootdevice
	#USN:uuid:UPnP_Thomson TG784n-1_58-98-35-56-36-3A::upnp:rootdevice	
	#url for the upnp device description
	#(ip:port)
	#list of (url,gateway)
	
	mytuple = None
	logging.debug("Sending M-SEARCH udp packet")
	for payload, address in send_rcv_udp_packet(m_search,ip=ip):
		try:		
			pattern = b"HTTP.*?(\d\d\d)"
			match = re.search(pattern,payload,flags=re.IGNORECASE)
			status_code = match.group(1)
			if status_code != b"200":
				logging.debug("search_device received html status code {}".format(status_code))
				continue		
			pattern = b"location:(.*)"
			match = re.search(pattern,payload,flags=re.IGNORECASE)
			tmp = match.group(1)
			pattern = b".*[.]xml.*"
			if re.search(pattern,tmp,flags=re.IGNORECASE):
				mytuple = (tmp.decode(),address)
				logging.debug("found xml url {}".format(mytuple))				
				break				
		except IndexError:
			pass
		except AttributeError:
			pass


	if mytuple == None:
		raise NoUpnpDeviceFoundError("Did not receive any IGD.xml url")
	logging.debug("search_device end")
	# we could return all of the urls				
	return mytuple

def read_igd(url):
	"""DESCRIPTION	gets relevant information from the IGD.xml 

	:returns: 
	"""
	"""
	Example of a part of a IGD.xml
	"""
	#...
	#<service>
	#	<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
	#	<serviceId>urn:upnp-org:serviceId:WANIPConn1</serviceId>
	#	<controlURL>/tkds39boc1z/IGD/upnp/control/igd/wanipc_2_1_1</controlURL>
	#	<eventSubURL>/tkds39boc1z/IGD/upnp/event/igd/wanipc_2_1_1</eventSubURL>
	#	<SCPDURL>/tkds39boc1z/IGD/upnp/WANIPConnection.xml</SCPDURL>
	#</service>
	#...
	logging.debug("read_igd start")
	f = urllib.request.urlopen(url)
	logging.debug("urlopen:{}".format(url))
	s = socket.fromfd(f.fileno(),socket.AF_INET,socket.SOCK_STREAM)
	logging.debug("from:{} to:{}".format(s.getsockname(),s.getpeername()))
	content = f.read().decode()
	if(f.status != 200):
		logging.debug("Status = {} reason = {}".format(f.status,f.reason))
		logging.debug("Headers:\n{}".format(f.getheaders()))
		logging.debug("Response:\n{}".format(content))
		raise IgdXmlError("Not ok html response")

	xml = content
	pattern = r"<service>(?:(?!<service>)[\s\S])*?<servicetype>.*?WANIPConnection.*?</servicetype>[\s\S]*?</service>"
	match = re.search(pattern,xml,flags=re.IGNORECASE)
	if not match:
		raise IgdXmlError("Failed to find servicetype WANIPConnection")
	refined_xml = match.group(0)
	pattern = r"<controlURL>(.*)</controlURL>"
	match = re.search(pattern,refined_xml,flags=re.IGNORECASE)
	if not match:
		raise IgdXmlError("Failed to find controlURL")
	controlURL = match.group(1)
	pattern = r"<URLBase>(http://(.*?):(\d+))</URLBase>"
	match = re.search(pattern,xml,flags=re.IGNORECASE)
	if not match:
		raise IgdXmlError("Failed to find URLBase")
	URLBase = match.group(1)
	Host_IP = match.group(2)
	Host_Port = match.group(3)
	logging.debug("controlURL:{}".format(controlURL))
	logging.debug("URLBase:{}".format(URLBase))
	logging.debug("read_igd end")
	return (controlURL,Host_IP,Host_Port)

def rpcSoap(controlURL,Host_IP,Host_Port,xml_body,action,ip=default_ip):	
	# {0} = xml_action	
	logging.debug("rpcSoap start")
	content_template=(
	"""<?xml version="1.0"?>\n"""
	"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">"""
	"""<s:Body>"""
	"""{0}"""
	"""</s:Body>"""
	"""</s:Envelope>"""
	)
	content_template=content_template.replace("\n","\r\n")
	# {0} = controlURL
	# {1} = Host_IP:Host_Port
	# {2} = len(content)
	# {3} = action		
	header_template=(
	"POST {0} HTTP/1.0\n"
	"Host:{1}\n"
	"""Content-Type: text/xml; charset="utf-8"\n"""
	"Content-Length: {2}\n"
	"Soapaction: {3}\n"
	"\n"
	)

	header_template=header_template.replace("\n","\r\n")

	content = content_template.format(xml_body)
	header = header_template.format(controlURL,	"{}:{}".format(Host_IP,Host_Port),	str(len(content)),	action)
	payload = header.encode()+content.encode()	
	response = b""
	max_tries = 5
	addr = (Host_IP,int(Host_Port))
	
	#
	#Try 2 times to POST on the url
	#
	sw=None
	total_time_waited=0
	for	t in range(max_tries):
		tmp_response=b""	
		with socket.socket() as s:
			lst = []
			s.settimeout(2)			
			s.bind((ip,0))
			logging.debug("Trying({}/{}) to connect with {}".format(t+1,max_tries,addr))	
			s.connect(addr)
			sw = stopwatch()
			logging.debug("tcp connection made from {}".format(s.getsockname()))
			s.sendall(payload)
			logging.debug("sent {} bytes".format(len(payload)))
			timeout=5
			time_waited=0
			max_time_waited=5000
			one_second=1000
			while True:
				s.settimeout(timeout/one_second)
				try:			
					data = s.recv(4096)
					if data != b"":
						logging.debug("received {} bytes".format(len(data)))
						lst.append(data)
					else:
						break
				except socket.timeout:
					logging.debug("recv timeout at {}ms sw:{}".format(timeout,sw()))
					time_waited += timeout
					if time_waited > max_time_waited:
						logging.debug("maximum timeout reached")
						break
					timeout *= 2
			total_time_waited += time_waited			
			tmp_response = b"".join(lst)
		logging.debug("connection ended after {}ms".format(sw()))	
		if tmp_response != b"":
			response = tmp_response
			break
	logging.debug("total time timeout {}ms sw:{}".format(total_time_waited,sw()))
	
	if response == b"" :
		raise SoapActionTimeOut("Failed to receive response to soap rpc")
	logging.debug("received total {} bytes".format(len(response)))	
	logging.debug("rpcSoap end")
	return (response,payload)

def insertSoap(sub_action,arguments_dictionary, ip):
	logging.debug("insertSoap start")	
	sw = stopwatch()
	(url,gateway) = search_device(ip)	
	(controlURL,Host_IP,Host_Port) = read_igd(url)
	action = "\"urn:schemas-upnp-org:service:WANIPConnection:1#{0}\"".format(sub_action)
	# this is assuming the localhost always has the same local network adress
	arguments = []
	for k,v in arguments_dictionary.items():
		arguments.append("<{0}>{1}</{0}>".format(k,v))
	arguments_string = "".join(arguments)
	xml="""<u:{0} xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">{1}</u:{0}>""".format(sub_action,arguments_string)
	(response,query) = rpcSoap(controlURL,Host_IP,Host_Port,xml,action,ip=ip)
	try:
		check_action_error(response)
	except:
		logging.debug("insertSoap end in {}ms".format(sw()))
		print_query_response(query,response)
		raise
	content = get_html_content(response).decode()
	pattern = "<(?P<argument>[a-zA-Z]+)>(?P<value>[\s\S]+?)</(?P=argument)>"
	arguments = dict(re.findall(pattern,content,flags=re.IGNORECASE))
	logging.debug("insertSoap end in {}ms".format(sw()))
	return arguments

# action : arguments
actions = {
	"GetExternalIPAddress":{}
	,"GetSpecificPortMappingEntry":{
		"NewRemoteHost":""
		,"NewExternalPort":""
		,"NewProtocol":""
	}
	,"GetGenericPortMappingEntry":{
		"NewPortMappingIndex":""
	}
	,"AddPortMapping":{
		"NewRemoteHost":""
		,"NewExternalPort":"port"
		,"NewProtocol":"tcp/udp"
		,"NewInternalPort":"port"
		,"NewInternalClient":"ip"
		,"NewEnabled":"1"
		,"NewPortMappingDescription":"Open by upnp.py"
		,"NewLeaseDuration":"0"
	}
	,"DeletePortMapping":{
		"NewRemoteHost":""
		,"NewExternalPort":"port"
		,"NewProtocol":"tcp/udp"
	}
}

def get_external_ip(ip = default_ip()):
	action = "GetExternalIPAddress"
	for k,v in insertSoap(action,actions[action],ip).items():
		return v

#it actually returns error if the its free
def check_port_protocol(port_number,protocol):
	action="GetSpecificPortMappingEntry"
	args=actions[action].copy()
	args["NewExternalPort"]=port_number
	args["NewProtocol"]=protocol
	return insertSoap(action,args)

def GetGenericPortMappingEntry(index,fun=insertSoap):
	action="GetGenericPortMappingEntry"
	args=actions[action].copy()
	args["NewPortMappingIndex"]=index	
	return fun(action,args)	


def AddPortMapping(port,protocol, ip=default_ip()):
	action="AddPortMapping"
	args=actions[action].copy()
	args["NewExternalPort"]=port
	args["NewProtocol"]=protocol
	args["NewInternalPort"]=port
	args["NewInternalClient"]=ip
	return insertSoap(action,args)


def DeletePortMapping(port,protocol):
	action="DeletePortMapping"
	args=actions[action].copy()
	args["NewExternalPort"]=port
	args["NewProtocol"]=protocol
	return insertSoap(action,args)
	

def GetConnectionTypeInfo():
	a = "GetConnectionTypeInfo"
	d = {}
	return insertSoap(a,d)

def GetStatusInfo():
	a = "GetStatusInfo"
	d = {}
	return insertSoap(a,d)


def get_array():
	lst=[]
	i=0
	fun = Ass()
	while True:
		try:
			lst.append(GetGenericPortMappingEntry(i,fun.insertSoap))
			print("YES {}".format(i))
		except SoapActionTimeOut:
			print("TO  {}".format(i))
			lst.appent({})
		except SoapActionError as e:
			print("ERROR  {}".format(i))
			break
		i+=1
	return lst


#logging.getLogger().setLevel(logging.WARNING)