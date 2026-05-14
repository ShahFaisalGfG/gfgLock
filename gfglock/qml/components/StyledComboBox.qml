// qmllint disable unqualified import
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material

ComboBox {
    id: control

    font.pixelSize: 12

    delegate: ItemDelegate {
        required property var modelData
        required property int index

        width:       control.popup.width
        height:      32
        text:        modelData ?? ""
        font.pixelSize: 12
        highlighted: control.highlightedIndex === index
    }

    popup.contentItem: ListView {
        clip:          true
        implicitHeight: Math.min(contentHeight, 260)
        model:         control.delegateModel
        currentIndex:  control.highlightedIndex
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    }

    popup.width: Math.max(width, implicitWidth)
}
