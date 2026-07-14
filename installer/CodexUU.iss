#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{1CF55DEB-643A-46DF-8409-D19D2A880B6B}
AppName=CodexUU
AppVersion={#MyAppVersion}
AppPublisher=CodexUU
DefaultDirName={localappdata}\Programs\CodexUU
DefaultGroupName=CodexUU
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=CodexUU-{#MyAppVersion}-win-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\CodexUU.exe

[Files]
Source: "..\dist\CodexUU\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CodexUU"; Filename: "{app}\CodexUU.exe"
Name: "{autodesktop}\CodexUU"; Filename: "{app}\CodexUU.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Run]
Filename: "{app}\CodexUU.exe"; Description: "启动 CodexUU"; Flags: nowait postinstall skipifsilent
