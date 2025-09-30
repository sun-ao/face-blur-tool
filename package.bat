@echo off

echo ======================================
echo   ����׼������������빤��...
echo ======================================
echo.

:: ��� Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo δ��⵽ Python�����Ȱ�װ Python �����û�������
    pause
    exit /b 1
)

:: ��� PyInstaller
pyinstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo δ��⵽ PyInstaller�����ڰ�װ...
    python -m pip install pyinstaller
)

:: ���ģ��
if not exist ".insightface\models\buffalo_l" (
    echo ����: δ�ҵ� buffalo_l ģ�ͣ���ȷ��ģ������ȷ������ models Ŀ¼��
    pause
    exit /b 1
)

:: ��� ffmpeg
if not exist "ffmpeg\ffmpeg.exe" (
    echo ����: δ�ҵ� ffmpeg.exe����ȷ�� ffmpeg ����ȷ������ ffmpeg Ŀ¼��
    pause
    exit /b 1
)

:: ɾ���ɵĴ��Ŀ¼
echo ����ɵ� build �� dist Ŀ¼...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo ��ʼ���...
python -m PyInstaller --clean face_blur.spec

:: ���������
if exist ".\dist\face-blur.exe" (
    echo.
    echo ======================================
    echo ����ɹ���
    echo ��ִ���ļ�λ�� dist\face-blur.exe
    echo ������ֱ�Ӹ������� dist �ļ���ʹ��
    echo ======================================
) else (
    echo.
    echo ���ʧ�ܣ�
)

pause
