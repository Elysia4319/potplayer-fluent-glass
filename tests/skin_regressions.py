"""Render the public DSF artifact at a real display scale, against upstream SVG."""
import io
from pathlib import Path
import json
import re
import unittest
from zipfile import ZipFile
from PIL import Image,ImageChops,ImageDraw,ImageFont,ImageStat
import resvg_py

ROOT=Path(__file__).resolve().parents[1]


def control(cmd):
    with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
        xml=z.read('VideoSkin.xml').decode('utf-8-sig')
        xml=xml[xml.index('<MainSkinArea '):]
        tag=next(t for t in re.findall(r'<(?:Button|Slider)\b[^>]+>',xml) if "CmdID='"+cmd+"'" in t)
        attrs=dict(re.findall(r"(\w+)='([^']*)'",tag))
        atlas=Image.open(io.BytesIO(z.read(attrs.get('Image','Fluent.png')))).convert('RGBA')
    return attrs,atlas


def panel_sprite(xml_name,cmd,width,height):
    """Read one button cell group out of the packaged secondary skin sheet."""
    with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
        xml=z.read(xml_name).decode('utf-8-sig')
        tag=next(t for t in re.findall(r'<Button\b[^>]+>',xml)
                 if "CmdID='"+cmd+"'" in t
                 and "Width='"+str(width)+"'" in t and "Height='"+str(height)+"'" in t)
        attrs=dict(re.findall(r"(\w+)='([^']*)'",tag))
        atlas=Image.open(io.BytesIO(z.read(attrs['Image']))).convert('RGBA')
    return attrs,atlas


def footer_button(cmd):
    """Read one footer button of the packaged main skin, whatever its size."""
    with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
        xml=z.read('VideoSkin.xml').decode('utf-8-sig')
        tag=next(t for t in re.findall(r'<Button\b[^>]+>',xml) if "CmdID='"+cmd+"'" in t)
        attrs=dict(re.findall(r"(\w+)='([^']*)'",tag))
        atlas=Image.open(io.BytesIO(z.read(attrs.get('Image','Fluent.png')))).convert('RGBA')
    return attrs,atlas


class SkinRegressions(unittest.TestCase):
    def test_panel_buttons_have_visible_frames_before_hover(self):
        import xml.etree.ElementTree as ET
        with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
            atlas=Image.open(io.BytesIO(z.read('FluentPanels.png'))).convert('RGBA')
            for name in ('FluentControls.xml','FluentPlaylist.xml'):
                root=ET.fromstring(z.read(name).decode('utf-8-sig'))
                for button in root.iter('Button'):
                    with self.subTest(panel=name,command=button.get('CmdID')):
                        x,y,w,h=(int(button.get(k)) for k in ('ImageLeft','ImageTop','Width','Height'))
                        cell=atlas.crop((x,y,x+w,y+h))
                        edge=cell.getpixel((1,h//2));inside=cell.getpixel((6,h//2))
                        self.assertGreater(edge[3],180,'Button outline must be visible at rest')
                        self.assertGreater(sum(edge[:3])-sum(inside[:3]),45,
                                           'Outline must contrast with the button fill')

    def test_time_track_reads_four_px_with_accent_progress(self):
        with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
            sheet=Image.open(io.BytesIO(z.read('FluentSliders.png'))).convert('RGBA')
        accent=json.loads((ROOT/'design-tokens.json').read_text(encoding='utf-8'))['palette']['accent']
        accent=tuple(int(accent[i:i+2],16) for i in (1,3,5))
        for top,label in ((0,'played'),(16,'remaining')):
            band=sheet.crop((16,top,112,top+16))
            solid=[y for y in range(band.height) if band.getpixel((40,y))[3]>200]
            self.assertGreaterEqual(len(solid),4,f'{label} track must be 4px thick')
        played=sheet.crop((16,0,112,16)).getpixel((40,8))
        self.assertLessEqual(max(abs(a-b) for a,b in zip(played[:3],accent)),12,
                             'Played portion must use the declared accent colour')

    def test_footer_mini_and_control_buttons_are_icon_only(self):
        for cmd,icon in (('CMD_LOAD_SKIN_XML','picture-in-picture-2'),
                         ('ID_CONTROL_BOX_WINDOW','sliders-horizontal')):
            attrs,atlas=footer_button(cmd)
            width,height=int(attrs['Width']),int(attrs['Height'])
            self.assertEqual((width,height),(36,36),
                             f'{cmd}: footer control must be icon sized, not a text pill')
            x,y=int(attrs['ImageLeft']),int(attrs['ImageTop'])
            actual=atlas.crop((x,y,x+width,y+height)).resize((45,45),Image.Resampling.LANCZOS).getchannel('A')
            svg=(ROOT/'assets'/'lucide'/(icon+'.svg')).read_text().replace('currentColor','#E7E7E7')
            expected=Image.new('L',(45,45))
            glyph=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg,width=25,height=25))).convert('RGBA')
            expected.paste(glyph.getchannel('A'),(10,10))
            error=ImageStat.Stat(ImageChops.difference(actual,expected)).mean[0]/255
            print(f'{cmd} matches {icon} with alpha-mask error {error:.4f}')
            self.assertLess(error,.05,f'{cmd} must render the {icon} silhouette like the other footer icons')

    def test_total_time_sits_at_the_right_end_of_the_time_bar(self):
        with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
            xml=z.read('VideoSkin.xml').decode('utf-8-sig')
        tags=re.findall(r'<(?:Label|Slider)\b[^>]+>',xml)
        def attrs(cmd):
            tag=next((t for t in tags if "CmdID='"+cmd+"'" in t),None)
            self.assertIsNotNone(tag,f'Footer must contain {cmd}')
            return dict(re.findall(r"(\w+)='([^']*)'",tag))
        total=attrs('CMD_TOTALTIME_MESSAGE')
        bar=attrs('CMD_TIMEBAR_CTRL')
        # Negative Left/Width are measured from the parent's right edge.
        total_right=int(total['Left'])+int(total['Width'])
        margin=abs(total_right)
        self.assertTrue(8<=margin<=32,
                        f'Total time must hug the footer edge, got {margin}px margin')
        bar_right=int(bar['Width'])
        self.assertLessEqual(bar_right,total_right-4,
                             'Time bar must not run into the total time label')

    def test_panel_actions_declare_consistent_native_body_type(self):
        import xml.etree.ElementTree as ET
        # DSF is PotPlayer's public skin interface. Native labels avoid scaling
        # baked text a second time when the player applies the display DPI.
        with ZipFile(ROOT/'dist'/'FluentGlass.dsf') as z:
            for name in ('FluentControls.xml','FluentPlaylist.xml'):
                root=ET.fromstring(z.read(name).decode('utf-8-sig'))
                icons={'ID_CONTROL_BOX_WINDOW','CMD_ATTACH_PLAYLIST','ID_PLAYLIST_WINDOW',
                       'CMD_PLAYLIST_UP','CMD_PLAYLIST_DOWN'}
                actions=[e for e in root.iter('Button') if e.get('CmdID') not in icons]
                self.assertTrue(actions,f'{name} needs visible native action labels')
                for button in actions:
                    label=button.find('Label')
                    self.assertIsNotNone(label,f'{button.get("CmdID")} must draw text natively')
                    self.assertEqual(label.get('FontSize'),'14',button.get('CmdID'))
                    self.assertEqual(label.get('FontName'),'Microsoft YaHei UI')
                    self.assertTrue(label.get('Text'),'Action label must be readable')

    def test_volume_thumb_stays_round_centered_and_complete_in_all_states(self):
        attrs,atlas=control('CMD_VOLUME_CTRL')
        tx,ty,tw,th=(int(attrs[k]) for k in ('ThumbImageLeft','ThumbImageTop','ThumbWidth','ThumbHeight'))
        frames=[]
        for state in range(4):
            # PotPlayer selects contiguous thumb cells, using ThumbWidth stride.
            frame=atlas.crop((tx+state*tw,ty,tx+(state+1)*tw,ty+th)).getchannel('A')
            bbox=frame.getbbox();self.assertIsNotNone(bbox,'Every thumb state must be visible')
            width,height=bbox[2]-bbox[0],bbox[3]-bbox[1]
            self.assertLessEqual(abs(width-height),1,'Hovered/pressed thumb must not become a clipped half-circle')
            self.assertGreater(ImageStat.Stat(frame).mean[0]/255,.35,'Thumb must remain complete in every state')
            frames.append(frame)
        x,y,w,h=(int(attrs[k]) for k in ('ImageLeft','ImageTop','ImageWidth','ImageHeight'))
        track=atlas.crop((x,y,x+w,y+h)).getchannel('A')
        bbox=track.getbbox()
        track_center=(bbox[1]+bbox[3])/2
        self.assertLessEqual(abs(track_center-h/2),.5,'Track must be vertically centered in the slider')
        self.assertEqual(frames[0].getbbox(),frames[1].getbbox(),'Hover must keep the thumb outline intact')


if __name__=='__main__':unittest.main(verbosity=2)
