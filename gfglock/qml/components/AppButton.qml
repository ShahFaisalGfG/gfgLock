import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// The app's single button style: "primary", "secondary", "ghost", or "danger", with an optional
// icon. Icon-only buttons must set toolTipText, which also becomes their accessible name.
// Keyboard focus draws a visible ring (WCAG 2.4.7).
Button {
    id: control

    property string kind: "secondary"
    property string iconName: ""
    property string toolTipText: ""
    property bool compact: false

    readonly property bool _iconOnly: control.text.length === 0 && control.iconName.length > 0
    readonly property color _fg: {
        if (!control.enabled) return Theme.textMuted
        switch (control.kind) {
        case "primary": return Theme.textOnAccent
        case "danger":  return Theme.danger
        case "ghost":   return Theme.text
        default:        return Theme.text
        }
    }

    implicitHeight: control.compact ? 28 : Theme.controlHeight
    implicitWidth: control._iconOnly
        ? implicitHeight
        : Math.max(implicitHeight, contentItem.implicitWidth + leftPadding + rightPadding)
    leftPadding: control._iconOnly ? 0 : (control.compact ? 10 : 14)
    rightPadding: control._iconOnly ? 0 : (control.compact ? 10 : 14)
    topPadding: 0
    bottomPadding: 0
    // The Material style insets the background 6 px top and bottom by default, which drew every
    // button 12 px shorter than its layout height (cramped pills, misaligned with text fields).
    topInset: 0
    bottomInset: 0
    leftInset: 0
    rightInset: 0
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    focusPolicy: Qt.StrongFocus
    hoverEnabled: true

    ToolTip.visible: control.toolTipText.length > 0 && (control.hovered || control.visualFocus)
    ToolTip.text: control.toolTipText
    ToolTip.delay: 500

    Accessible.role: Accessible.Button
    Accessible.name: control.text.length > 0 ? control.text : control.toolTipText
    Accessible.description: control.text.length > 0 ? control.toolTipText : ""

    contentItem: RowLayout {
        spacing: 6

        Icon {
            Layout.alignment: Qt.AlignVCenter
            Layout.fillWidth: control._iconOnly
            visible: control.iconName.length > 0
            name: control.iconName
            size: control.compact ? 12 : 14
            color: control._fg
        }
        Text {
            Layout.alignment: Qt.AlignVCenter
            visible: control.text.length > 0
            text: control.text
            font: control.font
            color: control._fg
            elide: Text.ElideRight
            Accessible.ignored: true
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: {
            if (control.kind === "primary")
                return !control.enabled ? Theme.border : (control.down || control.hovered ? Theme.accentHover : Theme.accentFill)
            if (control.kind === "danger" && control.enabled && (control.hovered || control.down))
                return Theme.dangerSoft
            if (control.down) return Theme.border
            if (control.hovered && control.enabled) return Theme.surfaceHover
            return control.kind === "secondary" ? Theme.surface : "transparent"
        }
        border.width: control.kind === "secondary" ? 1 : 0
        border.color: Theme.border

        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: Theme.radius + 3
            color: "transparent"
            border.width: 2
            border.color: Theme.focusRing
            visible: control.visualFocus
        }
    }
}
