import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// A labeled password box with a show/hide button, an optional error line, and an optional
// strength meter. The meter is spelled out in words as well as with its bar.
ColumnLayout {
    id: field

    property string label: "Password"
    property string errorText: ""
    property string helpText: ""
    property bool showStrength: false
    property alias text: input.text

    signal accepted()

    // 0 empty, 1 too short, 2 weak, 3 fair, 4 good, 5 strong
    readonly property int strength: field._strength(input.text)
    readonly property var _strengthNames: ["", "Too short", "Weak", "Fair", "Good", "Strong"]

    function forceInputFocus() { input.forceActiveFocus() }

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
        color: Theme.text
        Accessible.ignored: true
    }

    TextField {
        id: input
        Layout.fillWidth: true
        implicitHeight: Theme.controlHeight + 4
        echoMode: revealButton.checked ? TextInput.Normal : TextInput.Password
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBody
        color: Theme.text
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

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: input.activeFocus || field.errorText.length > 0 ? 2 : 1
            border.color: field.errorText.length > 0 ? Theme.danger
                : input.activeFocus ? Theme.focusRing : Theme.border
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
