"""Small local Win32 QA utility. Does not automate unrelated windows."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
from PIL import Image

U=C.WinDLL('user32',use_last_error=True)
U.SetProcessDPIAware()
U.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
U.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
U.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
U.IsWindowVisible.argtypes=[W.HWND]
U.SetForegroundWindow.argtypes=[W.HWND]
U.MoveWindow.argtypes=[W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.BOOL]
U.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
U.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
U.SendMessageW.restype=W.LPARAM
U.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.GetDpiForWindow.argtypes=[W.HWND]
U.GetDpiForWindow.restype=W.UINT
U.IsIconic.argtypes=[W.HWND]
U.ShowWindow.argtypes=[W.HWND,C.c_int]
U.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
U.WindowFromPoint.argtypes=[W.POINT]
U.WindowFromPoint.restype=W.HWND
U.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
U.ScreenToClient.argtypes=[W.HWND,C.POINTER(W.POINT)]


def windows(pid,include_hidden=False):
    found=[]
    @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def cb(hwnd,unused):
        p=W.DWORD()
        U.GetWindowThreadProcessId(hwnd,C.byref(p))
        if p.value==pid and (include_hidden or U.IsWindowVisible(hwnd)):
            name=C.create_unicode_buffer(512)
            cls=C.create_unicode_buffer(128)
            r=W.RECT()
            U.GetWindowTextW(hwnd,name,512)
            U.GetClassNameW(hwnd,cls,128)
            U.GetWindowRect(hwnd,C.byref(r))
            found.append(dict(hwnd=hwnd,title=name.value,cls=cls.value,rect=[r.left,r.top,r.right,r.bottom]))
        return True
    U.EnumWindows(cb,0)
    return found


def capture_window(hwnd,path):
    """Capture this window via WM_PRINT, never another app covering its rectangle."""
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    g=C.WinDLL('gdi32',use_last_error=True)
    U.GetWindowDC.argtypes=[W.HWND]; U.GetWindowDC.restype=W.HDC
    U.ReleaseDC.argtypes=[W.HWND,W.HDC]
    U.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT]
    g.CreateCompatibleDC.argtypes=[W.HDC];g.CreateCompatibleDC.restype=W.HDC
    g.CreateCompatibleBitmap.argtypes=[W.HDC,C.c_int,C.c_int];g.CreateCompatibleBitmap.restype=W.HBITMAP
    g.SelectObject.argtypes=[W.HDC,W.HGDIOBJ];g.SelectObject.restype=W.HGDIOBJ
    g.DeleteObject.argtypes=[W.HGDIOBJ];g.DeleteDC.argtypes=[W.HDC]
    g.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,C.c_void_p,C.c_void_p,W.UINT]
    r=W.RECT();U.GetWindowRect(hwnd,C.byref(r));w,h=r.right-r.left,r.bottom-r.top
    dc=U.GetWindowDC(hwnd);mem=g.CreateCompatibleDC(dc);bmp=g.CreateCompatibleBitmap(dc,w,h)
    old=g.SelectObject(mem,bmp)
    try:
        if not U.PrintWindow(hwnd,mem,2): raise RuntimeError('PrintWindow failed')
        import struct
        info=C.create_string_buffer(struct.pack('<IiiHHIIiiII',40,w,-h,1,32,0,w*h*4,0,0,0,0))
        buf=C.create_string_buffer(w*h*4)
        if not g.GetDIBits(mem,bmp,0,h,buf,info,0): raise RuntimeError('GetDIBits failed')
        Image.frombytes('RGB',(w,h),buf.raw,'raw','BGRX').save(path)
    finally:
        g.SelectObject(mem,old);g.DeleteObject(bmp);g.DeleteDC(mem);U.ReleaseDC(hwnd,dc)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('pid',type=int)
    p.add_argument('--capture',type=Path)
    p.add_argument('--size',nargs=2,type=int)
    p.add_argument('--close',action='store_true')
    p.add_argument('--click',choices=['open','playlist','play','next','prev','mute','fullscreen','seek','volume'])
    p.add_argument('--drop',type=Path)
    p.add_argument('--key',type=lambda s:int(s,0))
    args=p.parse_args()
    ws=windows(args.pid,include_hidden=True)
    print(json.dumps([w for w in ws if w['cls']=='PotPlayer64' or U.IsWindowVisible(w['hwnd'])],ensure_ascii=False))
    if ws:
        win=next((w for w in ws if w['cls']=='PotPlayer64'),max(ws,key=lambda x:(x['rect'][2]-x['rect'][0])*(x['rect'][3]-x['rect'][1])))
        hwnd=win['hwnd']
        if not args.close and (U.IsIconic(hwnd) or not U.IsWindowVisible(hwnd)):
            U.ShowWindow(hwnd,9)
            import time
            for _ in range(30):
                if not U.IsIconic(hwnd) and U.IsWindowVisible(hwnd):break
                time.sleep(.03)
        if args.click:
            rect=W.RECT()
            U.GetClientRect(hwnd,C.byref(rect))
            width,height=rect.right,rect.bottom
            scale=U.GetDpiForWindow(hwnd)/96
            positions={
                'open':(width/2,36*scale+(height-144*scale)/2+16*scale),
                'playlist':(width-85*scale,height-42*scale),
                'play':(width/2,height-42*scale),
                'next':(width/2+112*scale,height-42*scale),
                'prev':(width/2-112*scale,height-42*scale),
                'mute':(width-222*scale,height-42*scale),
                'fullscreen':(width-42*scale,height-42*scale),
                'seek':(width*.55,height-94*scale),
                'volume':(width-142*scale,height-42*scale),
            }
            x,y=map(round,positions[args.click])
            U.SetForegroundWindow(hwnd)
            # Bring only the selected preview window above other windows.
            U.SetWindowPos(hwnd,W.HWND(-1),0,0,0,0,0x43)
            point=W.POINT(x,y)
            U.ClientToScreen(hwnd,C.byref(point))
            target=U.WindowFromPoint(point)
            owner=W.DWORD()
            U.GetWindowThreadProcessId(target,C.byref(owner))
            if owner.value!=args.pid:
                U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)
                raise RuntimeError('Target is covered by another application; no click sent')
            old=W.POINT()
            U.GetCursorPos(C.byref(old))
            try:
                U.SetCursorPos(point.x,point.y)
                U.mouse_event(2,0,0,0,0)
                U.mouse_event(4,0,0,0,0)
                import time
                time.sleep(.15)
            finally:
                U.SetCursorPos(old.x,old.y)
                U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)
        if args.key is not None:
            U.PostMessageW(hwnd,0x100,args.key,0)
            U.PostMessageW(hwnd,0x101,args.key,0)
        if args.drop:
            import struct
            k=C.WinDLL('kernel32',use_last_error=True)
            k.GlobalAlloc.argtypes=[W.UINT,C.c_size_t]
            k.GlobalAlloc.restype=W.HGLOBAL
            k.GlobalLock.argtypes=[W.HGLOBAL]
            k.GlobalLock.restype=C.c_void_p
            k.GlobalUnlock.argtypes=[W.HGLOBAL]
            payload=struct.pack('<IiiII',20,0,0,0,1)+(str(args.drop.resolve())+'\0\0').encode('utf-16le')
            handle=k.GlobalAlloc(0x42,len(payload))
            ptr=k.GlobalLock(handle)
            C.memmove(ptr,payload,len(payload))
            k.GlobalUnlock(handle)
            U.PostMessageW(hwnd,0x233,handle,0)
        if args.size:
            U.MoveWindow(hwnd,100,100,*args.size,True)
        if args.capture:
            args.capture.parent.mkdir(exist_ok=True,parents=True)
            capture_window(hwnd,args.capture)
        if args.close:
            U.PostMessageW(hwnd,0x10,0,0)
