// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One row of a queue: type badge, name, size or result, and a status badge. Status is always
// spelled out in text and with an icon, never by color alone. Once a file has a result, its
// message (where it was saved, why it failed, or a note on a finished file) replaces the size
// and folder line.
Rectangle {
    id: fileItem

    signal clicked(int index, int modifiers)
    signal contextMenuRequested(int index)
    signal removeRequested(int index)

    required property int index
    required property string name
    required property string path
    required property string folder
    required property string size
    required property string ext
    required property bool selected
    required property string status
    required property real progress
    required property string message
    property bool current: false
    property bool listHasFocus: false
    // While the list runs, rows can't be removed: the run already has its files.
    property bool listBusy: false

    readonly property bool _busy: fileItem.status === "working"
    readonly property bool _encrypted: appController.encryptedExtensions.indexOf("." + fileItem.ext.toLowerCase()) >= 0
    readonly property string _statusText: {
        switch (fileItem.status) {
        case "working":
            // Once every byte is read, the output is still being flushed to disk.
            if (fileItem.progress >= 0.999) return "Finishing..."
            return fileItem.progress > 0 ? Math.floor(fileItem.progress * 100) + "%" : "Working"
        case "done":    return "Done"
        case "skipped": return "Skipped"
        case "failed":  return "Failed"
        default:        return "Waiting"
        }
    }
    readonly property color _statusColor: {
        switch (fileItem.status) {
        case "working": return Theme.accent
        case "done":    return Theme.success
        case "failed":  return Theme.danger
        default:        return Theme.textMuted
        }
    }

    implicitHeight: 60
    radius: Theme.radius
    color: fileItem.selected ? Theme.accentSoft : (hover.hovered ? Theme.surfaceHover : "transparent")
    border.width: fileItem.current && fileItem.listHasFocus ? 2 : 0
    border.color: Theme.focusRing

    Accessible.role: Accessible.ListItem
    Accessible.name: fileItem.name + ", " + fileItem._statusText + (fileItem.message ? ", " + fileItem.message : "")
    Accessible.description: fileItem.size + ", " + fileItem.folder
    Accessible.selectable: true
    Accessible.selected: fileItem.selected

    HoverHandler { id: hover }

    ToolTip.visible: hover.hovered && !removeButton.hovered
    ToolTip.text: fileItem.message ? fileItem.path + "\n" + fileItem.message : fileItem.path
    ToolTip.delay: 900

    Rectangle {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: 3
        height: parent.height - 16
        radius: 2
        color: Theme.accent
        visible: fileItem.selected
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spaceMd
        anchors.rightMargin: Theme.spaceSm
        spacing: Theme.spaceMd

        // The file type at caption size; encrypted files show the lock instead, since their
        // long extension wouldn't fit.
        Rectangle {
            Layout.preferredWidth: 40
            Layout.preferredHeight: 40
            radius: Theme.radius
            color: Theme.surfaceAlt
            border.width: 1
            border.color: Theme.border

            Icon {
                anchors.centerIn: parent
                visible: fileItem._encrypted
                name: "lock"
                size: Theme.iconLg
                color: Theme.accent
            }
            Text {
                anchors.centerIn: parent
                visible: !fileItem._encrypted
                width: parent.width - 4
                horizontalAlignment: Text.AlignHCenter
                text: fileItem.ext
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                font.weight: Font.DemiBold
                color: Theme.textMuted
                elide: Text.ElideRight
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: fileItem.name
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                font.weight: Font.DemiBold
                color: Theme.text
                elide: Text.ElideMiddle
            }
            Text {
                Layout.fillWidth: true
                text: fileItem.message ? fileItem.message : fileItem.size + "  ·  " + fileItem.folder
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                color: fileItem.status === "failed" ? Theme.danger : Theme.textMuted
                // A message is read from its start (the tooltip has all of it); a folder path
                // keeps both ends.
                elide: fileItem.message ? Text.ElideRight : Text.ElideMiddle
            }
        }

        RowLayout {
            spacing: 4
            visible: !removeButton.visible

            Icon {
                name: fileItem.status === "done" ? "completed"
                    : fileItem.status === "failed" ? "error"
                    : fileItem.status === "skipped" ? "skip"
                    : fileItem._busy ? "sync" : ""
                visible: name.length > 0
                size: Theme.iconSm
                color: fileItem._statusColor
            }
            Text {
                text: fileItem._statusText
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                font.weight: fileItem._busy ? Font.DemiBold : Font.Normal
                color: fileItem._statusColor
            }
        }

        AppButton {
            id: removeButton
            kind: "ghost"
            compact: true
            iconName: "cancel"
            toolTipText: "Remove " + fileItem.name + " from the list (the file itself is not deleted)"
            visible: hover.hovered && !fileItem._busy && !fileItem.listBusy
            focusPolicy: Qt.NoFocus
            onClicked: fileItem.removeRequested(fileItem.index)
        }
    }

    ProgressBar {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: Theme.spaceMd
        anchors.rightMargin: Theme.spaceMd
        height: 3
        visible: fileItem._busy
        from: 0
        to: 1
        value: Math.max(0, fileItem.progress)
        indeterminate: fileItem.progress <= 0
        Accessible.ignored: true
    }

    MouseArea {
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: function(mouse) {
            if (mouse.button === Qt.RightButton) {
                fileItem.contextMenuRequested(fileItem.index)
            } else {
                fileItem.clicked(fileItem.index, mouse.modifiers)
            }
        }
    }
}
