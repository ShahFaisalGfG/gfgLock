import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Window

Item {
    id: titleBar

    required property Window window
    property string title:        ""
    property bool   showMinimize: true
    property bool   showMaximize: false
    property bool   showClose:    true

    readonly property color _bgColor: Material.theme === Material.Dark ? "#1c1c1c" : "#e8e8e8"
    readonly property color _fgColor: Material.theme === Material.Dark ? "#e0e0e0" : "#202020"

    // Manual maximize state — window.visibility is unreliable for frameless windows
    property bool _maximized:     false
    property rect _savedGeometry: Qt.rect(0, 0, 800, 600)

    height: 34

    function _toggleMax() {
        if (!titleBar.showMaximize) return
        if (titleBar._maximized) {
            titleBar.window.x      = titleBar._savedGeometry.x
            titleBar.window.y      = titleBar._savedGeometry.y
            titleBar.window.width  = titleBar._savedGeometry.width
            titleBar.window.height = titleBar._savedGeometry.height
            titleBar._maximized    = false
        } else {
            titleBar._savedGeometry = Qt.rect(
                titleBar.window.x, titleBar.window.y,
                titleBar.window.width, titleBar.window.height
            )
            titleBar.window.x      = Screen.virtualX
            titleBar.window.y      = Screen.virtualY
            titleBar.window.width  = Screen.desktopAvailableWidth
            titleBar.window.height = Screen.desktopAvailableHeight
            titleBar._maximized    = true
        }
    }

    Rectangle {
        anchors.fill: parent
        color: titleBar._bgColor
    }

    // Drag-to-move — disabled while maximized
    DragHandler {
        target: null
        enabled: !titleBar._maximized
        grabPermissions: PointerHandler.CanTakeOverFromItems
        xAxis.enabled: true
        yAxis.enabled: true
        onActiveChanged: if (active) titleBar.window.startSystemMove()
    }

    // Double-click on title/icon area only (right boundary = buttons row)
    Rectangle {
        anchors.left:   parent.left
        anchors.right:  btnRow.left
        anchors.top:    parent.top
        anchors.bottom: parent.bottom
        color: "transparent"

        TapHandler {
            grabPermissions: PointerHandler.TakeOverForbidden
            onDoubleTapped:  titleBar._toggleMax()
        }
    }

    // App icon
    Image {
        id: appIcon
        anchors.left:           parent.left
        anchors.leftMargin:     10
        anchors.verticalCenter: parent.verticalCenter
        width: 16; height: 16
        source: "../../assets/icons/gfgLock.png"
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: status === Image.Ready
    }

    // Window title
    Text {
        anchors.left:           appIcon.visible ? appIcon.right : parent.left
        anchors.leftMargin:     appIcon.visible ? 6 : 12
        anchors.verticalCenter: parent.verticalCenter
        text:           titleBar.title
        color:          titleBar._fgColor
        font.pixelSize: 12
        font.weight:    Font.Medium
        elide: Text.ElideRight
        width: Math.max(0, btnRow.x - x - 8)
    }

    // Window control buttons
    Row {
        id: btnRow
        anchors.right:          parent.right
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height

        // ── Minimize ─────────────────────────────────────────────────────
        Rectangle {
            width: 46; height: parent.height
            visible: titleBar.showMinimize
            color: minHover.containsMouse ? Qt.rgba(0.5, 0.5, 0.5, 0.22) : "transparent"
            Behavior on color { ColorAnimation { duration: 100 } }

            Text {
                anchors.centerIn: parent
                text:           "─"
                color:          titleBar._fgColor
                font.pixelSize: 12
            }

            HoverHandler { id: minHover }
            TapHandler {
                grabPermissions: PointerHandler.TakeOverForbidden
                onTapped: titleBar.window.showMinimized()
            }

            Accessible.role:  Accessible.Button
            Accessible.name:  "Minimize"
            Accessible.onPressAction: titleBar.window.showMinimized()
        }

        // ── Maximize / Restore ────────────────────────────────────────────
        Rectangle {
            width: 46; height: parent.height
            visible: titleBar.showMaximize
            color: maxHover.containsMouse ? Qt.rgba(0.5, 0.5, 0.5, 0.22) : "transparent"
            Behavior on color { ColorAnimation { duration: 100 } }

            Text {
                anchors.centerIn: parent
                text:           titleBar._maximized ? "❐" : "□"
                color:          titleBar._fgColor
                font.pixelSize: 12
            }

            HoverHandler { id: maxHover }
            TapHandler {
                grabPermissions: PointerHandler.TakeOverForbidden
                onTapped: titleBar._toggleMax()
            }

            Accessible.role: Accessible.Button
            Accessible.name: titleBar._maximized ? "Restore" : "Maximize"
            Accessible.onPressAction: titleBar._toggleMax()
        }

        // ── Close ─────────────────────────────────────────────────────────
        Rectangle {
            width: 46; height: parent.height
            visible: titleBar.showClose
            color: closeHover.containsMouse ? "#e81123" : "transparent"
            Behavior on color { ColorAnimation { duration: 100 } }

            Text {
                anchors.centerIn: parent
                text:  "✕"
                color: closeHover.containsMouse ? "#ffffff" : titleBar._fgColor
                font.pixelSize: 12
                Behavior on color { ColorAnimation { duration: 100 } }
            }

            HoverHandler { id: closeHover }
            TapHandler {
                grabPermissions: PointerHandler.TakeOverForbidden
                onTapped: titleBar.window.close()
            }

            Accessible.role: Accessible.Button
            Accessible.name: "Close"
            Accessible.onPressAction: titleBar.window.close()
        }
    }

    // Bottom separator line
    Rectangle {
        anchors.bottom: parent.bottom
        anchors.left:   parent.left
        anchors.right:  parent.right
        height: 1
        color: Material.theme === Material.Dark ? "#2e2e2e" : "#d0d0d0"
    }
}
