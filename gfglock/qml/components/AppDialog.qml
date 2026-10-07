import QtQuick
import QtQuick.Controls

// Modal dialog centred in its window. The Material style gives each dialog its own pale dim
// layer, which overrides AppWindow's; this one dims the window with Theme.scrim in both themes,
// and a border keeps the dialog's edge visible against the dimmed dark theme.
Dialog {
    modal: true
    focus: true  // keys (Esc, Enter, Tab) go to the dialog, not the window behind it
    anchors.centerIn: parent

    background: Rectangle {
        radius: Theme.radiusLarge
        color: Theme.surface
        border.width: 1
        border.color: Theme.borderStrong
    }

    Overlay.modal: Rectangle {
        color: Theme.scrim
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }
}
