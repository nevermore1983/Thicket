; Thicket installer (Inno Setup 7). Built by scripts/build_installer.py, which passes:
;   AppVersion   e.g. 1.0.0 (from src/wildlife/__init__.py)
;   AppFolder    the PyInstaller app folder (build\dist\WildLife)
;   OutputDir    where Setup goes (build\installer)
;   TestBuild    defined only for the automated installer test: a separate app ID and
;                name, so testing never touches a real Thicket installation
;   Compression  lzma2/max for a release, lzma2/fast for the test
;
; Installs for the current user only (no administrator rights) into
; %LOCALAPPDATA%\Programs\Thicket. The data folder, %LOCALAPPDATA%\WildLife, is never
; part of the installation: installing, upgrading and uninstalling all leave it alone.
;
; Thicket was called WildLife up to version 1.1.0. The names Windows remembers keep that
; first name: the AppId, the .exe (taskbar pins point at it), AppMutex, AppUserModelID,
; the data folder, and an earlier installation's folder (UsePreviousAppDir).

#ifndef AppVersion
  #error AppVersion must be defined (use scripts/build_installer.py)
#endif
#ifndef AppFolder
  #error AppFolder must be defined (use scripts/build_installer.py)
#endif
#ifndef OutputDir
  #define OutputDir "..\build\installer"
#endif
#ifndef Compression
  #define Compression "lzma2/max"
#endif

#ifdef TestBuild
  #define AppName "Thicket installer test"
  #define OldAppName "WildLife installer test"
  #define AppIdGuid "{{6F1D0C52-9B7E-4C61-A0E3-3C5D2A7B8E14}"
  #define InstallName "Thicket-InstallerTest"
#else
  #define AppName "Thicket"
  #define OldAppName "WildLife"
  ; Never change this: Windows uses it to recognise Thicket (and WildLife) when upgrading.
  #define AppIdGuid "{{E2D9B816-2BC0-4AFD-A557-06006935AECE}"
  #define InstallName "Thicket"
#endif

[Setup]
AppId={#AppIdGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Thicket
AppComments=A personal wildlife sighting journal
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
; Per-user install: no administrator rights, nothing outside your own account
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#InstallName}
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Setup and the uninstaller both wait while Thicket is open (see app.py, RUNNING_MUTEX)
AppMutex=WildLife.Running
CloseApplications=no
WizardStyle=modern
SetupIconFile=..\src\wildlife\resources\icons\wildlife.ico
UninstallDisplayIcon={app}\WildLife.exe
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename={#InstallName}-Setup-{#AppVersion}
Compression={#Compression}
SolidCompression=yes
LZMANumBlockThreads=4

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Add a Thicket icon to the desktop"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the program files completely, so files a newer version no longer
; needs don't linger. Only the program's own folder: never the data folder.
Type: filesandordirs; Name: "{app}\_internal"
; Shortcuts from before the rename: an upgrade makes new ones with the new name
Type: files; Name: "{autoprograms}\{#OldAppName}.lnk"
Type: files; Name: "{autodesktop}\{#OldAppName}.lnk"

[Files]
Source: "{#AppFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\WildLife.exe"; AppUserModelID: "WildLife.WildLife"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\WildLife.exe"; AppUserModelID: "WildLife.WildLife"; Tasks: desktopicon

[Run]
Filename: "{app}\WildLife.exe"; Description: "Start Thicket now"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    // (No line may start with "#": the preprocessor would read it as a directive)
    MsgBox('Thicket has been removed from this PC.' + #13#10#13#10 +
      'Your sightings, photos and settings have not been touched. They are in your ' +
      'data folder, normally:' + #13#10 + ExpandConstant('{localappdata}\WildLife') + #13#10#13#10 +
      'Installing Thicket again picks them up. Delete that folder ' +
      'yourself only if you are sure you no longer need it (keep your backups).',
      mbInformation, MB_OK);
end;
