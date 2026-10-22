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
    // The free area (no taskbar) of the screen under `target`'s centre (a window; this one by
    // default). The window opens centred in that area, fits inside it, and maximizes to it. It
    // comes from appController.availableGeometry(x, y) when the app has one; otherwise a single
    // screen's free size is the desktop's, and with several screens the whole screen is used.
    function screenArea(target) {
        var w = target || win
        if (typeof appController.availableGeometry === "function")
            return appController.availableGeometry(Math.round(w.x + w.width / 2), Math.round(w.y + w.height / 2))
        // The desktop's free size fits inside this screen only when it is the only screen.
        if (w.screen.desktopAvailableWidth <= w.screen.width && w.screen.desktopAvailableHeight <= w.screen.height)
            return Qt.rect(w.screen.virtualX, w.screen.virtualY, w.screen.desktopAvailableWidth, w.screen.desktopAvailableHeight)
        return Qt.rect(w.screen.virtualX, w.screen.virtualY, w.screen.width, w.screen.height)
    }

    // Opens on the screen of the window it belongs to (or its own), shrunk to fit that screen
    // with a margin (never below the minimum size), centred, and with its top-left corner
    // inside the free area, so the title bar can always be reached.
    function placeOnScreen() {
        var area = win.screenArea(win.transientParent)
        var margin = Theme.spaceXl
        win.width = Math.max(win.minimumWidth, Math.min(win.width, area.width - 2 * margin))
        win.height = Math.max(win.minimumHeight, Math.min(win.height, area.height - 2 * margin))
        win.x = area.x + Math.max(0, Math.round((area.width - win.width) / 2))
        win.y = area.y + Math.max(0, Math.round((area.height - win.height) / 2))
    }

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

    Component.onCompleted: win.placeOnScreen()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 1
        spacing: 0

        TitleBar {
            id: titleBar
            Layout.fillWidth: true
            window: win
            maximizedArea: () => win.screenArea()
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
