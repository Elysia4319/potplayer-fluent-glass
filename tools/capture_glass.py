"""Capture the actual desktop compositor over our own controlled QA background."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import time
from PIL import ImageGrab
from native_window import U,windows

p=argparse.ArgumentParser()
p.add_argument('pid',type=int)
p.add_argument('background_pid',type=int)
p.add_argument('output',type=Path)
p.add_argument('--host',type=int)
args=p.parse_args()
main=next(w for w in windows(args.pid) if w['cls']=='PotPlayer64')['hwnd']
background=max(windows(args.background_pid),key=lambda w:(w['rect'][2]-w['rect'][0])*(w['rect'][3]-w['rect'][1]))['hwnd']
U.ShowWindow(main,9)
U.MoveWindow(background,40,40,1320,850,True)
U.MoveWindow(main,100,100,1120,725,True)
U.SetWindowPos(background,W.HWND(-1),0,0,0,0,0x43)
if args.host:
    U.MoveWindow(args.host,100,100,1120,725,True)
    U.SetWindowPos(args.host,W.HWND(-1),0,0,0,0,0x53)
U.SetWindowPos(main,W.HWND(-1),0,0,0,0,0x43)
time.sleep(.7)
r=W.RECT();U.GetWindowRect(main,C.byref(r))
br=W.RECT();U.GetWindowRect(background,C.byref(br))
assert br.left<=r.left-14 and br.top<=r.top-14 and br.right>=r.right+14 and br.bottom>=r.bottom+14,'QA background does not cover crop'
args.output.parent.mkdir(exist_ok=True,parents=True)
ImageGrab.grab(bbox=(r.left-14,r.top-14,r.right+14,r.bottom+14),all_screens=True).save(args.output)
U.SetWindowPos(main,W.HWND(-2),0,0,0,0,0x43)
U.SetWindowPos(background,W.HWND(-2),0,0,0,0,0x43)
if args.host:
    U.SetWindowPos(args.host,W.HWND(-2),0,0,0,0,0x53)
print('Saved compositor capture',args.output.name)
