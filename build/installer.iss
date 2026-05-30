; ────────────────────────────────────────────────────────────────────────────
;  installer.iss  —  Inno Setup script for Desktop Pet "Buddy"
;
;  Wraps the PyInstaller output (dist\Buddy\) into BuddySetup.exe with:
;    • Ollama detection page (with browser-open fallback if missing)
;    • Model picker page (text + vision dropdowns)
;    • Optional auto-launch on Windows startup
;    • Post-install: pulls selected Ollama models in a console window
;
;  Compile:  ISCC.exe build\installer.iss
;  Output:   build\Output\BuddySetup-<version>.exe
; ────────────────────────────────────────────────────────────────────────────

#define MyAppName       "Buddy Desktop Pet"
#define MyAppShortName  "Buddy"
#define MyAppVersion    GetEnv('BUDDY_VERSION')
#if MyAppVersion == ""
  #define MyAppVersion  "0.1.0"
#endif
#define MyAppPublisher  "Buddy Project"
#define MyAppURL        "https://github.com/sumitkanchan4/desktop-pet"
#define MyAppExeName    "Buddy.exe"
#define OllamaURL       "https://ollama.com/download"

[Setup]
AppId={{4E2A1B7C-9A4F-4D2C-8B6F-1E3A7C9D2F8A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppShortName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=Output
OutputBaseFilename=BuddySetup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create a &desktop shortcut";        GroupDescription: "Additional shortcuts:";   Flags: unchecked
Name: "startup";      Description: "Launch Buddy on Windows &startup";  GroupDescription: "Auto-start:";              Flags: unchecked

[Files]
Source: "..\dist\Buddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppShortName}";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppShortName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppShortName}";    Filename: "{app}\{#MyAppExeName}";       Tasks: desktopicon
Name: "{userstartup}\{#MyAppShortName}";    Filename: "{app}\{#MyAppExeName}";       Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppShortName} now"; Flags: nowait postinstall skipifsilent

; ────────────────────────────────────────────────────────────────────────────
;  Custom wizard pages
; ────────────────────────────────────────────────────────────────────────────
[Code]
var
  OllamaPage:  TWizardPage;
  OllamaLbl:   TNewStaticText;
  OllamaBtn:   TNewButton;
  OllamaFound: Boolean;

  ModelPage:   TWizardPage;
  TextCombo:   TNewComboBox;
  VisionCombo: TNewComboBox;
  PullCheck:   TNewCheckBox;


function IsOllamaInstalled(): Boolean;
var
  Path: string;
  ResultCode: Integer;
begin
  Result := False;
  // 1. PATH check
  if Exec('where', 'ollama', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
  begin
    Result := True;
    exit;
  end;
  // 2. Default install location
  Path := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe');
  if FileExists(Path) then
    Result := True;
end;


procedure OpenOllamaDownload(Sender: TObject);
var
  ResultCode: Integer;
begin
  ShellExec('open', '{#OllamaURL}', '', '', SW_SHOW, ewNoWait, ResultCode);
end;


procedure CreateOllamaPage();
begin
  OllamaPage := CreateCustomPage(
    wpSelectTasks,
    'Ollama (Local AI Engine)',
    'Buddy uses Ollama to run AI models locally on your machine.'
  );

  OllamaFound := IsOllamaInstalled();

  OllamaLbl := TNewStaticText.Create(OllamaPage);
  OllamaLbl.Parent := OllamaPage.Surface;
  OllamaLbl.Left := 0;
  OllamaLbl.Top := 8;
  OllamaLbl.Width := OllamaPage.SurfaceWidth;
  OllamaLbl.AutoSize := False;
  OllamaLbl.Height := 120;
  OllamaLbl.WordWrap := True;

  if OllamaFound then
  begin
    OllamaLbl.Caption :=
      '✓ Ollama was detected on this machine.' + #13#10#13#10 +
      'Buddy will use it to generate speech and (optionally) read your screen.' + #13#10 +
      'No data ever leaves your computer.';
  end
  else
  begin
    OllamaLbl.Caption :=
      '✗ Ollama was not found on this machine.' + #13#10#13#10 +
      'Buddy needs Ollama to talk and react. Click the button below to open the ' +
      'official Ollama download page in your browser. Install it, then return ' +
      'here and click Next to continue.' + #13#10#13#10 +
      'You can also install Ollama later — Buddy will work in silent mode until then.';

    OllamaBtn := TNewButton.Create(OllamaPage);
    OllamaBtn.Parent := OllamaPage.Surface;
    OllamaBtn.Left := 0;
    OllamaBtn.Top := OllamaLbl.Top + OllamaLbl.Height + 8;
    OllamaBtn.Width := 220;
    OllamaBtn.Height := 28;
    OllamaBtn.Caption := 'Open Ollama download page';
    OllamaBtn.OnClick := @OpenOllamaDownload;
  end;
end;


procedure CreateModelPage();
var
  Lbl, NoteLbl: TNewStaticText;
begin
  ModelPage := CreateCustomPage(
    OllamaPage.ID,
    'Choose AI Models',
    'Pick which AI models Buddy should use. These will be downloaded by Ollama after install.'
  );

  // ── Text model ───────────────────────────────────────────────────────────
  Lbl := TNewStaticText.Create(ModelPage);
  Lbl.Parent := ModelPage.Surface;
  Lbl.Top := 8;
  Lbl.Caption := 'Text model (required for Buddy to speak):';

  TextCombo := TNewComboBox.Create(ModelPage);
  TextCombo.Parent := ModelPage.Surface;
  TextCombo.Top := Lbl.Top + Lbl.Height + 4;
  TextCombo.Width := 360;
  TextCombo.Style := csDropDownList;
  TextCombo.Items.Add('gemma3:1b      — fastest, ~700 MB  (recommended)');
  TextCombo.Items.Add('gemma3:4b      — smarter, ~3 GB');
  TextCombo.Items.Add('phi3:mini      — Microsoft, ~2 GB');
  TextCombo.Items.Add('llama3.2:3b    — Meta, ~2 GB');
  TextCombo.Items.Add('tinyllama      — tiny, ~600 MB');
  TextCombo.ItemIndex := 0;

  // ── Vision model ─────────────────────────────────────────────────────────
  Lbl := TNewStaticText.Create(ModelPage);
  Lbl.Parent := ModelPage.Surface;
  Lbl.Top := TextCombo.Top + TextCombo.Height + 16;
  Lbl.Caption := 'Vision model (lets Buddy peek at your screen — optional):';

  VisionCombo := TNewComboBox.Create(ModelPage);
  VisionCombo.Parent := ModelPage.Surface;
  VisionCombo.Top := Lbl.Top + Lbl.Height + 4;
  VisionCombo.Width := 360;
  VisionCombo.Style := csDropDownList;
  VisionCombo.Items.Add('(none — skip vision features)');
  VisionCombo.Items.Add('moondream      — ~1.7 GB  (recommended)');
  VisionCombo.Items.Add('llava-phi3     — ~3 GB');
  VisionCombo.Items.Add('llava          — ~4.7 GB');
  VisionCombo.ItemIndex := 1;

  // ── Pull-now toggle ──────────────────────────────────────────────────────
  PullCheck := TNewCheckBox.Create(ModelPage);
  PullCheck.Parent := ModelPage.Surface;
  PullCheck.Top := VisionCombo.Top + VisionCombo.Height + 18;
  PullCheck.Width := ModelPage.SurfaceWidth;
  PullCheck.Caption := 'Download selected models now (opens a console window).';
  PullCheck.Checked := OllamaFound;
  PullCheck.Enabled := OllamaFound;

  NoteLbl := TNewStaticText.Create(ModelPage);
  NoteLbl.Parent := ModelPage.Surface;
  NoteLbl.Top := PullCheck.Top + PullCheck.Height + 8;
  NoteLbl.Width := ModelPage.SurfaceWidth;
  NoteLbl.AutoSize := False;
  NoteLbl.Height := 40;
  NoteLbl.WordWrap := True;
  if OllamaFound then
    NoteLbl.Caption := 'Tip: if you uncheck this, Ollama will download the models the first time Buddy uses them.'
  else
    NoteLbl.Caption := 'Install Ollama first (previous page) to enable model download.';
end;


procedure InitializeWizard();
begin
  CreateOllamaPage();
  CreateModelPage();
end;


// Extract the model name (first token before whitespace) from a combo entry
function ParseModel(Combo: TNewComboBox): string;
var
  S: string;
  P: Integer;
begin
  Result := '';
  if Combo.ItemIndex < 0 then exit;
  S := Combo.Items[Combo.ItemIndex];
  if Pos('(none', S) = 1 then exit;
  P := Pos(' ', S);
  if P > 0 then
    Result := Trim(Copy(S, 1, P - 1))
  else
    Result := Trim(S);
end;


// After files are copied, pull the chosen models if user requested it.
procedure CurStepChanged(CurStep: TSetupStep);
var
  TextModel, VisionModel, Cmd: string;
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then exit;
  if not Assigned(PullCheck) then exit;
  if not PullCheck.Checked then exit;
  if not OllamaFound then exit;

  TextModel   := ParseModel(TextCombo);
  VisionModel := ParseModel(VisionCombo);

  Cmd := '';
  if TextModel <> '' then
    Cmd := Cmd + 'echo Pulling ' + TextModel + ' && ollama pull ' + TextModel + ' && ';
  if VisionModel <> '' then
    Cmd := Cmd + 'echo Pulling ' + VisionModel + ' && ollama pull ' + VisionModel + ' && ';
  Cmd := Cmd + 'echo. && echo Done! Press any key to close. && pause >nul';

  if Cmd <> '' then
    Exec(ExpandConstant('{cmd}'), '/c ' + Cmd, '', SW_SHOW, ewNoWait, ResultCode);
end;
