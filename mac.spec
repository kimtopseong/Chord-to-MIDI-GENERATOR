# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('loading.png', '.'), ('pro_theme.json', '.'), ('root.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Chord-to-MIDI-GENERATOR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    # NOTE:
    # - Removed target_arch='universal2' to avoid fat-binary enforcement.
    # - Thin build is determined by the runner's native architecture.
    #   (arm64 on macos-14 runners, x86_64 on macos-13 runners)
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Chord-to-MIDI-GENERATOR',
)
app = BUNDLE(
    coll,
    name='Chord-to-MIDI-GENERATOR.app',
    icon=None,
    bundle_identifier=None,
)
