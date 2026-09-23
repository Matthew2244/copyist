# CopyistApp.ps1 - Copyist with native Windows dialogs a screen reader
# reads. Double-click Copyist.bat next to this file, or run:
#   powershell -ExecutionPolicy Bypass -File CopyistApp.ps1
#
# Needs Python 3 from python.org (tick "Add python.exe to PATH").
# Everything else is in this repository - no other installs.
#
# HONESTY NOTE: written on a Mac, not yet run on a real Windows
# machine. The controls are plain WinForms - buttons, a list box, the
# standard file dialog - chosen because NVDA and JAWS read them well.
# If something misbehaves, that is a bug worth reporting.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

$root = Split-Path -Parent $PSScriptRoot
$chartPy = Join-Path $root 'prototype\chart.py'
$lastFile = Join-Path $env:APPDATA 'copyist-last-chart.txt'

function Show-Info([string]$msg) {
    [System.Windows.Forms.MessageBox]::Show($msg, 'Copyist') | Out-Null
}

$py = $null
foreach ($cand in @('py', 'python', 'python3')) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) { $py = $cand; break }
}
if (-not $py) {
    Show-Info ("Copyist needs Python 3. Install it free from " +
        "python.org and tick 'Add python.exe to PATH', then run this again.")
    exit 1
}
if (-not (Test-Path $chartPy)) {
    Show-Info "Cannot find prototype\chart.py next to this app - keep the windows folder inside the copyist folder."
    exit 1
}

function Run-Chart([string]$argline) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $py
    $psi.Arguments = '"' + $chartPy + '" ' + $argline
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $p = [System.Diagnostics.Process]::Start($psi)
    # drain stderr in the background while stdout reads: two full
    # pipes read one after the other is the classic deadlock
    $errTask = $p.StandardError.ReadToEndAsync()
    $out = $p.StandardOutput.ReadToEnd()
    $err = $errTask.Result
    $p.WaitForExit()
    return ($out + $err).Trim()
}

function Tail([string]$text, [int]$n) {
    $lines = $text -split "`n"
    if ($lines.Count -le $n) { return $text }
    return ($lines[-$n..-1] -join "`n")
}

function Choose-FromList([string]$prompt, [string[]]$items) {
    $f = New-Object System.Windows.Forms.Form
    $f.Text = 'Copyist'
    $f.Width = 640; $f.Height = 460
    $f.StartPosition = 'CenterScreen'
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = $prompt; $lbl.Dock = 'Top'; $lbl.Height = 60
    $lb = New-Object System.Windows.Forms.ListBox
    $lb.Dock = 'Fill'
    foreach ($i in $items) { [void]$lb.Items.Add($i) }
    if ($lb.Items.Count -gt 0) { $lb.SelectedIndex = 0 }
    $panel = New-Object System.Windows.Forms.FlowLayoutPanel
    $panel.Dock = 'Bottom'; $panel.Height = 44
    $panel.FlowDirection = 'RightToLeft'
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = 'OK'; $ok.DialogResult = 'OK'
    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'Cancel'; $cancel.DialogResult = 'Cancel'
    $panel.Controls.Add($ok); $panel.Controls.Add($cancel)
    $f.Controls.Add($lb); $f.Controls.Add($lbl); $f.Controls.Add($panel)
    $f.AcceptButton = $ok      # Enter chooses
    $f.CancelButton = $cancel  # Escape backs out
    $lb.Add_DoubleClick({ $f.DialogResult = 'OK'; $f.Close() })
    if ($f.ShowDialog() -eq 'OK' -and $lb.SelectedItem) {
        return [string]$lb.SelectedItem
    }
    return $null
}

function Pick-Chart {
    if (Test-Path $lastFile) {
        $last = (Get-Content $lastFile -Raw).Trim()
        if ($last -and (Test-Path $last)) {
            $name = Split-Path -Leaf $last
            $c = Choose-FromList 'Which chart are we working on?' @(
                "Same chart: $name", 'Pick a different chart', 'Back')
            if (-not $c -or $c -eq 'Back') { return $null }
            if ($c -like 'Same chart*') { return $last }
        }
    }
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = 'Pick a .chart file'
    $dlg.Filter = 'Chart files (*.chart)|*.chart|All files (*.*)|*.*'
    if ($dlg.ShowDialog() -ne 'OK') { return $null }
    Set-Content -Path $lastFile -Value $dlg.FileName
    return $dlg.FileName
}

$buildLog = Join-Path $env:APPDATA 'copyist-build.log'
$buildState = Join-Path $env:APPDATA 'copyist-build.json'

function Do-Build([string]$mode, [string]$doing) {
    # the build runs in the background - the menu comes straight back,
    # and 'How is the build going' answers whenever you ask. Never a
    # timer: a dialog that talks over a screen reader is noise.
    $p = Pick-Chart
    if (-not $p) { return }
    Do-BuildKnown $p $mode $doing
}

function Do-HowGoes {
    if (-not (Test-Path $buildState)) {
        Show-Info 'No build has been started from here yet.'
        return
    }
    $st = Get-Content $buildState -Raw | ConvertFrom-Json
    $log = if (Test-Path $buildLog) {
        Get-Content $buildLog -Raw -ErrorAction SilentlyContinue } else { '' }
    if (-not $log) { $log = '' }
    $lines = ($log -split "`n") | Where-Object { $_.Trim() }
    $prog = $lines | Where-Object { $_ -like 'progress:*' } |
        Select-Object -Last 1
    $plain = $lines | Where-Object { $_ -notlike 'progress:*' }
    $running = Get-Process -Id $st.pid -ErrorAction SilentlyContinue
    if ($running) {
        $word = if ($prog) { ($prog -replace '^progress:\s*', '') }
                else { 'warming up' }
        Show-Info ("Still going: " + $st.name + " - " + $word)
    } else {
        $tail = if ($plain) {
            ($plain | Select-Object -Last 8) -join "`n" } else { 'Done.' }
        Show-Info ("Finished: " + $st.name + "`n`n" + $tail)
    }
}

function Do-Listen {
    $p = Pick-Chart
    if (-not $p) { return }
    $bar = [Microsoft.VisualBasic.Interaction]::InputBox(
        'Start at which bar? Your DAW number is fine. Empty means the top.',
        'Copyist', '')
    $solo = [Microsoft.VisualBasic.Interaction]::InputBox(
        'Solo who? Name parts like: bari, bone. Empty means the whole band.',
        'Copyist', '')
    $mode = 'l'
    if ($bar -match '^\d+$') { $mode += ' --from-bar ' + $bar }
    if ($solo.Trim()) { $mode += ' --solo "' + $solo.Trim() + '"' }
    Set-Content -Path $lastFile -Value $p
    Do-BuildKnown $p $mode ('Bouncing the listen. The band warms up.')
}

function Do-BuildKnown([string]$p, [string]$mode, [string]$doing) {
    # Do-Build without the chart question - the caller already asked
    if (Test-Path $buildState) {
        $st = Get-Content $buildState -Raw | ConvertFrom-Json
        if (Get-Process -Id $st.pid -ErrorAction SilentlyContinue) {
            Show-Info ("A build of '" + $st.name + "' is still going - " +
                "check on it first.")
            return
        }
    }
    Set-Content -Path $buildLog -Value ''
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'cmd.exe'
    $psi.Arguments = ('/c ' + $py + ' "' + $chartPy + '" "' + $p +
        '" ' + $mode + ' > "' + $buildLog + '" 2>&1')
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $psi.EnvironmentVariables['COPYIST_PROGRESS'] = '1'
    $proc = [System.Diagnostics.Process]::Start($psi)
    @{ pid = $proc.Id; name = (Split-Path -Leaf $p) } |
        ConvertTo-Json | Set-Content $buildState
    Show-Info ("$doing It runs in the background - keep working, " +
        "and pick 'How is the build going' whenever you want the news.")
}

function Do-ReadPart {
    $p = Pick-Chart
    if (-not $p) { return }
    $dir = Split-Path -Parent $p
    # read-alouds live next to the chart, unless settings sent them
    # somewhere else (spoken_to)
    $cfgPath = Join-Path $env:USERPROFILE '.config\copyist\config.json'
    if (Test-Path $cfgPath) {
        $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
        if ($cfg.spoken_to) { $dir = $cfg.spoken_to }
    }
    $files = Get-ChildItem -Path $dir -Filter '* read aloud.txt' -ErrorAction SilentlyContinue
    if (-not $files) {
        Show-Info 'No read-alouds here yet - build or check the chart first. They land next to the chart, or wherever your settings send them.'
        return
    }
    $c = Choose-FromList 'Which part should Notepad open? A screen reader reads it like a letter.' (
        @($files | ForEach-Object { $_.Name }) + @('Back'))
    if (-not $c -or $c -eq 'Back') { return }
    Start-Process notepad.exe -ArgumentList ('"' + (Join-Path $dir $c) + '"')
}

$settingGroups = [ordered]@{
    'Your charts - name and look'        = @('composer', 'look')
    'When a build lands - ping and open' = @('notify', 'open')
    'Where finished files go'            = @('pages_to', 'listens_to',
                                             'spoken_to')
    'MIDI and demos'                     = @('midi', 'quant', 'countin')
    'Sounds - the sample shelf'          = @('sounds', 'sounds_dir')
}

function Do-Settings {
    while ($true) {
        $g = Choose-FromList ('The defaults desk. Which corner?') (
            @($settingGroups.Keys) + @('Back'))
        if (-not $g -or $g -eq 'Back') { return }
        $desk = Run-Chart 'settings'
        $keys = $settingGroups[$g]
        $shown = ($desk -split "`n") | Where-Object {
            $line = $_; ($keys | Where-Object { $line -like "$_*" }) }
        $c = Choose-FromList (($shown -join "`n") +
            "`nChange which one?") ($keys + @('Back'))
        if (-not $c -or $c -eq 'Back') { continue }
        if ($c -in @('notify', 'open')) {
            $v = Choose-FromList "Set $c to:" @('yes', 'no', 'Back')
            if (-not $v -or $v -eq 'Back') { continue }
        } else {
            $hint = ''
            if ($c -eq 'look') {
                $hint = ' The looks are jazz, handwritten, engraved and plain; empty lets each chart decide.'
            }
            if ($c -eq 'sounds') {
                $hint = ' A sample library name or an .sf2 file path; empty plays the plain built-in synth.'
            }
            if ($c -eq 'sounds_dir') {
                $hint = ' Where sample libraries live and download; empty uses the standard spot.'
            }
            if ($c -eq 'midi') {
                $hint = ' The folder your DAW exports land in; play and the pickers start there.'
            }
            if ($c -eq 'quant') {
                $hint = ' How Copyist reads the rhythms you played: eighths, straight, sixteenths or triplets; empty lets each chart decide.'
            }
            if ($c -eq 'countin') {
                $hint = ' Count-in bars offered when a demo says nothing itself; any number, empty reads the demo.'
            }
            if ($c -like '*_to') {
                $hint = ' A folder path; empty keeps these files with the build.'
            }
            $v = [Microsoft.VisualBasic.Interaction]::InputBox(
                "New value for $c.$hint", 'Copyist', '')
        }
        Show-Info (Run-Chart ('set "' + $c + '=' + $v + '"'))
    }
}

while ($true) {
    $c = Choose-FromList ('Copyist - from your played demo to pages a band ' +
        'can read. What are we doing?') @(
        'Build - pages, listen MP3, findings',
        'Check - compile only, nothing rendered',
        'Listen - the whole band, or just your chair, from any bar',
        'What changed - since the last build, by part and by bar',
        'How is the build going - check in on a background build',
        'Read a part aloud',
        'Tell me the tune - the roadmap conversation, in a console',
        'Sounds - the band''s sample shelf',
        'Settings - the defaults desk',
        'Help - what this is',
        'Quit')
    if (-not $c) {
        # Escape at the main menu asks before leaving - sublists go
        # back on Escape, so the same key must not kill the app here
        $r = [System.Windows.Forms.MessageBox]::Show(
            'Leave Copyist?', 'Copyist', 'YesNo')
        if ($r -eq 'Yes') { break } else { continue }
    }
    if ($c -eq 'Quit') { break }
    switch -Wildcard ($c) {
        'Build*' { Do-Build '' 'Building the whole desk: pages, the listen MP3, read-alouds and findings.' }
        'Check*' { Do-Build 'c' 'Checking the chart - every measure gets counted.' }
        'Listen*' { Do-Listen }
        'What changed*' { Do-Build 'd' 'Reading what changed since your last build, part by part.' }
        'How is the build*' { Do-HowGoes }
        'Read*' { Do-ReadPart }
        'Tell me*' {
            $p = Pick-Chart
            if ($p) {
                # a real console window: the conversation is
                # interactive, and NVDA reads consoles natively
                Start-Process -FilePath $py -ArgumentList @(
                    ('"' + $chartPy + '"'), ('"' + $p + '"'), 'edit')
            }
        }
        'Sounds*' { Show-Info (Run-Chart 'sounds') }
        'Settings*' { Do-Settings }
        'Help*' {
            Show-Info ('Copyist turns a chart file - plain words and a ' +
                'played demo - into engraved parts, a conductor score, ' +
                'spoken read-alouds and a listening MP3, all its own ink. ' +
                'Write charts with any text editor; the guide is ' +
                'CHART-WRITING.md. The same brain answers to ' +
                '"python prototype\chart.py" in a terminal.')
        }
    }
}
