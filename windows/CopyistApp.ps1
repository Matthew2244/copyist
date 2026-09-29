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
Add-Type -AssemblyName System.Drawing
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
    # the chart the window says it is working on; the file dialog only
    # when there is none yet. "Open a chart" (Ctrl+O) changes it.
    if (Test-Path $lastFile) {
        $last = (Get-Content $lastFile -Raw).Trim()
        if ($last -and (Test-Path $last)) { return $last }
    }
    return (Open-Chart)
}

function Open-Chart {
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = 'Pick a .chart file'
    $dlg.Filter = 'Chart files (*.chart)|*.chart|All files (*.*)|*.*'
    if ($dlg.ShowDialog() -ne 'OK') { return $null }
    Set-Content -Path $lastFile -Value $dlg.FileName
    return $dlg.FileName
}

function Open-Talk([string]$p, [string]$cmd) {
    # a conversation runs in a real console window, which NVDA and JAWS
    # read natively. It waits for a key at the end, so the last thing
    # said ("Saved 4 notes...") is still there to be read - a window
    # that closes on its own takes the answer with it.
    Set-Content -Path $lastFile -Value $p
    $line = '/c "' + $py + ' "' + $chartPy + '" "' + $p + '" ' + $cmd +
        ' & echo. & echo Done. Press any key to close this window. & pause >nul"'
    Start-Process -FilePath 'cmd.exe' -ArgumentList $line
}

function Offer-Teach([string]$p, [string]$log) {
    # after a build: if the take played notes Copyist could not name,
    # offer the conversation that names them - once, then every chart
    # from that library or kit reads right
    $opts = @()
    if ($log -like "*aren't General MIDI drums*") {
        $opts += 'Name the drum notes - what each note is on your kit' }
    if ($log -like '*has no name yet*') {
        $opts += 'Name the keyswitches - what each unnamed key does' }
    if (-not $opts) { return }
    $c = Choose-FromList ('Your demo played notes Copyist could not name ' +
        'yet. Teach it now? It asks one at a time and remembers.') (
        $opts + @('Not now'))
    if ($c -like 'Name the drum*') { Open-Talk $p 'drums' }
    elseif ($c -like 'Name the key*') { Open-Talk $p 'keys' }
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
        if ($st.path) { Offer-Teach $st.path $log }
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
    @{ pid = $proc.Id; name = (Split-Path -Leaf $p); path = $p } |
        ConvertTo-Json | Set-Content $buildState
    Show-Info ("$doing It runs in the background - keep working, " +
        "and pick 'How is the build going' whenever you want the news.")
}

function Do-Export {
    # the export picker, one plain question at a time: bars, parts,
    # what to make, the look. Empty keeps the whole song, every part,
    # the settings' exports and the chart's own look.
    $p = Pick-Chart
    if (-not $p) { return }
    $bars = [Microsoft.VisualBasic.Interaction]::InputBox(
        'Which bars? As printed on the pages, like 9-24. Empty for the whole song.',
        'Copyist - Export', '')
    $parts = [Microsoft.VisualBasic.Interaction]::InputBox(
        ('Which parts? Names separated by commas, or score, or parts for every part without the score. Empty for the score and every part. The band: ' +
         ((Run-Chart ('"' + $p + '" parts --labels')) -split "`n" -join ', ')),
        'Copyist - Export', '')
    $makes = [Microsoft.VisualBasic.Interaction]::InputBox(
        'What to make? Any of pages, listen, braille, braille pages, read-alouds, separated by commas, or all. Empty uses your settings.',
        'Copyist - Export', '')
    $look = Choose-FromList 'How should the pages look?' @(
        "The chart's own", 'jazz', 'handwritten', 'engraved', 'plain', 'Back')
    if (-not $look -or $look -eq 'Back') { return }
    $mode = 'build'
    if ($bars.Trim()) { $mode += ' --bars "' + $bars.Trim() + '"' }
    if ($parts.Trim()) { $mode += ' --parts "' + $parts.Trim() + '"' }
    if ($makes.Trim()) { $mode += ' --exports "' + $makes.Trim() + '"' }
    if ($look -ne "The chart's own") { $mode += ' --look ' + $look }
    Do-BuildKnown $p $mode 'Exporting what you picked.'
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
    'What a build makes'                 = @('exports', 'braille_page')
    'Where finished files go'            = @('pages_to', 'listens_to',
                                             'spoken_to', 'braille_to')
    'MIDI and demos'                     = @('midi', 'quant', 'countin')
    'Sounds - the sample shelf'          = @('sounds', 'sounds_dir')
    'What the listen makes up'           = @('listen_grooves',
                                             'listen_solos',
                                             'listen_backgrounds',
                                             'listen_endings',
                                             'listen_mutes',
                                             'listen_brushes',
                                             'listen_builds',
                                             'listen_feather')
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
        if ($c -in @('notify', 'open') -or $c -like 'listen_*') {
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
            if ($c -eq 'braille_page') {
                $hint = ' Standard (40 cells by 25 lines, 11 by 11.5 inch paper), letter (34 by 25), a4 (35 by 28), or cells x lines like 32x25.'
            }
            if ($c -eq 'exports') {
                $hint = ' Any mix of pages, listen, braille, braille pages and read-alouds, separated by commas - or all.'
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

function Do-BringIn {
    # a score, a MIDI demo, or words and chords in any format - the
    # same door as the Mac app's Bring in a file
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = 'Bring in a file - a score, a MIDI demo, or words and chords'
    $dlg.Filter = ('Everything Copyist reads|*.musicxml;*.xml;*.mxl;' +
        '*.mscz;*.mid;*.midi;*.txt;*.md;*.rtf;*.doc;*.docx;*.odt;' +
        '*.html;*.htm;*.pdf;*.cho;*.chordpro;*.chopro;*.crd;*.pro;*.abc|' +
        'All files (*.*)|*.*')
    if ($dlg.ShowDialog() -ne 'OK') { return }
    $f = $dlg.FileName
    $ext = [System.IO.Path]::GetExtension($f).ToLower()
    if (@('.mid', '.midi', '.kar', '.smf') -contains $ext) {
        # the demo interview is a conversation: a real console window,
        # which NVDA reads natively
        $line = '/c "' + $py + ' "' + $chartPy + '" import "' + $f +
            '" & echo. & echo Done. Press any key to close this window. & pause >nul"'
        Start-Process -FilePath 'cmd.exe' -ArgumentList $line
        return
    }
    $into = ''
    $words = @('.txt', '.md', '.rtf', '.doc', '.docx', '.odt', '.html',
        '.htm', '.pdf')
    if (($words -contains $ext) -and (Test-Path $lastFile)) {
        $last = (Get-Content $lastFile -Raw).Trim()
        if ($last -and (Test-Path $last)) {
            $name = Split-Path -Leaf $last
            $c = Choose-FromList 'Where do these words go?' @(
                "Add them to $name", 'Start a new tune from this file',
                'Back')
            if (-not $c -or $c -eq 'Back') { return }
            if ($c -like 'Add them*') { $into = ' --into "' + $last + '"' }
        }
    }
    $out = Run-Chart ('import "' + $f + '"' + $into)
    $made = ($out -split "`n" | Where-Object { $_ -like 'chart: *' } |
        Select-Object -Last 1)
    $shown = ($out -split "`n" | Where-Object { $_ -notlike 'chart: *' }) -join "`n"
    if ($made) {
        $path = $made.Substring(7).Trim()
        Set-Content -Path $lastFile -Value $path
        $shown += "`n`nThis is now the chart you are working on: " +
            (Split-Path -Leaf $path) + '.'
    }
    Show-Info $shown
    if ($made) {
        $path = $made.Substring(7).Trim()
        if ($out -like '*tell me the tune.*') {
            $n = Choose-FromList 'Next: the words have no form yet.' @(
                'Tell me the tune - the roadmap conversation', 'Not now')
            if ($n -like 'Tell me*') { Open-Talk $path 'edit' }
        } else {
            $n = Choose-FromList 'Next?' @('Build it now', 'Not now')
            if ($n -eq 'Build it now') {
                Do-BuildKnown $path '' 'Building the whole desk: pages, the listen MP3, read-alouds and findings.'
            }
        }
    }
}

# ---------------------------------------------------------------- the window
# Five tabs, the Mac app's five. Ctrl+1 to Ctrl+5 jump straight to one
# and put focus on the tab control, so NVDA and JAWS say "Build tab, 2
# of 5" themselves; Ctrl+Tab steps through them, as in any Windows tab
# control. The work has keys too: Ctrl+B builds, Ctrl+Shift+B makes just the braille, Ctrl+E exports a choice of bars and parts, Ctrl+K checks, Ctrl+L
# listens, Ctrl+O opens a chart. Each button names its key in its
# accessible description, so the screen reader says it after the name.

$font = New-Object System.Drawing.Font('Segoe UI', 11)
$headFont = New-Object System.Drawing.Font('Segoe UI Semibold', 15)

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Copyist'
$form.Width = 820; $form.Height = 620
$form.StartPosition = 'CenterScreen'
$form.Font = $font
$form.KeyPreview = $true
$form.AutoScaleMode = 'Dpi'

$working = New-Object System.Windows.Forms.Label
$working.Dock = 'Top'; $working.Height = 40
$working.Padding = New-Object System.Windows.Forms.Padding(12, 10, 12, 0)
$working.AccessibleName = 'Working on'

function Update-Working {
    $n = 'no chart yet - Ctrl+O opens one'
    if (Test-Path $lastFile) {
        $last = (Get-Content $lastFile -Raw).Trim()
        if ($last -and (Test-Path $last)) {
            $n = [System.IO.Path]::GetFileNameWithoutExtension($last)
        }
    }
    $working.Text = "Working on: $n"
    $working.AccessibleName = "Working on: $n"
}

$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Dock = 'Fill'
$tabs.Padding = New-Object System.Drawing.Point(14, 6)
$tabs.AccessibleName = 'Copyist tabs'

$tabNames = @('Chart', 'Build', 'Listen and read', 'Conversation',
    'Settings')
$tabBlurbs = @(
    'Choose, start or bring in a chart.',
    'Build, check, and what changed. Builds run in the background.',
    'Hear the band from any bar, or open a part read aloud.',
    'Tell Copyist the tune, or teach it your keyswitches and drums.',
    'Every setting says what it is set to.')

function New-Page([int]$i) {
    $page = New-Object System.Windows.Forms.TabPage
    $page.Text = $tabNames[$i] + '  (Ctrl+' + ($i + 1) + ')'
    $page.AccessibleName = $tabNames[$i]
    $page.AccessibleDescription = $tabBlurbs[$i]
    $flow = New-Object System.Windows.Forms.FlowLayoutPanel
    $flow.Dock = 'Fill'; $flow.FlowDirection = 'TopDown'
    $flow.WrapContents = $false; $flow.AutoScroll = $true
    $flow.Padding = New-Object System.Windows.Forms.Padding(14)
    $head = New-Object System.Windows.Forms.Label
    $head.Text = $tabNames[$i]; $head.Font = $headFont
    $head.AutoSize = $true
    $head.AccessibleRole = 'StaticText'
    $sub = New-Object System.Windows.Forms.Label
    $sub.Text = $tabBlurbs[$i]; $sub.AutoSize = $true
    $sub.Margin = New-Object System.Windows.Forms.Padding(3, 0, 3, 14)
    $flow.Controls.Add($head); $flow.Controls.Add($sub)
    $page.Controls.Add($flow)
    [void]$tabs.TabPages.Add($page)
    return $flow
}

function Add-Action($flow, [string]$title, [string]$line, [string]$key,
                    [scriptblock]$act) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $title + $(if ($key) { "   ($key)" } else { '' }) +
        "`n" + $line
    $b.TextAlign = 'MiddleLeft'
    $b.Width = 700; $b.Height = 64
    $b.Margin = New-Object System.Windows.Forms.Padding(3, 3, 3, 8)
    $b.AccessibleName = $title
    $b.AccessibleDescription = $line + $(if ($key) { " $key." } else { '' })
    $b.Add_Click($act)
    $flow.Controls.Add($b)
}

$chartFlow = New-Page 0
Add-Action $chartFlow 'Open a chart' 'From your charts folder.' 'Ctrl+O' {
    if (Open-Chart) { Update-Working } }
Add-Action $chartFlow 'Bring in a file' 'A score, a MIDI demo, or words and chords in almost any format.' 'Ctrl+Shift+I' {
    Do-BringIn; Update-Working }
Add-Action $chartFlow 'Tell me the tune' 'The roadmap conversation, in a console your screen reader reads.' 'Ctrl+Shift+T' {
    $p = Pick-Chart; if ($p) { Open-Talk $p 'edit'; Update-Working } }

$buildFlow = New-Page 1
Add-Action $buildFlow 'Build it' 'Everything your settings ask for: pages, the listen MP3, braille, read-alouds and findings.' 'Ctrl+B' {
    Do-Build '' 'Building everything your settings ask for.' }
Add-Action $buildFlow 'Check it' 'Compile only - every measure gets counted, nothing rendered.' 'Ctrl+K' {
    Do-Build 'c' 'Checking the chart - every measure gets counted.' }
Add-Action $buildFlow 'What changed' 'Since the last build, by part and by bar.' 'Ctrl+D' {
    Do-Build 'd' 'Reading what changed since your last build, part by part.' }
Add-Action $buildFlow 'Export' 'Choose the bars, the parts, what to make and the look.' 'Ctrl+E' {
    Do-Export }
Add-Action $buildFlow 'Braille' 'Just the braille: a file for each part, read back against the score.' 'Ctrl+Shift+B' {
    Do-Build 'braille' 'Making the braille, each part read back against the score.' }
Add-Action $buildFlow 'How is the build going' 'The news on a background build, on a button press, never a timer.' 'F5' {
    Do-HowGoes }

$listenFlow = New-Page 2
Add-Action $listenFlow 'Listen' 'The whole band, or just your chair, from any bar.' 'Ctrl+L' {
    Do-Listen }
Add-Action $listenFlow 'Read a part aloud' 'Opens a part''s read-aloud in Notepad; a screen reader reads it like a letter.' 'Ctrl+R' {
    Do-ReadPart }
Add-Action $listenFlow 'The sound shelf' 'What the band plays on.' '' {
    Show-Info (Run-Chart 'sounds') }

$talkFlow = New-Page 3
Add-Action $talkFlow 'Tell me the tune' 'Describe it in one breath; Copyist writes the sections.' 'Ctrl+Shift+T' {
    $p = Pick-Chart; if ($p) { Open-Talk $p 'edit' } }
Add-Action $talkFlow 'Name the keyswitches' 'Say once what each unnamed key in your demo does.' '' {
    $p = Pick-Chart; if ($p) { Open-Talk $p 'keys' } }
Add-Action $talkFlow 'Name the drum notes' 'Your drum library''s note map, said once and kept.' '' {
    $p = Pick-Chart; if ($p) { Open-Talk $p 'drums' } }

$setFlow = New-Page 4
Add-Action $setFlow 'The settings desk' 'Your name, the look, where files go, how your playing is read.' 'Ctrl+Comma' {
    Do-Settings }
Add-Action $setFlow 'Help - what this is' 'Copyist in a paragraph.' 'F1' {
    Show-Info ('Copyist turns a chart file - plain words and a ' +
        'played demo - into engraved parts, a conductor score, ' +
        'spoken read-alouds and a listening MP3, all its own ink. ' +
        'Write charts with any text editor; the guide is ' +
        'CHART-WRITING.md. Ctrl+1 to Ctrl+5 move between the tabs.') }

function Go-Tab([int]$i) {
    $tabs.SelectedIndex = $i
    # focus on the tab strip: the screen reader names the tab and its
    # place, "Build tab, 2 of 5", with no speech of our own on top
    [void]$tabs.Focus()
}

$form.Add_KeyDown({
    param($s, $e)
    $k = $e.KeyCode
    if ($e.Control -and -not $e.Alt) {
        $n = [int]$k - [int][System.Windows.Forms.Keys]::D1
        if ($n -ge 0 -and $n -lt 5 -and -not $e.Shift) {
            Go-Tab $n; $e.Handled = $true; $e.SuppressKeyPress = $true
            return
        }
        $e.SuppressKeyPress = $true
        switch ($k) {
            'O' { if (Open-Chart) { Update-Working } }
            'B' {
                if ($e.Shift) { Do-Build 'braille' 'Making the braille, each part read back against the score.' }
                else { Do-Build '' 'Building everything your settings ask for.' }
            }
            'K' { Do-Build 'c' 'Checking the chart - every measure gets counted.' }
            'E' { Do-Export }
            'D' { Do-Build 'd' 'Reading what changed since your last build, part by part.' }
            'L' { Do-Listen }
            'R' { Do-ReadPart }
            'I' { if ($e.Shift) { Do-BringIn; Update-Working } }
            'T' { if ($e.Shift) { $p = Pick-Chart; if ($p) { Open-Talk $p 'edit' } } }
            'Oemcomma' { Go-Tab 4; Do-Settings }
            default { $e.SuppressKeyPress = $false; return }
        }
        $e.Handled = $true
        return
    }
    if ($k -eq 'F5') { Do-HowGoes; $e.Handled = $true }
    if ($k -eq 'F1') {
        Go-Tab 4
        Show-Info 'Ctrl+1 to Ctrl+5 move between the tabs: Chart, Build, Listen and read, Conversation, Settings. Ctrl+B builds, Ctrl+Shift+B makes just the braille, Ctrl+E exports a choice of bars and parts, Ctrl+K checks, Ctrl+L listens, Ctrl+O opens a chart, F5 asks how a build is going.'
        $e.Handled = $true
    }
})

$form.Controls.Add($tabs)
$form.Controls.Add($working)
Update-Working
$form.Add_Shown({ [void]$tabs.Focus() })
[void]$form.ShowDialog()
