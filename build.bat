@echo off
REM Build PicMeasure (one-folder Windows distribution).
REM Output: dist\PicMeasure\PicMeasure.exe

setlocal

where uv >nul 2>nul
if %errorlevel%==0 (
    set RUNNER=uv run
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set RUNNER=py
    ) else (
        set RUNNER=python
    )
)

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo === Running PyInstaller ===
%RUNNER% -m PyInstaller --noconfirm --clean picmeasure.spec
if errorlevel 1 (
    echo.
    echo Build failed.
    exit /b 1
)

echo.
echo === Build complete ===
copy /y stereo.toml dist\PicMeasure\stereo.toml >nul
echo Distribution folder: dist\PicMeasure\
echo Run:                 dist\PicMeasure\PicMeasure.exe
echo.

endlocal
