// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The update notice at the top of the main window: a new version, its download progress, or one
// ready to install. Driven by the app's UpdateController (controllers/update_ctrl.py) and hidden
// when there is nothing to say. Shared by gfgLock, gfgShield, and CC-Gen-Ultimate: keep the copies
// identical. Every action is a button, so the banner works from the keyboard.
Rectangle {
    id: banner

    // The app's UpdateController.
    property var controller: null
    // What installing now would interrupt, shown while an update waits (gfgShield: the windows
    // protected by hand lose their protection when the app restarts). "" shows nothing.
    property string restartNote: ""

    readonly property string status: banner.controller ? banner.controller.status : "idle"
    readonly property bool _problem: banner.status === "error" || banner.status === "failed"
    readonly property bool _waiting: banner.status === "ready" || banner.status === "failed"

    visible: banner.controller !== null && banner.controller.bannerVisible
    implicitHeight: column.implicitHeight + 2 * Theme.spaceMd
    radius: Theme.radius
    color: banner._problem ? Theme.dangerSoft : Theme.accentSoft

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.spaceMd
        spacing: Theme.spaceSm

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceMd

            Icon {
                name: banner._problem ? "warning" : (banner._waiting ? "completed" : "download")
                size: Theme.iconLg
                color: banner._problem ? Theme.danger : Theme.accent
            }
            Text {
                Layout.fillWidth: true
                text: banner.controller ? banner.controller.message : ""
                wrapMode: Text.WordWrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                color: Theme.text
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }
            AppButton {
                kind: "ghost"
                compact: true
                iconName: "close"
                toolTipText: banner._waiting ? "Hide this notice (the update still installs on close)" : "Hide this notice"
                onClicked: banner.controller.dismiss()
            }
        }

        ProgressBar {
            Layout.fillWidth: true
            visible: banner.status === "downloading"
            from: 0
            to: 1
            value: banner.controller ? banner.controller.progress : 0
            Accessible.role: Accessible.ProgressBar
            Accessible.name: "Update download progress"
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceSm

            AppButton {
                visible: banner.status === "available" || banner.status === "error"
                kind: "primary"
                compact: true
                text: !banner.controller || !banner.controller.canDownload ? "Download"
                    : (banner.status === "error" ? "Try again" : "Update")
                iconName: banner.controller && banner.controller.canDownload ? "download" : "openExternal"
                toolTipText: banner.controller && banner.controller.canDownload
                    ? "Download the update in the background; it installs when you close the app"
                    : "Open the releases page in your browser"
                onClicked: banner.controller.download()
            }
            AppButton {
                visible: banner._waiting
                kind: "primary"
                compact: true
                text: banner.status === "failed" ? "Install now" : "Restart now"
                iconName: "sync"
                enabled: banner.controller ? banner.controller.canRestart : false
                toolTipText: enabled ? "Close the app, install the update, and start the new version"
                                     : "Available once the current work finishes"
                onClicked: banner.controller.restartNow()
            }
            AppButton {
                visible: banner.status === "downloading"
                compact: true
                text: "Cancel"
                iconName: "cancel"
                toolTipText: "Stop the download; it resumes from here next time"
                onClicked: banner.controller.cancel()
            }
            Text {
                visible: banner.status === "downloading"
                text: banner.controller ? banner.controller.progressText : ""
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
            }
            AppButton {
                visible: banner.status !== "downloading"
                kind: "ghost"
                compact: true
                text: "Release notes"
                iconName: "openExternal"
                toolTipText: "What's new, on the release page"
                onClicked: banner.controller.openReleaseNotes()
            }
            AppButton {
                visible: banner.status === "available"
                kind: "ghost"
                compact: true
                text: "Skip this version"
                toolTipText: "Stop offering this version; later versions are offered as usual"
                onClicked: banner.controller.skipVersion()
            }
            Item { Layout.fillWidth: true }
        }

        Text {
            Layout.fillWidth: true
            visible: banner._waiting && banner.restartNote !== ""
            text: banner.restartNote
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            color: Theme.textMuted
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }
    }
}
