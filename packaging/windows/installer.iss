; Stable AppId identifies upgrades and the Windows uninstall entry.
#ifndef AppVersion
  #error AppVersion must be supplied from pyproject.toml
#endif
#ifndef BundleDir
  #error BundleDir must point to the tested PyInstaller folder
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#define AppName "Electron Microscopy Workbench"
[Setup]
AppId={{C855732D-8F90-44C0-ACF9-66B2F2A70658}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Electron Microscopy Workbench contributors
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\ElectronMicroscopyWorkbench
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ElectronMicroscopyWorkbench-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ElectronMicroscopyWorkbench.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
#if FileExists("app.ico")
SetupIconFile=app.ico
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\ElectronMicroscopyWorkbench.exe"; WorkingDir: "{userdocs}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\ElectronMicroscopyWorkbench.exe"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\ElectronMicroscopyWorkbench.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; User data and diagnostic logs are deliberately retained on uninstall.
