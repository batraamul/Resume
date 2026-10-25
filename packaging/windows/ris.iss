; Inno Setup script for the Windows installer (per-user, no administrator rights needed).
;   iscc /DAppVersion=1.1.0 /DSourceDir=..\..\dist\ResumeIntelligenceStudio /DOutputDir=..\..\dist\installer ris.iss
; The release workflow passes these values. Your data folder (%APPDATA%) is never touched by install,
; update or uninstall.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\ResumeIntelligenceStudio"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist\installer"
#endif

#define AppName "Resume Intelligence Studio"
#define AppExe "ResumeIntelligenceStudio.exe"

[Setup]
AppId={{8D2C6E1A-3B5F-4C7E-9A0D-2F6B1E4C9A73}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Resume Intelligence Studio
AppPublisherURL=https://github.com/batraamul/Resume
AppSupportURL=https://github.com/batraamul/Resume/issues
AppUpdatesURL=https://github.com/batraamul/Resume/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=ResumeIntelligenceStudio-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\assets\icons\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\..\LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
; Remove the previous version's program files so nothing stale remains after an update.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
; After a silent update started from the application, start it again.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent
