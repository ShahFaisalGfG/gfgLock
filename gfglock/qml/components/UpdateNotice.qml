// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The update notice in the main window's bottom bar: a new version, its download progress, or one
// ready to install, on one compact line beside the bar's own status. Driven by the app's
// UpdateController (controllers/update_ctrl.py) and hidden when there is nothing to say; the full
// message shows on hover when the line is cut short. Shared by gfgLock, gfgShield, and
// CC-Gen-Ultimate: keep the copies identical. Every action is a button, so it works from the keyboard.
Rectangle {
    id: notice

    // The app's UpdateController.
    property var controller: null
    // What installing now would interrupt, added to Restart now's tooltip (gfgShield: the windows
    // protected by hand lose their protection when the app restarts). "" adds nothing.
    property string restartNote: ""

    readonly property string status: notice.controller ? notice.controller.status : "idle"
    readonly property bool _problem: notice.status === "error" || notice.status === "failed"
    readonly property bool _waiting: notice.status === "ready" || notice.status === "failed"
    readonly property bool _downloading: notice.status === "downloading"
    readonly property bool _canDownload: notice.controller !== null && notice.controller.canDownload

    visible: notice.controller !== null && notice.controller.bannerVisible
    implicitHeight: row.implicitHeight + 2 * Theme.spaceXs
    radius: Theme.radius
    color: notice._problem ? Theme.dangerSoft : Theme.accentSoft

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: Theme.spaceSm
        anchors.rightMargin: Theme.spaceXs
        spacing: Theme.spaceSm

        Icon {
            name: notice._problem ? "warning" : (notice._waiting ? "completed" : "download")
            size: Theme.iconMd
            color: notice._problem ? Theme.danger : Theme.accent
        }
        Text {
            id: message
            Layout.fillWidth: true
            text: notice.controller ? notice.controller.message : ""
            elide: Text.ElideRight
            maximumLineCount: 1
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            color: Theme.text
            Accessible.role: Accessible.StaticText
            Accessible.name: text
            HoverHandler { id: messageHover }
            ToolTip.visible: messageHover.hovered && message.truncated
            ToolTip.text: message.text
            ToolTip.delay: 500
        }
        ProgressBar {
            Layout.preferredWidth: 110
            visible: notice._downloading
            from: 0
            to: 1
            value: notice.controller ? notice.controller.progress : 0
            Accessible.role: Accessible.ProgressBar
            Accessible.name: "Update download progress"
        }
        Text {
            visible: notice._downloading
            text: notice.controller ? notice.controller.progressText : ""
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            color: Theme.textMuted
        }
        AppButton {
            visible: notice.status === "available" || notice.status === "error"
            kind: "primary"
            compact: true
            text: !notice._canDownload ? "Download" : (notice.status === "error" ? "Try again" : "Update")
            iconName: notice._canDownload ? "download" : "openExternal"
            toolTipText: notice._canDownload
                ? "Download the update in the background; it installs when you close the app"
                : "Open the releases page in your browser"
            onClicked: notice.controller.download()
        }
        AppButton {
            visible: notice._waiting
            kind: "primary"
            compact: true
            text: notice.status === "failed" ? "Install now" : "Restart now"
            iconName: "sync"
            enabled: notice.controller ? notice.controller.canRestart : false
            toolTipText: (enabled ? "Close the app, install the update, and start the new version"
                                  : "Available once the current work finishes")
                + (notice.restartNote ? ". " + notice.restartNote : "")
            onClicked: notice.controller.restartNow()
        }
        AppButton {
            visible: notice._downloading
            compact: true
            text: "Cancel"
            toolTipText: "Stop the download; it resumes from here next time"
            onClicked: notice.controller.cancel()
        }
        AppButton {
            visible: notice.status === "available"
            kind: "ghost"
            compact: true
            text: "Skip"
            toolTipText: "Skip this version; later versions are offered as usual"
            onClicked: notice.controller.skipVersion()
        }
        AppButton {
            visible: !notice._downloading
            kind: "ghost"
            compact: true
            iconName: "openExternal"
            toolTipText: "Release notes: what's new in this version"
            onClicked: notice.controller.openReleaseNotes()
        }
        AppButton {
            kind: "ghost"
            compact: true
            iconName: "close"
            toolTipText: notice._waiting ? "Hide this notice (the update still installs on close)" : "Hide this notice"
            onClicked: notice.controller.dismiss()
        }
    }
}
