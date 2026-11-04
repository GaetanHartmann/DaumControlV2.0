$ErrorActionPreference = 'Stop'
Write-Host 'SSH-Zugang fuer gha@ghapi3.local einrichten'
Write-Host 'Bitte jetzt das im Imager festgelegte Pi-Passwort eingeben. Beim Tippen erscheinen keine Zeichen.'
Get-Content -LiteralPath 'C:\Users\GaetanHartmann\.ssh\ghapi3_ed25519.pub' | ssh -4 -o ConnectTimeout=15 gha@ghapi3.local 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
if ($LASTEXITCODE -eq 0) { Write-Host 'SSH-Schluessel erfolgreich eingerichtet.' -ForegroundColor Green } else { Write-Host 'Anmeldung fehlgeschlagen. Bitte den Fehler hier im Chat mitteilen.' -ForegroundColor Red }
Read-Host 'Enter zum Schliessen'
