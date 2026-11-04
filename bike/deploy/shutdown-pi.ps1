Write-Host 'Pi herunterfahren: Bitte bei der sudo-Abfrage das Passwort von gha eingeben.'
ssh -4 -t -i C:\Users\GaetanHartmann\.ssh\ghapi3_ed25519 -o ServerAliveInterval=15 -o ConnectTimeout=10 gha@192.168.178.125 'sudo shutdown -h now'
Write-Host 'Nach erfolgreicher Passworteingabe faehrt der Pi herunter. Vor dem Abziehen etwa 20 Sekunden warten.'
Read-Host 'Enter zum Schliessen'
