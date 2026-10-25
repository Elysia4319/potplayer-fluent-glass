"""Native rounded player and an idle-only live Windows acrylic backing window.

The player stays fully opaque during playback. No injection or DLL changes.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import time
from pathlib import Path

U=C.WinDLL('user32',use_last_error=True)
D=C.WinDLL('dwmapi',use_last_error=True)
G=C.WinDLL('gdi32',use_last_error=True)
U.SetProcessDPIAware()
U.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
U.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
U.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];U.GetWindowLongPtrW.restype=C.c_ssize_t
U.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];U.SetWindowLongPtrW.restype=C.c_ssize_t
U.SetWindowRgn.argtypes=[W.HWND,W.HRGN,W.BOOL]
U.GetWindowRgnBox.argtypes=[W.HWND,C.POINTER(W.RECT)]
U.IsWindow.argtypes=[W.HWND]
U.IsZoomed.argtypes=[W.HWND]
D.DwmSetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
D.DwmExtendFrameIntoClientArea.argtypes=[W.HWND,C.c_void_p]
D.DwmFlush.argtypes=[];D.DwmFlush.restype=C.c_long
U.SetLayeredWindowAttributes.argtypes=[W.HWND,W.COLORREF,W.BYTE,W.DWORD]
G.CreateRoundRectRgn.argtypes=[C.c_int]*6;G.CreateRoundRectRgn.restype=W.HRGN


class Accent(C.Structure):
    _fields_=[('state',C.c_int),('flags',C.c_int),('color',W.DWORD),('animation',C.c_int)]


class Composition(C.Structure):
    _fields_=[('attribute',C.c_int),('data',C.c_void_p),('size',C.c_size_t)]


class MonitorInfo(C.Structure):
    _fields_=[('size',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD)]


U.MonitorFromWindow.argtypes=[W.HWND,W.DWORD];U.MonitorFromWindow.restype=W.HANDLE
U.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(MonitorInfo)]


class PanelBounds:
    """Keep this preview's auxiliary windows inside their nearest work area.

    Window events only queue a correction. A short settle period lets PotPlayer
    finish docking/resizing, and an active user drag always takes precedence.
    """
    titles={'播放列表','控制窗口','控制面板','Playlist','Control Panel','Control panel'}

    def __init__(self,pid):
        self.pid=pid
        self.dragging=set()
        self.pending=0.0
        self.next_display_check=0.0
        self.displays=None

    def is_panel(self,window):
        owner=W.DWORD();U.GetWindowThreadProcessId(window,C.byref(owner))
        if owner.value!=self.pid:return False
        title=C.create_unicode_buffer(256);U.GetWindowTextW(window,title,256)
        return title.value in self.titles

    def queue(self):
        self.pending=time.perf_counter()+.15

    def event(self,event,window,object_id,child_id):
        if event==0xA:
            self.dragging.add(window)
        elif event==0xB:
            self.dragging.discard(window)
            self.queue()
        elif object_id==0 and child_id==0 and event in (0x8002,0x800B):
            self.queue()

    def display_layout(self):
        layout=[]
        @C.WINFUNCTYPE(W.BOOL,W.HANDLE,W.HDC,C.POINTER(W.RECT),W.LPARAM)
        def monitor(handle,dc,rectangle,data):
            info=MonitorInfo();info.size=C.sizeof(info)
            if U.GetMonitorInfoW(handle,C.byref(info)):
                r,w=info.monitor,info.work
                layout.append((r.left,r.top,r.right,r.bottom,w.left,w.top,w.right,w.bottom))
            return True
        U.EnumDisplayMonitors(None,None,monitor,0)
        return tuple(sorted(layout))

    def tick(self):
        now=time.perf_counter()
        self.dragging={window for window in self.dragging if U.IsWindow(window)}
        # Work areas can change without a player event (monitor unplug, taskbar,
        # resolution). Only a changed layout queues work; no continuous snapping.
        if now>=self.next_display_check:
            layout=self.display_layout()
            if self.displays is not None and layout!=self.displays:self.queue()
            self.displays=layout
            self.next_display_check=now+1
        if self.dragging or self.pending is None or now<self.pending:return
        self.pending=None
        panels=[]
        @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        def collect(window,_):
            if U.IsWindowVisible(window) and not U.IsIconic(window) and self.is_panel(window):panels.append(window)
            return True
        U.EnumWindows(collect,0)
        for window in panels:
            if not self.is_panel(window):continue
            r=W.RECT();U.GetWindowRect(window,C.byref(r))
            info=MonitorInfo();info.size=C.sizeof(info)
            if not U.GetMonitorInfoW(U.MonitorFromWindow(window,2),C.byref(info)):continue
            area=info.work
            width=min(r.right-r.left,area.right-area.left)
            height=min(r.bottom-r.top,area.bottom-area.top)
            if width<=0 or height<=0:continue
            left=max(area.left,min(r.left,area.right-width))
            top=max(area.top,min(r.top,area.bottom-height))
            if (left,top,width,height)!=(r.left,r.top,r.right-r.left,r.bottom-r.top):
                # Preserve activation and Z order. This may emit another location
                # event; the next pass is a no-op once the rectangle fits.
                U.SetWindowPos(window,None,left,top,width,height,0x14)


def main_window(pid):
    found=[]
    @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def cb(hwnd,_):
        p=W.DWORD();U.GetWindowThreadProcessId(hwnd,C.byref(p))
        name=C.create_unicode_buffer(128);U.GetClassNameW(hwnd,name,128)
        if p.value==pid and name.value=='PotPlayer64': found.append(hwnd)
        return True
    U.EnumWindows(cb,0)
    return found[0] if found else None


def apply(hwnd,mode='acrylic',region=False,alpha=255,key=False):
    results={}
    def attr(n,value):
        v=C.c_int(value)
        results[str(n)]=D.DwmSetWindowAttribute(hwnd,n,C.byref(v),4)
    U.SetWindowRgn(hwnd,None,True)
    attr(20,1)
    attr(33,2)
    if mode!='none':
        margins=(C.c_int*4)(-1,-1,-1,-1)
        results['extend']=D.DwmExtendFrameIntoClientArea(hwnd,margins)
        attr(38,3 if mode=='acrylic' else 2)
        policy=Accent(4 if mode=='acrylic' else 3,2,0xA0202020,0)
        data=Composition(19,C.cast(C.pointer(policy),C.c_void_p),C.sizeof(policy))
        U.SetWindowCompositionAttribute.argtypes=[W.HWND,C.POINTER(Composition)]
        results['accent']=U.SetWindowCompositionAttribute(hwnd,C.byref(data))
    if alpha<255 or key:
        old=U.GetWindowLongPtrW(hwnd,-20)
        U.SetWindowLongPtrW(hwnd,-20,old|0x80000)
        results['alpha']=U.SetLayeredWindowAttributes(hwnd,0x202020,alpha,3 if key else 2)
    if region:
        r=W.RECT();U.GetWindowRect(hwnd,C.byref(r))
        region=G.CreateRoundRectRgn(0,0,r.right-r.left+1,r.bottom-r.top+1,22,22)
        results['region']=U.SetWindowRgn(hwnd,region,True)
    U.RedrawWindow(hwnd,None,None,0x185)
    return results


LRESULT=C.c_ssize_t
PROC=C.WINFUNCTYPE(LRESULT,W.HWND,W.UINT,W.WPARAM,W.LPARAM)


class WC(C.Structure):
    _fields_=[('style',W.UINT),('proc',PROC),('extra',C.c_int),('wndextra',C.c_int),('instance',W.HINSTANCE),('icon',W.HICON),('cursor',W.HANDLE),('brush',W.HBRUSH),('menu',W.LPCWSTR),('name',W.LPCWSTR)]


U.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
U.ShowWindow.argtypes=[W.HWND,C.c_int]
U.IsIconic.argtypes=[W.HWND];U.IsWindowVisible.argtypes=[W.HWND]
U.GetDpiForWindow.argtypes=[W.HWND];U.GetDpiForWindow.restype=W.UINT
U.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
U.DefWindowProcW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];U.DefWindowProcW.restype=LRESULT
U.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p];U.CreateWindowExW.restype=W.HWND
U.RegisterClassW.argtypes=[C.POINTER(WC)]
U.DestroyWindow.argtypes=[W.HWND]
U.PeekMessageW.argtypes=[C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT]
U.DispatchMessageW.argtypes=[C.POINTER(W.MSG)];U.DispatchMessageW.restype=LRESULT
EVENTPROC=C.WINFUNCTYPE(None,W.HANDLE,W.DWORD,W.HWND,W.LONG,W.LONG,W.DWORD,W.DWORD)
U.SetWinEventHook.argtypes=[W.DWORD,W.DWORD,W.HMODULE,EVENTPROC,W.DWORD,W.DWORD,W.DWORD]
U.SetWinEventHook.restype=W.HANDLE
U.UnhookWinEvent.argtypes=[W.HANDLE]
U.MsgWaitForMultipleObjects.argtypes=[W.DWORD,C.POINTER(W.HANDLE),W.BOOL,W.DWORD,W.DWORD]


@PROC
def host_proc(hwnd,msg,wparam,lparam):
    if msg==0x14: return 1  # Do not cover the system material with a GDI brush.
    if msg==0x84: return -1  # Mouse input passes through.
    if msg==0x21: return 3  # The backing window never activates.
    return U.DefWindowProcW(hwnd,msg,wparam,lparam)


def verify_local_process(pid):
    k=C.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    k.CloseHandle.argtypes=[W.HANDLE]
    handle=k.OpenProcess(0x1000,False,pid)
    if not handle:raise RuntimeError('Preview process is unavailable')
    try:
        text=C.create_unicode_buffer(32768);size=W.DWORD(len(text))
        if not k.QueryFullProcessImageNameW(handle,0,text,C.byref(size)):raise C.WinError()
        expected=Path(__file__).resolve().parents[1]/'.runtime'/'PotPlayerMini64.exe'
        if Path(text.value).resolve()!=expected.resolve():
            raise RuntimeError('Only this project preview executable can be enhanced')
    finally:k.CloseHandle(handle)


def watch_bounds_only(pid,hwnd):
    """NoGlass still provides panel recovery without touching main composition."""
    bounds=PanelBounds(pid)
    @EVENTPROC
    def on_event(hook,event,window,object_id,child_id,thread,stamp):
        bounds.event(event,window,object_id,child_id)
    hooks=[U.SetWinEventHook(first,last,None,on_event,pid,0,2)
           for first,last in ((0xA,0xB),(0x8002,0x8002),(0x800B,0x800B))]
    if not all(hooks):
        for hook in hooks:
            if hook:U.UnhookWinEvent(hook)
        raise C.WinError()
    status=Path(__file__).resolve().parents[1]/'.runtime'/'window-effects.json'
    status.write_text(json.dumps({'pid':pid,'main':hwnd,'host':0,'mode':'bounds only',
                                 'startupOpacity':255},indent=2),encoding='utf-8')
    msg=W.MSG()
    try:
        while U.IsWindow(hwnd):
            owner=W.DWORD();U.GetWindowThreadProcessId(hwnd,C.byref(owner))
            if owner.value!=pid:break
            while U.PeekMessageW(C.byref(msg),None,0,0,1):
                U.TranslateMessage(C.byref(msg));U.DispatchMessageW(C.byref(msg))
            bounds.tick()
            U.MsgWaitForMultipleObjects(0,None,False,50,0x4FF)
    finally:
        for hook in hooks:U.UnhookWinEvent(hook)


def watch(pid,no_glass=False):
    verify_local_process(pid)
    for _ in range(100):
        hwnd=main_window(pid)
        if hwnd:break
        time.sleep(.1)
    else:raise RuntimeError('Player window did not appear')
    if no_glass:
        watch_bounds_only(pid,hwnd)
        return
    bounds=PanelBounds(pid)
    original=U.GetWindowLongPtrW(hwnd,-20)
    wc=WC(0,host_proc,0,0,None,None,None,None,None,f'FluentGlassMaterial{pid}')
    if not U.RegisterClassW(C.byref(wc)):raise C.WinError()
    host=U.CreateWindowExW(0x08000080|0x00200000,wc.name,'Fluent Glass material',0x80000000,0,0,100,100,None,None,None,None)
    if not host:raise C.WinError()
    results=apply(host,'acrylic',False)
    # Touch DWM preferences only. SetWindowRgn sends WM_WINDOWPOS messages which
    # PotPlayer handles by restoring its cached geometry, causing resize jumps.
    for number,value in ((20,1),(33,2)):
        setting=C.c_int(value)
        D.DwmSetWindowAttribute(hwnd,number,C.byref(setting),4)
    last_geometry=None
    last_mode=None
    moving=[False]
    release_at=[0.0]
    def round_panel(window):
        if bounds.is_panel(window):
            for number,value in ((20,1),(33,2)):
                setting=C.c_int(value)
                D.DwmSetWindowAttribute(window,number,C.byref(setting),4)
    @EVENTPROC
    def on_window_event(hook,event,window,object_id,child_id,thread,stamp):
        bounds.event(event,window,object_id,child_id)
        if window!=hwnd:
            if event==0x8002 and object_id==0:round_panel(window)
            return
        if event==0xA:
            moving[0]=True
            U.SetLayeredWindowAttributes(hwnd,0,255,2)
            # Complete the opaque composition before hiding the old backdrop.
            D.DwmFlush()
            U.ShowWindow(host,0)
        elif event==0xB:
            moving[0]=False
            # Keep the player opaque for one compositor settle interval after
            # mouse release; this prevents a stale backing position from ever
            # being revealed for a single frame.
            release_at[0]=time.perf_counter()+0.10
        elif event==0x800B and object_id==0 and child_id==0 and U.IsWindowVisible(host):
            position=W.RECT();U.GetWindowRect(hwnd,C.byref(position))
            U.SetWindowPos(host,hwnd,position.left,position.top,position.right-position.left,position.bottom-position.top,0x10)
    hooks=[U.SetWinEventHook(0xA,0xB,None,on_window_event,pid,0,2),U.SetWinEventHook(0x800B,0x800B,None,on_window_event,pid,0,2),U.SetWinEventHook(0x8002,0x8002,None,on_window_event,pid,0,2)]
    if not all(hooks):raise C.WinError()
    @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def existing_panel(window,_):
        owner=W.DWORD();U.GetWindowThreadProcessId(window,C.byref(owner))
        if owner.value==pid:round_panel(window)
        return True
    U.EnumWindows(existing_panel,0)
    status=Path(__file__).resolve().parents[1]/'.runtime'/'window-effects.json'
    msg=W.MSG()
    try:
        while U.IsWindow(hwnd) and U.IsWindow(host):
            while U.PeekMessageW(C.byref(msg),None,0,0,1):
                U.TranslateMessage(C.byref(msg));U.DispatchMessageW(C.byref(msg))
            bounds.tick()
            owner=W.DWORD();U.GetWindowThreadProcessId(hwnd,C.byref(owner))
            if owner.value!=pid:break
            r=W.RECT();U.GetWindowRect(hwnd,C.byref(r))
            width,height=r.right-r.left,r.bottom-r.top
            hidden=U.IsIconic(hwnd) or not U.IsWindowVisible(hwnd)
            title=C.create_unicode_buffer(1024);U.GetWindowTextW(hwnd,title,1024)
            dpi=U.GetDpiForWindow(hwnd) or 96
            monitor=MonitorInfo();monitor.size=C.sizeof(monitor)
            if not U.GetMonitorInfoW(U.MonitorFromWindow(hwnd,2),C.byref(monitor)):raise C.WinError()
            fullscreen=all(abs(a-b)<=2 for a,b in zip((r.left,r.top,r.right,r.bottom),(monitor.monitor.left,monitor.monitor.top,monitor.monitor.right,monitor.monitor.bottom)))
            square=bool(U.IsZoomed(hwnd) or fullscreen)
            geometry=(width,height,dpi,square)
            if geometry!=last_geometry:
                # Native composition rounds the entire window without a region mask.
                preference=C.c_int(1 if square else 2)
                D.DwmSetWindowAttribute(hwnd,33,C.byref(preference),4)
                last_geometry=geometry
            # Any loaded media keeps the player fully opaque, including black pixels.
            mode='startup acrylic' if title.value=='PotPlayer' and not hidden and not square and not moving[0] and time.perf_counter()>=release_at[0] else 'opaque playback'
            if mode!=last_mode:
                if mode=='startup acrylic':
                    # Release transition: establish the aligned backing surface
                    # before exposing any player transparency.
                    U.SetWindowPos(host,hwnd,r.left,r.top,width,height,0x10|0x40)
                    U.ShowWindow(host,8)
                    U.SetWindowPos(host,hwnd,r.left,r.top,width,height,0x10|0x40)
                    # A visible Win32 window is not yet a completed DWM frame.
                    # Let Acrylic compose at its final position while the player
                    # remains opaque, then reveal only the finished material.
                    D.DwmFlush()
                    D.DwmFlush()
                    if U.IsWindowVisible(host) and U.IsWindow(host):
                        U.SetWindowLongPtrW(hwnd,-20,original|0x80000)
                        U.SetLayeredWindowAttributes(hwnd,0,200,2)
                    else:
                        # Never expose transparency while the backing surface
                        # failed to become visible in the same transition.
                        U.SetLayeredWindowAttributes(hwnd,0,255,2)
                        U.SetWindowLongPtrW(hwnd,-20,original)
                else:
                    U.SetLayeredWindowAttributes(hwnd,0,255,2)
                    D.DwmFlush()
                    U.SetWindowLongPtrW(hwnd,-20,original)
                status.write_text(json.dumps({'pid':pid,'main':hwnd,'host':host,'mode':mode,'corners':'native DWM round','startupOpacity':200,'apiResults':results},indent=2),encoding='utf-8')
                last_mode=mode
            if mode=='startup acrylic':
                # Behind the player in the current Z order; never bring it to front.
                U.SetWindowPos(host,hwnd,r.left,r.top,width,height,0x10|0x40)
            else:
                U.ShowWindow(host,0)
            U.MsgWaitForMultipleObjects(0,None,False,16,0x4FF)
    finally:
        for hook in hooks:U.UnhookWinEvent(hook)
        if U.IsWindow(hwnd):
            U.SetLayeredWindowAttributes(hwnd,0,255,2)
            U.SetWindowLongPtrW(hwnd,-20,original)
        U.DestroyWindow(host)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('pid',type=int)
    p.add_argument('--no-glass',action='store_true',help='Only recover off-screen auxiliary windows')
    args=p.parse_args()
    k=C.WinDLL('kernel32',use_last_error=True)
    k.CreateMutexW.argtypes=[C.c_void_p,W.BOOL,W.LPCWSTR];k.CreateMutexW.restype=W.HANDLE
    k.CloseHandle.argtypes=[W.HANDLE]
    mutex=k.CreateMutexW(None,False,f'Local\\FluentGlass-{args.pid}')
    if not mutex:raise C.WinError()
    try:
        if C.get_last_error()!=183:watch(args.pid,args.no_glass)
    finally:k.CloseHandle(mutex)
