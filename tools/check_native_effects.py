"""Integration checks against actual external Win32 window state."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import time
from window_effects import U,D,G,main_window,verify_local_process

ROOT=Path(__file__).resolve().parents[1]
U.GetWindowRgn.argtypes=[W.HWND,W.HRGN]
U.GetLayeredWindowAttributes.argtypes=[W.HWND,C.POINTER(W.COLORREF),C.POINTER(W.BYTE),C.POINTER(W.DWORD)]
G.CreateRectRgn.argtypes=[C.c_int]*4;G.CreateRectRgn.restype=W.HRGN
G.PtInRegion.argtypes=[W.HRGN,C.c_int,C.c_int]
G.DeleteObject.argtypes=[W.HGDIOBJ]
D.DwmGetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]


def check(pid,expect):
    verify_local_process(pid)
    state=json.loads((ROOT/'.runtime'/'window-effects.json').read_text())
    assert state['pid']==pid,'Stale enhancer status'
    hwnd=main_window(pid);host=state['host']
    assert hwnd==state['main']
    r=W.RECT();U.GetWindowRect(hwnd,C.byref(r));width,height=r.right-r.left,r.bottom-r.top
    region=G.CreateRectRgn(0,0,0,0)
    kind=U.GetWindowRgn(hwnd,region)
    corners=[bool(G.PtInRegion(region,x,y)) for x,y in [(0,0),(width-1,0),(0,height-1),(width-1,height-1)]]
    center=bool(G.PtInRegion(region,width//2,height//2))
    G.DeleteObject(region)
    preference=C.c_int()
    assert D.DwmGetWindowAttribute(hwnd,33,C.byref(preference),4)==0
    if expect in ('idle','playback'):
        assert preference.value==2,'Native DWM rounding is not requested'
    if expect=='idle':
        assert state['mode']=='startup acrylic'
        assert U.IsWindowVisible(host),'Acrylic surface hidden'
        hr=W.RECT();U.GetWindowRect(host,C.byref(hr))
        assert [r.left,r.top,r.right,r.bottom]==[hr.left,hr.top,hr.right,hr.bottom],'Backdrop does not follow the player'
        key=W.COLORREF();alpha=W.BYTE();flags=W.DWORD()
        assert U.GetLayeredWindowAttributes(hwnd,C.byref(key),C.byref(alpha),C.byref(flags))
        assert alpha.value==200 and flags.value==2,'Idle opacity incorrect'
    else:
        assert state['mode']=='opaque playback'
        assert not U.IsWindowVisible(host),'Backdrop leaked into playback/minimized/fullscreen'
        assert not U.GetWindowLongPtrW(hwnd,-20)&0x80000,'Player did not restore opaque composition'
    if expect=='playback':
        text=C.create_unicode_buffer(1024);U.GetWindowTextW(hwnd,text,1024)
        assert text.value!='PotPlayer' and text.value,'No media loaded'
        assert U.IsWindowVisible(hwnd) and not U.IsIconic(hwnd),'Playback window is hidden'
    if expect=='hidden':assert U.IsIconic(hwnd)
    if expect=='fullscreen':assert preference.value==1,'Fullscreen must have square edges'
    return {'expect':expect,'mode':state['mode'],'windowSize':[width,height],'nativeCornerPreference':preference.value,'passed':True}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('expect',choices=['idle','playback','hidden','fullscreen']);args=p.parse_args()
    for attempt in range(20):
        try:
            result=check(args.pid,args.expect);break
        except (AssertionError,FileNotFoundError) as exc:
            if attempt==19:raise
            time.sleep(.12)
    out=ROOT/'qa'/'native-checks-v2.json'
    results=json.loads(out.read_text()) if out.exists() else []
    results.append(result);out.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(result))
