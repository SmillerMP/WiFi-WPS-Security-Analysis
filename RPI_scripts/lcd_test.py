#!/usr/bin/env python3
import pygame, struct, threading, time

W,H = 480,320
FB="/dev/fb1"
DEV="/dev/input/event0"

# ==== CALIBRACIÓN CORRECTA ====
X_MIN=200
X_MAX=3900
Y_MIN=200
Y_MAX=3900

pygame.init()
pygame.font.init()
screen = pygame.Surface((W,H))
print("✓ pygame listo")

def refresh():
    with open(FB,"wb") as f:
        f.write(screen.convert(16,0).get_buffer())

def map_val(v,a,b,c,d):
    v=max(a,min(b,v))
    return int((v-a)*(d-c)/(b-a)+c)

WHITE=(255,255,255)
BLACK=(0,0,0)
RED=(255,0,0)
GREEN=(0,200,0)
BLUE=(0,120,255)

font=pygame.font.Font(None,48)

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

btn_plus=Button(40,80,180,90,"+",GREEN)
btn_minus=Button(260,80,180,90,"-",BLUE)

rawx=rawy=0
touch=False
pos=(0,0)
stable=[]

def read_touch():
    global rawx,rawy,touch,pos,stable
    f=open(DEV,"rb")
    evsz=struct.calcsize("llHHI")
    print("✓ touch abierto")

    while True:
        d=f.read(evsz)
        _,_,t,c,v=struct.unpack("llHHI",d)

        if t==3:
            if c==0: 
                rawx=v
            if c==1: 
                rawy=v

        if t==0:  # SYN_REPORT
            px = W - map_val(rawy, Y_MIN, Y_MAX, 0, W)
            py = map_val(rawx, X_MIN, X_MAX, 0, H)

            stable.append((px,py))
            if len(stable)>3:
                stable.pop(0)

        if t==1 and c==330:
            if v==1:
                stable.clear()
                touch=True
            else:
                if stable:
                    sx=sum(p[0] for p in stable)//len(stable)
                    sy=sum(p[1] for p in stable)//len(stable)
                    pos=(sx,sy)
                    print("TOUCH:",pos,"RAW X:",rawx,"Y:",rawy)
                touch=False

threading.Thread(target=read_touch,daemon=True).start()

last=False
count=0
show_click=0
print("✓ loop")

while True:
    screen.fill(WHITE)
    btn_plus.draw()
    btn_minus.draw()

    if not touch and last:
        show_click=8
        
        if btn_plus.hit(pos):
            count+=1
            print("+",count)
        if btn_minus.hit(pos):
            count-=1
            print("-",count)

    if show_click>0:
        pygame.draw.circle(screen,RED,pos,6)
        show_click-=1

    last=touch

    txt=font.render(str(count),True,BLACK)
    screen.blit(txt,(220,10))

    refresh()
    time.sleep(0.016)