// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

// Custom title bar for the frameless windows: drag to move, double-click to maximize, optional
// action buttons (`actions`) before the window controls.
Rectangle {
    id: titleBar

    required property Window window
    property string title: ""
    property bool showMinimize: true
    property bool showMaximize: false
    property alias actions: actionRow.data
    readonly property bool maximized: titleBar._maximized

    property bool _maximized: false
    property rect _savedGeometry: Qt.rect(0, 0, 0, 0)

    implicitHeight: 40
    color: Theme.titleBar

    function toggleMaximize() {
        if (!titleBar.showMaximize) return
        var win = titleBar.window
        if (titleBar._maximized) {
            win.x = titleBar._savedGeometry.x
            win.y = titleBar._savedGeometry.y
            win.width = titleBar._savedGeometry.width
            win.height = titleBar._savedGeometry.height
            titleBar._maximized = false
        } else {
            titleBar._savedGeometry = Qt.rect(win.x, win.y, win.width, win.height)
            win.x = win.screen.virtualX
            win.y = win.screen.virtualY
            win.width = win.screen.desktopAvailableWidth
            win.height = win.screen.desktopAvailableHeight
            titleBar._maximized = true
        }
    }

    DragHandler {
        target: null
        enabled: !titleBar._maximized
        grabPermissions: PointerHandler.CanTakeOverFromItems
        onActiveChanged: if (active) titleBar.window.startSystemMove()
    }

    TapHandler {
        onDoubleTapped: titleBar.toggleMaximize()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spaceMd
        spacing: Theme.spaceSm

        Image {
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            source: "../../assets/icons/Square44x44Logo.targetsize-24.png"
            fillMode: Image.PreserveAspectFit
            smooth: true
            visible: status === Image.Ready
            Accessible.ignored: true
        }

        Text {
            Layout.fillWidth: true
            text: titleBar.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            font.weight: Font.DemiBold
            elide: Text.ElideRight
            Accessible.role: Accessible.TitleBar
            Accessible.name: titleBar.title
        }

        RowLayout {
            id: actionRow
            spacing: 2
            Layout.rightMargin: Theme.spaceSm
        }

        Row {
            Layout.fillHeight: true

            WindowButton {
                visible: titleBar.showMinimize
                iconName: "minimize"
                label: "Minimize"
                onClicked: titleBar.window.showMinimized()
            }
            WindowButton {
                visible: titleBar.showMaximize
                iconName: titleBar._maximized ? "restore" : "maximize"
                label: titleBar._maximized ? "Restore" : "Maximize"
                onClicked: titleBar.toggleMaximize()
            }
            WindowButton {
                iconName: "close"
                label: "Close"
                closeStyle: true
                onClicked: titleBar.window.close()
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }

    component WindowButton: AbstractButton {
        id: button
        property string iconName: ""
        property string label: ""
        property bool closeStyle: false

        width: 46
        height: titleBar.height - 1
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        Accessible.role: Accessible.Button
        Accessible.name: button.label
        ToolTip.visible: button.hovered
        ToolTip.text: button.label
        ToolTip.delay: 800

        contentItem: Icon {
            name: button.iconName
            size: 10
            color: button.closeStyle && button.hovered ? Theme.closeHoverText : Theme.text
        }
        background: Rectangle {
            color: !button.hovered ? "transparent"
                : button.closeStyle ? Theme.closeHover : Theme.surfaceHover
        }
    }
}
