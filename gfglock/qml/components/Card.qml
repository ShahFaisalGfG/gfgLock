import QtQuick
import QtQuick.Layouts

// A titled settings section. Children go into the body; `trailing` holds header controls such
// as an on/off switch. Exposed to screen readers as a named group.
Rectangle {
    id: card

    property string title: ""
    property string description: ""
    property string iconName: ""
    property alias trailing: trailingRow.data
    default property alias content: body.data

    implicitHeight: layout.implicitHeight + 2 * Theme.spaceLg
    radius: Theme.radiusLarge
    color: Theme.surface
    border.width: 1
    border.color: Theme.border

    Accessible.role: Accessible.Grouping
    Accessible.name: card.title

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.spaceLg
        spacing: Theme.spaceMd

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceMd

            Rectangle {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                Layout.alignment: Qt.AlignTop
                radius: Theme.radius
                color: Theme.accentSoft
                visible: card.iconName.length > 0

                Icon {
                    anchors.centerIn: parent
                    name: card.iconName
                    size: 16
                    color: Theme.accent
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: card.title
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.DemiBold
                    color: Theme.text
                    elide: Text.ElideRight
                    Accessible.role: Accessible.Heading
                    Accessible.name: card.title
                }
                Text {
                    Layout.fillWidth: true
                    visible: card.description.length > 0
                    text: card.description
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                    wrapMode: Text.WordWrap
                }
            }

            RowLayout {
                id: trailingRow
                Layout.alignment: Qt.AlignTop
                spacing: Theme.spaceSm
            }
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: Theme.spaceMd
            visible: children.length > 0
        }
    }
}
