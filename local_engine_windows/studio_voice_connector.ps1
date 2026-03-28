param(
  [string]$EnginePort = "",
  [string]$DefaultWebUrl = "https://free-voice-ai-production.up.railway.app"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

if ([string]::IsNullOrWhiteSpace($EnginePort)) {
  $EnginePort = $env:LOCAL_ENGINE_PORT
}
if ($EnginePort -notmatch '^\d+$') {
  $EnginePort = "57641"
}

$script:enginePort = [int]$EnginePort
$script:engineUrl = "http://127.0.0.1:$EnginePort"
$script:engineRoot = $PSScriptRoot
$script:dataDir = Join-Path $env:USERPROFILE ".studio_voice_local"
$script:tokenPath = Join-Path $script:dataDir "api_token.txt"
$script:configPath = Join-Path $script:dataDir "config.json"
$script:runBatPath = Join-Path $script:engineRoot "run_portable_engine.bat"
$script:installBatPath = Join-Path $script:engineRoot "Install Studio Voice Local Engine.bat"
$script:diagBatPath = Join-Path $script:engineRoot "Export Studio Voice Diagnostics.bat"
$script:defaultWebUrl = $DefaultWebUrl

function Get-WebUrl {
  if (-not [string]::IsNullOrWhiteSpace($env:STUDIO_VOICE_PUBLIC_WEB_URL)) {
    return $env:STUDIO_VOICE_PUBLIC_WEB_URL.Trim()
  }

  if (Test-Path $script:configPath) {
    try {
      $cfg = Get-Content -Raw $script:configPath | ConvertFrom-Json
      if ($cfg.public_web_url -and "$($cfg.public_web_url)".Trim()) {
        return "$($cfg.public_web_url)".Trim()
      }
    } catch {
      # Ignore malformed config and use fallback.
    }
  }

  return $script:defaultWebUrl
}

function Add-Log {
  param([string]$Message)
  if (-not $script:logBox) {
    return
  }
  $timestamp = Get-Date -Format "HH:mm:ss"
  $script:logBox.AppendText("[$timestamp] $Message`r`n")
  $script:logBox.SelectionStart = $script:logBox.TextLength
  $script:logBox.ScrollToCaret()
}

function Get-Token {
  if (-not (Test-Path $script:tokenPath)) {
    return ""
  }
  try {
    return (Get-Content -Raw $script:tokenPath).Trim()
  } catch {
    return ""
  }
}

function Get-ListeningPid {
  $patterns = @(
    "127\.0\.0\.1:$($script:enginePort)\s+.*LISTENING",
    "0\.0\.0\.0:$($script:enginePort)\s+.*LISTENING",
    "\[::\]:$($script:enginePort)\s+.*LISTENING"
  )

  $netstatLines = netstat -ano
  foreach ($pattern in $patterns) {
    $matches = $netstatLines | Select-String -Pattern $pattern
    foreach ($match in $matches) {
      $line = $match.Line.Trim()
      if (-not $line) {
        continue
      }
      $parts = $line -split '\s+'
      if ($parts.Length -gt 0) {
        $pidCandidate = $parts[$parts.Length - 1]
        if ($pidCandidate -match '^\d+$') {
          return [int]$pidCandidate
        }
      }
    }
  }
  return $null
}

function Test-EngineHealthy {
  try {
    $resp = Invoke-RestMethod -UseBasicParsing -Uri "$($script:engineUrl)/health" -Method Get -TimeoutSec 2
    return ($resp.status -eq "ok" -and $resp.service -eq "studio-voice-local-engine")
  } catch {
    return $false
  }
}

function Refresh-UiState {
  $healthy = Test-EngineHealthy
  $pid = Get-ListeningPid
  $token = Get-Token

  $script:tokenBox.Text = $token

  if ($healthy) {
    $script:statusLabel.Text = "Estado: conectado en $($script:engineUrl) (PID $pid)"
    $script:statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(20, 120, 20)
  } elseif ($pid) {
    $script:statusLabel.Text = "Estado: proceso detectado (PID $pid), esperando health..."
    $script:statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(160, 120, 0)
  } else {
    $script:statusLabel.Text = "Estado: detenido"
    $script:statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(150, 30, 30)
  }

  $script:startBtn.Enabled = -not $healthy
  $script:stopBtn.Enabled = [bool]$pid
  $script:copyBtn.Enabled = -not [string]::IsNullOrWhiteSpace($token)
}

function Open-WebUrl {
  $url = Get-WebUrl
  if ([string]::IsNullOrWhiteSpace($url)) {
    Add-Log "No hay URL publica configurada."
    return
  }

  try {
    Start-Process -FilePath $url -ErrorAction Stop | Out-Null
    Add-Log "Web abierta: $url"
    return
  } catch {
    # fallback below
  }

  try {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "start", "", $url -WindowStyle Hidden -ErrorAction Stop | Out-Null
    Add-Log "Web abierta via fallback: $url"
  } catch {
    Add-Log "No se pudo abrir navegador. Abre manualmente: $url"
  }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Studio Voice Connector"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(760, 560)
$form.MinimumSize = New-Object System.Drawing.Size(760, 560)

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "Studio Voice Connector"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$titleLabel.Location = New-Object System.Drawing.Point(18, 16)
$titleLabel.AutoSize = $true
$form.Controls.Add($titleLabel)

$script:statusLabel = New-Object System.Windows.Forms.Label
$script:statusLabel.Text = "Estado: iniciando..."
$script:statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Regular)
$script:statusLabel.Location = New-Object System.Drawing.Point(20, 52)
$script:statusLabel.Size = New-Object System.Drawing.Size(700, 24)
$form.Controls.Add($script:statusLabel)

$installBtn = New-Object System.Windows.Forms.Button
$installBtn.Text = "Instalar / Reparar"
$installBtn.Location = New-Object System.Drawing.Point(20, 88)
$installBtn.Size = New-Object System.Drawing.Size(130, 34)
$form.Controls.Add($installBtn)

$script:startBtn = New-Object System.Windows.Forms.Button
$script:startBtn.Text = "Iniciar Motor"
$script:startBtn.Location = New-Object System.Drawing.Point(160, 88)
$script:startBtn.Size = New-Object System.Drawing.Size(110, 34)
$form.Controls.Add($script:startBtn)

$script:stopBtn = New-Object System.Windows.Forms.Button
$script:stopBtn.Text = "Detener Motor"
$script:stopBtn.Location = New-Object System.Drawing.Point(280, 88)
$script:stopBtn.Size = New-Object System.Drawing.Size(110, 34)
$form.Controls.Add($script:stopBtn)

$openWebBtn = New-Object System.Windows.Forms.Button
$openWebBtn.Text = "Abrir Web"
$openWebBtn.Location = New-Object System.Drawing.Point(400, 88)
$openWebBtn.Size = New-Object System.Drawing.Size(100, 34)
$form.Controls.Add($openWebBtn)

$diagBtn = New-Object System.Windows.Forms.Button
$diagBtn.Text = "Exportar Diagnostico"
$diagBtn.Location = New-Object System.Drawing.Point(510, 88)
$diagBtn.Size = New-Object System.Drawing.Size(150, 34)
$form.Controls.Add($diagBtn)

$tokenLabel = New-Object System.Windows.Forms.Label
$tokenLabel.Text = "Token local:"
$tokenLabel.Location = New-Object System.Drawing.Point(20, 144)
$tokenLabel.AutoSize = $true
$form.Controls.Add($tokenLabel)

$script:tokenBox = New-Object System.Windows.Forms.TextBox
$script:tokenBox.Location = New-Object System.Drawing.Point(20, 166)
$script:tokenBox.Size = New-Object System.Drawing.Size(600, 28)
$script:tokenBox.ReadOnly = $true
$form.Controls.Add($script:tokenBox)

$script:copyBtn = New-Object System.Windows.Forms.Button
$script:copyBtn.Text = "Copiar Token"
$script:copyBtn.Location = New-Object System.Drawing.Point(630, 164)
$script:copyBtn.Size = New-Object System.Drawing.Size(100, 30)
$form.Controls.Add($script:copyBtn)

$logLabel = New-Object System.Windows.Forms.Label
$logLabel.Text = "Log:"
$logLabel.Location = New-Object System.Drawing.Point(20, 210)
$logLabel.AutoSize = $true
$form.Controls.Add($logLabel)

$script:logBox = New-Object System.Windows.Forms.TextBox
$script:logBox.Location = New-Object System.Drawing.Point(20, 232)
$script:logBox.Size = New-Object System.Drawing.Size(710, 270)
$script:logBox.Multiline = $true
$script:logBox.ScrollBars = "Vertical"
$script:logBox.ReadOnly = $true
$script:logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$form.Controls.Add($script:logBox)

$installBtn.Add_Click({
  if (-not (Test-Path $script:installBatPath)) {
    Add-Log "No se encontro instalador: $script:installBatPath"
    return
  }

  $env:STUDIO_VOICE_SKIP_PAUSE_ON_INSTALL_ERROR = "1"
  $env:STUDIO_VOICE_OPEN_WEB_ON_INSTALL = "0"
  Add-Log "Lanzando instalador..."
  Start-Process -FilePath $script:installBatPath -WorkingDirectory $script:engineRoot | Out-Null
})

$script:startBtn.Add_Click({
  if (-not (Test-Path $script:runBatPath)) {
    Add-Log "No se encontro launcher: $script:runBatPath"
    return
  }
  Add-Log "Lanzando motor local..."
  Start-Process -FilePath $script:runBatPath -WorkingDirectory $script:engineRoot | Out-Null
})

$script:stopBtn.Add_Click({
  $pid = Get-ListeningPid
  if (-not $pid) {
    Add-Log "No hay proceso escuchando en puerto $($script:enginePort)."
    return
  }
  try {
    Stop-Process -Id $pid -Force -ErrorAction Stop
    Add-Log "Proceso detenido (PID $pid)."
  } catch {
    Add-Log "No se pudo detener PID ${pid}: $($_.Exception.Message)"
  }
})

$script:copyBtn.Add_Click({
  $token = Get-Token
  if ([string]::IsNullOrWhiteSpace($token)) {
    Add-Log "No se encontro token todavia."
    return
  }
  try {
    Set-Clipboard -Value $token
    Add-Log "Token copiado al portapapeles."
  } catch {
    Add-Log "No se pudo copiar token automaticamente. Token: $token"
  }
})

$openWebBtn.Add_Click({
  Open-WebUrl
})

$diagBtn.Add_Click({
  if (-not (Test-Path $script:diagBatPath)) {
    Add-Log "No se encontro exportador de diagnostico."
    return
  }
  Add-Log "Lanzando exportador de diagnostico..."
  Start-Process -FilePath $script:diagBatPath -WorkingDirectory $script:engineRoot | Out-Null
})

$refreshTimer = New-Object System.Windows.Forms.Timer
$refreshTimer.Interval = 2000
$refreshTimer.Add_Tick({
  Refresh-UiState
})

$form.Add_Shown({
  Add-Log "Connector listo."
  Add-Log "Motor local: $($script:engineUrl)"
  Add-Log "Token esperado en: $($script:tokenPath)"
  Refresh-UiState
  $refreshTimer.Start()
})

$form.Add_FormClosing({
  $refreshTimer.Stop()
})

[void][System.Windows.Forms.Application]::Run($form)
