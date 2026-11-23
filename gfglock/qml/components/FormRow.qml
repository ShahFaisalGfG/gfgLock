import QtQuick
import QtQuick.Layouts

// A label beside its control. On narrow widths the label moves above the control instead of
// squeezing it; a switch needs no width, so it stays on its label's line. Give the control
// `Layout.fillWidth: true` and an Accessible.name.
GridLayout {
    id: row

    property string label: ""
    property string hint: ""
    property int labelWidth: 170
    // Narrow rows stack the label above the control. The 60 px gap between the two thresholds
    // stops the row from flipping back and forth as its own width settles, and the choice waits
    // until the layout pass is over (Qt.callLater) so it is made on the settled width.
    property bool stacked: false
    function _restack() {
        if (!row.stacked && row.width > 0 && row.width < 420) row.stacked = true
        else if (row.stacked && row.width > 480) row.stacked = false
    }
    onWidthChanged: Qt.callLater(row._restack)
    default property alias content: slot.data

    readonly property bool _holdsSwitch: Array.prototype.some.call(slot.children, item => item instanceof AppSwitch)
    readonly property bool _labelAbove: row.stacked && !row._holdsSwitch

    columns: row._labelAbove ? 1 : 2
    columnSpacing: Theme.spaceMd
    rowSpacing: Theme.spaceXs
    Layout.fillWidth: true

    ColumnLayout {
        Layout.preferredWidth: row.stacked ? -1 : row.labelWidth
        Layout.fillWidth: row.stacked
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: row._labelAbove ? 0 : 8
        spacing: 2

        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.preferredWidth: 1
            text: row.label
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: row.enabled ? Theme.text : Theme.textMuted
            wrapMode: Text.WordWrap
            Accessible.ignored: true
        }
        Text {
            textFormat: Text.PlainText
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
        Layout.fillWidth: !row.stacked || row._labelAbove
        // A layout's widest is its children's widest, so a control that can't stretch (a switch, a
        // row of check boxes) would cap the whole row at label plus control. The grid couldn't widen
        // the row, it stacked as if narrow, stacking let it widen, and it unstacked again, without
        // end (the Options panel blinked, and froze before the choice waited for the layout pass).
        Layout.maximumWidth: Number.POSITIVE_INFINITY
        Layout.alignment: Qt.AlignTop
        spacing: Theme.spaceSm
    }
}
