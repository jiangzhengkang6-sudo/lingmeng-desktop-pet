from pptx import Presentation
from pathlib import Path
ppt=Path(r'C:\Users\j\WorkBuddy\2026-09-13-18-11-53\二次元桌宠智能体项目汇报.pptx')
prs=Presentation(ppt)
out=[]
for si,slide in enumerate(prs.slides,1):
 out.append(f'\n===== SLIDE {si} =====')
 for pi,shape in enumerate(slide.shapes,1):
  if hasattr(shape,'text') and shape.text.strip():
   out.append(f'[shape {pi}] {shape.name}')
   out.append(shape.text.replace('\x0b','\n'))
  if shape.has_table:
   out.append(f'[table {pi}]')
   for row in shape.table.rows:
    out.append(' | '.join(cell.text.replace('\n',' / ') for cell in row.cells))
Path('ppt-text-readable.txt').write_text('\n'.join(out),encoding='utf-8')
print('\n'.join(out))
