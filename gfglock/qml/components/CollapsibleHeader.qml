// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

// Click (or Space/Enter) to show or hide the section below it. Shows an optional badge,
// e.g. "2 new", so a collapsed section can still signal that something happened.
AbstractButton {
    id: header

    property bool expanded: false
    property string title: ""
    property string badge: ""

    implicitHeight: 30
    implicitWidth: row.implicitWidth + 16
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    onClicked: header.expanded = !header.expanded

    Accessible.role: Accessible.Button
    Accessible.name: header.title + (header.expanded ? ", expanded" : ", collapsed")

    ToolTip.visible: hovered
    ToolTip.text: (header.expanded ? "Hide " : "Show ") + header.title.toLowerCase()
    ToolTip.delay: 600

    contentItem: RowLayout {
        id: row
        spacing: 6

        Text {
            text: header.expanded ? "▾" : "▸"
            font.pixelSize: 12
            color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
        }
        Text {
            text: header.title
            font.pixelSize: 12
            font.weight: Font.Medium
            color: Material.theme === Material.Dark ? "#cccccc" : "#444444"
        }
        Rectangle {
            visible: header.badge.length > 0
            radius: 8
            implicitHeight: 16
            implicitWidth: badgeText.implicitWidth + 12
            color: "#0078d4"
            Text {
                id: badgeText
                anchors.centerIn: parent
                text: header.badge
                font.pixelSize: 10
                color: "#ffffff"
            }
        }
        Item { Layout.fillWidth: true }
    }

    background: Rectangle {
        radius: 4
        color: header.hovered ? (Material.theme === Material.Dark ? "#2a2a2a" : "#e8e8e8") : "transparent"
        border.width: header.visualFocus ? 2 : 0
        border.color: "#0078d4"
    }
}
