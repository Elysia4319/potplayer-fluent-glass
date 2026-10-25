"""User-visible regressions exercised against the running preview window."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
import time
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from native_window import U,windows,capture_window
from PIL import Image,ImageGrab

PLAYER_PID=None
U.GetForegroundWindow.restype=W.HWND
class MONITORINFO(C.Structure):
    _fields_=[('cbSize',W.DWORD),('rcMonitor',W.RECT),('rcWork',W.RECT),('flags',W.DWORD)]
U.MonitorFromWindow.argtypes=[W.HWND,W.DWORD];U.MonitorFromWindow.restype=W.HANDLE
U.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(MONITORINFO)]
U.GetLayeredWindowAttributes.argtypes=[W.HWND,C.POINTER(W.COLORREF),C.POINTER(W.BYTE),C.POINTER(W.DWORD)]
U.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];U.GetWindowLongPtrW.restype=C.c_ssize_t


def rect(hwnd):
    r=W.RECT();U.GetWindowRect(hwnd,C.byref(r))
    return (r.left,r.top,r.right,r.bottom)


def player():
    return next(w['hwnd'] for w in windows(PLAYER_PID,True) if w['cls']=='PotPlayer64')


def material_windows():
    found=[]
    @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def cb(h,_):
        text=C.create_unicode_buffer(256);U.GetWindowTextW(h,text,256)
        if text.value=='Fluent Glass material' and U.IsWindowVisible(h):found.append(h)
        return True
    U.EnumWindows(cb,0)
    return found


def front(hwnd):
    U.ShowWindow(hwnd,9)
    U.SetWindowPos(hwnd,W.HWND(-1),0,0,0,0,0x43)
    U.SetForegroundWindow(hwnd)
    time.sleep(.15)


def click_client(hwnd,cx,cy):
    U.ShowWindow(hwnd,9)
    U.SetWindowPos(hwnd,W.HWND(-1),0,0,0,0,0x43)
    time.sleep(.1)
    point=W.POINT(round(cx),round(cy));U.ClientToScreen(hwnd,C.byref(point))
    target=U.WindowFromPoint(point);a=W.DWORD();b=W.DWORD()
    U.GetWindowThreadProcessId(hwnd,C.byref(a));U.GetWindowThreadProcessId(target,C.byref(b))
    assert a.value==b.value,'Click would hit another application'
    old=W.POINT();U.GetCursorPos(C.byref(old))
    try:
        U.SetCursorPos(point.x,point.y);U.mouse_event(2,0,0,0,0);U.mouse_event(4,0,0,0,0)
        time.sleep(.12)
    finally:
        U.SetCursorPos(old.x,old.y)
        U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)


def playlist():
    return next((w for w in windows(PLAYER_PID) if w['title']=='播放列表'),None)


class NativeRegressions(unittest.TestCase):
    def test_playlist_search_has_visible_frame_and_magnifier(self):
        win=playlist();self.assertIsNotNone(win,'Playlist must be open')
        ph=win['hwnd'];scale=U.GetDpiForWindow(ph)/96
        path=ROOT/'qa'/'playlist-search-check.png';capture_window(ph,path)
        im=Image.open(path).convert('L')
        # Search occupies the row immediately under the 48px title bar.
        top=round(54*scale);bottom=round(84*scale)
        x=im.width//2
        border=max(im.getpixel((x,y)) for y in range(top-1,top+3))
        fill=im.getpixel((x,(top+bottom)//2))
        icon=im.crop(tuple(round(v*scale) for v in (26,61,44,79)))
        self.assertGreater(border-fill,20,'Search field needs a visible outline')
        self.assertGreater(sum(v>100 for v in icon.tobytes()),15,
                           'Search field needs a visible magnifying glass')

    def test_video_text_sliders_and_actions_are_centered_in_rows(self):
        from qa_secondary import click
        panel=next(w for w in windows(PLAYER_PID,True) if w['title']=='控制面板')
        ph=panel['hwnd'];scale=U.GetDpiForWindow(ph)/96
        click(ph,158*scale,71*scale);U.SetCursorPos(10,10);time.sleep(.15)
        path=ROOT/'qa'/'panel-row-centers.png';capture_window(ph,path)
        im=Image.open(path).convert('L')
        for row in range(4):
            top=104+46*row;expected=(top+23)*scale
            for name,left,right in (('label',32,92),('slider',106,310),('action',322,396)):
                with self.subTest(row=row,control=name):
                    box=tuple(round(v*scale) for v in (left,top,right,top+46))
                    ink=im.crop(box).point(lambda v:255 if v>180 else 0).getbbox()
                    self.assertIsNotNone(ink,'Row content must be visible')
                    center=box[1]+(ink[1]+ink[3])/2
                    self.assertLessEqual(abs(center-expected),2,
                                         f'{name} must align with its row center')

    def test_playlist_search_filters_and_clear_restores_media(self):
        ph=playlist()['hwnd'];edits=[]
        @C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
        def child(h,_):
            name=C.create_unicode_buffer(128);U.GetClassNameW(h,name,128)
            if name.value=='Edit' and U.IsWindowVisible(h):edits.append(h)
            return True
        U.EnumChildWindows(ph,child,0)
        self.assertEqual(len(edits),1,'Search must contain a real native text input')
        old=C.create_unicode_buffer(1024);U.GetWindowTextW(edits[0],old,1024)
        scale=U.GetDpiForWindow(ph)/96
        def query(text):
            payload=C.create_unicode_buffer(text)
            U.SendMessageW(edits[0],0xC,0,C.cast(payload,C.c_void_p).value)
            time.sleep(.5)
            path=ROOT/'qa'/('search-no-results.png' if text else 'search-results.png')
            capture_window(ph,path);im=Image.open(path).convert('L')
            body=im.crop((round(12*scale),round(124*scale),
                          im.width-round(12*scale),round(150*scale)))
            return sum(v>180 for v in body.tobytes())
        try:
            before=query('')
            self.assertGreater(before,30,'Load the playback-check fixture before running search QA')
            filtered=query('zzzz-fluent-no-match')
            restored=query('')
            self.assertLess(filtered,10,'A non-matching query must hide the media row')
            self.assertGreater(restored,before*.8,'Clearing search must restore the media row')
            result={'beforeInkPixels':before,'filteredInkPixels':filtered,
                    'restoredInkPixels':restored,'nativeInput':True}
            (ROOT/'qa'/'playlist-search-functional.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result))
        finally:
            payload=C.create_unicode_buffer(old.value)
            U.SendMessageW(edits[0],0xC,0,C.cast(payload,C.c_void_p).value)

    def test_glass_returns_after_drag(self):
        hwnd=player();front(hwnd)
        U.MoveWindow(hwnd,200,150,1120,725,True);time.sleep(.2)
        r=rect(hwnd);x,y=r[0]+250,r[1]+22
        old=W.POINT();U.GetCursorPos(C.byref(old))
        try:
            U.SetCursorPos(x,y);U.mouse_event(2,0,0,0,0);time.sleep(.04)
            for i in range(1,17):
                U.SetCursorPos(x+i*8,y+i*2);time.sleep(.012)
            U.mouse_event(4,0,0,0,0);time.sleep(.7)
            self.assertGreater(rect(hwnd)[0]-r[0],50,'Test must really move the player')
            surfaces=material_windows()
            self.assertTrue(surfaces,'Acrylic must return after releasing a drag without restarting the player')
            self.assertTrue(any(rect(h)==rect(hwnd) for h in surfaces),'Restored Acrylic must follow the new player position')
            key=W.COLORREF();alpha=W.BYTE();flags=W.DWORD()
            self.assertTrue(U.GetLayeredWindowAttributes(hwnd,C.byref(key),C.byref(alpha),C.byref(flags)))
            self.assertLess(alpha.value,255,'Player must reveal the restored blur')
        finally:
            U.mouse_event(4,0,0,0,0);U.SetCursorPos(old.x,old.y)
            U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)

    def test_drag_release_never_exposes_unbacked_transparency(self):
        hwnd=player();front(hwnd)
        U.MoveWindow(hwnd,180,150,1120,725,True);time.sleep(.2)
        # Observe external Win32 window state at high frequency. No enhancer
        # status file, implementation callbacks or mock compositor are used.
        hosts=material_windows();self.assertTrue(hosts,'Idle glass must be running')
        stop=threading.Event();violations=[];observations=[]
        def sample():
            key=W.COLORREF();alpha=W.BYTE();flags=W.DWORD()
            while not stop.is_set():
                layered=U.GetLayeredWindowAttributes(hwnd,C.byref(key),C.byref(alpha),C.byref(flags))
                layered_style=bool(U.GetWindowLongPtrW(hwnd,-20)&0x80000)
                if layered and layered_style and alpha.value<255:
                    covered=any(U.IsWindowVisible(h) and rect(h)==rect(hwnd) for h in hosts)
                    if not covered:
                        violations.append((time.perf_counter(),alpha.value))
                observations.append(1)
        worker=threading.Thread(target=sample,daemon=True)
        old=W.POINT();U.GetCursorPos(C.byref(old))
        worker.start()
        try:
            for cycle in range(8):
                r=rect(hwnd);x=r[0]+250;y=r[1]+22
                U.SetCursorPos(x,y);U.mouse_event(2,0,0,0,0);time.sleep(.025)
                for step in range(1,9):
                    U.SetCursorPos(x+step*(10 if cycle%2==0 else -10),y+step)
                    time.sleep(.012)
                # Wait beyond Windows' double-click interval so successive
                # drags cannot accidentally maximize the title bar.
                U.mouse_event(4,0,0,0,0);time.sleep(max(.6,U.GetDoubleClickTime()/1000+.05))
        finally:
            stop.set();worker.join(timeout=2)
            U.mouse_event(4,0,0,0,0);U.SetCursorPos(old.x,old.y)
            U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)
        print(json.dumps({'case':'release-transition','samples':len(observations),'unbackedTransparentSamples':len(violations)}))
        self.assertGreater(len(observations),100,'Transition observer must actually sample the drag/release sequence')
        self.assertEqual(len(violations),0,'Player must never become transparent before a visible aligned backing surface exists')

    def test_drag_has_no_detached_shadow(self):
        hwnd=player();front(hwnd)
        U.MoveWindow(hwnd,200,150,1120,725,True);time.sleep(.2)
        left,top,right,bottom=rect(hwnd)
        self.assertGreater(right-left,700,'Player must be restored before dragging')
        old=W.POINT();U.GetCursorPos(C.byref(old))
        x,y=left+250,top+22
        U.SetCursorPos(x,y);U.mouse_event(2,0,0,0,0)
        time.sleep(.03)
        offsets=[]
        try:
            for i in range(32):
                U.SetCursorPos(x+i*12,y+i*3)
                time.sleep(.012)
                r=rect(hwnd)
                for h in material_windows():
                    offsets.append(max(abs(a-b) for a,b in zip(rect(h),r)))
        finally:
            U.mouse_event(4,0,0,0,0);time.sleep(.2)
            U.SetCursorPos(old.x,old.y)
            U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)
        final=rect(hwnd)
        self.assertGreater(final[0]-left,200,'The test must actually drag the player')
        worst=max(offsets,default=0)
        print(json.dumps({'case':'drag','samples':len(offsets),'worstDetachedPixels':worst}))
        self.assertLessEqual(worst,20,'Visible glass/shadow must not trail the dragged player by more than one frame')
        resumed=material_windows()
        self.assertTrue(resumed,'Glass must return after dragging, without restarting')
        self.assertTrue(all(rect(h)==final for h in resumed),'Restored glass must align with the new player position')

    def test_idle_footer_icons_stay_bright(self):
        # The idle acrylic state used to dim the whole window to 66%, which made
        # the footer icons and text darker and softer than while dragging.
        hwnd=player();front(hwnd)
        U.MoveWindow(hwnd,150,120,1120,725,True)
        old=W.POINT();U.GetCursorPos(C.byref(old))
        try:
            U.SetCursorPos(60,60);time.sleep(.8)
            r=rect(hwnd)
            img=ImageGrab.grab(bbox=r,all_screens=True).convert('L')
            scale=U.GetDpiForWindow(hwnd)/96
            centre=img.height-round(42*scale)
            band=img.crop((0,centre-14,img.width,centre+14))
            peak=max(band.getdata())
            ink=231  # design token text colour #E7E7E7
            key=W.COLORREF();alpha=W.BYTE();flags=W.DWORD()
            layered=U.GetLayeredWindowAttributes(hwnd,C.byref(key),C.byref(alpha),C.byref(flags))
            print(json.dumps({'case':'idle-brightness','peak':peak,'ratio':round(peak/ink,3),'windowAlpha':alpha.value}))
            # The material can only show through a uniform window alpha, so glass
            # strength and content brightness trade off one for one. Both ends are
            # pinned: too low an alpha dims the UI, too high hides the glass.
            self.assertGreaterEqual(peak/ink,.80,
                                    'Idle footer icons must stay bright; transparency must not dim the UI')
            self.assertLessEqual(alpha.value,225,
                                 'Window alpha must leave enough transparency for the acrylic to read')
        finally:
            U.SetCursorPos(old.x,old.y)
            U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)

    def test_playlist_strip_is_painted_across_the_whole_width(self):
        hwnd=player();front(hwnd)
        win=playlist()
        if not win:
            r=rect(hwnd);scale=U.GetDpiForWindow(hwnd)/96
            click_client(hwnd,r[2]-r[0]-85*scale,r[3]-r[1]-42*scale)
            time.sleep(.6)
            win=playlist()
        self.assertIsNotNone(win,'Playlist must open from the footer button')
        ph=win['hwnd'];old=rect(ph)
        try:
            for width,height in ((450,408),(900,420),(600,700)):
                with self.subTest(size=(width,height)):
                    # Widen past the album tabs, then resize vertically too.
                    U.MoveWindow(ph,old[0],old[1],width,height,True);time.sleep(.4)
                    path=ROOT/'qa'/f'playlist-strip-{width}.png'
                    capture_window(ph,path)
                    im=Image.open(path).convert('L')
                    total=im.width*im.height
                    black=sum(value<6 for value in im.tobytes())
                    print(json.dumps({'case':'playlist-strip','size':[width,height],
                                      'blackFraction':round(black/total,4)}))
                    self.assertLess(black/total,.005,
                                    'Playlist chrome must stay painted; black holes mean an undrawn surface')
        finally:
            U.MoveWindow(ph,old[0],old[1],old[2]-old[0],old[3]-old[1],True)

    def test_control_labels_and_actions_share_crisp_body_type(self):
        from qa_secondary import click
        hwnd=player();front(hwnd)
        panel=next((w for w in windows(PLAYER_PID) if w['title']=='控制面板'),None)
        if panel is None:
            r=rect(hwnd);scale=U.GetDpiForWindow(hwnd)/96
            click(hwnd,130*scale,r[3]-r[1]-42*scale)
            panel=next(w for w in windows(PLAYER_PID) if w['title']=='控制面板')
        ph=panel['hwnd'];scale=U.GetDpiForWindow(ph)/96
        click(ph,158*scale,71*scale)
        U.SetCursorPos(10,10);time.sleep(.2)
        path=ROOT/'qa'/'panel-type-check.png';capture_window(ph,path)
        im=Image.open(path).convert('L')
        metrics=[]
        # User-visible two-character field label and action, from the same row.
        for name,box in (('亮度',(32,104,92,150)),('重置',(322,104,384,150))):
            crop=im.crop(tuple(round(v*scale) for v in box))
            values=list(crop.tobytes());ink=[v for v in values if v>160]
            bounds=crop.point(lambda v:255 if v>160 else 0).getbbox()
            self.assertIsNotNone(bounds,f'{name} must be visible')
            metrics.append({'text':name,'height':bounds[3]-bounds[1],
                            'solidFraction':sum(v>=210 for v in ink)/len(ink)})
        print(json.dumps({'case':'panel-type','metrics':metrics},ensure_ascii=True))
        # Different CJK glyphs have up to two pixels of ink-height variation
        # in the same em box. The old bitmap/native mix differed by five.
        self.assertLessEqual(abs(metrics[0]['height']-metrics[1]['height']),2,
                             'Field labels and actions must use the same body text size')
        for item in metrics:
            self.assertGreaterEqual(item['solidFraction'],.35,
                                    'Body text must keep solid strokes at the actual display scale')

    def test_idle_fullscreen_covers_monitor(self):
        hwnd=player();front(hwnd)
        # The public fullscreen control is at the right edge of the footer.
        r=rect(hwnd);x=r[2]-42;y=r[3]-42
        old=W.POINT();U.GetCursorPos(C.byref(old))
        try:
            U.SetCursorPos(x,y);U.mouse_event(2,0,0,0,0);U.mouse_event(4,0,0,0,0)
            time.sleep(.55)
            r=rect(hwnd)
            monitor=U.MonitorFromWindow(hwnd,2)
            info=MONITORINFO();info.cbSize=C.sizeof(info);U.GetMonitorInfoW(monitor,C.byref(info))
            self.assertEqual((r[0],r[1],r[2],r[3]),(info.rcMonitor.left,info.rcMonitor.top,info.rcMonitor.right,info.rcMonitor.bottom),'Idle fullscreen must cover the monitor')
            path=ROOT/'qa'/'idle-fullscreen.png';capture_window(hwnd,path)
            im=Image.open(path).convert('RGB')
            samples=[im.getpixel((x,y)) for x,y in ((0,0),(im.width-1,0),(0,im.height-1),(im.width-1,im.height-1))]
            self.assertTrue(all(sum(p)>12 for p in samples),'Idle fullscreen must not leave black uncovered corners')
            # The screenshot in the report has black bands midway across the
            # title/footer, which corner-only checks miss. Reveal each chrome
            # area with the real pointer and sample its full horizontal span.
            scale=U.GetDpiForWindow(hwnd)/96
            fractions=[]
            for name,screen_y,row in (('title',r[1]+20,r[1]+round(8*scale)),('footer',r[3]-35,r[3]-round(10*scale))):
                U.SetCursorPos(r[0]+200,screen_y);time.sleep(.18)
                frame=ROOT/'qa'/('fullscreen-'+name+'.png');capture_window(hwnd,frame)
                shot=Image.open(frame).convert('RGB')
                values=[shot.getpixel((x,row-r[1])) for x in range(8,shot.width-8,8)]
                dark=sum(max(pixel)<12 for pixel in values)/len(values)
                fractions.append(dark)
            print(json.dumps({'case':'fullscreen-chrome','blackTitleFraction':fractions[0],'blackFooterFraction':fractions[1]}))
            self.assertTrue(all(value<.01 for value in fractions),'Full title/footer backgrounds must remain painted across the monitor, including when controls are visible')
        finally:
            # Leave the preview in normal mode so a second run starts from the
            # same state; fullscreen geometry/composition settles asynchronously.
            U.PostMessageW(hwnd,0x100,0x1B,0)
            U.PostMessageW(hwnd,0x101,0x1B,0)
            time.sleep(.3)
            U.SetCursorPos(old.x,old.y)
            U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)

    def test_volume_thumb_survives_real_pointer_hover(self):
        hwnd=player();front(hwnd)
        U.MoveWindow(hwnd,150,120,1120,725,True);time.sleep(.2)
        r=rect(hwnd);width,height=r[2]-r[0],r[3]-r[1]
        scale=U.GetDpiForWindow(hwnd)/96
        x=round(r[0]+width-158*scale);y=round(r[1]+height-42*scale)
        old=W.POINT();U.GetCursorPos(C.byref(old))
        try:
            U.SetCursorPos(x,y);U.mouse_event(2,0,0,0,0);U.mouse_event(4,0,0,0,0)
            U.SetCursorPos(r[0]+70,r[1]+100);time.sleep(.15)
            normal=ROOT/'qa'/'volume-normal.png';capture_window(hwnd,normal)
            im=Image.open(normal).convert('RGB')
            left=round(width-197*scale);right=round(width-119*scale)
            top=round(height-50*scale);bottom=round(height-34*scale)
            def pixels(image):
                return [(xx,yy) for yy in range(top,bottom) for xx in range(left,right) if (lambda p:max(p)>80 and max(p)-min(p)>20)(image.getpixel((xx,yy)))]
            before=pixels(im);self.assertTrue(before,'Volume control must be visible')
            counts={xx:sum(1 for a,b in before if a==xx) for xx in range(left,right)}
            center=max(counts,key=counts.get)
            U.SetCursorPos(r[0]+center,y);time.sleep(.15)
            hover=ROOT/'qa'/'volume-hover.png';capture_window(hwnd,hover)
            after=pixels(Image.open(hover).convert('RGB'))
            heights=[]
            for points in (before,after):
                local=[yy for xx,yy in points if abs(xx-center)<4*scale]
                self.assertTrue(local,'Thumb must not disappear during hover')
                heights.append(max(local)-min(local)+1)
                self.assertLessEqual(abs((min(local)+max(local))/2-(top+bottom-1)/2),2,'Thumb must stay centered on the track')
            self.assertGreaterEqual(heights[1],heights[0]*.9,'Pointer hover must not clip the thumb into a half circle')
            print(json.dumps({'case':'volume-hover','normalThumbHeight':heights[0],'hoverThumbHeight':heights[1]}))
        finally:
            U.SetCursorPos(old.x,old.y)
            U.SetWindowPos(hwnd,W.HWND(-2),0,0,0,0,0x43)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('case')
    args=p.parse_args();PLAYER_PID=args.pid
    if args.case=='all':
        suite=unittest.TestSuite(NativeRegressions(name) for name in ('test_volume_thumb_survives_real_pointer_hover','test_drag_release_never_exposes_unbacked_transparency','test_drag_has_no_detached_shadow','test_glass_returns_after_drag','test_idle_footer_icons_stay_bright','test_playlist_strip_is_painted_across_the_whole_width','test_playlist_search_has_visible_frame_and_magnifier','test_video_text_sliders_and_actions_are_centered_in_rows','test_control_labels_and_actions_share_crisp_body_type','test_idle_fullscreen_covers_monitor'))
    else:
        suite=unittest.defaultTestLoader.loadTestsFromName('NativeRegressions.'+args.case,module=sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
