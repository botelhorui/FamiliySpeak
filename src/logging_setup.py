import logging
import datetime

def logging_setup():
	if False:
		log_name = ".\\logs\\family_speak_LOG_"+datetime.datetime.now().strftime("%Y-%m-%d %H.%M.%S")+".txt"
		with open(log_name,"w"):
			pass
		logging.basicConfig(filename=log_name,filemode="w+",level=logging.DEBUG,format="[%(levelname)s]%(message)s")
	logging.basicConfig(level=logging.DEBUG,format="%(message)s")
	#logging.basicConfig(level=logging.DEBUG,format="[%(levelname)s]%(message)s")