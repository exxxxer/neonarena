from pathlib import Path

project = Path(SPECPATH)
a = Analysis(
    [str(project / "main.py")], pathex=[str(project)], binaries=[],
    datas=[(str(project / "ui"), "ui"), (str(project / "assets"), "assets")],
    hiddenimports=["PyQt6.QtSvg", "PyQt6.QtMultimedia"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="NeonArena",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="NeonArena")
