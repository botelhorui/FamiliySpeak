FamiliySpeak
============

Tested on Windows 7 64 bits.
Python 3.4
Adicional libraries: pyaudio

Tested and working:
-Server - manages connected clients, broadcasts information.
-Child processes' - management
-Listener/Client - for sending python objects through TCP (based on multiprocessing module)
-Simple remote procedure calls - 
-Text Chat -
-UPNP - router detection, adding/removing open ports for listening to audio in UDP
-VOIP - uses UDP, orders incoming packets, supports multiple people speaking
-G711 - Apendice II algorithm, used for remove the effects of packet loss
-GUI - simple interface, lists clients connected, shows chat history, allows sending chat, shows program statistics
