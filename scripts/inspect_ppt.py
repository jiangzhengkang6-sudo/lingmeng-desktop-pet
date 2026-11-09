from pptx import Presentation
from pathlib import Path
ppt=Path(r'C:\Users\j\WorkBuddy\2026-09-13-18-11-53\二次元桌宠智能体项目汇报.pptx')
prs=Presentation(ppt)
lines=[]
lines.append(f'slides={len(prs.slides)} size={prs.slide_width}x{prs.slide_height}')
for si,slide in enumerate(prs.slides,1):
    lines.append(f'\n===== SLIDE {si} layout={slide.slide_layout.name} =====')
    for pi,shape in enumerate(slide.shapes,1):
        stype=str(shape.shape_type)
        name=getattr(shape,'name','')
        lines.append(f'-- shape {pi} id={shape.shape_id} type={stype} name={name} pos=({shape.left},{shape.top},{shape.width},{shape.height})')
        if hasattr(shape,'text') and shape.text:
            for p_i,p in enumerate(shape.text_frame.paragraphs,1):
                runs=[]
                for r in p.runs:
                    f=r.font
                    runs.append(f'[size={f.size} bold={f.bold} color={getattr(f.color,"rgb",None) if f.color and f.color.type else None}] {r.text}')
                lines.append(f'  P{p_i}: ' + (' | '.join(runs) if runs else p.text))
        if shape.has_table:
            for row in shape.table.rows:
                lines.append('TABLE: '+' | '.join(cell.text.replace('\n',' / ') for cell in row.cells))
Path('ppt-content-dump.txt').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines[:80]))
print('... dumped to ppt-content-dump.txt lines',len(lines))
