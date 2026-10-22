// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// A labeled password box with a show/hide button, a Caps Lock warning while it has focus, an
// optional error line, and an optional strength meter. The meter is spelled out in words as
// well as with its bar.
ColumnLayout {
    id: field

    property string label: "Password"
    property string errorText: ""
    property string helpText: ""
    property bool showStrength: false
    property alias text: input.text

    signal accepted()
    // Enter or leaving the box (see TextInput.editingFinished).
    signal editingFinished()

    // 0 empty, 1 very weak (under 8 characters), 2 weak, 3 fair, 4 good, 5 strong
    readonly property int strength: field._strength(input.text)
    readonly property var _strengthNames: ["", "Very weak", "Weak", "Fair", "Good", "Strong"]
    property bool _capsLock: false

    function forceInputFocus() { input.forceActiveFocus() }

    // Focuses the box with its text selected, so typing replaces it.
    function selectInput() {
        input.selectAll()
        input.forceActiveFocus()
    }

    function _checkCapsLock() { field._capsLock = input.activeFocus && appController.capsLockOn() }

    function _strength(pass) {
        if (pass.length === 0) return 0
        if (pass.length < 8) return 1
        var lower = pass.toLowerCase()
        var common = ["password", "123456", "qwerty", "letmein", "iloveyou", "admin", "welcome", "abc123", "111111"]
        if (common.some(word => lower.indexOf(word) >= 0) || /^(.)\1+$/.test(pass)) return 2
        var kinds = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter(re => re.test(pass)).length
        var score = (pass.length >= 12 ? 2 : 1) + (pass.length >= 16 ? 1 : 0) + Math.max(0, kinds - 1)
        return score <= 2 ? 2 : score <= 3 ? 3 : score <= 4 ? 4 : 5
    }

    spacing: Theme.spaceXs

    Text {
        text: field.label
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        color: field.enabled ? Theme.text : Theme.textMuted
        Accessible.ignored: true
    }

    TextField {
        id: input
        Layout.fillWidth: true
        implicitHeight: Theme.controlHeight
        echoMode: revealButton.checked ? TextInput.Normal : TextInput.Password
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        color: input.enabled ? Theme.text : Theme.textMuted
        selectByMouse: true
        leftPadding: 10
        rightPadding: revealButton.width + 6
        topPadding: 0
        bottomPadding: 0
        verticalAlignment: TextInput.AlignVCenter
        inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
        Accessible.name: field.label
        Accessible.description: field.errorText || field.helpText
        Accessible.passwordEdit: !revealButton.checked
        onAccepted: field.accepted()
        onEditingFinished: field.editingFinished()
        onActiveFocusChanged: field._checkCapsLock()
        // Released as well as pressed: the Caps Lock key changes the state as it goes down.
        Keys.onPressed: field._checkCapsLock()
        Keys.onReleased: field._checkCapsLock()

        // A disabled box (during a run) takes the muted fill, so it doesn't look editable.
        background: Rectangle {
            radius: Theme.radius
            color: input.enabled ? Theme.surface : Theme.surfaceAlt
            border.width: input.activeFocus || field.errorText.length > 0 ? 2 : 1
            border.color: field.errorText.length > 0 ? Theme.danger
                : input.activeFocus ? Theme.focusRing
                : input.enabled ? Theme.inputBorder : Theme.border
        }

        AppButton {
            id: revealButton
            anchors.right: parent.right
            anchors.rightMargin: 3
            anchors.verticalCenter: parent.verticalCenter
            kind: "ghost"
            compact: true
            checkable: true
            iconName: checked ? "hide" : "view"
            toolTipText: checked ? "Hide the password" : "Show the password"
            focusPolicy: Qt.TabFocus
        }
    }

    RowLayout {
        Layout.fillWidth: true
        visible: field._capsLock
        spacing: Theme.spaceXs

        Icon {
            name: "warning"
            size: Theme.iconSm
            color: Theme.warning
        }
        Text {
            Layout.fillWidth: true
            text: "Caps Lock is on"
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            color: Theme.warning
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }
    }

    // Strength meter: a bar plus the strength in words.
    RowLayout {
        Layout.fillWidth: true
        visible: field.showStrength && input.text.length > 0
        spacing: Theme.spaceSm

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 4
            radius: 2
            color: Theme.border
            Accessible.ignored: true

            Rectangle {
                height: parent.height
                radius: 2
                width: parent.width * field.strength / 5
                color: field.strength <= 2 ? Theme.danger : field.strength === 3 ? Theme.warning : Theme.success
                Behavior on width { NumberAnimation { duration: 150 } }
            }
        }
        Text {
            text: "Strength: " + field._strengthNames[field.strength]
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontCaption
            color: Theme.textMuted
            Accessible.role: Accessible.StaticText
            Accessible.name: text
        }
    }

    Text {
        Layout.fillWidth: true
        visible: text.length > 0
        text: field.errorText || field.helpText
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontCaption
        color: field.errorText.length > 0 ? Theme.danger : Theme.textMuted
        wrapMode: Text.WordWrap
        Accessible.role: Accessible.StaticText
        Accessible.name: text
    }
}
