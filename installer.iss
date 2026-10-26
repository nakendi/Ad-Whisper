; Script generated for Inno Setup 6
; AdWhisper Standalone Desktop Setup

#define MyAppName "AdWhisper"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "saha12cheh"
#define MyAppURL "https://github.com/nakendi/Ad-Whisper"
#define MyAppExeName "AdWhisper.exe"

[Setup]
AppId={{F84A1C9D-9214-4B2E-8E5A-7163D0C2F304}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=AdWhisper-Setup
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\app_icon.ico
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Core Application Files
Source: "AdWhisper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.yaml"; DestDir: "{app}"; Flags: ignoreversion
Source: "app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "launcher.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "scanner_engine.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "matcher.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "transcriber.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "collector.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "downloader.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "audio_processor.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "exporter.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "database.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "run.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: ".streamlit\*"; DestDir: "{app}\.streamlit"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "data\temp_audio\.gitkeep"; DestDir: "{app}\data\temp_audio"; Flags: ignoreversion
Source: "data\demucs_audio\.gitkeep"; DestDir: "{app}\data\demucs_audio"; Flags: ignoreversion
Source: "data\exports\.gitkeep"; DestDir: "{app}\data\exports"; Flags: ignoreversion

; Embedded Standalone Python 3.11 Runtime
Source: "C:\Users\Oleksandr\AppData\Local\Programs\Python\Python311\python.exe"; DestDir: "{app}\runtime"; Flags: ignoreversion
Source: "C:\Users\Oleksandr\AppData\Local\Programs\Python\Python311\pythonw.exe"; DestDir: "{app}\runtime"; Flags: ignoreversion
Source: "C:\Users\Oleksandr\AppData\Local\Programs\Python\Python311\python311.dll"; DestDir: "{app}\runtime"; Flags: ignoreversion
Source: "C:\Users\Oleksandr\AppData\Local\Programs\Python\Python311\python3.dll"; DestDir: "{app}\runtime"; Flags: ignoreversion
Source: "C:\Users\Oleksandr\AppData\Local\Programs\Python\Python311\DLLs\*"; DestDir: "{app}\runtime\DLLs"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "C:\Users\Oleksandr\AppData\Local\Programs\Python\Python311\Lib\*"; DestDir: "{app}\runtime\Lib"; Excludes: "site-packages,test,idle_test,turtledemo"; Flags: ignoreversion recursesubdirs createallsubdirs

; Pre-installed AI & PyTorch CUDA Libraries from .venv
Source: ".venv\Lib\site-packages\*"; DestDir: "{app}\runtime\Lib\site-packages"; Excludes: "playwright,playwright-*,__pycache__"; Flags: ignoreversion recursesubdirs createallsubdirs

; Pre-packaged FFmpeg and FFprobe Binaries
Source: "C:\Users\Oleksandr\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe"; DestDir: "{app}\runtime\bin"; Flags: ignoreversion
Source: "C:\Users\Oleksandr\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin\ffprobe.exe"; DestDir: "{app}\runtime\bin"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
