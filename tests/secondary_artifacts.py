"""Check the delivered DSF through its public resource and command interfaces."""
import io
from pathlib import Path
import re
import unittest
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


class SecondaryArtifacts(unittest.TestCase):
    def test_native_surfaces_keep_media_operations_and_valid_images(self):
        expected={
            'FluentPlaylist.xml':{'CMD_PLAYLIST_ADD','CMD_PLAYLIST_DEL','CMD_PLAYLIST_MENU_SORT','CMD_PLAYLIST_UP','CMD_PLAYLIST_DOWN','CMD_PLAYLIST_HOLDER','CMD_PLAY_LIST_ALBUM_TAB','CMD_PLAY_LIST_SEARCH'},
            'FluentControls.xml':{'CMD_SELECT_PAGE','CMD_EQULIZER_0','CMD_EQULIZER_9','CMD_MASTER_VOLUME','CMD_WAVE_VOLUME','CMD_COLOR_OFFSET','CMD_COLOR_GAIN','CMD_COLOR_SAT','CMD_COLOR_HUE','ID_CAPTION_FONT_SELECT','ID_CAPTION_INC_SIZE','ID_CAPTION_DEC_SIZE','ID_CAPTION_SLOW_SYNC','ID_CAPTION_FAST_SYNC','ID_PLAY_SPEED_NORMAL','ID_PLAY_REPEAT_START_SET','ID_PLAY_REPEAT_STOP_SET','ID_PLAY_REPEAT_RESET'},
            'FluentOsc.xml':{'CMD_MEDIA_PLAY','CMD_MEDIA_PAUSE','CMD_VOLUME_CTRL','CMD_TIMEBAR_CTRL','CMD_FULL_WINDOW','ID_CONTROL_BOX_WINDOW'},
            'AudioMini.xml':{'CMD_LOAD_SKIN_XML','CMD_MEDIA_PLAY','CMD_MEDIA_PAUSE','CMD_TIMEBAR_CTRL','CMD_VOLUME_CTRL'},
        }
        with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
            self.assertIsNone(z.testzip())
            for name,commands in expected.items():
                text=z.read(name).decode('utf-8-sig')
                used=set(re.findall(r"(?:CmdID|Contain)='([^']+)'",text))
                self.assertFalse(commands-used,f'{name} lost native behavior: {commands-used}')
                wrapped=re.sub(r'#include<[^>]+>','',text)
                wrapped=re.sub(r'<\?xml[^>]+\?>','',wrapped)
                root=ET.fromstring('<Root>'+wrapped+'</Root>')
                def inspect(e,inherited='Fluent.png'):
                    image=e.attrib.get('Image',inherited)
                    if image and 'ImageLeft' in e.attrib:
                        self.assertIn(image,z.namelist())
                        im=Image.open(io.BytesIO(z.read(image)))
                        x,y,w,h=[int(e.attrib.get(k,'1')) for k in ('ImageLeft','ImageTop','ImageWidth','ImageHeight')]
                        self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                        self.assertLessEqual(x+w*(4 if e.tag=='Button' else 1),im.width,f'{name}: {e.attrib}')
                        self.assertLessEqual(y+h,im.height)
                    for child in e:inspect(child,image)
                inspect(root)
            controls=z.read('FluentControls.xml').decode('utf-8-sig')
            self.assertEqual(set(re.findall(r"State='CMD_PAGE_CONTROL' PageIndex='(\d)'",controls)),{'0','1','2','3'})
            self.assertIn("String='AudioSkin.xml'",z.read('AudioMini.xml').decode('utf-8-sig'))
            mini=z.read('AudioMini.xml').decode('utf-8-sig')
            self.assertIn("CmdID='ID_AUDIO_MUTE'",mini)
            self.assertGreaterEqual(mini.count("AutoVisible='-1'"),1)
            self.assertGreaterEqual(mini.count("AutoVisible='1'"),1)
            self.assertIn('FluentMiniMark.png',mini)
            for name in ('VideoSkin.xml','AudioSkin.xml'):
                self.assertIn('#include<FluentOsc.xml>',z.read(name).decode('utf-8-sig'))


if __name__=='__main__':unittest.main(verbosity=2)
