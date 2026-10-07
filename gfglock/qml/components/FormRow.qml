import QtQuick
import QtQuick.Layouts

// A label beside its control. On narrow widths the label moves above the control instead of
// squeezing it. Give the control `Layout.fillWidth: true` and an Accessible.name.
GridLayout {
    id: row

    property string label: ""
    property string hint: ""
    property int labelWidth: 170
    // Narrow rows stack the label above the control. The 60 px gap between the two thresholds
    // stops the row from flipping back and forth as its own width settles.
    property bool stacked: false
    onWidthChanged: {
        if (!row.stacked && width > 0 && width < 420) row.stacked = true
        else if (row.stacked && width > 480) row.stacked = false
    }
    default property alias content: slot.data

    columns: row.stacked ? 1 : 2
    columnSpacing: Theme.spaceMd
    rowSpacing: Theme.spaceXs
    Layout.fillWidth: true

    ColumnLayout {
        Layout.preferredWidth: row.stacked ? -1 : row.labelWidth
        Layout.fillWidth: row.stacked
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: row.stacked ? 0 : 8
        spacing: 2

        // Wrapped text must not size the column by its unwrapped length: a long hint would
        // otherwise push the grid's width around and lay the row out again without end.
        Text {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            text: row.label
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: row.enabled ? Theme.text : Theme.textMuted  // a disabled row looks disabled
            wrapMode: Text.WordWrap
            Accessible.ignored: true
        }
        Text {
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            visible: row.hint.length > 0
            text: row.hint
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            color: Theme.textMuted
            wrapMode: Text.WordWrap
        }
    }

    RowLayout {
        id: slot
        Layout.fillWidth: true
        spacing: Theme.spaceSm
    }
}
