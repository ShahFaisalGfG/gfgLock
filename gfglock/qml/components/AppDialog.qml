pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Templates as T

// Modal dialog centred in its window, with a Theme title and AppButtons for its standard
// buttons. The Material style gives each dialog its own pale dim layer, which overrides
// AppWindow's; this one dims the window with Theme.scrim in both themes, and a border keeps the
// dialog's edge visible against the dimmed dark theme. `defaultButton` (a standard button such
// as Dialog.Close) is drawn as the primary button, takes focus on open, and is pressed by
// Return or Enter unless another button has focus; leave it unset where no choice is safe.
Dialog {
    id: dialog

    property int defaultButton: Dialog.NoButton
    // Read through the button box's standardButtons, which change only once its buttons exist.
    readonly property Item _defaultItem: (buttonBox.standardButtons & dialog.defaultButton) !== 0
        ? dialog.standardButton(dialog.defaultButton) : null

    modal: true
    focus: true  // keys (Esc, Enter, Tab) go to the dialog, not the window behind it
    anchors.centerIn: parent

    onOpened: if (dialog._defaultItem) dialog._defaultItem.forceActiveFocus()

    Shortcut {
        sequences: ["Return", "Enter"]
        enabled: dialog.opened && dialog._defaultItem !== null
        onActivated: {
            var focused = buttonBox.Window.activeFocusItem
            var target = (focused instanceof T.AbstractButton ? focused : dialog._defaultItem) as T.AbstractButton
            if (target.enabled)
                target.clicked()  // the signal the button box listens to; click() needs Qt 6.8
        }
    }

    background: Rectangle {
        radius: Theme.radiusLarge
        color: Theme.surface
        border.width: 1
        border.color: Theme.borderStrong
    }

    // No backgrounds behind the title or the buttons: Material's would paint over the border.
    header: Text {
        visible: text.length > 0
        text: dialog.title
        leftPadding: Theme.spaceXl
        rightPadding: Theme.spaceXl
        topPadding: Theme.spaceXl
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSubtitle
        font.weight: Font.DemiBold
        color: Theme.text
        elide: Text.ElideRight
        Accessible.role: Accessible.Heading
        Accessible.name: text
    }

    footer: DialogButtonBox {
        id: buttonBox
        visible: count > 0
        alignment: Qt.AlignRight
        buttonLayout: DialogButtonBox.WinLayout
        spacing: Theme.spaceSm
        leftPadding: Theme.spaceXl
        rightPadding: Theme.spaceXl
        topPadding: 0
        bottomPadding: Theme.spaceXl
        background: null
        delegate: AppButton {
            id: footerButton
            kind: footerButton === dialog._defaultItem ? "primary" : "secondary"
        }
    }

    Overlay.modal: Rectangle {
        color: Theme.scrim
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }
}
