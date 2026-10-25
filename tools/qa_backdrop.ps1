# Controlled background for verifying blur and the four window corners.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = 'FluentGlass controlled blur background'
$form.FormBorderStyle = 'None'
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point(40,40)
$form.Size = New-Object System.Drawing.Size(1320,850)
$form.BackColor = [System.Drawing.Color]::White
$form.ShowInTaskbar = $false
$form.Add_Paint({
    param($sender,$e)
    $g = $e.Graphics
    $g.Clear([System.Drawing.Color]::White)
    $colors = @('#E9EDF5','#6C94C5','#A6BBD6','#C5999B','#8CA7B1','#D6C8B7')
    for ($x=16; $x -lt 1290; $x+=64) {
        $color = [System.Drawing.ColorTranslator]::FromHtml($colors[[int]($x/64) % $colors.Count])
        $brush = New-Object System.Drawing.SolidBrush($color)
        $g.FillRectangle($brush,$x,16,64,810)
        $brush.Dispose()
    }
    for ($x=640; $x -lt 1230; $x+=8) {
        $g.FillRectangle([System.Drawing.Brushes]::Black,$x,120,4,480)
    }
    $font = New-Object System.Drawing.Font('Segoe UI',40)
    $g.DrawString('Glass verification',$font,[System.Drawing.Brushes]::White,70,330)
    $font.Dispose()
})
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval=300000
$timer.Add_Tick({$form.Close()})
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
