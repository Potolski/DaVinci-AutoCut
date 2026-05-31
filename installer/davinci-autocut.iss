; Inno Setup script for DaVinci AutoCut.
;
; Produces DaVinciAutoCut-Setup.exe, which:
;   * copies the plugin into Resolve's per-user Scripts folder (no admin),
;   * bundles ffmpeg.exe next to the plugin (so PATH is never touched),
;   * checks for Python 3 and offers to install it if missing.
;
; ffmpeg binaries are expected in the folder passed as /DFFmpegDir=... at build
; time (defaults to "vendor" beside this script). Build with:
;   iscc /DFFmpegDir=vendor installer\davinci-autocut.iss

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif
#ifndef FFmpegDir
  #define FFmpegDir "vendor"
#endif
#ifndef PythonUrl
  #define PythonUrl "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
#endif

[Setup]
AppId={{B6E4C0A1-7E2D-4D2E-9C3A-1A2B3C4D5E6F}}
AppName=DaVinci AutoCut
AppVersion={#AppVersion}
AppPublisher=David Potolski Lafeta
DefaultDirName={userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\DaVinciAutoCut
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=DaVinciAutoCut-Setup
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
UninstallDisplayName=DaVinci AutoCut

[Files]
Source: "..\DaVinci AutoCut.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\autocut\*"; DestDir: "{app}\autocut"; Excludes: "__pycache__\*,bin\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#FFmpegDir}\ffmpeg.exe"; DestDir: "{app}\autocut\bin"; Flags: ignoreversion
Source: "{#FFmpegDir}\ffprobe.exe"; DestDir: "{app}\autocut\bin"; Flags: ignoreversion skipifsourcedoesntexist

[Code]
function IsPython3Installed(): Boolean;
var
  ResultCode: Integer;
begin
  Result :=
    RegKeyExists(HKCU, 'Software\Python\PythonCore') or
    RegKeyExists(HKLM, 'Software\Python\PythonCore') or
    RegKeyExists(HKLM64, 'Software\Python\PythonCore');
  if Result then
    exit;
  // Fallback: the 'py' launcher resolves a real interpreter if one exists.
  if Exec('cmd.exe', '/C py -3 --version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := (ResultCode = 0);
end;

procedure InstallPythonIfMissing();
var
  TmpFile: String;
  ResultCode: Integer;
begin
  if IsPython3Installed() then
    exit;

  if MsgBox('DaVinci Resolve needs Python 3 to run this plugin, and it was not'
      + ' found on this PC.' + #13#10#13#10
      + 'Download and install Python 3 now?', mbConfirmation, MB_YESNO) = IDYES then
  begin
    try
      DownloadTemporaryFile('{#PythonUrl}', 'python-setup.exe', '', nil);
      TmpFile := ExpandConstant('{tmp}\python-setup.exe');
      // Passive: a progress bar, no prompts. Per-user, added to PATH.
      Exec(TmpFile, '/passive InstallAllUsers=0 PrependPath=1 Include_test=0',
        '', SW_SHOW, ewWaitUntilTerminated, ResultCode);
    except
      MsgBox('Python could not be downloaded automatically. Please install'
        + ' Python 3 from python.org, then restart DaVinci Resolve.',
        mbError, MB_OK);
    end;
  end
  else
    MsgBox('Without Python 3, DaVinci Resolve cannot run the plugin. Install'
      + ' Python 3 from python.org later, then restart Resolve.',
      mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallPythonIfMissing();
    MsgBox('DaVinci AutoCut is installed.' + #13#10#13#10
      + 'Restart DaVinci Resolve, then open it from'
      + ' Workspace -> Scripts -> DaVinci AutoCut.', mbInformation, MB_OK);
  end;
end;
