# notifier.py - Windows toast notification utility

import subprocess
import sys

# PowerShell AUMID guaranteed registered on every Windows installation
_PS_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def send_notification(title: str, body: str) -> None:
    """Fire a Windows 10/11 toast notification via PowerShell WinRT APIs."""
    try:
        if sys.platform != "win32":
            return
        safe_title = title.replace('"', "'")
        safe_body = body.replace('"', "'")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager,"
            "Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null\n"
            "[Windows.Data.Xml.Dom.XmlDocument,"
            "Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null\n"
            "$t=[Windows.UI.Notifications.ToastTemplateType]::ToastText02\n"
            "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t)\n"
            "$d=[xml]$x.GetXml()\n"
            f'$d.GetElementsByTagName("text")[0].InnerText="{safe_title}"\n'
            f'$d.GetElementsByTagName("text")[1].InnerText="{safe_body}"\n'
            "$n=[Windows.Data.Xml.Dom.XmlDocument]::new()\n"
            "$n.LoadXml($d.OuterXml)\n"
            "$z=[Windows.UI.Notifications.ToastNotification]::new($n)\n"
            f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{_PS_AUMID}").Show($z)'
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=0x08000000,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
