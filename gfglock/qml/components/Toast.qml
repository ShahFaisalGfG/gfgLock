import QtQuick
import QtQuick.Layouts

// A short notice near the bottom of the window that fades out by itself (click to dismiss).
Rectangle {
    id: toast

    property int duration: 4500

    function show(message) {
        if (!message) return
        label.text = message
        toast.opacity = 1
        hideTimer.restart()
    }

    implicitWidth: Math.min(row.implicitWidth + 2 * Theme.spaceLg, 560)
    implicitHeight: row.implicitHeight + 2 * Theme.spaceMd
    radius: Theme.radiusLarge
    color: Theme.inverseSurface
    opacity: 0
    visible: opacity > 0

    Behavior on opacity { NumberAnimation { duration: 180 } }

    Timer {
        id: hideTimer
        interval: toast.duration
        onTriggered: toast.opacity = 0
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Theme.spaceMd
        anchors.leftMargin: Theme.spaceLg
        anchors.rightMargin: Theme.spaceLg
        spacing: Theme.spaceSm

        Icon {
            name: "info"
            size: 14
            color: Theme.inverseText
        }
        Text {
            id: label
            Layout.fillWidth: true
            Layout.maximumWidth: 500
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: Theme.inverseText
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.StaticText
            Accessible.name: label.text
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: toast.opacity = 0
    }
}
