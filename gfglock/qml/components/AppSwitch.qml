import QtQuick
import QtQuick.Controls

// On/off switch drawn in Theme colors, with a hover/focus tooltip that explains what turning it
// on does. It has no text of its own: the FormRow or Card beside it labels it.
Switch {
    id: control

    property string toolTipText: ""
    property string accessibleName: ""

    implicitWidth: indicator.implicitWidth + leftPadding + rightPadding
    implicitHeight: Theme.controlHeight
    padding: 0
    focusPolicy: Qt.StrongFocus
    Accessible.name: control.accessibleName
    Accessible.description: control.toolTipText

    ToolTip.visible: control.toolTipText.length > 0 && (control.hovered || control.visualFocus)
    ToolTip.text: control.toolTipText
    ToolTip.delay: 500
    ToolTip.timeout: control.hovered ? -1 : Theme.focusTipTimeout

    contentItem: null
    indicator: Rectangle {
        implicitWidth: 40
        implicitHeight: 20
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: height / 2
        // The outline keeps the off state visible (3:1); on, the accent fill does that.
        color: !control.enabled ? (control.checked ? Theme.border : Theme.surfaceAlt)
            : control.checked ? Theme.accentFill
            : control.hovered ? Theme.surfaceHover : Theme.surface
        border.width: control.checked ? 0 : 1
        border.color: control.enabled ? Theme.inputBorder : Theme.border

        Rectangle {
            readonly property int inset: 4
            width: control.enabled && (control.hovered || control.down) ? 14 : 12
            height: width
            radius: width / 2
            x: inset + control.visualPosition * (parent.width - width - 2 * inset)
            y: (parent.height - height) / 2
            color: !control.enabled ? (control.checked ? Theme.surface : Theme.border)
                : control.checked ? Theme.textOnAccent : Theme.textMuted
            Behavior on x {
                enabled: !control.pressed
                NumberAnimation { duration: 120; easing.type: Easing.OutQuad }
            }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: Theme.focusRing
            visible: control.visualFocus
        }
    }
}
