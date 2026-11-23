// qmllint disable unqualified
import QtQml.Models
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Status, progress, and Start / Cancel for one tab. The status line says what is happening, why
// Start is unavailable, what a run will do to the files, or how the last run went; below it,
// between runs, the update notice. After a run it offers the file or the folders it wrote.
Rectangle {
    id: bar

    required property var controller
    // The app's UpdateController, whose notice shows here while no run is going.
    property var updates: null
    // Why Start is unavailable, or "" when the tab is ready.
    property string blocker: ""
    // What pressing Start will do to the files, shown while the tab is ready.
    property string readyText: ""
    // A folder scan as the page shows it: only once it has run for a moment, so checking a few
    // added files doesn't flash "Scanning...".
    property bool scanning: false
    property string startText: "Start"
    property string startIcon: "play"
    // A second action beside Start that changes nothing (Check on the Decrypt tab); "" hides it.
    property string checkText: ""
    property string checkTip: ""

    signal startRequested()
    signal checkRequested()

    readonly property var queue: bar.controller.fileModel
    readonly property bool busy: bar.controller.busy
    // The last run's result stays until the list changes (the controller then clears it); it
    // matters more than the reason Start is off.
    readonly property bool _showSummary: bar.controller.summary.length > 0
    readonly property bool _showBlocker: !bar.busy && !bar.scanning && !bar._showSummary
        && bar.blocker.length > 0 && bar.queue.count > 0
    readonly property bool _error: !bar.busy && bar._showSummary && bar.controller.summaryIsError
    readonly property var _folders: bar.controller.lastFolders
    property real _elapsed: 0
    property real _startedAt: 0

    // Elapsed time as m:ss, for example 12:34.
    function _clock(seconds) {
        var whole = Math.floor(seconds)
        return Math.floor(whole / 60) + ":" + String(whole % 60).padStart(2, "0")
    }

    // A folder's own name, as a button names it ("D:\" for a drive).
    function _folderName(path) {
        var parts = path.split(/[\\/]/).filter(part => part.length > 0)
        var name = parts.length > 1 ? parts[parts.length - 1] : path
        return name.length > 22 ? name.slice(0, 21) + "…" : name
    }

    implicitHeight: Math.max(72, content.implicitHeight + 2 * Theme.spaceMd)
    color: Theme.surface

    Connections {
        target: bar.controller
        function onBusyChanged(busy) {
            if (busy) {
                bar._startedAt = Date.now()
                bar._elapsed = 0
            }
        }
    }

    Timer {
        interval: 500
        repeat: true
        running: bar.busy
        onTriggered: bar._elapsed = (Date.now() - bar._startedAt) / 1000
    }

    Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: Theme.border }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spaceXl
        anchors.rightMargin: Theme.spaceXl
        spacing: Theme.spaceLg

        ColumnLayout {
            id: content
            Layout.fillWidth: true
            spacing: Theme.spaceXs

            RowLayout {
                Layout.fillWidth: true
                // An empty status line gives its height to the update notice.
                visible: bar.busy || statusText.text.length > 0
                spacing: Theme.spaceSm

                Icon {
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 2
                    visible: name.length > 0
                    name: bar._error ? "error" : bar._showBlocker ? "warning"
                        : !bar.busy && bar._showSummary ? "completed" : ""
                    size: Theme.iconMd
                    color: bar._error ? Theme.danger : bar._showBlocker ? Theme.warning : Theme.success
                }
                Text {
                    id: statusText
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: {
                        if (bar.busy) {
                            if (bar.controller.cancelling) return "Stopping..."
                            var verb = bar.controller.checking ? "checked" : "done"
                            // Several files run at once, so count finished files rather than "file N of M".
                            return bar.controller.filesDone + " of " + bar.controller.filesTotal + " files " + verb
                                + (bar.controller.currentFile ? "  ·  " + bar.controller.currentFile : "")
                        }
                        // The list's scan banner shows the count, and its empty state says what to add.
                        if (bar.scanning) return "Scanning..."
                        if (bar._showSummary) return bar.controller.summary
                        if (bar.queue.count === 0) return ""
                        if (bar.blocker) return bar.blocker
                        return bar.readyText || "Ready. Press " + bar.startText + " to start."
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    color: bar._error ? Theme.danger : bar._showBlocker ? Theme.warning : Theme.text
                    // Long messages wrap rather than losing their middle.
                    wrapMode: Text.Wrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                }
                Text {
                    textFormat: Text.PlainText
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 2
                    visible: bar.busy
                    text: Math.round(bar.controller.progress * 100) + "%  ·  " + bar._clock(bar._elapsed)
                        + (bar.controller.timeLeft ? "  ·  " + bar.controller.timeLeft : "")
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                }
            }

            ProgressBar {
                Layout.fillWidth: true
                visible: bar.busy
                from: 0
                to: 1
                value: bar.controller.progress
                Accessible.role: Accessible.ProgressBar
                Accessible.name: "Overall progress"
            }

            UpdateNotice {
                Layout.fillWidth: true
                controller: bar.updates
                visible: !bar.busy && bar.updates !== null && bar.updates.bannerVisible
            }
        }

        AppButton {
            visible: !bar.busy && bar.controller.lastFile.length > 0 && bar.controller.mode === "decrypt"
            text: "Open file"
            iconName: "openFile"
            toolTipText: "Open " + bar.controller.lastFile
            onClicked: bar.controller.openLastFile()
        }

        AppButton {
            id: foldersButton
            visible: !bar.busy && bar._folders.length > 0
            text: bar._folders.length === 1 ? "Open " + bar._folderName(bar._folders[0]) : "Open folder"
            iconName: "folderOpen"
            toolTipText: bar._folders.length === 1 ? "Open " + bar._folders[0]
                                                   : "Choose one of the " + bar._folders.length + " folders this run wrote to"
            onClicked: bar._folders.length === 1 ? bar.controller.openFolder(bar._folders[0])
                                                 : foldersMenu.popup(foldersButton, 0, foldersButton.height)

            // The folders the run wrote to, in the order it first wrote to each (the first 12 of many).
            AppMenu {
                id: foldersMenu
                maxWidth: 520

                Instantiator {
                    model: bar._folders.slice(0, 12)
                    delegate: AppMenuItem {
                        required property string modelData
                        text: modelData
                        onTriggered: bar.controller.openFolder(modelData)
                    }
                    onObjectAdded: (index, object) => foldersMenu.insertItem(index, object)
                    onObjectRemoved: (index, object) => foldersMenu.removeItem(object)
                }
            }
        }

        AppButton {
            visible: bar.busy
            kind: "danger"
            text: bar.controller.cancelling ? "Stopping..." : "Cancel"
            iconName: "stop"
            enabled: !bar.controller.cancelling
            toolTipText: "Stop now; files in progress are left unchanged and finished files stay done (Esc)"
            onClicked: bar.controller.cancel()
        }

        AppButton {
            visible: !bar.busy && bar.checkText.length > 0
            text: bar.checkText
            iconName: "check"
            enabled: bar.blocker.length === 0
            toolTipText: bar.checkTip
            onClicked: bar.checkRequested()
        }

        AppButton {
            visible: !bar.busy
            kind: "primary"
            text: bar.queue.runnableCount > 0 ? bar.startText + " (" + bar.queue.runnableCount + ")" : bar.startText
            iconName: bar.startIcon
            enabled: bar.blocker.length === 0
            toolTipText: bar.startText + " the files in the list (Ctrl+Enter)"
            onClicked: bar.startRequested()
        }
    }
}
