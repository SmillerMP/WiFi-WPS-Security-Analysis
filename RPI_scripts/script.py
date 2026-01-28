#!/usr/bin/env python3
import pygame, struct, threading, time, os, subprocess, re, signal, sys

running = True

W,H = 480,320
FB="/dev/fb1"
DEV="/dev/input/event0"

# ==== CALIBRACIÓN (NO TOCAR) ====
X_MIN=200
X_MAX=3900
Y_MIN=200
Y_MAX=3900

pygame.init()
pygame.font.init()
screen = pygame.Surface((W,H))

def refresh():
    with open(FB,"wb") as f:
        f.write(screen.convert(16,0).get_buffer())

WHITE=(255,255,255)
BLACK=(0,0,0)
RED=(255,0,0)
GREEN=(0,200,0)
BLUE=(0,120,255)
YELLOW=(240,200,0)
ORANGE=(255,140,0)

def cleanup_and_exit(signum=None, frame=None):
    global running
    running = False
    try:
        screen.fill(BLACK)
        refresh()
    except:
        pass
    try:
        pygame.quit()
    except:
        pass
    os.system("stty sane")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

def map_val(v,a,b,c,d):
    v=max(a,min(b,v))
    return int((v-a)*(d-c)/(b-a)+c)

font=pygame.font.Font(None,42)
smallfont=pygame.font.Font(None,22)
msgfont=pygame.font.Font(None,32)

class Button:
    def __init__(self,x,y,w,h,t,c):
        self.r=pygame.Rect(x,y,w,h)
        self.t=t
        self.c=c
    def draw(self):
        pygame.draw.rect(screen,self.c,self.r,border_radius=10)
        pygame.draw.rect(screen,BLACK,self.r,3,border_radius=10)
        txt=font.render(self.t,True,WHITE)
        screen.blit(txt,txt.get_rect(center=self.r.center))
    def hit(self,p):
        return self.r.collidepoint(p)

BTN_W=200
BTN_H=70

btn_start = Button(40,  25, BTN_W, BTN_H, "START", GREEN)
btn_stop  = Button(260, 25, BTN_W, BTN_H, "STOP",  YELLOW)
btn_reset = Button(40, 110, BTN_W, BTN_H, "RESET", ORANGE)
btn_power = Button(260,220, BTN_W, BTN_H, "SHUTDOWN", RED)

rawx=rawy=0
touch=False
pos=(0,0)
stable=[]

status_msg=""
status_until=0
busy=False

last_activity=time.time()
DIM_TIMEOUT=60
dimmed=False

def run(cmd):
    return subprocess.run(cmd,shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode == 0

def detect_iface():
    try:
        out=subprocess.check_output("iw dev", shell=True).decode()
        ifaces=re.findall(r'Interface\s+(\w+)',out)
        for i in ifaces:
            if i!="lo":
                return i
    except: pass
    return None

def get_ip():
    try:
        out=subprocess.check_output("ip -4 addr show", shell=True).decode()
        for l in out.splitlines():
            if "inet " in l:
                ip=l.split()[1].split("/")[0]
                if not ip.startswith("127."):
                    return ip
    except: pass
    return "no ip"

def get_mode():
    try:
        out=subprocess.check_output("iw dev", shell=True).decode()
        m=re.search(r'type (\w+)',out)
        if m: return m.group(1)
    except: pass
    return "unknown"

# ==== ACTIONS ====

def start_monitor():
    iface=detect_iface()
    if not iface: return False

    run("sudo systemctl start gpsd")
    ok=True
    ok &= run("sudo airmon-ng check kill")
    ok &= run(f"sudo ip link set {iface} down")
    ok &= run(f"sudo macchanger -r {iface}")
    ok &= run(f"sudo iw dev {iface} set type monitor")
    ok &= run(f"sudo ip link set {iface} up")
    run("pgrep cgps || cgps >/dev/null 2>&1 &")
    run(f"kismet -c {iface} -t $(date +%F_%H-%M-%S) --override wardrive >/dev/null 2>&1 &")
    return ok

def stop_all():
    run("pkill kismet")
    run("pkill cgps")
    return True

def reset_iface():
    iface=detect_iface()
    if not iface: return False

    ok=True
    run("pkill kismet")
    run("pkill cgps")
    run("sudo systemctl stop gpsd")
    run("sudo pkill gpsd")

    ok &= run(f"sudo ip link set {iface} down")
    ok &= run(f"sudo macchanger -p {iface}")
    ok &= run(f"sudo iw dev {iface} set type managed")
    ok &= run(f"sudo ip link set {iface} up")
    ok &= run("sudo systemctl restart NetworkManager")
    return ok

def async_job(fn,msg_ok,msg_err):
    global status_msg,status_until,busy
    if fn():
        status_msg=msg_ok
    else:
        status_msg=msg_err
    status_until=time.time()+2
    busy=False

# ==== TOUCH ====

def read_touch():
    global rawx,rawy,touch,pos,stable,last_activity,dimmed
    f=open(DEV,"rb")
    evsz=struct.calcsize("llHHI")

    while True:
        d=f.read(evsz)
        _,_,t,c,v=struct.unpack("llHHI",d)

        if t==3:
            if c==0: rawx=v
            if c==1: rawy=v

        if t==0:
            px=W-map_val(rawy,Y_MIN,Y_MAX,0,W)
            py=map_val(rawx,X_MIN,X_MAX,0,H)
            stable.append((px,py))
            if len(stable)>3: stable.pop(0)

        if t==1 and c==330:
            if v==1:
                stable.clear()
                touch=True
            else:
                if stable:
                    sx=sum(p[0] for p in stable)//len(stable)
                    sy=sum(p[1] for p in stable)//len(stable)
                    pos=(sx,sy)
                touch=False
                last_activity=time.time()
                dimmed=False

threading.Thread(target=read_touch,daemon=True).start()

last=False
show_click=0
last_shutdown_click=0

# ==== LOOP ====

while running:
    now=time.time()

    if now-last_activity>DIM_TIMEOUT:
        dimmed=True

    if dimmed:
        screen.fill(BLACK)
        refresh()
        time.sleep(0.05)
        continue

    screen.fill(WHITE)

    btn_start.draw()
    btn_stop.draw()
    btn_reset.draw()
    btn_power.draw()

    ip=get_ip()
    mode=get_mode()
    info=smallfont.render(f"IP: {ip}   MODE: {mode}",True,BLACK)
    screen.blit(info,(10,5))

    if status_msg and time.time()<status_until:
        msg = msgfont.render(status_msg, True, BLACK)
        screen.blit(msg, msg.get_rect(center=(140,255)))

    if not touch and last:
        show_click=8

        if btn_start.hit(pos) and not busy:
            busy=True
            status_msg="WORKING..."
            status_until=time.time()+2
            threading.Thread(target=async_job,args=(start_monitor,"OK!","ERROR"),daemon=True).start()

        if btn_stop.hit(pos) and not busy:
            busy=True
            status_msg="WORKING..."
            status_until=time.time()+2
            threading.Thread(target=async_job,args=(stop_all,"STOPPED","ERROR"),daemon=True).start()

        if btn_reset.hit(pos) and not busy:
            busy=True
            status_msg="WORKING..."
            status_until=time.time()+2
            threading.Thread(target=async_job,args=(reset_iface,"RESET OK","ERROR"),daemon=True).start()

        if btn_power.hit(pos):
            if now-last_shutdown_click<1:
                os.system("sudo shutdown now")
                last_shutdown_click=0
            else:
                last_shutdown_click=now

    if show_click>0:
        pygame.draw.circle(screen,RED,pos,6)
        show_click-=1

    last=touch
    refresh()
    time.sleep(0.016)