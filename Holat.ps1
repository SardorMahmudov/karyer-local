$ErrorActionPreference = 'SilentlyContinue'
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host "     KARYER LOCAL SERVER  -  HOLAT TEKSHIRUVI" -ForegroundColor Cyan
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

# 1) Dastur fonda ishlayaptimi (pythonw + boshlash.py)
$proc = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
        Where-Object { $_.CommandLine -like '*boshlash.py*' -or $_.CommandLine -like '*main.py*' }
if (-not $proc) { $proc = Get-Process pythonw -ErrorAction SilentlyContinue }

if ($proc) {
    $pid0 = if ($proc.ProcessId) { $proc.ProcessId } else { $proc.Id }
    Write-Host "   [  OK  ]  DASTUR ISHLAYAPTI (fonda)" -ForegroundColor Black -BackgroundColor Green
    Write-Host "            (jarayon PID: $pid0)" -ForegroundColor DarkGray
} else {
    Write-Host "   [ XATO ]  DASTUR ISHLAMAYAPTI!" -ForegroundColor White -BackgroundColor Red
    Write-Host "            Yoqish: 'Karyer Server.bat' ni ikki marta bosing." -ForegroundColor Yellow
}
Write-Host ""

# config.json — stansiyalar va kameralarni undan o'qiymiz (o'zgarsa ham to'g'ri)
$cfg = $null
try { $cfg = Get-Content (Join-Path $PSScriptRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch {}

if ($cfg) {
    # 2) Kameralar (har stansiya: raqam + video)
    foreach ($st in $cfg.stations) {
        foreach ($c in @(@{ rol = 'raqam'; ip = $st.anpr.ip }, @{ rol = 'video'; ip = $st.video.ip })) {
            if (-not $c.ip) { continue }
            $up = Test-Connection -ComputerName $c.ip -Count 1 -Quiet
            $label = ("{0} / {1}" -f $st.name, $c.rol).PadRight(22)
            if ($up) { Write-Host ("   [  OK  ]  {0} {1}  ulanadi" -f $label, $c.ip) -ForegroundColor Green }
            else     { Write-Host ("   [ XATO ]  {0} {1}  ULANMADI" -f $label, $c.ip) -ForegroundColor Red }
        }
    }
    Write-Host ""

    # 3) Tarozi portlari (faqat serial tarozili stansiyalar)
    $ports = [System.IO.Ports.SerialPort]::GetPortNames()
    $scalePorts = @()
    foreach ($st in $cfg.stations) {
        if ($st.scale -and $st.scale.type -eq 'serial' -and $st.scale.port) { $scalePorts += $st.scale.port }
    }
    foreach ($p in ($scalePorts | Select-Object -Unique)) {
        if ($ports -contains $p) { Write-Host "   [  OK  ]  Tarozi porti $p mavjud" -ForegroundColor Green }
        else { Write-Host "   [ XATO ]  $p topilmadi (tarozi kabeli ulanganmi?)" -ForegroundColor Red }
    }
    if ($scalePorts.Count -gt 0) { Write-Host "" }
} else {
    Write-Host "   [ OGOH ]  config.json o'qilmadi" -ForegroundColor Yellow
    Write-Host ""
}

# 4) Auto-yoqish sozlamasi
$vbs = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\KaryerServer.vbs'
$w   = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
$aal = (Get-ItemProperty $w).AutoAdminLogon
if ((Test-Path $vbs) -and $aal -eq '1') {
    Write-Host "   [  OK  ]  Kompyuter yonganda O'ZI ishga tushadi" -ForegroundColor Green
} else {
    Write-Host "   [ OGOH ]  Avto-yoqish to'liq sozlanmagan" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
if ($proc) {
    Write-Host "   XULOSA: dastur ishlayapti." -ForegroundColor Green
} else {
    Write-Host "   XULOSA: dastur ishlamayapti - yuqoridagini bajaring." -ForegroundColor Red
}
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""
