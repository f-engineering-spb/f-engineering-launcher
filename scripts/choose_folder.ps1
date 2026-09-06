Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "Select Project Files - F-Engineering Launcher"
$dialog.Filter = "All Supported Files (*.dwg;*.pdf;*.xlsx;*.docx;*.xls;*.doc;*.jpg;*.png)|*.dwg;*.pdf;*.xlsx;*.docx;*.xls;*.doc;*.jpg;*.png|All Files (*.*)|*.*"
$dialog.Multiselect = $true
$dialog.CheckFileExists = $true
$dialog.RestoreDirectory = $true
$dialog.ShowHelp = $false

$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dialog.FileNames) {
    foreach ($f in $dialog.FileNames) {
        [Console]::WriteLine($f)
    }
}
