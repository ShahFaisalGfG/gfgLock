// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtQuick.Window

// Shared chrome for every window: theme, frameless border, title bar, edge resizing, centering.
// Children are placed below the title bar and should fill their parent.
ApplicationWindow {
    id: win

    default property alias content: body.data
    property alias titleActions: titleBar.actions
    property bool showMaximize: true

    flags: Qt.FramelessWindowHint | Qt.Window
    color: Theme.background
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody

    Material.theme: Theme.dark ? Material.Dark : Material.Light
    Material.accent: Theme.accentFill
    Material.primary: Theme.accentFill
    Material.background: Theme.surface
    Material.foreground: Theme.text

    Overlay.modal: Rectangle { color: Theme.scrim }

    Binding {
        target: Theme
        property: "dark"
        value: appController.currentTheme === "dark"
    }

    // Follow a Windows light/dark switch whenever the window regains focus.
    onActiveChanged: if (active) appController.detectTheme()

    Component.onCompleted: {
        x = screen.virtualX + Math.round((screen.desktopAvailableWidth - width) / 2)
        y = screen.virtualY + Math.round((screen.desktopAvailableHeight - height) / 2)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 0

        TitleBar {
            id: titleBar
            Layout.fillWidth: true
            window: win
            title: win.title
            showMaximize: win.showMaximize
        }

        Item {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: Theme.borderStrong
        z: 99
    }

    ResizeHandles {
        window: win
        visible: !titleBar.maximized
    }
}
