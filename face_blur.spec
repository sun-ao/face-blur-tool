# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import onnxruntime
import insightface

# 获取当前脚本目录（增强路径兼容性）
basedir = os.path.abspath(os.path.dirname(sys.argv[0]))

# 获取所有需要打包的依赖库路径
def get_package_path(package_name):
    """获取指定Python包的安装路径"""
    try:
        import importlib.util
        spec = importlib.util.find_spec(package_name)
        if spec and spec.origin:
            return os.path.dirname(spec.origin)
        return None
    except Exception as e:
        print(f"获取{package_name}路径失败: {e}")
        return None

# 分析程序依赖（适配最新库结构）
a = Analysis(
    ['main.py'],
    pathex=[basedir],
    binaries=[],
    datas=[
        (os.path.join(basedir, '.insightface'), '.insightface'),
        (os.path.join(basedir, 'ffmpeg'), 'ffmpeg'),
        (os.path.join(basedir, 'openh264-1.8.0-win64.dll'), '.'),
        (os.path.join(get_package_path('onnxruntime')), 'onnxruntime'),
        (os.path.join(get_package_path('insightface')), 'insightface')
    ],
    hiddenimports=[
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
    ],
    noarchive=False,
)

# 生成可执行文件
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='face-blur',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(basedir, 'icon.ico') if os.path.exists(os.path.join(basedir, 'icon.ico')) else None,
)

# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='face-blur'
# )    
    