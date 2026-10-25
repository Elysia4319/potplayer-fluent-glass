"""Create a short, silent, original MJPEG AVI without external video tools."""
from pathlib import Path
import io
import struct
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]


def chunk(tag,data):
    return tag+struct.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')


def make():
    w,h,fps,count=640,360,12,360
    frames=[]
    index=[]
    offset=4
    for i in range(count):
        im=Image.new('RGB',(w,h),'#111923')
        d=ImageDraw.Draw(im)
        d.rounded_rectangle((30,30,w-30,h-30),20,outline='#33495E',width=2)
        d.text((52,50),'Fluent Glass / playback check',fill='#B9DFFF',font_size=22)
        x=60+int((w-120)*(i%fps*4)/(fps*4))
        d.ellipse((x-20,150,x+20,190),fill='#8CCBFF')
        d.text((52,260),f'Frame {i:03d}   {i/fps:05.1f} s',fill='#9EAFC1',font_size=18)
        b=io.BytesIO(); im.save(b,format='JPEG',quality=85)
        jpeg=b.getvalue()
        data=chunk(b'00dc',jpeg)
        frames.append(data)
        index.append(struct.pack('<4sIII',b'00dc',0x10,offset,len(jpeg)))
        offset+=len(data)
    avih=struct.pack('<14I',int(1e6/fps),1_000_000,0,0x10,count,0,1,w*h*3,w,h,0,0,0,0)
    strh=struct.pack('<4s4sIHHIIIIIIIIhhhh',b'vids',b'MJPG',0,0,0,0,1,fps,0,count,w*h*3,0xffffffff,0,0,0,w,h)
    strf=struct.pack('<IiiHH4sIiiII',40,w,h,1,24,b'MJPG',w*h*3,0,0,0,0)
    hdrl=chunk(b'LIST',b'hdrl'+chunk(b'avih',avih)+chunk(b'LIST',b'strl'+chunk(b'strh',strh)+chunk(b'strf',strf)))
    body=b'AVI '+hdrl+chunk(b'LIST',b'movi'+b''.join(frames))+chunk(b'idx1',b''.join(index))
    out=ROOT/'qa'/'playback-check.avi'
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(chunk(b'RIFF',body))
    print(f'Created {out.name}: {w}x{h}, {fps} fps, {count/fps:g} sec, silent MJPEG AVI')


if __name__=='__main__':
    make()
