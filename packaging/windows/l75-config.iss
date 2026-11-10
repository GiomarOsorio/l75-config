; Instalador de Windows (Inno Setup 6) para L75 Config.
;   1) pyinstaller --noconfirm packaging/l75-config.spec      -> dist\L75 Config\
;   2) iscc /DAppVersion=0.3.0 packaging\windows\l75-config.iss -> dist\L75_Config-0.3.0-Setup.exe
#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif
#define AppName "L75 Config"
#define AppExe "l75-config.exe"

[Setup]
AppId={{F607F98C-38FB-51AF-9028-BC6BB2C03460}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=l75-config (proyecto no oficial)
AppPublisherURL=https://github.com/GiomarOsorio/l75-config
AppSupportURL=https://github.com/GiomarOsorio/l75-config/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=L75_Config-{#AppVersion}-Setup
SetupIconFile=..\..\l75ctl\assets\icon\l75-config.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\L75 Config\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
