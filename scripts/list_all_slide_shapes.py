from pptx import Presentation
ppt=r'C:\Users\j\WorkBuddy\2026-09-13-18-11-53\二次元桌宠智能体项目汇报.pptx'
prs=Presentation(ppt)
for i,slide in enumerate(prs.slides,1):
 print(i, 'shapes',len(slide.shapes))
 for j,s in enumerate(slide.shapes,1):
  print(' ',j,s.shape_type,getattr(s,'name',''), 'text' if hasattr(s,'text') and s.text.strip() else '')
