Write-Host 'DAUM Studio: LAN, Bluetooth und Autostart einrichten.'
Write-Host 'Pi-Passwort bei der sudo-Abfrage eingeben und Enter druecken.'
Write-Host 'Beim Tippen erscheinen keine Zeichen. Das ist normal.'
ssh -4 -t -i C:\Users\GaetanHartmann\.ssh\ghapi3_ed25519 -o ServerAliveInterval=15 -o ServerAliveCountMax=8 -o ConnectTimeout=15 gha@192.168.178.125 'sudo sh /home/gha/daum-studio/deploy/configure-pi.sh'
if ($LASTEXITCODE -eq 0) { Write-Host 'Pi-Einrichtung erfolgreich.' -ForegroundColor Green } else { Write-Host 'Bitte Fehlermeldung im Chat mitteilen.' -ForegroundColor Yellow }
Read-Host 'Enter zum Schliessen'
