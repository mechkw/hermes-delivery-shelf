import sys,glob,os
from PIL import Image, ImageDraw
d=sys.argv[1]; fs=sorted(glob.glob(d+'/*.jpg')); out=sys.argv[2]; os.makedirs(out,exist_ok=True)
for k in range(0,len(fs),4):
    S=Image.new('RGB',(1920,1080),'gray')
    for j,f in enumerate(fs[k:k+4]):
        im=Image.open(f).resize((956,538)); S.paste(im,((j%2)*964,(j//2)*542))
        ImageDraw.Draw(S).text(((j%2)*964+8,(j//2)*542+8),os.path.basename(f),fill='magenta')
    S.save(f'{out}/sheet{k//4:02d}.jpg',quality=85)
