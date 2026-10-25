"""Check auxiliary-window visibility through the real preview's Win32 interface.

Run with the local preview PID. The helper must be running in either normal or
--no-glass mode. Window rectangles are restored after each case.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from native_window import U,windows

PLAYER_PID=None


class MonitorInfo(C.Structure):
    _fields_=[('size',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD)]


U.MonitorFromWindow.argtypes=[W.HWND,W.DWORD];U.MonitorFromWindow.restype=W.HANDLE
U.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(MonitorInfo)]


def rect(hwnd):
    r=W.RECT();U.GetWindowRect(hwnd,C.byref(r))
    return r.left,r.top,r.right,r.bottom


def work_area(hwnd):
    info=MonitorInfo();info.size=C.sizeof(info)
    assert U.GetMonitorInfoW(U.MonitorFromWindow(hwnd,2),C.byref(info))
    r=info.work
    return r.left,r.top,r.right,r.bottom


def contained(hwnd):
    r=rect(hwnd);area=work_area(hwnd)
    return area[0]<=r[0] and area[1]<=r[1] and r[2]<=area[2] and r[3]<=area[3]


class WindowBounds(unittest.TestCase):
    def setUp(self):
        self.panels=[w for w in windows(PLAYER_PID,True)
                     if w['title'] in ('播放列表','控制面板','控制窗口')]
        self.assertTrue(self.panels,'The local preview must expose its auxiliary panels')
        self.original={w['hwnd']:(rect(w['hwnd']),bool(U.IsWindowVisible(w['hwnd']))) for w in self.panels}

    def tearDown(self):
        for hwnd,(r,visible) in self.original.items():
            if U.IsWindow(hwnd):
                U.MoveWindow(hwnd,r[0],r[1],r[2]-r[0],r[3]-r[1],True)
                if not visible:U.ShowWindow(hwnd,0)

    def wait_inside(self,hwnd):
        for _ in range(40):
            if contained(hwnd):break
            time.sleep(.05)
        actual,area=rect(hwnd),work_area(hwnd)
        print(json.dumps({'window':hwnd,'rect':actual,'nearestWorkArea':area}))
        self.assertTrue(contained(hwnd),'Auxiliary window must return fully inside its nearest monitor work area')
        return actual

    def test_panels_recover_after_a_media_style_offscreen_position_change(self):
        for panel in self.panels:
            hwnd=panel['hwnd'];U.ShowWindow(hwnd,9)
            old=rect(hwnd);w,h=old[2]-old[0],old[3]-old[1]
            area=work_area(hwnd)
            U.MoveWindow(hwnd,area[2]-40,area[3]-35,w,h,True)
            with self.subTest(panel=panel['title']):
                recovered=self.wait_inside(hwnd)
                self.assertEqual((recovered[2]-recovered[0],recovered[3]-recovered[1]),(w,h),
                                 'Recovering a normal-size panel must preserve its size')

    def test_resizable_playlist_larger_than_a_monitor_is_reduced_to_fit(self):
        panel=next(w for w in self.panels if w['title']=='播放列表')
        hwnd=panel['hwnd'];U.ShowWindow(hwnd,9);area=work_area(hwnd)
        U.MoveWindow(hwnd,area[0]+10,area[1]+10,area[2]-area[0]+200,area[3]-area[1]+200,True)
        self.wait_inside(hwnd)

    def test_in_bounds_panel_placement_is_preserved(self):
        for panel in self.panels:
            hwnd=panel['hwnd'];U.ShowWindow(hwnd,9)
            current=rect(hwnd);area=work_area(hwnd)
            w,h=current[2]-current[0],current[3]-current[1]
            desired=(area[0]+40,area[1]+40,area[0]+40+w,area[1]+40+h)
            U.MoveWindow(hwnd,desired[0],desired[1],w,h,True);time.sleep(.5)
            self.assertEqual(rect(hwnd),desired,'An in-bounds user placement must not be snapped elsewhere')

    def test_recovery_waits_for_the_native_move_size_end_event(self):
        hwnd=next(w['hwnd'] for w in self.panels if w['title'] in ('控制面板','控制窗口'))
        U.ShowWindow(hwnd,9);r=rect(hwnd);area=work_area(hwnd)
        desired=(area[2]-40,area[3]-35,r[2]-r[0],r[3]-r[1])
        U.NotifyWinEvent.argtypes=[W.DWORD,W.HWND,W.LONG,W.LONG]
        try:
            # Exercise the public OS move/size lifecycle without sending pointer
            # input to a desktop app that might cover the preview window.
            U.NotifyWinEvent(0xA,hwnd,0,0);time.sleep(.1)
            U.MoveWindow(hwnd,*desired,True);time.sleep(.4)
            held=rect(hwnd)
            self.assertEqual(held,(desired[0],desired[1],desired[0]+desired[2],desired[1]+desired[3]),
                             'An active native move/size operation must not be snapped back')
            U.NotifyWinEvent(0xB,hwnd,0,0)
            self.wait_inside(hwnd)
        finally:
            U.NotifyWinEvent(0xB,hwnd,0,0)

    def test_another_process_window_with_the_same_title_is_untouched(self):
        U.CreateWindowExW.argtypes=[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,
                                   C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p]
        U.CreateWindowExW.restype=W.HWND;U.DestroyWindow.argtypes=[W.HWND]
        area=work_area(self.panels[0]['hwnd'])
        foreign=U.CreateWindowExW(0x08000080,'STATIC','播放列表',0x80000000,
                                  area[2]-10,area[3]-10,120,80,None,None,None,None)
        self.assertTrue(foreign)
        try:
            U.ShowWindow(foreign,8);before=rect(foreign)
            h=self.panels[0]['hwnd'];r=rect(h)
            U.MoveWindow(h,r[0]+1,r[1],r[2]-r[0],r[3]-r[1],True)
            time.sleep(.5)
            self.assertEqual(rect(foreign),before,'Panel recovery must never move another process window')
        finally:U.DestroyWindow(foreign)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pid',type=int);p.add_argument('case',nargs='?',default='all')
    args=p.parse_args();PLAYER_PID=args.pid
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(WindowBounds) if args.case=='all' else unittest.defaultTestLoader.loadTestsFromName('WindowBounds.'+args.case,module=sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
