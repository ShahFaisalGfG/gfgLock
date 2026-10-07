// qmllint disable unqualified
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

AppWindow {
    id: prefsWin

    width: 760
    height: 560
    minimumWidth: 600
    minimumHeight: 460
    title: "Preferences"
    showMaximize: false
    modality: Qt.ApplicationModal

    property bool dirty: false
    property bool _closeAfterSave: false
    property string _statusMessage: ""
    property string _speedTestMessage: ""
    property bool _statusIsError: false
    property var _values: ({})

    readonly property var sections: [
        { name: "Appearance", icon: "settings" },
        { name: "Encryption", icon: "lock" },
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
    onClosing: {
        prefsController.cancelReadSizeTest()
        prefsWin.destroy()
    }

    Connections {
        target: prefsController
        // The speed test picks a size for each direction; like any edit, Save keeps it.
        function onReadSizeTestFinished(encryptSize, decryptSize, message) {
            if (encryptSize >= 0) {
                var changed = encryptSize !== encReadCombo.value || decryptSize !== decReadCombo.value
                if (encryptSize !== encReadCombo.value) prefsWin.set("encryption.read_size", encryptSize)
                if (decryptSize !== decReadCombo.value) prefsWin.set("decryption.read_size", decryptSize)
                message += changed ? " Press Save to keep them." : " They are already selected."
            }
            prefsWin._speedTestMessage = message
        }
        function onSaveFinished(success, message) {
            if (success && prefsWin._closeAfterSave) { prefsWin.close(); return }
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

    function value(key, fallback) {
        return key in prefsWin._values ? prefsWin._values[key] : fallback
    }

    function loadValues() {
        prefsWin._values = {}
        themeCombo.value = prefsController.theme
        algorithmCombo.value = prefsController.encMode
        hideNamesSwitch.checked = prefsController.encFilenames
        reserveSwitch.checked = prefsController.clampThreads
        notifySwitch.checked = prefsController.operationNotifications
        logsSwitch.checked = prefsController.enableLogs
        logLevelCombo.value = prefsController.logLevel
        prefsWin.dirty = false
    }

    function save() {
        if (!prefsWin.dirty) { prefsWin.close(); return }
        if ("theme" in prefsWin._values) appController.applyTheme(prefsWin._values["theme"])
        prefsWin._closeAfterSave = true
        prefsController.saveSettings(prefsWin._values)
    }

    AppDialog {
        id: resetDialog
        title: "Reset all preferences?"
        standardButtons: Dialog.Reset | Dialog.Cancel
        Text {
            width: 340
            text: "Every preference returns to its default. Your files are not affected."
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: Theme.text
        }
        onReset: {
            prefsController.resetDefaults()
            appController.applyTheme("system")
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

            // Section navigation (Up/Down to move, Tab to the content)
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 210
                color: Theme.surfaceAlt

                ListView {
                    id: nav
                    anchors.fill: parent
                    anchors.margins: Theme.spaceSm
                    model: prefsWin.sections
                    spacing: 2
                    focus: true
                    activeFocusOnTab: true
                    keyNavigationEnabled: true
                    Accessible.role: Accessible.List
                    Accessible.name: "Preference sections"

                    delegate: ItemDelegate {
                        id: navItem
                        required property var modelData
                        required property int index
                        width: ListView.view.width
                        height: 38
                        highlighted: ListView.isCurrentItem
                        onClicked: nav.currentIndex = navItem.index
                        Accessible.name: navItem.modelData.name

                        contentItem: RowLayout {
                            spacing: Theme.spaceSm
                            Icon {
                                name: navItem.modelData.icon
                                size: 14
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
                            border.width: nav.activeFocus && navItem.highlighted ? 2 : 0
                            border.color: Theme.focusRing
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
                        description: "System follows your Windows light or dark mode setting."
                        FormRow {
                            label: "App theme"
                            StyledComboBox {
                                id: themeCombo
                                Layout.fillWidth: true
                                accessibleName: "App theme"
                                toolTipText: "Light, dark, or follow the Windows setting."
                                model: prefsController.themeOptions
                                onActivated: prefsWin.set("theme", currentValue)
                            }
                        }
                    }
                }

                // Encryption
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Encryption defaults"
                        description: "Used each time the app opens; you can still change them on the Encrypt tab."
                        FormRow {
                            label: "Encryption method"
                            hint: algorithmCombo.currentIndex >= 0
                                ? prefsController.algorithmOptions[algorithmCombo.currentIndex].hint : ""
                            StyledComboBox {
                                id: algorithmCombo
                                Layout.fillWidth: true
                                accessibleName: "Encryption method"
                                toolTipText: "Decrypting picks the right method automatically."
                                model: prefsController.algorithmOptions
                                onActivated: prefsWin.set("advanced.encryption_mode", currentValue)
                            }
                        }
                        FormRow {
                            label: "Hide file names"
                            hint: "Give encrypted files random names; the original name comes back when you decrypt."
                            Item { Layout.fillWidth: true }
                            AppSwitch {
                                id: hideNamesSwitch
                                accessibleName: "Hide file names by default"
                                toolTipText: "Turn on to hide file names by default"
                                onToggled: prefsWin.set("encryption.encrypt_filenames", checked)
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
                        description: "How much of a file is read at once. The fastest size depends on the disk and processor; Automatic (4 MB) suits most PCs. Each file being worked on holds about four times the size in memory."
                        FormRow {
                            label: "When encrypting"
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
                            StyledComboBox {
                                id: decReadCombo
                                Layout.fillWidth: true
                                accessibleName: "Read size when decrypting"
                                model: prefsController.readSizeOptions
                                value: prefsWin.value("decryption.read_size", prefsController.decReadSize)
                                onActivated: prefsWin.set("decryption.read_size", currentValue)
                            }
                        }
                        FormRow {
                            label: "Find the fastest"
                            hint: prefsController.readSizeTestRunning
                                ? "Testing each size... " + Math.round(prefsController.readSizeTestProgress * 100) + "%"
                                : prefsWin._speedTestMessage
                                  || "Encrypts and decrypts a 256 MB test file in the temp folder with every size, then selects the fastest. Takes about a minute; the test file is deleted afterwards."
                            Item { Layout.fillWidth: true }
                            AppButton {
                                text: prefsController.readSizeTestRunning ? "Stop" : "Run speed test"
                                iconName: prefsController.readSizeTestRunning ? "stop" : "speed"
                                toolTipText: prefsController.readSizeTestRunning
                                    ? "Stop the speed test; nothing is changed"
                                    : "Time every read size on this PC and select the fastest"
                                onClicked: {
                                    if (prefsController.readSizeTestRunning) {
                                        prefsController.cancelReadSizeTest()
                                    } else {
                                        prefsWin._speedTestMessage = ""
                                        prefsController.startReadSizeTest(
                                            prefsWin.value("advanced.encryption_mode", prefsController.encMode))
                                    }
                                }
                            }
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
                            hint: "Show a Windows notification when encrypting or decrypting ends."
                            Item { Layout.fillWidth: true }
                            AppSwitch {
                                id: notifySwitch
                                accessibleName: "Notify when finished"
                                toolTipText: "Useful for long jobs while you work in another window"
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
                                toolTipText: "Write log files on this PC"
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
                text: "Reset to defaults"
                toolTipText: "Restore every preference to its original value"
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
