param(
  [switch]$OneFile,
  [switch]$SkipDefenderScan,
  [switch]$SkipSign,
  [string]$PfxPath,
  [string]$PfxPassword,
  [string]$CertThumbprint,
  [switch]$MachineStore,
  [string]$TimestampUrl = "http://timestamp.acs.microsoft.com",
  [string]$ProductVersion = "",
  [string]$CompanyName = "Studio Voice",
  [string]$ProductName = "Studio Voice Local Engine",
  [string]$FileDescription = "Studio Voice Local Engine for Windows"
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Get-LocalEngineVersion {
  $initPath = Join-Path $PSScriptRoot "__init__.py"
  if (-not (Test-Path $initPath)) {
    return "0.1.0"
  }
  $content = Get-Content -Raw $initPath
  $match = [regex]::Match($content, "__version__\s*=\s*""([^""]+)""")
  if ($match.Success) {
    return $match.Groups[1].Value
  }
  return "0.1.0"
}

function Convert-ToFileVersionParts([string]$Version) {
  $parts = @()
  foreach ($piece in ($Version -split '\.')) {
    if ($parts.Count -ge 4) {
      break
    }
    $digits = [regex]::Match($piece, '^\d+').Value
    if ([string]::IsNullOrWhiteSpace($digits)) {
      $parts += 0
      continue
    }
    $parts += [int]$digits
  }
  while ($parts.Count -lt 4) {
    $parts += 0
  }
  return $parts
}

function Get-SignToolPath {
  $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $kitsRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
  if (-not (Test-Path $kitsRoot)) {
    return $null
  }

  $candidate = Get-ChildItem -Path $kitsRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1
  if ($candidate) {
    return $candidate.FullName
  }
  return $null
}

if ([string]::IsNullOrWhiteSpace($ProductVersion)) {
  $ProductVersion = Get-LocalEngineVersion
}

$versionParts = Convert-ToFileVersionParts -Version $ProductVersion
$fileVersionString = "$($versionParts[0]).$($versionParts[1]).$($versionParts[2]).$($versionParts[3])"

$buildDir = Join-Path $PSScriptRoot "build"
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
$specDir = Join-Path $buildDir "spec"
New-Item -ItemType Directory -Path $specDir -Force | Out-Null

if ($OneFile) {
  $buildName = "StudioVoiceLocalEngine-OneFile"
} else {
  $buildName = "StudioVoiceLocalEngine"
}

$versionFilePath = Join-Path $buildDir "$buildName-version.txt"
$originalFilename = "$buildName.exe"

$versionFile = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($($versionParts[0]), $($versionParts[1]), $($versionParts[2]), $($versionParts[3])),
    prodvers=($($versionParts[0]), $($versionParts[1]), $($versionParts[2]), $($versionParts[3])),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', '$CompanyName'),
            StringStruct('FileDescription', '$FileDescription'),
            StringStruct('FileVersion', '$fileVersionString'),
            StringStruct('InternalName', '$buildName'),
            StringStruct('LegalCopyright', 'Copyright (c) 2026 $CompanyName'),
            StringStruct('OriginalFilename', '$originalFilename'),
            StringStruct('ProductName', '$ProductName'),
            StringStruct('ProductVersion', '$ProductVersion')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -Path $versionFilePath -Value $versionFile -Encoding UTF8

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  python -m venv .venv
}

$py = ".venv\\Scripts\\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt pyinstaller

$pyInstallerArgs = @(
  "-m", "PyInstaller",
  "--name", $buildName,
  "--noconfirm",
  "--windowed",
  "--clean",
  "--noupx",
  "--specpath", $specDir,
  "--version-file", $versionFilePath
)

if ($OneFile) {
  $pyInstallerArgs += "--onefile"
}

$pyInstallerArgs += "app.py"
& $py @pyInstallerArgs

if ($OneFile) {
  $exePath = Join-Path $PSScriptRoot "dist\\$buildName.exe"
} else {
  $exePath = Join-Path $PSScriptRoot "dist\\$buildName\\$buildName.exe"
}

if (-not (Test-Path $exePath)) {
  throw "No se encontro el ejecutable esperado: $exePath"
}

$didSign = $false

if (-not $SkipSign) {
  if ([string]::IsNullOrWhiteSpace($PfxPath) -and [string]::IsNullOrWhiteSpace($CertThumbprint)) {
    Write-Warning "Build sin firma digital. Con Smart App Control en 'On' este .exe se bloqueara."
    Write-Warning "Para release publica firma con Authenticode + timestamp (certificado RSA de CA confiable)."
  } else {
    $signToolPath = Get-SignToolPath
    if (-not $signToolPath) {
      throw "No se encontro signtool.exe. Instala Windows SDK para firmar el ejecutable."
    }

    $signArgs = @(
      "sign",
      "/v",
      "/fd", "SHA256",
      "/tr", $TimestampUrl,
      "/td", "SHA256",
      "/d", $FileDescription
    )

    if (-not [string]::IsNullOrWhiteSpace($PfxPath)) {
      if (-not (Test-Path $PfxPath)) {
        throw "No existe el certificado PFX: $PfxPath"
      }
      $signArgs += @("/f", $PfxPath)
      if (-not [string]::IsNullOrWhiteSpace($PfxPassword)) {
        $signArgs += @("/p", $PfxPassword)
      }
    } else {
      $signArgs += @("/sha1", $CertThumbprint, "/s", "My")
      if ($MachineStore) {
        $signArgs += "/sm"
      }
    }

    $signArgs += $exePath
    & $signToolPath @signArgs
    & $signToolPath verify /pa /v $exePath
    $signature = Get-AuthenticodeSignature -FilePath $exePath
    if ($signature.Status -ne "Valid") {
      throw "La firma no quedo valida. Status: $($signature.Status) - $($signature.StatusMessage)"
    }
    $pubKeyAlg = $signature.SignerCertificate.PublicKey.Oid.FriendlyName
    if ([string]::IsNullOrWhiteSpace($pubKeyAlg) -or $pubKeyAlg -notmatch "RSA") {
      Write-Warning "Smart App Control requiere firma con certificado RSA. Algoritmo detectado: $pubKeyAlg"
    }
    $didSign = $true
  }
}

if (-not $SkipDefenderScan) {
  $scanCmd = Get-Command Start-MpScan -ErrorAction SilentlyContinue
  if ($scanCmd) {
    Write-Host "Ejecutando escaneo de Microsoft Defender sobre: $exePath"
    Start-MpScan -ScanPath $exePath -ScanType CustomScan
  } else {
    Write-Warning "Start-MpScan no esta disponible en esta maquina. Se omite escaneo Defender."
  }
}

$fileHash = Get-FileHash -Path $exePath -Algorithm SHA256
$hashPath = "$exePath.sha256"
$hashLine = "$($fileHash.Hash) *$([IO.Path]::GetFileName($exePath))"
Set-Content -Path $hashPath -Value $hashLine -Encoding ASCII

$manifestPath = Join-Path $PSScriptRoot "dist\\$buildName-release.json"
$manifest = [ordered]@{
  generatedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
  oneFile = [bool]$OneFile
  executable = [IO.Path]::GetFullPath($exePath)
  version = $ProductVersion
  signed = $didSign
  sha256 = $fileHash.Hash
}
$manifest | ConvertTo-Json | Set-Content -Path $manifestPath -Encoding UTF8

if ($OneFile) {
  Write-Host "Build completado. Output: dist/$buildName.exe"
} else {
  Write-Host "Build completado. Output: dist/$buildName (folder)"
}
Write-Host "Hash SHA256: $hashPath"
Write-Host "Manifest release: $manifestPath"
