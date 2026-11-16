# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for building NEXUS FILES as a standalone Windows desktop executable.
Run via: pyinstaller nexus_files.spec --noconfirm --clean
"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('resources/styles/dark_theme.qss', 'resources/styles'),
        ('resources/icons/nexus_files.ico', 'resources/icons'),
        ('resources/icons/nexus_app_icon.ico', 'resources/icons'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'psutil',
        'watchdog',
        'pymupdf',
        'fitz',
        'PIL',
        'openpyxl',
        'docx',
        'send2trash',
        'reportlab',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
        'onnxruntime',
        'pymupdf_layout',
        'pymupdf4llm',
        'networkx',
        'pyqtgraph',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtTest',
        'PySide6.Qt3DCore',
        'PySide6.QtMultimedia',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NexusFiles',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='resources/icons/nexus_app_icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NexusFiles',
)
