// qmllint disable unqualified import
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: fileItem

    signal itemClicked(int idx, int modifiers)

    required property int    index
    required property string name
    required property string path
    required property string size
    required property string ext
    required property bool   selected

    property string fileName:  name
    property string filePath:  path
    property string fileSize:  size
    property string fileExt:   ext.length > 0 ? ext : "FILE"
    property bool   isSelected: selected

    height: 80
    radius: 6
    color: isSelected
        ? (Material.theme === Material.Dark ? "#1a3a5c" : "#cce4f7")
        : (Material.theme === Material.Dark ? "#2a2a2a" : "#ffffff")

    border.color: isSelected
        ? "#0078d4"
        : (Material.theme === Material.Dark ? "#3a3a3a" : "#e0e0e0")
    border.width: isSelected ? 2 : 1

    Behavior on color { ColorAnimation { duration: 80 } }

    // Hover tint
    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: itemMouse.containsMouse && !fileItem.isSelected
            ? (Material.theme === Material.Dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03))
            : "transparent"
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 14

        // Extension badge
        Rectangle {
            Layout.preferredWidth: 52
            Layout.preferredHeight: 52
            radius: 8
            color: Material.theme === Material.Dark
                ? Qt.rgba(0, 0.471, 0.831, 0.18)
                : Qt.rgba(0, 0.471, 0.831, 0.10)
            border.color: "#0078d4"
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: fileItem.fileExt.length > 6 ? fileItem.fileExt.substring(0, 5) + "…" : fileItem.fileExt
                color: "#0078d4"
                font.pixelSize: fileItem.fileExt.length > 4 ? 10 : 12
                font.weight: Font.Bold
                horizontalAlignment: Text.AlignHCenter
            }
        }

        // Name + path column
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            Text {
                Layout.fillWidth: true
                text: fileItem.fileName
                color: Material.foreground
                font.pixelSize: 13
                font.weight: Font.Medium
                elide: Text.ElideMiddle
            }

            Text {
                Layout.fillWidth: true
                text: fileItem.filePath
                color: Material.theme === Material.Dark ? "#888888" : "#767676"
                font.pixelSize: 11
                elide: Text.ElideMiddle
                maximumLineCount: 1
            }
        }

        // Size label — hidden while hovering (X button takes that slot)
        Text {
            text: fileItem.fileSize
            color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
            font.pixelSize: 11
            horizontalAlignment: Text.AlignRight
            visible: !itemMouse.containsMouse
        }

        // Placeholder so layout width stays stable when size label hides
        Item {
            Layout.preferredWidth:  26
            Layout.preferredHeight: 26
            visible: itemMouse.containsMouse
        }
    }

    // Click-to-select — declared before removeBtn so removeBtn wins on overlap
    MouseArea {
        id: itemMouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: function(mouse) {
            if (mouse.button === Qt.RightButton) {
                if (!fileItem.isSelected)
                    fileItem.itemClicked(fileItem.index, Qt.NoModifier)
                contextMenu.popup()
            } else {
                fileItem.itemClicked(fileItem.index, mouse.modifiers)
            }
        }
    }

    Menu {
        id: contextMenu
        MenuItem {
            text:           "Copy file name(s)"
            height:         32
            font.pixelSize: 12
            onTriggered: encryptController.copySelectedNames()
        }
        MenuItem {
            text:           "Copy full path(s)"
            height:         32
            font.pixelSize: 12
            onTriggered: encryptController.copySelectedPaths()
        }
        MenuItem {
            text:           "Remove selected"
            height:         32
            font.pixelSize: 12
            onTriggered: encryptController.fileModel.removeSelected()
        }
    }

    // Quick remove — declared AFTER itemMouse so it stacks above it and grabs clicks
    Rectangle {
        id: removeBtn
        width: 26; height: 26
        radius: 4
        anchors.right:          parent.right
        anchors.rightMargin:    12
        anchors.verticalCenter: parent.verticalCenter
        visible: itemMouse.containsMouse
        color: removeMouse.containsMouse ? "#e81123" : "transparent"
        Behavior on color { ColorAnimation { duration: 80 } }

        Text {
            anchors.centerIn: parent
            text:  "✕"
            font.pixelSize: 10
            color: removeMouse.containsMouse
                ? "#ffffff"
                : (Material.theme === Material.Dark ? "#888888" : "#777777")
            Behavior on color { ColorAnimation { duration: 80 } }
        }

        MouseArea {
            id: removeMouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: encryptController.fileModel.removeAt(fileItem.index)
        }
    }

    Accessible.name:      "File: " + fileName + ", " + fileSize
    Accessible.role:      Accessible.ListItem
    Accessible.checkable: true
    Accessible.checked:   isSelected
    Accessible.onPressAction: encryptController.fileModel.toggleSelection(fileItem.index)
}
