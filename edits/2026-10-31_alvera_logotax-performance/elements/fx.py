# Impact effects baked into one clip: zoom punch + decaying shake + colour flash at clip time T.
import subprocess,sys,os
src,out,T,flash=sys.argv[1],sys.argv[2],float(sys.argv[3]),sys.argv[4]
k=f"gte(it,{T})*exp(-(it-{T})*9)"
z=f"1.03+0.07*{k}"
dx=f"28*{k}*sin((it-{T})*95)"; dy=f"20*{k}*cos((it-{T})*80)"
vf=(f"scale=2160:3840:flags=lanczos,zoompan=z='{z}':x='iw/2-iw/zoom/2+{dx}':y='ih/2-ih/zoom/2+{dy}':d=1:s=1080x1920:fps=24,"
    f"drawbox=x=0:y=0:w=iw:h=ih:color={flash}@0.45:t=fill:enable='between(t,{T},{T+0.042})',"
    f"drawbox=x=0:y=0:w=iw:h=ih:color={flash}@0.18:t=fill:enable='between(t,{T+0.042},{T+0.125})',setsar=1")
subprocess.run([os.path.expanduser('~/.local/bin/ffmpeg'),'-nostdin','-v','error','-y','-i',src,'-vf',vf,'-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',out],check=True)
