@echo off
chcp 65001 >nul
rem === Avtomatik ishga tushirishni O'CHIRISH ===
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KaryerServer.vbs" 2>nul
echo.
echo   [OK] Avtomatik ishga tushirish O'CHIRILDI.
echo   Dastur endi kompyuter yoqilganda o'zi ishlamaydi.
echo.
pause
