import socket
import re
import time
import logging
import urllib.request
import traceback
import datetime
"""
First time using upnp.
I learned a lot by reading https://github.com/miniupnp
"""

#logging.basicConfig(level=logging.DEBUG,format="[%(levelname)s]%(message)s")

MSEARCH_TIMEOUT = 10
SOAP_REQUEST_TIMEOUT = 10

def default_ip():
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
	s.connect(("123.123.123.123",80))
	return s.getsockname()[0]

#globals
control_url=None
host_address=None
local_ip=default_ip()

class MyException(Exception):
	def __init__(self,value=""):
		self.value=value

	def __str__(self):
		return repr(self.value)

class SoapFaultException(Exception):
	def __init__(self,value=""):
		self.value=value

	def __str__(self):
		return repr(self.value)

def parse_msearch_response(response):
	"""
	HTTP/1.1 200 OK
	CACHE-CONTROL:max-age=1800
	EXT:
	LOCATION:http://192.168.1.254:8000/tkds39boc1z/IGD/upnp/IGD.xml
	SERVER:Thomson TG 784n 10.2.2.8 UPnP/1.0 (58-98-35-56-36-3A)
	ST:upnp:rootdevice
	USN:uuid:UPnP_Thomson TG784n-1_58-98-35-56-36-3A::upnp:rootdevice
	"""
	pattern = "location:(.*)"
	match = re.search(pattern,response,flags=re.IGNORECASE)
	location = match.group(1)
	pattern = "ST:(.*)"
	match = re.search(pattern,response,flags=re.IGNORECASE)
	st = match.group(1)
	return (location,st)

		

def parse_idg_xml(igd_url):
	#...
	#<service>
	#	<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
	#	<serviceId>urn:upnp-org:serviceId:WANIPConn1</serviceId>
	#	<controlURL>/tkds39boc1z/IGD/upnp/control/igd/wanipc_2_1_1</controlURL>
	#	<eventSubURL>/tkds39boc1z/IGD/upnp/event/igd/wanipc_2_1_1</eventSubURL>
	#	<SCPDURL>/tkds39boc1z/IGD/upnp/WANIPConnection.xml</SCPDURL>
	#</service>
	#...
	http_response = urllib.request.urlopen(igd_url)
	if(http_response.status != 200):
		raise MyException("igd url http response not ok")
	xml = http_response.read().decode()
	pattern = r"<service>(?:(?!<service>)[\s\S])*?<servicetype>.*?WANIPConnection.*?</servicetype>[\s\S]*?</service>"
	match = re.search(pattern,xml,flags=re.IGNORECASE)
	if not match:
		raise MyException("Failed to find servicetype WANIPConnection in xml")
	refined_xml = match.group(0)
	pattern = r"<controlURL>(.*)</controlURL>"
	match = re.search(pattern,refined_xml,flags=re.IGNORECASE)
	if not match:
		raise MyException("Failed to find controlURL")
	control_url = match.group(1)
	pattern = r"<URLBase>(http://(.*?):(\d+))</URLBase>"
	match = re.search(pattern,xml,flags=re.IGNORECASE)
	if not match:
		raise MyException("Failed to find URLBase")
	url_base = match.group(1)
	host_ip = match.group(2)
	host_port = int(match.group(3))
	return (control_url,(host_ip,host_port))


def msearch():
	global local_ip
	UPNP_BROADCAST_ADDRESS = ("239.255.255.250",1900)
	request_fmt = """M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nST:{}\r\nMAN:"ssdp:discover"\r\nMX:1\r\n\r\n"""
	sts = [
		"urn:schemas-upnp-org:device:InternetGatewayDevice:1",
		"urn:schemas-upnp-org:service:WANIPConnection:1",
		"urn:schemas-upnp-org:service:WANPPPConnection:1",
	]
	with socket.socket(type=socket.SOCK_DGRAM) as sock:
		sock.bind((local_ip,0))
		sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
		logging.debug("sending udp from: {}".format(sock.getsockname()))
		for st in sts:
			req = request_fmt.format(st)
			sock.sendto(req.encode(),UPNP_BROADCAST_ADDRESS)	
			logging.debug("sent m-search to {} with ST:{}".format(UPNP_BROADCAST_ADDRESS,st))

		start = time.time()
		while True:
			try:				
					sock.settimeout(3)
					receive_data, from_address = sock.recvfrom(4096)
					receive_data=receive_data.decode()
					logging.debug("Received from {}:\n\"\n{}\"\n".format(from_address,receive_data))
					location,st = parse_msearch_response(receive_data)
					control_url,host_address=parse_idg_xml(location)
					logging.debug("got control_url:{} host_address:{}".format(control_url,host_address))
					return (control_url,host_address)
			except MyException as e:
				pass
			except socket.timeout as e:
				break
	raise MyException("Didnt find any devices")		

def soap_request(action,args,control_url,host_address):
	global local_ip
	# Resquest building
	action_urn = "\"urn:schemas-upnp-org:service:WANIPConnection:1#{0}\"".format(action)
	arguments = []
	for k,v in args:
		arguments.append("<{0}>{1}</{0}>".format(k,v))
	arguments = "".join(arguments)
	action_xml="""<u:{0} xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">{1}</u:{0}>""".format(action,arguments)
	xml_template =(
	"""<?xml version="1.0"?>\r\n"""
	"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">"""
	"""<s:Body>"""
	"""{0}"""
	"""</s:Body>"""
	"""</s:Envelope>\r\n"""
	)	
	xml = xml_template.format(action_xml)
	http_header_template=(
	"POST {0} HTTP/1.1\n"
	"Host:{1}\n"
	"User-Agent: MSWindows/6.0.6002, UPnP/1.0, upnp.py/0.0\n"
	"Content-Length: {2}\n"
	"""Content-Type: text/xml; charset="utf-8"\n"""	
	"SOAPaction: {3}\n"
	"Connection: Close\n"
	"Cache-Control: no-cache\n"
	"Pragma: no-cache\n"
	"\n"
	)
	http_header_template=http_header_template.replace("\n","\r\n")
	http_header = http_header_template.format(control_url,"{}:{}".format(host_address[0],host_address[1]),str(len(xml.encode())),action_urn)
	http_request = http_header+xml
	logging.debug("http_request:\n{}".format(http_request))
	payload = http_request.encode()
	#Request Send/Receive
	start = time.time()
	response = None
	data = b''
	finished=False
	while True:
		if (time.time() - start) > SOAP_REQUEST_TIMEOUT:
			raise MyException("Soap request timedout")
		try:
			with socket.socket() as sock:
				sock.bind((local_ip,0))
				logging.debug("Sending SOAP from: {}".format(sock.getsockname()))
				sock.settimeout(3)
				sock.connect(host_address)
				sock.sendall(payload)				
				while True:	
					sock.settimeout(3)	
					buf = sock.recv(4096)
					logging.debug("Received {} bytes from {}".format(len(buf),host_address))				
					data += buf
					pattern = '</s:envelope>'.encode()
					if re.search(pattern,data,flags=re.IGNORECASE):
						logging.debug("Received Total {} bytes from {}".format(len(data),host_address))
						finished=True
						break
					if len(buf) == 0:
						break
				if finished:
					break
		except socket.timeout:
			continue
			
	response = data
			
	if len(response) == 0:
		raise SoapFaultException("Soap response not received")

	logging.debug("Response:\n{}".format(response.decode()))
	logging.debug("")

	pattern = b"HTTP.*?(\d\d\d)"
	match = re.search(pattern,response,flags=re.IGNORECASE)
	status_code = match.group(1).decode()

	pattern = b"Content-Length:\s*(\d+)\r\n"
	match = re.search(pattern,response,flags=re.IGNORECASE)
	length =  int(match.group(1).decode())	
	xml = response[-length:].decode()

	if status_code != "200":
		raise MyException("SOAP Error:\n"+response.decode())

	response_pattern = """<.:{0} xmlns:.="urn:schemas-upnp-org:service:WANIPConnection:1">(.*?)</.:{0}>""".format(action+"Response")
	arguments_xml = re.search(response_pattern,xml,flags=re.IGNORECASE).group(1)
	args_pattern = "<(?P<arg>[^>]+)>(?P<value>[^>]+)</(?P=arg)>"
	arguments = re.findall(args_pattern,arguments_xml,flags=re.IGNORECASE)
	return arguments



def soap(action,args):
	global control_url
	global host_address
	if control_url == None or host_address == None:
		control_url,host_address=msearch()
	return soap_request(action,args,control_url,host_address)

def GetExternalIPAddress():
	action = "GetExternalIPAddress"
	args = []
	return soap(action,args)[0][1]

def GetStatusInfo():
	action = "GetStatusInfo"
	args = []
	return soap(action,args)

#it actually returns error if the its free
def GetSpecificPortMappingEntry(port,protocol):
	action="GetSpecificPortMappingEntry"
	args = [
		("NewRemoteHost",""),
		("NewExternalPort",port),
		("NewProtocol",protocol.upper()),
	]
	return soap(action,args)

def GetGenericPortMappingEntry(port):
	action = "GetGenericPortMappingEntry"
	args=[
		("NewPortMappingIndex",port),
	]
	return soap(action,args)
	

def AddPortMapping(port,protocol):
	global ip
	action="AddPortMapping"
	args = [
		("NewRemoteHost",""),
		("NewExternalPort",port),
		("NewProtocol",protocol.upper()),
		("NewInternalPort",port),
		("NewInternalClient",local_ip),
		("NewEnabled","1"),
		("NewPortMappingDescription","Opened by upnp.py"),
		("NewLeaseDuration","0"),
	]
	return soap(action,args)

def DeletePortMapping(port,protocol):
	action="DeletePortMapping"
	args=[
		("NewRemoteHost",""),
		("NewExternalPort",port),
		("NewProtocol",protocol.upper()),
	]
	return soap(action,args)

def open_port(port,protocol):	
	AddPortMapping(port,protocol)
	GetSpecificPortMappingEntry(port,protocol)


def is_port_open(port,protocol):
	try:		
		logging.debug("GetSpecificPortMappingEntry:\n{}".format(GetSpecificPortMappingEntry(port,protocol)))
		return True
	except MyException:
		return False

def is_behind_gateway():
	try:
		GetStatusInfo()
		return True
	except MyException:
		return False

def get_external_ip(local_ip):
	global ip
	ip = local_ip
	return GetExternalIPAddress()