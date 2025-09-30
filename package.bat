@echo off

echo ======================================
echo   正在准备打包人脸打码工具...
echo ======================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 未检测到 Python，请先安装 Python 并配置环境变量
    pause
    exit /b 1
)

:: 检查 PyInstaller
pyinstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 未检测到 PyInstaller，正在安装...
    python -m pip install pyinstaller
)

:: 检查模型
if not exist ".insightface\models\buffalo_l" (
    echo 警告: 未找到 buffalo_l 模型，请确保模型已正确放置在 models 目录下
    pause
    exit /b 1
)

:: 检查 ffmpeg
if not exist "ffmpeg\ffmpeg.exe" (
    echo 警告: 未找到 ffmpeg.exe，请确保 ffmpeg 已正确放置在 ffmpeg 目录下
    pause
    exit /b 1
)

:: 删除旧的打包目录
echo 清理旧的 build 和 dist 目录...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo 开始打包...
python -m PyInstaller --clean face_blur.spec

:: 检查输出结果
if exist ".\dist\face-blur.exe" (
    echo.
    echo ======================================
    echo 打包成功！
    echo 可执行文件位于 dist\face-blur.exe
    echo 您可以直接复制整个 dist 文件夹使用
    echo ======================================
) else (
    echo.
    echo 打包失败！
)

pause
