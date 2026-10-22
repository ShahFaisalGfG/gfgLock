// qmllint disable unqualified
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

AppWindow {
    id: prefsWin

    width: 820
    height: 600
    minimumWidth: 640
    minimumHeight: 480
    title: "Preferences"
    showMaximize: false
    modality: Qt.ApplicationModal

    property bool dirty: false
    property bool _closeAfterSave: false
    property string _statusMessage: ""
    property string _speedTestMessage: ""
    // The values shown when the speed test started, by setting key, so the lists it changes
    // can be pointed out.
    property var _beforeTest: ({})
    property bool _statusIsError: false
    property var _values: ({})
    readonly property bool _runBusy: encryptController.busy || decryptController.busy

    readonly property var sections: [
        { name: "Appearance", icon: "settings" },
        { name: "Speed", icon: "speed" },
        { name: "Notifications & logs", icon: "notify" }
    ]

    // 1 up to every thread, or one fewer when a thread is kept free for Windows.
    readonly property var threadOptions: {
        var total = prefsController.cpuCount
        var max = prefsWin.value("advanced.clamp_cpu_threads", prefsController.clampThreads) ? Math.max(1, total - 1) : total
        var list = []
        for (var i = 1; i <= max; i++) list.push({ label: i === 1 ? "1 file" : i + " files", code: i })
        return list
    }

    Component.onCompleted: prefsWin.loadValues()
    // Closing ends the preview: the saved theme shows, which is the new one after Save and the
    // old one after Cancel, Esc, or the title bar.
    onClosing: {
        prefsController.cancelReadSizeTest()
        appController.endPreview()
        prefsWin.destroy()
    }

    Connections {
        target: prefsController
        // The speed test saves what it measured: a read size and a number of files at a time for
        // each direction, -1 for any it didn't measure. Dropping unsaved choices of those lets
        // their lists show the saved result; other unsaved edits stay pending.
        function onReadSizeTestFinished(encryptSize, decryptSize, encryptThreads, decryptThreads, message) {
            var results = [
                { key: "encryption.read_size", value: encryptSize, combo: encReadCombo },
                { key: "decryption.read_size", value: decryptSize, combo: decReadCombo },
                { key: "encryption.cpu_threads", value: encryptThreads, combo: encThreadsCombo },
                { key: "decryption.cpu_threads", value: decryptThreads, combo: decThreadsCombo }
            ].filter(result => result.value >= 0)
            prefsWin.forget(results.map(result => result.key))
            for (var i = 0; i < results.length; i++) {
                if (results[i].value !== prefsWin._beforeTest[results[i].key]) results[i].combo.flash()
            }
            prefsWin._speedTestMessage = message
        }
        function onSaveFinished(success, message) {
            if (success && prefsWin._closeAfterSave) {
                prefsWin.close()
                return
            }
            prefsWin._closeAfterSave = false
            prefsWin._statusMessage = message
            prefsWin._statusIsError = !success
        }
    }

    Shortcut { sequences: [StandardKey.Save]; onActivated: prefsWin.save() }
    Shortcut { sequence: "Escape"; onActivated: prefsWin.close() }

    // ── Value plumbing ─────────────────────────────────────────────────────

    // Record an edited value; controls call this from their change handlers.
    function set(key, value) {
        var values = Object.assign({}, prefsWin._values)
        values[key] = value
        prefsWin._values = values
        prefsWin.dirty = true
        prefsWin._statusMessage = ""
    }

    // Drop unsaved edits of these keys, so their controls show the saved values again.
    function forget(keys) {
        var values = Object.assign({}, prefsWin._values)
        for (var i = 0; i < keys.length; i++) delete values[keys[i]]
        prefsWin._values = values
        prefsWin.dirty = Object.keys(values).length > 0
    }

    function value(key, fallback) {
        return key in prefsWin._values ? prefsWin._values[key] : fallback
    }

    function loadValues() {
        prefsWin._values = {}
        themeCombo.value = prefsController.theme
        reserveSwitch.checked = prefsController.clampThreads
        notifySwitch.checked = prefsController.operationNotifications
        logsSwitch.checked = prefsController.enableLogs
        logLevelCombo.value = prefsController.logLevel
        prefsWin.dirty = false
    }

    // The theme is already showing (it previews as it is chosen), so saving only stores it.
    function save() {
        if (!prefsWin.dirty) { prefsWin.close(); return }
        prefsWin._closeAfterSave = true
        prefsController.saveSettings(prefsWin._values)
    }

    function startSpeedTest() {
        prefsWin._speedTestMessage = ""
        prefsWin._beforeTest = {
            "encryption.read_size": encReadCombo.currentValue,
            "decryption.read_size": decReadCombo.currentValue,
            "encryption.cpu_threads": encThreadsCombo.currentValue,
            "decryption.cpu_threads": decThreadsCombo.currentValue
        }
        prefsController.startReadSizeTest(prefsController.encMode)
    }

    AppDialog {
        id: resetDialog
        title: "Reset all preferences?"
        width: Math.min(420, prefsWin.width - 48)
        standardButtons: Dialog.Reset | Dialog.Cancel
        defaultButton: Dialog.Cancel
        Component.onCompleted: resetDialog.standardButton(Dialog.Reset).text = "Reset and save"
        Text {
            width: parent.width
            text: "Every preference returns to its default and is saved at once; unsaved changes here are dropped. Your files are not affected."
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: Theme.text
        }
        onReset: {
            prefsController.resetDefaults()
            appController.endPreview()  // the saved theme is now the default one
            prefsWin.loadValues()
            resetDialog.close()
        }
    }

    // ── Layout ─────────────────────────────────────────────────────────────

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Section navigation (Up/Down to move, Tab to the content). The Control holds the
            // focus, so the ring shows only when it came from the keyboard.
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 210
                color: Theme.surfaceAlt

                Control {
                    id: navBox
                    anchors.fill: parent
                    padding: Theme.spaceSm
                    focus: true
                    focusPolicy: Qt.TabFocus
                    Accessible.role: Accessible.List
                    Accessible.name: "Preference sections"
                    // The arrow keys are keyboard use too, so they bring up the ring.
                    Keys.onUpPressed: {
                        nav.decrementCurrentIndex()
                        navBox.focusReason = Qt.TabFocusReason
                    }
                    Keys.onDownPressed: {
                        nav.incrementCurrentIndex()
                        navBox.focusReason = Qt.TabFocusReason
                    }

                    contentItem: ListView {
                        id: nav
                        model: prefsWin.sections
                        spacing: 2
                        interactive: false

                        delegate: ItemDelegate {
                            id: navItem
                            required property var modelData
                            required property int index
                            width: ListView.view.width
                            height: 38
                            focusPolicy: Qt.NoFocus
                            highlighted: ListView.isCurrentItem
                            onClicked: {
                                nav.currentIndex = navItem.index
                                navBox.forceActiveFocus(Qt.MouseFocusReason)
                            }
                            Accessible.name: navItem.modelData.name

                            contentItem: RowLayout {
                                spacing: Theme.spaceSm
                                Icon {
                                    name: navItem.modelData.icon
                                    size: Theme.iconMd
                                    color: navItem.highlighted ? Theme.accent : Theme.textMuted
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: navItem.modelData.name
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontBody
                                    font.weight: navItem.highlighted ? Font.DemiBold : Font.Normal
                                    color: Theme.text
                                    elide: Text.ElideRight
                                }
                            }
                            background: Rectangle {
                                radius: Theme.radius
                                color: navItem.highlighted ? Theme.accentSoft : (navItem.hovered ? Theme.surfaceHover : "transparent")
                                border.width: navBox.visualFocus && navItem.highlighted ? 2 : 0
                                border.color: Theme.focusRing
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: Theme.border }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: nav.currentIndex

                // Appearance
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Theme"
                        FormRow {
                            label: "App theme"
                            StyledComboBox {
                                id: themeCombo
                                Layout.fillWidth: true
                                accessibleName: "App theme"
                                toolTipText: "Previews as you choose; Cancel or Esc puts the saved theme back."
                                model: prefsController.themeOptions
                                onActivated: {
                                    prefsWin.set("theme", currentValue)
                                    appController.previewTheme(currentValue)
                                }
                            }
                        }
                    }
                }

                // Speed
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Files at a time"
                        description: "Each file is read, encrypted, and saved at the same time, so a big file goes about as fast as the disk allows. Working on several files at once speeds up batches of smaller files."
                        FormRow {
                            label: "When encrypting"
                            enabled: !prefsController.readSizeTestRunning
                            StyledComboBox {
                                id: encThreadsCombo
                                Layout.fillWidth: true
                                accessibleName: "Files encrypted at a time"
                                model: prefsWin.threadOptions
                                // Bound to the edited value so rebuilding the list keeps the choice.
                                value: Math.min(prefsWin.value("encryption.cpu_threads", prefsController.encThreads),
                                                prefsWin.threadOptions.length)
                                onActivated: prefsWin.set("encryption.cpu_threads", currentValue)
                            }
                        }
                        FormRow {
                            label: "When decrypting"
                            enabled: !prefsController.readSizeTestRunning
                            StyledComboBox {
                                id: decThreadsCombo
                                Layout.fillWidth: true
                                accessibleName: "Files decrypted at a time"
                                model: prefsWin.threadOptions
                                value: Math.min(prefsWin.value("decryption.cpu_threads", prefsController.decThreads),
                                                prefsWin.threadOptions.length)
                                onActivated: prefsWin.set("decryption.cpu_threads", currentValue)
                            }
                        }
                        FormRow {
                            label: "Keep the PC responsive"
                            hint: "Leaves one processor thread free for Windows during large jobs."
                            Item { Layout.fillWidth: true }
                            AppSwitch {
                                id: reserveSwitch
                                accessibleName: "Keep one processor thread free"
                                toolTipText: "Turn off to use every processor thread"
                                onToggled: prefsWin.set("advanced.clamp_cpu_threads", checked)
                            }
                        }
                    }
                    Card {
                        Layout.fillWidth: true
                        title: "Read size"
                        description: "How much of a file is read at once. The fastest size depends on the disk and processor; the default, 4 MB, suits most PCs. Each file being worked on holds about eight times the size in memory."
                        FormRow {
                            label: "When encrypting"
                            enabled: !prefsController.readSizeTestRunning
                            StyledComboBox {
                                id: encReadCombo
                                Layout.fillWidth: true
                                accessibleName: "Read size when encrypting"
                                model: prefsController.readSizeOptions
                                value: prefsWin.value("encryption.read_size", prefsController.encReadSize)
                                onActivated: prefsWin.set("encryption.read_size", currentValue)
                            }
                        }
                        FormRow {
                            label: "When decrypting"
                            enabled: !prefsController.readSizeTestRunning
                            StyledComboBox {
                                id: decReadCombo
                                Layout.fillWidth: true
                                accessibleName: "Read size when decrypting"
                                model: prefsController.readSizeOptions
                                value: prefsWin.value("decryption.read_size", prefsController.decReadSize)
                                onActivated: prefsWin.set("decryption.read_size", currentValue)
                            }
                        }
                    }
                    // The test sets both cards above, so it has a card of its own.
                    Card {
                        Layout.fillWidth: true
                        title: "Best settings for this PC"
                        description: prefsController.readSizeTestRunning
                            ? "Testing... " + Math.round(prefsController.readSizeTestProgress * 100) + "%"
                            : prefsWin._runBusy
                              ? "Available once encrypting or decrypting finishes, so the timings are right."
                              : prefsWin._speedTestMessage
                                || "Encrypts and decrypts test files in the temp folder with each read size and number of files at a time (about a minute), then selects and saves the fastest. The test files are deleted afterwards."
                        AppButton {
                            text: prefsController.readSizeTestRunning ? "Stop" : "Optimize for this PC"
                            iconName: prefsController.readSizeTestRunning ? "stop" : "speed"
                            enabled: prefsController.readSizeTestRunning || !prefsWin._runBusy
                            toolTipText: prefsController.readSizeTestRunning ? "Stop the test; the settings stay as they are" : ""
                            onClicked: prefsController.readSizeTestRunning ? prefsController.cancelReadSizeTest()
                                                                           : prefsWin.startSpeedTest()
                        }
                        ProgressBar {
                            Layout.fillWidth: true
                            visible: prefsController.readSizeTestRunning
                            from: 0
                            to: 1
                            value: prefsController.readSizeTestProgress
                            Accessible.role: Accessible.ProgressBar
                            Accessible.name: "Speed test progress"
                        }
                    }
                }

                // Notifications & logs
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Notifications"
                        FormRow {
                            label: "Notify when finished"
                            hint: "Show a Windows notification when a run ends while you're in another window, or after a run of more than 10 seconds."
                            Item { Layout.fillWidth: true }
                            AppSwitch {
                                id: notifySwitch
                                accessibleName: "Notify when finished"
                                onToggled: prefsWin.set("advanced.operation_notifications", checked)
                            }
                        }
                    }
                    Card {
                        Layout.fillWidth: true
                        title: "Logs"
                        description: "Log files help when reporting a problem. They list file names, never passwords."
                        FormRow {
                            label: "Keep logs"
                            Item { Layout.fillWidth: true }
                            AppSwitch {
                                id: logsSwitch
                                accessibleName: "Keep logs"
                                toolTipText: "Logs stay on this PC; nothing is sent anywhere"
                                onToggled: prefsWin.set("advanced.enable_logs", checked)
                            }
                        }
                        FormRow {
                            label: "What to log"
                            enabled: logsSwitch.checked
                            StyledComboBox {
                                id: logLevelCombo
                                Layout.fillWidth: true
                                accessibleName: "What to log"
                                toolTipText: "Errors only, or every file processed"
                                model: prefsController.logLevelOptions
                                onActivated: prefsWin.set("advanced.log_level", currentValue)
                            }
                        }
                        RowLayout {
                            spacing: Theme.spaceSm
                            AppButton {
                                text: "Open logs folder"
                                iconName: "folderOpen"
                                toolTipText: "Show the log files in File Explorer"
                                onClicked: prefsController.openLogsFolder()
                            }
                            AppButton {
                                kind: "danger"
                                text: "Clear logs"
                                iconName: "delete"
                                toolTipText: "Empty the log files (your files are not affected)"
                                onClicked: prefsController.clearLogs()
                            }
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.spaceMd
            spacing: Theme.spaceSm

            AppButton {
                kind: "ghost"
                text: "Reset to defaults..."
                toolTipText: "Asks first, then saves the defaults at once"
                onClicked: resetDialog.open()
            }
            Text {
                id: statusText
                Layout.fillWidth: true
                text: prefsWin._statusMessage || (prefsWin.dirty ? "Unsaved changes" : "")
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                color: prefsWin._statusIsError && prefsWin._statusMessage ? Theme.danger : Theme.textMuted
                wrapMode: Text.WordWrap
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }
            AppButton {
                text: "Cancel"
                toolTipText: "Close without saving (Esc)"
                onClicked: prefsWin.close()
            }
            AppButton {
                kind: "primary"
                text: "Save"
                toolTipText: "Save and close (Ctrl+S)"
                onClicked: prefsWin.save()
            }
        }
    }

    // A scrollable column of cards for one preferences section.
    component PrefsPage: ScrollView {
        id: page
        default property alias cards: column.data
        contentWidth: availableWidth
        contentHeight: column.implicitHeight + 2 * Theme.spaceLg
        clip: true

        ColumnLayout {
            id: column
            x: Theme.spaceXl
            y: Theme.spaceLg
            width: page.availableWidth - 2 * Theme.spaceXl
            spacing: Theme.spaceLg
        }
    }
}
