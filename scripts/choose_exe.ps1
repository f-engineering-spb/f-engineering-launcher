# Windows Open File Dialog for picking executable (.exe) in FLauncher.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Filter = "Исполняемые файлы (*.exe)|*.exe|Все файлы (*.*)|*.*"
$dlg.Title = "Выберите программу для запуска (.exe)"
$dlg.RestoreDirectory = $true

if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    if ($dlg.FileName -and (Test-Path $dlg.FileName)) {
        [Console]::WriteLine($dlg.FileName)
    }
}
