@echo off
chcp 65001 >nul
setlocal
rem === Karyer Local Server — Windows avtomatik ishga tushirishni YOQISH ===
rem Kompyuter yoqilganda dastur fonda (tray) avtomatik ishlaydi.

set "PROJ=%~dp0"
set "PROJ=%PROJ:~0,-1%"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "OUT=%STARTUP%\KaryerServer.vbs"

> "%OUT%" echo Set sh = CreateObject("WScript.Shell")
>> "%OUT%" echo sh.CurrentDirectory = "%PROJ%"
>> "%OUT%" echo sh.Run "pythonw.exe boshlash.py", 0, False

echo.
echo   [OK] Avtomatik ishga tushirish YOQILDI.
echo   Endi kompyuter yoqilganda dastur o'zi fonda ishlaydi.
echo   (Soat yonidagi ikonkadan boshqarasiz.)
echo.
echo   Hoziroq ishga tushirish uchun "Karyer Server.bat" ni ikki marta bosing.
echo.
pause
