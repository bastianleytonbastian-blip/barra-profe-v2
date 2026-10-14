# Reproduce el sonido de inicio mientras corre el instalador.
#
# Se usa MCI (winmm.dll), que viene en Windows y sabe de MP3: en este momento
# el PC puede no tener Python todavia, asi que no se puede depender de el.
#
# Deja su PID en un archivo para que INSTALAR.bat pueda callarlo al terminar.

param(
    [Parameter(Mandatory = $true)][string]$Archivo,
    [string]$ArchivoPid = "$env:TEMP\webclass_musica.pid"
)

if (-not (Test-Path $Archivo)) { exit }

try {
    $PID | Out-File -FilePath $ArchivoPid -Encoding ascii -Force

    Add-Type -Name Mci -Namespace Winmm -MemberDefinition @'
[DllImport("winmm.dll", CharSet = CharSet.Unicode)]
public static extern int mciSendString(string orden, System.Text.StringBuilder respuesta,
                                       int largo, System.IntPtr callback);
'@

    $resp = New-Object System.Text.StringBuilder 256
    $nulo = [System.IntPtr]::Zero
    if ([Winmm.Mci]::mciSendString("open `"$Archivo`" type mpegvideo alias musica", $null, 0, $nulo) -ne 0) {
        exit
    }
    [Winmm.Mci]::mciSendString("status musica length", $resp, 256, $nulo) | Out-Null
    $segundos = 180
    if ($resp.ToString() -match '^\d+$') { $segundos = [int]$resp.ToString() / 1000 }

    [Winmm.Mci]::mciSendString("play musica", $null, 0, $nulo) | Out-Null
    Start-Sleep -Seconds ([Math]::Min($segundos + 1, 600))
    [Winmm.Mci]::mciSendString("close musica", $null, 0, $nulo) | Out-Null
}
catch {
    # Que no suene no puede impedir la instalacion.
}
finally {
    Remove-Item $ArchivoPid -Force -ErrorAction SilentlyContinue
}
