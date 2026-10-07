import QtQuick
import QtQuick.Controls

// On/off switch with a hover/focus tooltip that explains what turning it on does.
Switch {
    id: control

    property string toolTipText: ""
    property string accessibleName: ""

    focusPolicy: Qt.StrongFocus
    Accessible.name: control.accessibleName
    Accessible.description: control.toolTipText

    ToolTip.visible: control.toolTipText.length > 0 && (control.hovered || control.visualFocus)
    ToolTip.text: control.toolTipText
    ToolTip.delay: 500
}
