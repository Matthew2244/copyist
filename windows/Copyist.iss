; Copyist for Windows: the installer (Inno Setup 6).
; Built by build-installer.ps1, which fetches WinSparkle first:
;   ISCC /DAppVersion=x.y.z Copyist.iss
;
; Installs for the current person only, into their own Programs folder,
; so it never asks for an administrator password. The same layout as
; the repository (windows\, prototype\, fonts\), so CopyistApp.ps1 finds
; the engine exactly as it does from a checkout. Adds a Start menu
; entry and an entry in Settings, Apps for uninstalling; uninstalling
; leaves charts and settings alone. WinSparkle runs this same installer
; quietly to update.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Never change AppId: it's how Windows knows a new version replaces the old one.
AppId={{5b7d3e2a-8f41-4c6e-9a0b-c0b1e57a7c21}
AppName=Copyist
AppVersion={#AppVersion}
AppVerName=Copyist {#AppVersion}
AppPublisher=Matthew Whitaker
AppPublisherURL=https://github.com/Matthew2244/copyist
AppSupportURL=https://github.com/Matthew2244/copyist/issues
DefaultDirName={localappdata}\Programs\Copyist
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\app\build
OutputBaseFilename=Copyist-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Put Copyist on the desktop"; Flags: unchecked

[Files]
Source: "..\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHART-WRITING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\CHART-FORMAT.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\prototype\*.py"; DestDir: "{app}\prototype"; Flags: ignoreversion
Source: "..\fonts\*"; DestDir: "{app}\fonts"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "CopyistApp.ps1"; DestDir: "{app}\windows"; Flags: ignoreversion
Source: "Copyist.bat"; DestDir: "{app}\windows"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}\windows"; Flags: ignoreversion
Source: "winsparkle\x64\WinSparkle.dll"; DestDir: "{app}\windows\x64"; Flags: ignoreversion
Source: "winsparkle\ARM64\WinSparkle.dll"; DestDir: "{app}\windows\ARM64"; Flags: ignoreversion

[InstallDelete]
; a new version may drop engine files the old one had: start clean there
Type: filesandordirs; Name: "{app}\prototype"

[Icons]
Name: "{autoprograms}\Copyist"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\CopyistApp.ps1"""; WorkingDir: "{app}"; Comment: "Charts into parts, braille, read-alouds and a listen"
Name: "{autodesktop}\Copyist"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\CopyistApp.ps1"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; After a normal install: offer to open it. After a quiet update (WinSparkle): open it again.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\CopyistApp.ps1"""; Description: "Open Copyist now"; Flags: nowait postinstall skipifsilent runhidden
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\windows\CopyistApp.ps1"""; Flags: nowait runhidden; Check: Relaunch

[Code]
// WinSparkle passes /relaunch=1 when it runs this quietly to update, so
// Copyist comes back by itself. A quiet install without it opens nothing.
function Relaunch(): Boolean;
begin
  Result := WizardSilent() and (ExpandConstant('{param:relaunch|0}') = '1');
end;
