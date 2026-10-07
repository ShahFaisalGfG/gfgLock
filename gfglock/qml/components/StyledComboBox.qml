pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Combo box for {label, code} option lists. Bind `value` to the option it shows; the box
// follows it as it changes and flags a value missing from the list instead of silently showing
// another one. `readiness` maps a code to true (downloaded) or false (downloads on first use)
// and adds a badge to that row and to the tooltip.
ComboBox {
    id: control

    property var value: undefined
    property var readiness: ({})
    property string accessibleName: ""
    property string toolTipText: ""
    readonly property bool valueMissing: control.value !== undefined && control.value !== null
        && control.count > 0 && control.indexOfValue(control.value) < 0

    function selectCode(code) {
        var idx = control.indexOfValue(code)
        if (idx >= 0) control.currentIndex = idx
    }

    function _sync() {
        if (control.value !== undefined) control.selectCode(control.value)
    }

    onValueChanged: control._sync()
    // A new model resets the selection after these handlers run, so re-select once it settles.
    onModelChanged: Qt.callLater(control._sync)
    onCountChanged: Qt.callLater(control._sync)
    Component.onCompleted: control._sync()

    function _badge(code) {
        var ready = control.readiness[code]
        if (ready === undefined) return ""
        return ready ? "Downloaded" : "Downloads on first use"
    }

    textRole: "label"
    valueRole: "code"
    implicitHeight: Theme.controlHeight
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    hoverEnabled: true

    Accessible.name: control.accessibleName
    Accessible.description: control.toolTipText

    ToolTip.visible: control.toolTipText.length > 0 && !control.popup.visible && (control.hovered || control.visualFocus)
    ToolTip.text: (control.valueMissing ? "The saved choice \"" + control.value + "\" isn't available here. Pick another.\n" : "")
        + (control._badge(control.currentValue)
           ? control.toolTipText + "\n" + control.currentText + ": " + control._badge(control.currentValue).toLowerCase() + "."
           : control.toolTipText)
    ToolTip.delay: 600

    contentItem: Text {
        leftPadding: 10
        rightPadding: control.indicator.width + 6
        text: control.displayText
        font: control.font
        color: control.enabled ? Theme.text : Theme.textMuted
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        Accessible.ignored: true
    }

    indicator: Icon {
        x: control.width - width - 10
        y: (control.height - height) / 2
        name: "chevronDown"
        size: 10
        color: Theme.textMuted
    }

    background: Rectangle {
        radius: Theme.radius
        color: control.hovered && control.enabled ? Theme.surfaceHover : Theme.surface
        border.width: control.visualFocus || control.valueMissing ? 2 : 1
        border.color: control.visualFocus ? Theme.focusRing : control.valueMissing ? Theme.warning : Theme.border
    }

    delegate: ItemDelegate {
        id: row
        required property var modelData
        required property int index

        readonly property string badge: control._badge(row.modelData[control.valueRole])

        width: control.popup.width
        height: 34
        highlighted: control.highlightedIndex === row.index
        Accessible.name: row.modelData[control.textRole] + (row.badge ? ", " + row.badge : "")

        contentItem: RowLayout {
            spacing: Theme.spaceSm
            Text {
                Layout.fillWidth: true
                text: row.modelData[control.textRole]
                font: control.font
                color: Theme.text
                elide: Text.ElideRight
            }
            Icon {
                visible: row.badge.length > 0
                name: control.readiness[row.modelData[control.valueRole]] ? "completed" : "download"
                size: 12
                color: control.readiness[row.modelData[control.valueRole]] ? Theme.success : Theme.textMuted
            }
        }
        background: Rectangle {
            color: row.highlighted ? Theme.accentSoft : "transparent"
        }
    }

    popup: Popup {
        y: control.height + 2
        width: Math.max(control.width, 220)
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 320)
        padding: 4
        // Keeps the list inside the window; near the bottom edge it shifts up instead of
        // opening off-screen.
        margins: Theme.spaceSm

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.borderStrong
        }
    }
}
