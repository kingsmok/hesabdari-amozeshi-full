; ============================================================================
;  Hesabdari Rahsa - Windows installer (Inno Setup 6)
;
;  Build:   ISCC.exe setup.iss        (or run build.bat which does everything)
;  Input:   dist\AcademyManager\      (produced by: pyinstaller app.spec)
;  Output:  installer_output\HesabdariRahsa_Setup_<version>.exe
;
;  The installer asks the operator for the initial admin credentials and the
;  cPanel host, then persists them to {app}\config.ini so the Python app can
;  bootstrap itself on first launch (see utils/installer_config.py).
; ============================================================================

#define MyAppName          "حساب داری آموزشگاهی رهسا"
#define MyAppNameEn        "Hesabdari Rahsa"
#define MyAppVersion       "1.0.1"
#define MyAppPublisher     "Aria Padideh"
#define MyAppURL           "https://ls.ariapadideh.ir"
#define MyAppExeName       "AcademyManager.exe"
#define MySourceDir        "dist\AcademyManager"
#define MyConfigFile       "{app}\config.ini"

[Setup]
AppId={{9F2C7A54-3B18-4C2E-9E31-7A5D0C6B4E11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppNameEn} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; --- Output ---------------------------------------------------------------
OutputDir=installer_output
OutputBaseFilename=HesabdariRahsa_Setup_{#MyAppVersion}
; --- Compression (requested: lzma) ---------------------------------------
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
; --- Appearance -----------------------------------------------------------
WizardStyle=modern
WizardSizePercent=115
DefaultDialogFontName=Tahoma
SetupIconFile=static\images\icon.ico
UninstallDisplayName={#MyAppNameEn} {#MyAppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
; --- Requirements ---------------------------------------------------------
PrivilegesRequired=admin
MinVersion=6.1sp1
; For Inno Setup 6.3+ you may add: ArchitecturesInstallIn64BitMode=x64compatible
; Do not let the wizard finish while the app is running
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Optional Persian translation (download Farsi.isl into Inno Setup\Languages):
; Name: "persian"; MessagesFile: "compiler:Languages\Farsi.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon";  Description: "Start the application when Windows starts"; GroupDescription: "Options:"; Flags: unchecked

[Files]
; Everything PyInstaller produced (onedir layout)
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Data folders the application writes to.
;   * "uninsneveruninstall" keeps customer data safe on uninstall/upgrade.
;   * "Permissions: users-modify" is mandatory: the program is installed under
;     Program Files, and a standard (non-elevated) user must still be able to
;     write the SQLite database, backups, logs and uploads.
Name: "{app}\instance";        Flags: uninsneveruninstall; Permissions: users-modify
Name: "{app}\backups";         Flags: uninsneveruninstall; Permissions: users-modify
Name: "{app}\logs";            Flags: uninsneveruninstall; Permissions: users-modify
Name: "{app}\static\uploads";  Flags: uninsneveruninstall; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}";                Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppNameEn}";    Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; HKA resolves to HKLM in this admin-mode installer, so the entry also applies
; to the end user - the installer's own HKCU hive belongs to the elevated account.
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "HesabdariRahsa"; ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: startupicon; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppNameEn}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove only generated artefacts; instance/, backups/ and config.ini survive.
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\.update_backup"
Type: files;          Name: "{app}\restart.bat"

; ============================================================================
;  Pascal Script
; ============================================================================
[Code]
var
  ConfigPage: TInputQueryWizardPage;

const
  FIELD_ADMIN_USER = 0;
  FIELD_ADMIN_PASS = 1;
  FIELD_HOST_URL   = 2;

{ Full path of the configuration file inside the selected target directory. }
function ConfigFilePath: String;
begin
  Result := AddBackslash(WizardDirValue) + 'config.ini';
end;

{ An existing config.ini means this is an upgrade / re-install over live data. }
function IsUpgradeInstall: Boolean;
begin
  Result := FileExists(ConfigFilePath);
end;

{ Value of a command line parameter (silent installs), '' when not supplied. }
function ParamValue(const Name: String): String;
begin
  Result := Trim(ExpandConstant('{param:' + Name + '|}'));
end;

{ True when the string only contains characters that survive every Windows
  code page (SetIniString writes ANSI, so non-ASCII names can be mangled). }
function IsAsciiName(const Value: String): Boolean;
var
  I: Integer;
  C: Char;
begin
  Result := True;
  for I := 1 to Length(Value) do
  begin
    C := Value[I];
    if not (((C >= 'a') and (C <= 'z')) or ((C >= 'A') and (C <= 'Z')) or
            ((C >= '0') and (C <= '9')) or (C = '.') or (C = '_') or (C = '-')) then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

{ Trim leading/trailing spaces - operators often paste values with blanks. }
function CleanValue(const Value: String): String;
begin
  Result := Trim(Value);
end;

{ Normalise the host: add a scheme when missing, drop the trailing slash. }
function NormalizeHost(const Value: String): String;
var
  Host: String;
begin
  Host := CleanValue(Value);
  if Host = '' then
  begin
    Result := '';
    Exit;
  end;
  if (Pos('http://', Lowercase(Host)) <> 1) and (Pos('https://', Lowercase(Host)) <> 1) then
    Host := 'https://' + Host;
  while (Length(Host) > 0) and (Host[Length(Host)] = '/') do
    Host := Copy(Host, 1, Length(Host) - 1);
  Result := Host;
end;

{ Create the custom wizard page right after the "Select Destination" page. }
procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(
    wpSelectDir,
    'Initial configuration',
    'Administrator account and platform host',
    'These values are written to config.ini and used the first time the ' +
    'application starts. You can change them later inside the software.');

  { 0 - administrator user name }
  ConfigPage.Add('Admin username:', False);
  { 1 - administrator password (masked with "*") }
  ConfigPage.Add('Admin password:', True);
  { 2 - cPanel host URL or IP address }
  ConfigPage.Add('cPanel host URL / IP:', False);

  { Sensible defaults so a fast operator can just press Next. }
  ConfigPage.Values[FIELD_ADMIN_USER] := 'admin';
  ConfigPage.Values[FIELD_ADMIN_PASS] := '';
  ConfigPage.Values[FIELD_HOST_URL]   := 'https://';

  { Belt and braces: force the mask character even if the theme resets it. }
  ConfigPage.Edits[FIELD_ADMIN_PASS].PasswordChar := '*';

  { Small usability touches. }
  ConfigPage.Edits[FIELD_ADMIN_USER].MaxLength := 50;
  ConfigPage.Edits[FIELD_ADMIN_PASS].MaxLength := 100;
  ConfigPage.Edits[FIELD_HOST_URL].MaxLength   := 200;
end;

{ On an upgrade the credentials already exist - never ask (and never overwrite) them. }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = ConfigPage.ID) and IsUpgradeInstall;
end;

{ Validate the custom page before allowing the wizard to continue. }
function NextButtonClick(CurPageID: Integer): Boolean;
var
  AdminUser, AdminPass, HostUrl: String;
begin
  Result := True;
  if CurPageID <> ConfigPage.ID then
    Exit;

  AdminUser := CleanValue(ConfigPage.Values[FIELD_ADMIN_USER]);
  AdminPass := ConfigPage.Values[FIELD_ADMIN_PASS];
  HostUrl   := NormalizeHost(ConfigPage.Values[FIELD_HOST_URL]);

  if AdminUser = '' then
  begin
    MsgBox('Please enter the administrator username.', mbError, MB_OK);
    WizardForm.ActiveControl := ConfigPage.Edits[FIELD_ADMIN_USER];
    Result := False;
    Exit;
  end;

  if not IsAsciiName(AdminUser) then
  begin
    MsgBox('The username may only contain English letters, digits, dot, dash ' +
           'or underscore.', mbError, MB_OK);
    WizardForm.ActiveControl := ConfigPage.Edits[FIELD_ADMIN_USER];
    Result := False;
    Exit;
  end;

  if Length(AdminPass) < 6 then
  begin
    MsgBox('The administrator password must be at least 6 characters long.', mbError, MB_OK);
    WizardForm.ActiveControl := ConfigPage.Edits[FIELD_ADMIN_PASS];
    Result := False;
    Exit;
  end;

  if HostUrl = '' then
  begin
    MsgBox('Please enter the cPanel host URL or IP address.', mbError, MB_OK);
    WizardForm.ActiveControl := ConfigPage.Edits[FIELD_HOST_URL];
    Result := False;
    Exit;
  end;

  { Write the normalised values back so the summary and ssPostInstall agree. }
  ConfigPage.Values[FIELD_ADMIN_USER] := AdminUser;
  ConfigPage.Values[FIELD_HOST_URL]   := HostUrl;
end;

{ Show the chosen settings (never the password) on the "Ready to install" page. }
function UpdateReadyMemo(const Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine;
  if IsUpgradeInstall then
    Result := Result + 'Initial configuration:' + NewLine +
              Space + 'existing config.ini detected - it will be kept unchanged' + NewLine
  else
    Result := Result + 'Initial configuration:' + NewLine +
              Space + 'Admin username: ' + ConfigPage.Values[FIELD_ADMIN_USER] + NewLine +
              Space + 'Admin password: ********' + NewLine +
              Space + 'cPanel host: ' + ConfigPage.Values[FIELD_HOST_URL] + NewLine;
  Result := Result + NewLine + MemoTasksInfo;
end;

{ Persist the answers into {app}\config.ini once the files are on disk. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigFile, AdminUser, AdminPass, HostUrl, HostParam: String;
  Upgrade: Boolean;
  ErrorCode: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;

  ConfigFile := ExpandConstant('{#MyConfigFile}');
  Upgrade    := FileExists(ConfigFile);

  { Command line parameters win over the wizard values, so an unattended
    install works too:
      setup.exe /VERYSILENT /AdminUser=admin /AdminPass=Secret123 /Host=panel.example.com }
  AdminUser := ParamValue('AdminUser');
  if AdminUser = '' then AdminUser := CleanValue(ConfigPage.Values[FIELD_ADMIN_USER]);
  AdminPass := ParamValue('AdminPass');
  if AdminPass = '' then AdminPass := ConfigPage.Values[FIELD_ADMIN_PASS];
  HostParam := ParamValue('Host');
  if HostParam <> '' then
    HostUrl := NormalizeHost(HostParam)
  else
    HostUrl := NormalizeHost(ConfigPage.Values[FIELD_HOST_URL]);

  { [Admin] - written only on a fresh install and only when we really have a
    password; the application consumes it once and then clears it. }
  if (not Upgrade) and (AdminUser <> '') and (AdminPass <> '') then
  begin
    SetIniString('Admin', 'username', AdminUser, ConfigFile);
    SetIniString('Admin', 'password', AdminPass, ConfigFile);
    SetIniString('Admin', 'password_consumed', 'false', ConfigFile);
  end;

  { [Platform] - cPanel / WordPress endpoint used by the integrations. }
  if ((not Upgrade) or (HostParam <> '')) and (HostUrl <> '') then
  begin
    SetIniString('Platform', 'host_url', HostUrl, ConfigFile);
    SetIniString('Platform', 'verify_ssl', 'true', ConfigFile);
  end;

  { [License] - defaults only; never clobber values edited by support. }
  if GetIniString('License', 'server_url', '', ConfigFile) = '' then
  begin
    SetIniString('License', 'server_url', '{#MyAppURL}', ConfigFile);
    SetIniString('License', 'channel', 'stable', ConfigFile);
    SetIniString('License', 'auto_update', 'true', ConfigFile);
  end;

  { [Install] - always refreshed; useful for diagnostics and support tickets. }
  SetIniString('Install', 'version', '{#MyAppVersion}', ConfigFile);
  SetIniString('Install', 'installed_at', GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':'), ConfigFile);
  SetIniString('Install', 'install_dir', ExpandConstant('{app}'), ConfigFile);

  { The file briefly holds a plaintext password (until the first launch clears
    it). Drop inherited ACLs and grant: Administrators + SYSTEM full control,
    Users modify - the last one is required because the application runs
    unelevated and must be able to erase the password itself. }
  if not Exec(ExpandConstant('{sys}\icacls.exe'),
              '"' + ConfigFile + '" /inheritance:r /grant:r "*S-1-5-32-544:(F)"' +
              ' /grant:r "*S-1-5-18:(F)" /grant:r "*S-1-5-32-545:(M)"',
              '', SW_HIDE, ewWaitUntilTerminated, ErrorCode) then
    Log('icacls failed on config.ini (non fatal): ' + IntToStr(ErrorCode));
end;

{ Ask before deleting customer data during uninstall. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  AppDir := ExpandConstant('{app}');
  if DirExists(AppDir + '\instance') or DirExists(AppDir + '\backups') then
  begin
    { UninstallSilent: never destroy data during an unattended removal. }
    if UninstallSilent then
      Exit;
    if MsgBox('Do you also want to delete the database, backups and settings?' + #13#10 +
              'Choose No to keep your data for a future re-installation.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(AppDir + '\instance', True, True, True);
      DelTree(AppDir + '\backups', True, True, True);
      DelTree(AppDir + '\static\uploads', True, True, True);
      DeleteFile(AppDir + '\config.ini');
      DeleteFile(AppDir + '\settings.json');
    end;
  end;
end;
