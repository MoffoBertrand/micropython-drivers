"""
exemple_04_animation.py — SSD1351 RGB OLED 1.5" (128x128)
Exemple 4 : Animations, horloge, particules, spirale, plasma
"""
import time, math, random
from ssd1351 import (SSD1351, color565, hsv_to_rgb565,
                     BLACK, WHITE, RED, GREEN, BLUE,
                     YELLOW, CYAN, MAGENTA, ORANGE, GRAY)

oled = SSD1351()
W, H = oled.width, oled.height

# 1 : Balle rebondissante (show_region pour fluidite)
bx, by = 40.0, 40.0
vx, vy = 2.2, 1.7
R = 10
for _ in range(300):
    ox, oy = int(bx), int(by)
    bx += vx; by += vy
    if bx <= R or bx >= W-R: vx=-vx; bx=max(R,min(W-R,bx))
    if by <= R or by >= H-R: vy=-vy; by=max(R,min(H-R,by))
    nx, ny = int(bx), int(by)
    oled.fill_circle(ox, oy, R+2, BLACK)
    # Effet sillage
    for i in range(3, 0, -1):
        tx=int(bx-vx*i*2); ty=int(by-vy*i*2)
        if 0<=tx<W and 0<=ty<H:
            oled.fill_circle(tx, ty, max(1,R-i*3),
                             color565(255-i*60, 100-i*30, 0))
    oled.fill_circle(nx, ny, R, ORANGE)
    oled.draw_circle(nx, ny, R, WHITE)
    x0=max(0,min(ox,nx)-R-3); y0=max(0,min(oy,ny)-R-3)
    x1=min(W-1,max(ox,nx)+R+3); y1=min(H-1,max(oy,ny)+R+3)
    oled.show_region(x0, y0, x1, y1)
    time.sleep_ms(16)

oled.fill(BLACK); oled.show()

# 2 : Horloge analogique avec cadran elabore
cx, cy, Rc = 64, 64, 58

def draw_clock(sec):
    oled.fill(BLACK)
    # Cadran exterieur
    oled.fill_circle(cx, cy, Rc+2, color565(20,20,40))
    oled.draw_circle(cx, cy, Rc, color565(100,100,200))
    oled.draw_circle(cx, cy, Rc-2, color565(60,60,140))
    # Graduations
    for i in range(60):
        a = i * math.pi / 30 - math.pi / 2
        if i % 5 == 0:  # heure
            x0=int(cx+(Rc-8)*math.cos(a)); y0=int(cy+(Rc-8)*math.sin(a))
            x1=int(cx+Rc*math.cos(a));     y1=int(cy+Rc*math.sin(a))
            oled.line(x0,y0,x1,y1, WHITE)
        else:           # minute
            x0=int(cx+(Rc-3)*math.cos(a)); y0=int(cy+(Rc-3)*math.sin(a))
            x1=int(cx+Rc*math.cos(a));     y1=int(cy+Rc*math.sin(a))
            oled.pixel(x1, y1, GRAY)
    # Chiffres 12,3,6,9
    for num, a in [(12,-90),(3,0),(6,90),(9,180)]:
        ax=int(cx+(Rc-16)*math.cos(math.radians(a)))
        ay=int(cy+(Rc-16)*math.sin(math.radians(a)))
        oled.text(str(num), ax-4*(len(str(num))), ay-4, CYAN)
    # Aiguilles
    ah=(sec//3600%12)*math.pi/6+(sec%3600)*math.pi/21600-math.pi/2
    for t in range(3, 0, -1):  # epaisseur aiguille heures
        oled.line(cx,cy, cx+int((Rc*0.5+t)*math.cos(ah)),
                  cy+int((Rc*0.5+t)*math.sin(ah)), WHITE)
    am=(sec//60%60)*math.pi/30-math.pi/2
    for t in range(2, 0, -1):
        oled.line(cx,cy, cx+int((Rc*0.75+t)*math.cos(am)),
                  cy+int((Rc*0.75+t)*math.sin(am)), CYAN)
    a_s=(sec%60)*math.pi/30-math.pi/2
    oled.line(cx,cy, cx+int(Rc*0.9*math.cos(a_s)),
              cy+int(Rc*0.9*math.sin(a_s)), RED)
    # Centre
    oled.fill_circle(cx, cy, 5, color565(200,200,200))
    oled.fill_circle(cx, cy, 3, RED)
    oled.show()

t0 = time.ticks_ms()
for _ in range(60):
    draw_clock(time.ticks_diff(time.ticks_ms(),t0)//1000 + 10*3600+30*60)
    time.sleep_ms(1000)

oled.fill(BLACK); oled.show()

# 3 : Spirale de couleurs
for frame in range(200):
    angle = frame * 0.15
    for i in range(12):
        a = angle + i * math.pi / 6
        dist = 5 + frame * 0.15
        if dist > 62: break
        px = int(cx + dist * math.cos(a))
        py = int(cy + dist * math.sin(a))
        hue = (frame * 3 + i * 30) % 360
        c = hsv_to_rgb565(hue, 1.0, 1.0)
        if 0 <= px < W and 0 <= py < H:
            oled.fill_circle(px, py, 3, c)
    if frame % 5 == 0:
        oled.show()
    time.sleep_ms(20)

oled.fill(BLACK); oled.show()

# 4 : Plasma (effet psychedelique)
for frame in range(80):
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            t = frame * 0.1
            v = (math.sin(x/8 + t) +
                 math.sin(y/8 + t) +
                 math.sin((x+y)/12 + t) +
                 math.sin(math.sqrt(x*x+y*y)/8 + t))
            hue = (v * 45 + 180) % 360
            c = hsv_to_rgb565(hue, 1.0, 1.0)
            oled.fill_rect(x, y, 2, 2, c)
    oled.show()
    time.sleep_ms(10)

# 5 : Systeme de particules
N = 50
px_a  = [random.uniform(0,W) for _ in range(N)]
py_a  = [random.uniform(0,H) for _ in range(N)]
pvx_a = [random.uniform(-2,2) for _ in range(N)]
pvy_a = [random.uniform(-2,2) for _ in range(N)]
pr_a  = [random.randint(2,5) for _ in range(N)]
pc_a  = [hsv_to_rgb565(random.uniform(0,360), 1.0, 1.0) for _ in range(N)]

for frame in range(200):
    oled.fill(BLACK)
    for i in range(N):
        px_a[i]+=pvx_a[i]; py_a[i]+=pvy_a[i]
        if px_a[i]<0 or px_a[i]>=W: pvx_a[i]=-pvx_a[i]
        if py_a[i]<0 or py_a[i]>=H: pvy_a[i]=-pvy_a[i]
        oled.fill_circle(int(px_a[i]), int(py_a[i]), pr_a[i], pc_a[i])
    oled.show()
    time.sleep_ms(20)

# Fin
oled.fill(BLACK)
oled.text("Exemple 4  OK ! ", 0, 60, GREEN)
oled.show()
print("Exemple 4 termine.")
