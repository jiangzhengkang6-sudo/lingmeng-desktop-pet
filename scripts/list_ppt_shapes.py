from pptx import Presentation
from pathlib import Path
ppt=Path(r'C:\Users\j\WorkBuddy\2026-09-13-18-11-53\二次元桌宠智能体项目汇报.pptx')
prs=Presentation(ppt)
for si,slide in enumerate(prs.slides,1):
 print(f'--- slide {si} ---')
 for pi,shape in enumerate(slide.shapes,1):
  if hasattr(shape,'text') and shape.text.strip():
   print(pi, shape.shape_id, shape.name.encode('unicode_escape').decode(), 'box', shape.width,shape.height,'text=',shape.text.replace('\n',' / ').encode('unicode_escape').decode()[:300])
