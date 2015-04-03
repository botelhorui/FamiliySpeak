from tkinter import *
from tkinter import ttk
import time


from head import Statistics

mytime = time.perf_counter
mytime()


#time in milliseconds
POLL_TIMEOUT = 50

WINDOW_TITLE = "FamilySpeak"
DEFAULT_SERVER = "46.189.129.246:15000"
DEFAULT_NICK = "test user"

STATS_UPDATE_RATE = 1

def speed_string(speed):
    unit = "B"
    num = 0
    if speed < 1000:
        num=speed
    elif speed < 1000000:
        unit = "KB"
        num=speed/1000
    else:
        unit = "MB"
        num=speed/1000000

    return "{:.01f} {}/s".format(num,unit)

class MyAppWindow():

    def __init__(self,gui_end,stats):
        self.client_pipe=gui_end
        self.stats=stats
        self.run()

    def run(self):
        self.root=Tk()
        self.root.protocol("WM_DELETE_WINDOW",self.close_window)
        self.root.columnconfigure(0,weight=1)
        self.root.rowconfigure(0,weight=1)
        self.root.title(WINDOW_TITLE)

        self.setup_login_frame()
        self.setup_connecting_frame()
        self.setup_chat_frame()

        self.poll_state = self.empty
        self.root.after(POLL_TIMEOUT,self.loop)

        self.root.mainloop()


    def loop(self):
        self.handle_rpc()
        try:
            self.poll_state()         
            self.root.after(POLL_TIMEOUT,self.loop)
        except:
            self.close_window()
            raise


    def close_window(self):
        self.client_pipe.send(["close"])
        self.root.destroy()
        self.root.quit()        

    def stop(self):
        self.root.destroy()
        self.root.quit()   

    def set_clients(self,txt):
        self.users["state"]="normal"
        self.users.delete("1.0","end")
        self.users.insert("end",txt)
        self.users["state"]="disabled"      

    def show_message(self,message):
        self.chat["state"]="normal"     
        self.chat.insert("end",message+"\n")
        self.chat.yview("end")
        self.chat["state"]="disabled"

    def handle_rpc(self):
        if not self.client_pipe.poll():
            return
        rpc = self.client_pipe.recv()
        func, *args = rpc
        func=getattr(self,func)
        print("[GUI]rpc {}".format(rpc))
        func(*args)

    def empty(self):
        pass

    def setup_connecting_frame(self):
        self.connecting_frame=ttk.Frame(self.root,padding="60")
        self.connecting_frame.grid(column=0,row=0,sticky=(N,W,E,S))
        self.connecting_string = StringVar()
        ttk.Label(self.connecting_frame,textvariable=self.connecting_string).grid(column=0,row=0)       
        self.connecting_frame.grid_remove()


    def setup_chat_frame(self):
        self.chat_frame=ttk.Frame(self.root, width=20,height=5)
        self.chat_frame.grid(column=0,row=0,sticky=(N,W,E,S))
        self.chat_frame.columnconfigure(0,weight=1)
        self.chat_frame.rowconfigure(1,weight=1)
        self.chat_frame.rowconfigure(3,weight=1)    
        self.chat_frame.grid_remove()   
        ttk.Label(self.chat_frame,text="Family members online:").grid(column=0,row=0,sticky=(W,E))
        #client list
        self.users = Text(self.chat_frame, width=20,height=5)
        self.users.grid(column=0,row=1,sticky=(N,W,E,S),columnspan=2)
        self.userS = ttk.Scrollbar(self.chat_frame, orient=VERTICAL, command=self.users.yview)
        self.userS.grid(column=2,row=1,sticky=(N,S))
        self.users["yscrollcommand"]=self.userS.set
        self.users["state"]="disabled"
        #chat text box
        ttk.Label(self.chat_frame,text="chat:").grid(column=0,row=2,sticky=(W,E))
        self.chat = Text(self.chat_frame, width=20,height=5)
        self.chat.grid(column=0,row=3,sticky=(N,W,E,S))
        self.chatS = ttk.Scrollbar(self.chat_frame, orient=VERTICAL, command=self.chat.yview)
        self.chatS.grid(column=2,row=3,sticky=(N,S))
        self.chat["yscrollcommand"]=self.chatS.set
        self.chat["state"]="disabled"
        #chatInput text box
        self.chatInput = ttk.Entry(self.chat_frame)
        self.chatInput.grid(column=0,row=4,sticky=(W,E))
        self.chatInput.focus()
        self.chatInput.bind("<Return>", self.send_message)
        #stats labels
        self.stats_label = StringVar()
        ttk.Label(self.chat_frame,textvariable=self.stats_label).grid(column=0,row=5,sticky=(W,E),columnspan=2)

    def chat_poll(self):
        d = mytime() - self.chat_poll_time
        if d < STATS_UPDATE_RATE: 
            return

        self.chat_poll_time = mytime()

        sent = self.stats.sent.value
        received = self.stats.received.value
        produced = self.stats.produced.value
        played = self.stats.played.value
        rejected = self.stats.rejected.value

        self.stats.sent.value =0
        self.stats.received.value=0
        self.stats.produced.value=0
        self.stats.played.value=0
        self.stats.rejected.value=0

        sent = speed_string(sent/d)
        received = speed_string(received/d)
        produced = speed_string(produced/d)
        played = speed_string(played/d)
        rejected = speed_string(rejected/d)

        s = "sent: {} produced: {} received: {} rejected: {} played: {}".format(
            sent,
            produced,
            received,
            rejected,
            played
            )
        self.stats_label.set(s)

    def send_message(self,*args):
        message = self.chatInput.get()      
        self.chatInput.delete(0,"end")
        action = ["send_message",message]
        self.client_pipe.send(action)    
 

    def setup_login_frame(self):
        self.login_frame = ttk.Frame(self.root,padding="60")
        self.login_frame.grid(column=0,row=0,sticky=(N,W,E,S))
        self.login_frame.columnconfigure(1,weight=1)
        self.server = StringVar()
        self.nickname = StringVar()
        self.server.set(DEFAULT_SERVER)
        self.nickname.set(DEFAULT_NICK)
        width = len("xxx.xxx.xxx.xxx:xxxxx")
        ttk.Label(self.login_frame,text="Server").grid(column=0,row=0,sticky=E)
        ttk.Entry(self.login_frame,textvariable=self.server).grid(column=1,row=0,sticky=(W,E))
        ttk.Label(self.login_frame,text="Nickname").grid(column=0,row=1,sticky=E)
        x = ttk.Entry(self.login_frame, textvariable=self.nickname)
        x.grid(column=1,row=1,sticky=(W,E))
        x.focus()
        x.bind("<Return>", self.login_button)

        #setup the network adapters ips
        ttk.Label(self.login_frame,text="Network Adapter").grid(column=0,row=3,sticky=E)
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
        s.connect(("123.123.123.123",80))
        public_ip = s.getsockname()[0]
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
        i = ips.index(public_ip)
        ips[0],ips[i]=ips[i],ips[0]     
        self.addr = StringVar()
        self.addr.set(ips[0])
        for i in range(len(ips)):
            ip = ips[i]
            row = 3 + i
            ttk.Radiobutton(self.login_frame,text=ip,variable=self.addr,value=ip).grid(column=1,row=row,sticky=(W,E))
        ttk.Button(self.login_frame,text="Login",command=self.login_button).grid(column=0,row=3 + len(ips),columnspan=2)

    def login_button(self,*args):
        self.login_frame.grid_remove()
        #try to connect
        login_action = ["login",self.server.get(),self.nickname.get(),self.addr.get()]
        self.client_pipe.send(login_action)
        self.connecting_frame.grid()
        self.connecting_string.set("Connecting")
        self.connecting_i = 0
        self.connecting_time = mytime()
        self.poll_state = self.connecting_poll

    def connecting_poll(self):
        if mytime() - self.connecting_time > 0.6:                    
            if self.connecting_i == 4:
                self.connecting_i = 0
            self.connecting_string.set("Connecting"+"."*self.connecting_i)
            self.connecting_i += 1

    def connecting_failed(self):
        self.connecting_frame.grid_remove()
        self.login_frame.grid()
        self.poll_state=self.empty

    def connecting_successfull(self):
        self.connecting_frame.grid_remove()
        self.chat_frame.grid()
        self.poll_state=self.chat_poll
        self.chat_poll_time = mytime()      







if __name__ == "__main__":
    from multiprocessing import *
    gui_end, gui_conn = Pipe()
    stats = Statistics(
            sent=Value("i",0),
            received=Value("i",0),
            produced=Value("i",0),
            played=Value("i",0),
            rejected=Value("i",0)
    )
    p = Process(target=MyAppWindow,args=(gui_conn,stats))
    p.start()
    while True:
        if gui_end.poll():
            print(gui_end.recv())
        action = input(":")
        if action != "":
            gui_end.send(action)

