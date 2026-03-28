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
  $enginePid = Get-ListeningPid
  $token = Get-Token

  $script:tokenBox.Text = $token

  if ($healthy) {
    $script:statusLabel.Text = "Estado: conectado en $($script:engineUrl) (PID $enginePid)"
    $script:statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(20, 120, 20)
  } elseif ($enginePid) {
    $script:statusLabel.Text = "Estado: proceso detectado (PID $enginePid), esperando health..."
    $script:statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(160, 120, 0)
  } else {
    $script:statusLabel.Text = "Estado: detenido"
    $script:statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(150, 30, 30)
  }

  $script:startBtn.Enabled = -not $healthy
  $script:stopBtn.Enabled = [bool]$enginePid
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

$colorBackground = [System.Drawing.ColorTranslator]::FromHtml("#F3F5F7")
$colorCard = [System.Drawing.Color]::White
$colorBrand = [System.Drawing.ColorTranslator]::FromHtml("#0F6CBD")
$colorTextPrimary = [System.Drawing.ColorTranslator]::FromHtml("#1B1A19")
$colorTextSecondary = [System.Drawing.ColorTranslator]::FromHtml("#605E5C")
$colorBorder = [System.Drawing.ColorTranslator]::FromHtml("#E1DFDD")

function Set-ButtonStyle {
  param(
    [System.Windows.Forms.Button]$Button,
    [System.Drawing.Color]$BackColor,
    [System.Drawing.Color]$ForeColor,
    [switch]$Outlined
  )
  $Button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
  $Button.BackColor = $BackColor
  $Button.ForeColor = $ForeColor
  $Button.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
  if ($Outlined) {
    $Button.FlatAppearance.BorderSize = 1
    $Button.FlatAppearance.BorderColor = [System.Drawing.ColorTranslator]::FromHtml("#C8C6C4")
  } else {
    $Button.FlatAppearance.BorderSize = 0
  }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Studio Voice Connector"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(800, 620)
$form.MinimumSize = New-Object System.Drawing.Size(800, 620)
$form.BackColor = $colorBackground
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

$headerPanel = New-Object System.Windows.Forms.Panel
$headerPanel.Dock = [System.Windows.Forms.DockStyle]::Top
$headerPanel.Height = 92
$headerPanel.BackColor = $colorBrand
$form.Controls.Add($headerPanel)

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "Studio Voice Connector"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 15, [System.Drawing.FontStyle]::Bold)
$titleLabel.ForeColor = [System.Drawing.Color]::White
$titleLabel.Location = New-Object System.Drawing.Point(20, 16)
$titleLabel.AutoSize = $true
$headerPanel.Controls.Add($titleLabel)

$subtitleLabel = New-Object System.Windows.Forms.Label
$subtitleLabel.Text = "Instala, inicia y conecta el motor local en una sola ventana."
$subtitleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$subtitleLabel.ForeColor = [System.Drawing.ColorTranslator]::FromHtml("#EAF2FB")
$subtitleLabel.Location = New-Object System.Drawing.Point(22, 50)
$subtitleLabel.AutoSize = $true
$headerPanel.Controls.Add($subtitleLabel)

$statusCard = New-Object System.Windows.Forms.Panel
$statusCard.Location = New-Object System.Drawing.Point(20, 106)
$statusCard.Size = New-Object System.Drawing.Size(744, 48)
$statusCard.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$statusCard.BackColor = $colorCard
$form.Controls.Add($statusCard)

$script:statusLabel = New-Object System.Windows.Forms.Label
$script:statusLabel.Text = "Estado: iniciando..."
$script:statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$script:statusLabel.Location = New-Object System.Drawing.Point(14, 12)
$script:statusLabel.Size = New-Object System.Drawing.Size(712, 24)
$statusCard.Controls.Add($script:statusLabel)

$actionsCard = New-Object System.Windows.Forms.Panel
$actionsCard.Location = New-Object System.Drawing.Point(20, 166)
$actionsCard.Size = New-Object System.Drawing.Size(744, 130)
$actionsCard.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$actionsCard.BackColor = $colorCard
$form.Controls.Add($actionsCard)

$installBtn = New-Object System.Windows.Forms.Button
$installBtn.Text = "Instalar / Reparar"
$installBtn.Location = New-Object System.Drawing.Point(14, 14)
$installBtn.Size = New-Object System.Drawing.Size(138, 34)
Set-ButtonStyle -Button $installBtn -BackColor $colorBrand -ForeColor ([System.Drawing.Color]::White)
$actionsCard.Controls.Add($installBtn)

$script:startBtn = New-Object System.Windows.Forms.Button
$script:startBtn.Text = "Iniciar Motor"
$script:startBtn.Location = New-Object System.Drawing.Point(162, 14)
$script:startBtn.Size = New-Object System.Drawing.Size(112, 34)
Set-ButtonStyle -Button $script:startBtn -BackColor ([System.Drawing.ColorTranslator]::FromHtml("#107C10")) -ForeColor ([System.Drawing.Color]::White)
$actionsCard.Controls.Add($script:startBtn)

$script:stopBtn = New-Object System.Windows.Forms.Button
$script:stopBtn.Text = "Detener Motor"
$script:stopBtn.Location = New-Object System.Drawing.Point(284, 14)
$script:stopBtn.Size = New-Object System.Drawing.Size(112, 34)
Set-ButtonStyle -Button $script:stopBtn -BackColor ([System.Drawing.ColorTranslator]::FromHtml("#A4262C")) -ForeColor ([System.Drawing.Color]::White)
$actionsCard.Controls.Add($script:stopBtn)

$openWebBtn = New-Object System.Windows.Forms.Button
$openWebBtn.Text = "Abrir Web"
$openWebBtn.Location = New-Object System.Drawing.Point(406, 14)
$openWebBtn.Size = New-Object System.Drawing.Size(102, 34)
Set-ButtonStyle -Button $openWebBtn -BackColor ([System.Drawing.Color]::White) -ForeColor $colorTextPrimary -Outlined
$actionsCard.Controls.Add($openWebBtn)

$diagBtn = New-Object System.Windows.Forms.Button
$diagBtn.Text = "Exportar Diagnostico"
$diagBtn.Location = New-Object System.Drawing.Point(518, 14)
$diagBtn.Size = New-Object System.Drawing.Size(200, 34)
Set-ButtonStyle -Button $diagBtn -BackColor ([System.Drawing.Color]::White) -ForeColor $colorTextPrimary -Outlined
$actionsCard.Controls.Add($diagBtn)

$tokenLabel = New-Object System.Windows.Forms.Label
$tokenLabel.Text = "Token local:"
$tokenLabel.ForeColor = $colorTextSecondary
$tokenLabel.Location = New-Object System.Drawing.Point(14, 62)
$tokenLabel.AutoSize = $true
$actionsCard.Controls.Add($tokenLabel)

$script:tokenBox = New-Object System.Windows.Forms.TextBox
$script:tokenBox.Location = New-Object System.Drawing.Point(14, 84)
$script:tokenBox.Size = New-Object System.Drawing.Size(600, 28)
$script:tokenBox.ReadOnly = $true
$actionsCard.Controls.Add($script:tokenBox)

$script:copyBtn = New-Object System.Windows.Forms.Button
$script:copyBtn.Text = "Copiar Token"
$script:copyBtn.Location = New-Object System.Drawing.Point(622, 82)
$script:copyBtn.Size = New-Object System.Drawing.Size(100, 30)
Set-ButtonStyle -Button $script:copyBtn -BackColor ([System.Drawing.ColorTranslator]::FromHtml("#E8F1FB")) -ForeColor $colorBrand
$actionsCard.Controls.Add($script:copyBtn)

$logCard = New-Object System.Windows.Forms.Panel
$logCard.Location = New-Object System.Drawing.Point(20, 308)
$logCard.Size = New-Object System.Drawing.Size(744, 254)
$logCard.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$logCard.BackColor = $colorCard
$form.Controls.Add($logCard)

$logLabel = New-Object System.Windows.Forms.Label
$logLabel.Text = "Log:"
$logLabel.ForeColor = $colorTextSecondary
$logLabel.Location = New-Object System.Drawing.Point(14, 12)
$logLabel.AutoSize = $true
$logCard.Controls.Add($logLabel)

$script:logBox = New-Object System.Windows.Forms.TextBox
$script:logBox.Location = New-Object System.Drawing.Point(14, 34)
$script:logBox.Size = New-Object System.Drawing.Size(712, 206)
$script:logBox.Multiline = $true
$script:logBox.ScrollBars = "Vertical"
$script:logBox.ReadOnly = $true
$script:logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$script:logBox.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#FAFAFA")
$script:logBox.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$logCard.Controls.Add($script:logBox)

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
  $enginePid = Get-ListeningPid
  if (-not $enginePid) {
    Add-Log "No hay proceso escuchando en puerto $($script:enginePort)."
    return
  }
  try {
    Stop-Process -Id $enginePid -Force -ErrorAction Stop
    Add-Log "Proceso detenido (PID $enginePid)."
  } catch {
    Add-Log "No se pudo detener PID ${enginePid}: $($_.Exception.Message)"
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
