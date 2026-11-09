from pathlib import Path

target = Path(r"C:\Users\j\AppData\Local\LingMengDesktopPet\.env")
line = "TOOLS_ALLOWED_APPLICATIONS=QQ音乐=D:\\QQMusic\\QQMusic.exe"
lines = [
    existing
    for existing in target.read_text(encoding="utf-8-sig").splitlines()
    if not existing.strip().startswith("TOOLS_ALLOWED_APPLICATIONS=")
]
lines.append(line)
target.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(line)

