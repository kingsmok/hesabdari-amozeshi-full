; ═══════════════════════════════════════════════════
; Inno Setup Script — Academy Manager Pro
; ساخت اینستالر ویندوز
; ═══════════════════════════════════════════════════
; اجرا با Inno Setup 6: iscc setup.iss

[Setup]
AppName=Academy Manager Pro
AppVersion=1.0.0
AppPublisher=Academy Manager
AppPublisherURL=https://academy-manager.ir
DefaultDirName={autopf}\AcademyManager
DefaultGroupName=Academy Manager Pro
AllowNoIcons=yes
OutputDir=..\output
OutputBaseFilename=AcademyManager_Setup_v1.0
SetupIconFile=..\static\images\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion=1.0.0.0
VersionInfoCompany=Academy Manager
VersionInfoDescription=Academy Management System
VersionInfoCopyright=Copyright 2026
VersionInfoProductName=Academy Manager Pro
VersionInfoProductVersion=1.0.0

[Languages]
Name: "persian"; MessagesFile: "compiler:Languages\Farsi.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "ایجاد آیکون روی دسکتاپ"; GroupDescription: "آیکون‌ها:"
Name: "quicklaunchicon"; Description: "ایجاد آیکون در نوار وظیفه"; GroupDescription: "آیکون‌ها:"; Flags: unchecked
Name: "autostart"; Description: "شروع خودکار هنگام روشن شدن ویندوز"; GroupDescription: "شروع خودکار:"; Flags: unchecked

[Files]
; فایل‌های اصلی
Source: "..\dist\AcademyManager.exe"; DestDir: "{app}"; Flags: ignoreversion
; دیتابیس نمونه
Source: "..\instance\academy.db"; DestDir: "{app}\instance"; Flags: onlyifdoesntexist uninsneveruninstall
; فایل‌های پشتیبان
Source: "..\backups\*"; DestDir: "{app}\backups"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist recursesubdirs
; فایل‌های آپلود
Source: "..\static\uploads\*"; DestDir: "{app}\static\uploads"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist recursesubdirs
; راهنما
Source: "..\README.md"; DestDir: "{app}"; Flags: isreadme
; فایل آپدیتر
Source: "updater.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Dirs]
Name: "{app}\instance"
Name: "{app}\backups"
Name: "{app}\static\uploads"
Name: "{app}\logs"

[Icons]
; منوی استارت
Name: "{group}\Academy Manager Pro"; Filename: "{app}\AcademyManager.exe"
Name: "{group}\اطلاعات شبکه"; Filename: "http://localhost:5000/network-info"
Name: "{group}\حذف برنامه"; Filename: "{uninstallexe}"
; دسکتاپ
Name: "{autodesktop}\Academy Manager Pro"; Filename: "{app}\AcademyManager.exe"; Tasks: desktopicon
; نوار وظیفه
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\Academy Manager Pro"; Filename: "{app}\AcademyManager.exe"; Tasks: quicklaunchicon

[Registry]
; ثبت در رجیستری ویندوز
Root: HKCU; Subkey: "Software\AcademyManager"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\AcademyManager"; ValueType: string; ValueName: "Version"; ValueData: "1.0.0"; Flags: uninsdeletekey
; شروع خودکار
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AcademyManager"; ValueData: """{app}\AcademyManager.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; اجرای برنامه بعد از نصب
Filename: "{app}\AcademyManager.exe"; Description: "اجرای Academy Manager Pro"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: files; Name: "{app}\*.pyc"

[Code]
// بررسی نصب قبلی
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function InitializeSetup(): Boolean;
var
  V: Integer;
  iResultCode: Integer;
  sUnInstallString: String;
begin
  Result := True;
  
  // بررسی نصب قبلی
  if IsUpgrade() then
  begin
    if MsgBox('نسخه قبلی Academy Manager Pro نصب شده است.' + #13#10 + 'آیا می‌خواهید آن را حذف و نسخه جدید نصب شود؟', mbConfirmation, MB_YESNO) = IDYES then
    begin
      sUnInstallString := GetUninstallString();
      Exec(RemoveQuotes(sUnInstallString), '/SILENT', '', SW_SHOWNORMAL, ewWaitUntilTerminated, iResultCode);
      Result := True;
    end
    else
      Result := False;
  end;
end;

// صفحه خوش‌آمدگویی سفارشی
procedure InitializeWizard;
begin
  // می‌توان صفحات سفارشی اضافه کرد
end;

// پیام پایان نصب
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // ایجاد میانبر اضافی
    // لاگ نصب
  end;
end;
