"""Operate and capture only the project's preview windows for native UI QA."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import time
import json
from PIL import Image,ImageChops,ImageStat

from native_window import U,windows,capture_window
from window_effects import verify_local_process

ROOT=Path(__file__).resolve().parents[1]


def click(hwnd,x,y):
    U.ShowWindow(hwnd,9)
    U.SetWindowPos(hwnd,W.HWND(-1),0,0,0,0,0x43)
    time.sleep(.08)
    point=W.POINT(round(x),round(y));U.ClientToScreen(hwnd,C.byref(point))
    target=U.WindowFromPoint(point);a=W.DWORD();b=W.DWORD()
    U.GetWindowThreadProcessId(hwnd,C.byref(a));U.GetWindowThreadProcessId(target,C.byref(b))
    assert a.value==b.value,'Click would hit another application'
    old=W.POINT();U.GetCursorPos(C.byref(old))
    try:
        U.SetCursorPos(point.x,point.y);U.mouse_event(2,0,0,0,0);U.mouse_event(4,0,0,0,0)
        time.sleep(.1)
    finally:
        U.SetCursorPos(old.x,old.y)
        U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('action',choices=['controls','mini','pages','verify-controls','menu','playlist','capture-mini','standard','capture-fullscreen']);args=p.parse_args()
    verify_local_process(args.pid)
    main=next(w for w in windows(args.pid,True) if w['cls']=='PotPlayer64')['hwnd']
    if U.IsIconic(main) or not U.IsWindowVisible(main):
        U.ShowWindow(main,9);time.sleep(.2)
    r=W.RECT();U.GetClientRect(main,C.byref(r));s=U.GetDpiForWindow(main)/96
    if args.action=='controls':click(main,130*s,r.bottom-42*s)
    elif args.action=='mini':click(main,86*s,r.bottom-42*s)
    elif args.action=='standard':click(main,r.right-150*s,18*s)
    elif args.action=='capture-mini':capture_window(main,ROOT/'qa'/'complete-mini.png')
    elif args.action=='capture-fullscreen':capture_window(main,ROOT/'qa'/'complete-fullscreen.png')
    elif args.action=='playlist':
        w=next(w for w in windows(args.pid) if w['title']=='播放列表')
        capture_window(w['hwnd'],ROOT/'qa'/'complete-playlist.png')
    elif args.action=='verify-controls':
        w=next(w for w in windows(args.pid,True) if w['title'] in ('控制窗口','控制面板') or (w['cls'].startswith('Afx:') and 500 <= w['rect'][2]-w['rect'][0] <= 560 and 480 <= w['rect'][3]-w['rect'][1] <= 540))
        hwnd=w['hwnd'];scale=U.GetDpiForWindow(hwnd)/96
        click(hwnd,254*scale,71*scale);time.sleep(.15)
        before=ROOT/'qa'/'subtitle-size-before.png';capture_window(hwnd,before)
        click(hwnd,284*scale,200*scale)
        U.SetCursorPos(10,10);time.sleep(.15)
        after=ROOT/'qa'/'subtitle-size-after.png';capture_window(hwnd,after)
        bbox=tuple(round(v*scale) for v in (178,184,238,216))
        change=ImageStat.Stat(ImageChops.difference(Image.open(before).crop(bbox),Image.open(after).crop(bbox))).sum
        assert sum(change)>100,'Subtitle size label must change after Increase'
        click(hwnd,132*scale,200*scale)
        click(hwnd,158*scale,71*scale);time.sleep(.15)
        before=ROOT/'qa'/'video-slider-before.png';capture_window(hwnd,before)
        click(hwnd,130*scale,127*scale);U.SetCursorPos(10,10);time.sleep(.15)
        after=ROOT/'qa'/'video-slider-after.png';capture_window(hwnd,after)
        bbox=tuple(round(v*scale) for v in (106,119,310,135))
        sliderchange=sum(ImageStat.Stat(ImageChops.difference(Image.open(before).crop(bbox),Image.open(after).crop(bbox))).sum)
        assert sliderchange>100,'Video brightness slider must respond to a real click'
        click(hwnd,350*scale,127*scale)
        click(hwnd,254*scale,71*scale);time.sleep(.1)
        click(hwnd,260*scale,120*scale);time.sleep(.2)
        dialogs=[w for w in windows(args.pid) if w['cls']=='#32770']
        assert dialogs,'Subtitle font button must open a native font dialog'
        for dialog in dialogs:U.PostMessageW(dialog['hwnd'],0x10,0,0)
        result={'subtitleSizeResponds':True,'videoSliderResponds':True,'fontDialogOpens':True}
        (ROOT/'qa'/'secondary-native-checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
    elif args.action=='menu':
        U.SetWindowPos(main,W.HWND(-1),0,0,0,0,0x43)
        r=W.RECT();U.GetWindowRect(main,C.byref(r))
        U.SetCursorPos(r.left+round(r.right-r.left)*2//3,r.top+120)
        U.mouse_event(8,0,0,0,0);U.mouse_event(16,0,0,0,0);time.sleep(.2)
        menus=[w for w in windows(args.pid) if w['cls']=='#32768']
        if menus:
            capture_window(menus[0]['hwnd'],ROOT/'qa'/'complete-menu.png')
            U.PostMessageW(main,0x100,0x1B,0)
        else:
            # Some versions render the skinned popup as a normal custom window.
            w=max((w for w in windows(args.pid) if w['hwnd']!=main and w['title']==''),key=lambda w:(w['rect'][2]-w['rect'][0])*(w['rect'][3]-w['rect'][1]))
            capture_window(w['hwnd'],ROOT/'qa'/'complete-menu.png')
        U.SetWindowPos(main,W.HWND(-2),0,0,0,0,0x43)
    elif args.action=='pages':
        w=next(w for w in windows(args.pid,True) if w['title']=='控制窗口' or w['title']=='控制面板' or (w['cls'].startswith('Afx:') and 500 <= w['rect'][2]-w['rect'][0] <= 560 and 480 <= w['rect'][3]-w['rect'][1] <= 540))
        scale=U.GetDpiForWindow(w['hwnd'])/96
        for i,name in enumerate(('audio','video','subtitle','playback')):
            click(w['hwnd'],(62+96*i)*scale,71*scale);time.sleep(.15)
            capture_window(w['hwnd'],ROOT/'qa'/f'complete-controls-{name}.png')
        print('Captured four native control pages')
