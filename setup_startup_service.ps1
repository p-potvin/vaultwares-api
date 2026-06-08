<#
.SYNOPSIS
Sets up the vaultwares pipeline to run automatically upon Windows boot.
This creates a hidden background service that launches Redis, API (with reload),
the frontend, and the Task Assigner.

It will copy a VBScript into the user's Startup folder.
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$StartupFolder = [Environment]::GetFolderPath('Startup')
$CmdTarget = "$ScriptDir\start_dev_background.cmd"
$VbsTarget = "$ScriptDir\vaultwares_background.vbs"
$StartupLink = "$StartupFolder\vaultwares_background.vbs"

# 1. Create the VBS Wrapper (runs the bat completely hidden)
$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "$CmdTarget" & Chr(34), 0
Set WshShell = Nothing
"@
Out-File -FilePath $VbsTarget -InputObject $VbsContent -Encoding UTF8

# 2. Copy the VBS to Startup Folder
Copy-Item -Path $VbsTarget -Destination $StartupLink -Force
Write-Host "Success: Added VaultWares pipeline to Windows Startup!" -ForegroundColor Green
Write-Host "It is now configured to start listening automatically when Windows boots."
Write-Host "You can stop the service using: stop_dev_background.cmd"
Write-Host "Or you can remove it from startup by deleting: $StartupLink"
Write-Host "Press any key to test and start the background service now..."
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')

# Optional: Run it right away for them
wscript.exe $StartupLink
Write-Host "`nBackground service started!" -ForegroundColor Cyan