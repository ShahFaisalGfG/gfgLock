import QtQuick
import QtQuick.Controls

// One row of an AppMenu, in Theme sizes and colours: a compact height, the whole text (the menu
// grows to fit it), and a submenu arrow. `danger` tints actions that delete something.
MenuItem {
    id: item

    property bool danger: false

    implicitWidth: item.leftPadding + label.implicitWidth + item.rightPadding
    // A hidden row takes no room (the menu's list would otherwise keep a gap for it).
    implicitHeight: item.visible ? Theme.controlHeight - 2 : 0
    leftPadding: Theme.spaceMd
    rightPadding: item.subMenu ? Theme.spaceMd + Theme.iconLg + Theme.spaceXs : Theme.spaceMd
    topPadding: 0
    bottomPadding: 0
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody

    contentItem: Text {
        id: label
        textFormat: Text.PlainText
        text: item.text
        font: item.font
        color: !item.enabled ? Theme.textMuted : item.danger ? Theme.danger : Theme.text
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    arrow: Icon {
        x: item.width - width - Theme.spaceSm
        y: (item.height - height) / 2
        width: Theme.iconLg
        visible: item.subMenu !== null
        name: "chevronRight"
        size: Theme.iconSm
        color: item.enabled ? Theme.textMuted : Theme.border
    }

    background: Rectangle {
        implicitWidth: 160
        radius: Theme.radius
        color: !item.enabled || !item.highlighted ? "transparent"
            : item.danger ? Theme.dangerSoft : Theme.surfaceHover
    }
}
