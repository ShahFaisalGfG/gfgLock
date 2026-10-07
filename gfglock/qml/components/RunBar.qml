// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Status, progress, and Start / Cancel for one tab. The status line says what is happening, why
// Start is unavailable, or how the last run went.
Rectangle {
    id: bar

    required property var controller
    // Why Start is unavailable, or "" when the tab is ready.
    property string blocker: ""
    property string startText: "Start"
    property string startIcon: "play"

    signal startRequested()

    readonly property var queue: bar.controller.fileModel
    readonly property bool busy: bar.controller.busy
    // The last run's result stays until the list changes (the controller then clears it); it
    // matters more than the reason Start is off.
    readonly property bool _showSummary: bar.controller.summary.length > 0
    readonly property bool _showBlocker: !bar.busy && !bar.controller.scanning && !bar._showSummary
        && bar.blocker.length > 0 && bar.queue.count > 0
    readonly property bool _warn: bar._showBlocker || (bar._showSummary && bar.queue.failedCount > 0)
    property real _elapsed: 0
    property real _startedAt: 0

    implicitHeight: 72
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
            Layout.fillWidth: true
            spacing: Theme.spaceXs

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spaceSm

                Text {
                    Layout.fillWidth: true
                    text: {
                        if (bar.busy) {
                            if (bar.controller.cancelling)
                                return "Stopping after the files in progress..."
                            // Several files run at once, so count finished files rather than "file N of M".
                            return bar.controller.filesDone + " of " + bar.controller.filesTotal + " files done"
                                + (bar.controller.currentFile ? "  ·  " + bar.controller.currentFile : "")
                        }
                        if (bar.controller.scanning)
                            return "Scanning folder... " + bar.controller.scanFound.toLocaleString(Qt.locale(), "f", 0)
                                + " files found so far."
                        if (bar._showSummary) return bar.controller.summary
                        if (bar.blocker) return bar.blocker
                        return "Ready. Press " + bar.startText + " to start."
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.DemiBold
                    color: bar._warn ? Theme.warning : Theme.text
                    // Long messages wrap onto a second line rather than losing their middle.
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                }
                Text {
                    visible: bar.busy
                    text: Math.round(bar.controller.progress * 100) + "%  ·  " + Math.floor(bar._elapsed) + " s"
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
        }

        AppButton {
            visible: !bar.busy && bar.controller.lastFolder.length > 0
            text: "Open folder"
            iconName: "folderOpen"
            toolTipText: "Open " + bar.controller.lastFolder
            onClicked: bar.controller.openLastFolder()
        }

        AppButton {
            visible: bar.busy
            kind: "danger"
            text: bar.controller.cancelling ? "Stopping..." : "Cancel"
            iconName: "stop"
            enabled: !bar.controller.cancelling
            toolTipText: "Stop after the files in progress; files not started yet stay unchanged (Esc)"
            onClicked: bar.controller.cancel()
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
