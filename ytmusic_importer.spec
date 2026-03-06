import sys

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("index.html", "."),
        ("static", "static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "ytmusicapi",
        "anyio",
        "anyio._backends._asyncio",
        "starlette",
        "starlette.routing",
        "multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

exe = EXE(
    pyz,
    a.scripts,
    [] if IS_MAC else (a.binaries + a.datas),
    exclude_binaries=IS_MAC,
    name="YTMusic Importer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if IS_MAC:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="YTMusic Importer",
    )
    app = BUNDLE(
        coll,
        name="YTMusic Importer.app",
        icon=None,
        bundle_identifier="com.ytmusic.importer",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "1.0.0",
        },
    )
