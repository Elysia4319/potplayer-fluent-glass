"""Check real compositor screenshots: actual corners and blur, not API success."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageStat


def variation(values):
    mean=sum(values)/len(values)
    return (sum((v-mean)**2 for v in values)/len(values))**.5


def frequency(im):
    region=im.convert('L').crop((800,200,1050,400))
    p=region.load()
    return sum(abs(p[x+1,y]-p[x,y]) for y in range(region.height) for x in range(region.width-1))/(region.height*(region.width-1))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('sharp',type=Path);p.add_argument('glass',type=Path);args=p.parse_args()
    sharp=Image.open(args.sharp).convert('RGB');glass=Image.open(args.glass).convert('RGB')
    assert sharp.size==glass.size
    w,h=glass.size
    corners=[(14,14),(w-15,14),(14,h-15),(w-15,h-15)]
    inner=[(35,35),(w-36,35),(35,h-36),(w-36,h-36)]
    differences=[sum(glass.getpixel(c))/3-sum(glass.getpixel(i))/3 for c,i in zip(corners,inner)]
    assert all(d>25 for d in differences),f'Window is not visibly rounded at every corner: {differences}'
    sharp_energy=frequency(sharp);blurred_energy=frequency(glass)
    assert sharp_energy>2,'Control image must contain unblurred narrow stripes'
    assert blurred_energy<sharp_energy*.25,'Narrow background stripes are still sharp'
    # An opaque flat background also removes stripes; it must retain broad color.
    samples=[glass.getpixel((x,200)) for x in range(100,700,8)]
    broad=variation([v[0]-v[2] for v in samples])
    assert broad>2,'Surface is flat/opaque; broad background color did not survive'
    result={'fourVisibleRoundedCorners':True,'cornerBrightnessDifferences':differences,'sharpStripeEnergy':sharp_energy,'glassStripeEnergy':blurred_energy,'retainedBroadColorVariation':broad,'passed':True}
    (args.glass.parent/'glass-checks-v2.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
