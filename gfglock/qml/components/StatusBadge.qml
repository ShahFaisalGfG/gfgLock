import QtQuick
import QtQuick.Layouts

// A small pill that spells a state in text and with an icon, never by color alone. `tone` picks
// the colors: "success", "warning", "danger", "accent", or "neutral".
Rectangle {
    id: badge

    property string text: ""
    property string iconName: ""
    property string tone: "neutral"

    readonly property color _fg: {
        switch (badge.tone) {
        case "success": return Theme.success
        case "warning": return Theme.warning
        case "danger":  return Theme.danger
        case "accent":  return Theme.accent
        default:        return Theme.textMuted
        }
    }
    readonly property color _bg: {
        switch (badge.tone) {
        case "success": return Theme.successSoft
        case "warning": return Theme.warningSoft
        case "danger":  return Theme.dangerSoft
        case "accent":  return Theme.accentSoft
        default:        return Theme.surfaceAlt
        }
    }

    implicitWidth: strip.implicitWidth + 2 * Theme.spaceSm
    implicitHeight: 22
    radius: height / 2
    color: badge._bg
    border.width: badge.tone === "neutral" ? 1 : 0
    border.color: Theme.border

    Accessible.role: Accessible.StaticText
    Accessible.name: badge.text

    RowLayout {
        id: strip
        anchors.centerIn: parent
        spacing: Theme.spaceXs

        Icon {
            visible: badge.iconName.length > 0
            name: badge.iconName
            size: Theme.iconSm
            color: badge._fg
        }
        Text {
            textFormat: Text.PlainText
            text: badge.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            font.weight: Font.DemiBold
            color: badge._fg
            Accessible.ignored: true
        }
    }
}
