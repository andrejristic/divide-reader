; Inno Setup script for the Windows installer; build_exe.sh passes
; AppVersion, SourceDir (the staged bundle) and OutDir.
; Installs for the current user only, so no administrator rights are needed.

#define AppName "Divide Reader"

[Setup]
AppId={{6F0E2C1A-4B7D-4E59-9C3B-2D8A1F5E7B40}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Andrej Ristić
AppPublisherURL=https://github.com/andrejristic/divide-reader
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#SourceDir}\LICENSE.txt
OutputDir={#OutDir}
OutputBaseFilename=DivideReader-Setup-{#AppVersion}
SetupIconFile={#SourceDir}\divide-reader.ico
UninstallDisplayIcon={app}\divide-reader.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\divide-reader.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\divide-reader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\divide-reader.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
