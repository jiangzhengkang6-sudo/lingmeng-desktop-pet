from pptx import Presentation
from pathlib import Path
ppt=Path(r'C:\Users\j\WorkBuddy\2026-09-13-18-11-53\二次元桌宠智能体项目汇报-详实版.pptx')
prs=Presentation(ppt)
lines=[f'file={ppt}',f'size={ppt.stat().st_size}',f'slides={len(prs.slides)}']
for i,slide in enumerate(prs.slides,1):
 texts=[]
 for s in slide.shapes:
  if hasattr(s,'text') and s.text.strip(): texts.append(s.text.strip().replace('\n',' / '))
 lines.append(f'--- {i} ---')
 lines.extend(texts)
Path('ppt-enriched-dump.txt').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines[:120]))
