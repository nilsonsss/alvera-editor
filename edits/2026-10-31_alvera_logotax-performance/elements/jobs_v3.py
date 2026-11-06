import json,os
A=os.path.expanduser('~/Documents/Alvera'); V=A+'/SHOOTS/NO1/VIDS/'; L=A+'/LUTS/ALVERA_0915_match.cube'
FIN="split[a][b];[b]lutyuv=y='if(gt(val,205),val,16)',gblur=sigma=22[g];[a][g]blend=c0_mode=screen:c0_opacity=0.16:c1_opacity=0:c2_opacity=0,noise=c0s=5:c0f=t,vignette=PI/7"
UP="eq=gamma=1.18,unsharp=5:5:0.4,"
def j(n,c,in_,dur,**k):
    d=dict(src=V+c+'.MP4',**{'in':in_},dur=round(dur,3),fps=24,speed=0.48,canvas=[1080,1920],lut=L,finish=FIN,grade_extra="unsharp=5:5:0.4,",smooth=1.0);d.update(k)
    json.dump(d,open(f'elements/clips/{n}.json','w'),indent=1)
j('01a','C7348',0.6,2.56,grade_extra=UP,rotate='ccw',punch=1.08,push=[1,1.05],center=[.5,.47])
j('01b','C7348',1.83,2.0,grade_extra=UP,rotate='ccw',punch=1.8,push=[1,1.05],center=[.5,.47])
j('02','C7328',0.6,3.1,punch=1.08,push=[1,1.08])
j('03','C7361',0.4,1.73,punch=1.08,push=[1,1.05])
j('04','C7366',0.2,3.01,punch=1.05,push=[1,1.08])
j('05','C7323',1.0,2.01,rotate='cw',punch=1.08,push=[1.2,1.0])
j('06','C7330',0.93,1.75,punch=1.08,push=[1,1.05])
j('07','C7344',0.3,3.22,punch=1.08,push=[1,1.1])
j('08','C7325',0.5,2.06,punch=1.08,push=[1.08,1])
j('09a','C7320',0.5,1.13,rotate='cw',punch=1.1,push=[1,1.03],center=[.5,.56])
j('09b','',0,1.6,src=os.getcwd()+'/elements/wrist_upright.jpg',lut=None,speed=1.0,punch=1.25,push=[1,1.06],center=[.48,.58],grade_extra="eq=saturation=0.55:contrast=1.14:brightness=-0.05,colorbalance=rm=-0.04:bm=0.03,")
j('10','C7319',1.2,2.37,rotate='cw',punch=1.15,push=[1,1.08])
j('11','C7347',0.6,2.49,grade_extra=UP,rotate='ccw',punch=1.08,push=[1.05,1],center=[.5,.48])
