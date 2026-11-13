#ifndef AppVersion
  #define AppVersion "0.4.1"
#endif
#ifndef FileVersion
  #define FileVersion "0.4.1.0"
#endif
[Setup]
AppId={{8479A86A-8E35-49BC-BCC5-45A823BC37F2}
AppName=Radar de Cortes - CefasGamer
AppVersion={#AppVersion}
VersionInfoVersion={#FileVersion}
AppPublisher=PedroHenrique1788
AppPublisherURL=https://github.com/PedroHenrique1788/Radar
DefaultDirName={localappdata}\Programs\RadarCortes
DefaultGroupName=Radar de Cortes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=RadarCortes-Setup-{#AppVersion}-Windows-x64
UninstallDisplayIcon={app}\RadarCortes.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked
[Files]
Source: "..\dist\RadarCortes\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Radar de Cortes"; Filename: "{app}\RadarCortes.exe"; WorkingDir: "{localappdata}\RadarCortes"
Name: "{autodesktop}\Radar de Cortes"; Filename: "{app}\RadarCortes.exe"; WorkingDir: "{localappdata}\RadarCortes"; Tasks: desktopicon
[Dirs]
Name: "{localappdata}\RadarCortes"
[Run]
Filename: "{app}\RadarCortes.exe"; Description: "Abrir Radar de Cortes"; Flags: nowait postinstall skipifsilent
; User videos, reports, models and cache are intentionally preserved on uninstall.
