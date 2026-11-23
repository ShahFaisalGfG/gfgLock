// qmllint disable unqualified
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

// Preferences, saved as each one changes (as in the sister apps): Close, Esc, and the title bar
// only close the window.
AppWindow {
    id: prefsWin

    width: 820
    height: 600
    minimumWidth: 640
    minimumHeight: 480
    title: "Preferences"
    showMaximize: false
    modality: Qt.ApplicationModal

    property string _statusMessage: ""
    property bool _statusIsError: false
    property string _speedTestMessage: ""
    // The values shown when the speed test started, by setting key, so the lists it changes
    // can be pointed out.
    property var _beforeTest: ({})
    readonly property bool _runBusy: encryptController.busy || decryptController.busy

    readonly property var sections: [
        { name: "General", icon: "settings" },
        { name: "Speed", icon: "speed" },
        { name: "Logs", icon: "notify" },
        { name: "Updates", icon: "sync" },
        { name: "Advanced", icon: "more" }
    ]

    // 1 up to every thread, or one fewer when a thread is kept free for Windows.
    readonly property var threadOptions: {
        var total = prefsController.cpuCount
        var max = prefsController.clampThreads ? Math.max(1, total - 1) : total
        var list = []
        for (var i = 1; i <= max; i++) list.push({ label: i === 1 ? "1 file" : i + " files", code: i })
        return list
    }

    onClosing: {
        prefsController.cancelReadSizeTest()
        prefsWin.destroy()
    }

    Connections {
        target: prefsController
        // The speed test saves what it measured: a read size and a number of files at a time for
        // each direction, -1 for any it didn't measure. The lists show the saved values, so the
        // ones it changed are pointed out.
        function onReadSizeTestFinished(encryptSize, decryptSize, encryptThreads, decryptThreads, message) {
            var results = [
                { key: "encryption.read_size", value: encryptSize, combo: encReadCombo },
                { key: "decryption.read_size", value: decryptSize, combo: decReadCombo },
                { key: "encryption.cpu_threads", value: encryptThreads, combo: encThreadsCombo },
                { key: "decryption.cpu_threads", value: decryptThreads, combo: decThreadsCombo }
            ].filter(result => result.value >= 0)
            for (var i = 0; i < results.length; i++) {
                if (results[i].value !== prefsWin._beforeTest[results[i].key]) results[i].combo.flash()
            }
            prefsWin._speedTestMessage = message
        }
        function onSaveFinished(success, message) {
            prefsWin._statusMessage = success ? (message || "Saved.") : message
            prefsWin._statusIsError = !success
            statusClear.restart()
        }
    }

    Timer {
        id: statusClear
        interval: 4000
        onTriggered: if (!prefsWin._statusIsError) prefsWin._statusMessage = ""
    }

    Shortcut { sequence: "Escape"; onActivated: prefsWin.close() }

    // Save one preference now; the window says "Saved." or why it couldn't be saved.
    function save(key, value) {
        var update = {}
        update[key] = value
        prefsController.saveSettings(update)
    }

    // "Last checked 17 Nov 2026 10:42", or "" before the first check.
    function lastChecked() {
        var ms = updateController.lastCheckedMs
        return ms > 0 ? "Last checked " + new Date(ms).toLocaleString(Qt.locale(), Locale.ShortFormat) : ""
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

    function _updatesText() {
        var privacy = " The request carries only gfgLock's name and version; your files, passwords, and settings never leave this PC."
        if (!updateController.canSelfUpdate)
            return "This copy runs from an unpacked folder, so it can't replace itself. "
                + (prefsController.autoCheckUpdates ? "gfgLock still tells you when a new version is out, with a link to download it."
                                                    : "Press Check now to see whether a new version is out.") + privacy
        if (!prefsController.autoCheckUpdates)
            return "gfgLock checks for a new version only when you press Check now." + privacy
                + " An update installs only after its publisher signature and checksums match."
        return "gfgLock asks GitHub at most once a day whether a newer version is out." + privacy
            + " An update installs only after its publisher signature and checksums match."
    }

    AppDialog {
        id: resetDialog
        title: "Reset all preferences?"
        width: Math.min(420, prefsWin.width - 48)
        standardButtons: Dialog.Reset | Dialog.Cancel
        defaultButton: Dialog.Cancel
        Component.onCompleted: resetDialog.standardButton(Dialog.Reset).text = "Reset"
        Text {
            textFormat: Text.PlainText
            width: parent.width
            text: "Every preference returns to its default, including each tab's options. Your files are not affected."
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: Theme.text
        }
        onReset: {
            prefsController.resetDefaults()
            appController.detectTheme()  // the saved theme is now the default one
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

            // Section navigation (Up/Down to move, Tab to the content), read as a list of page
            // tabs. The Control holds the focus, so the ring shows only when it came from the keyboard.
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
                    Accessible.role: Accessible.PageTabList
                    Accessible.name: "Preference sections"
                    // The arrow keys are keyboard use too, so they bring up the ring.
                    Keys.onUpPressed: navBox._move(-1)
                    Keys.onDownPressed: navBox._move(1)

                    function _move(step) {
                        var index = Math.max(0, Math.min(prefsWin.sections.length - 1, nav.currentIndex + step))
                        if (index === nav.currentIndex) return
                        nav.currentIndex = index
                        navBox.focusReason = Qt.TabFocusReason
                        navBox.Accessible.announce(prefsWin.sections[index].name + ", " + (index + 1) + " of "
                                                   + prefsWin.sections.length)
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
                            Accessible.role: Accessible.PageTab
                            Accessible.name: navItem.modelData.name
                            Accessible.selected: navItem.highlighted

                            contentItem: RowLayout {
                                spacing: Theme.spaceSm
                                Icon {
                                    name: navItem.modelData.icon
                                    size: Theme.iconMd
                                    color: navItem.highlighted ? Theme.accent : Theme.textMuted
                                }
                                Text {
                                    textFormat: Text.PlainText
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

                // General
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Appearance"
                        FormRow {
                            label: "App theme"
                            StyledComboBox {
                                Layout.fillWidth: true
                                accessibleName: "App theme"
                                model: prefsController.themeOptions
                                value: prefsController.theme
                                onActivated: {
                                    prefsWin.save("theme", currentValue)
                                    appController.detectTheme()
                                }
                            }
                        }
                    }
                    Card {
                        Layout.fillWidth: true
                        title: "Notifications"
                        FormRow {
                            label: "Notify when finished"
                            hint: "Show a Windows notification when a run ends while you're in another window, or after a run of more than 10 seconds."
                            Item { Layout.fillWidth: true }
                            SettingSwitch {
                                key: "advanced.operation_notifications"
                                saved: prefsController.operationNotifications
                                accessibleName: "Notify when finished"
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
                                value: Math.min(prefsController.encThreads, prefsWin.threadOptions.length)
                                onActivated: prefsWin.save("encryption.cpu_threads", currentValue)
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
                                value: Math.min(prefsController.decThreads, prefsWin.threadOptions.length)
                                onActivated: prefsWin.save("decryption.cpu_threads", currentValue)
                            }
                        }
                        FormRow {
                            label: "Keep the PC responsive"
                            hint: "Leaves one processor thread free for Windows during large jobs."
                            Item { Layout.fillWidth: true }
                            SettingSwitch {
                                key: "advanced.clamp_cpu_threads"
                                saved: prefsController.clampThreads
                                accessibleName: "Keep one processor thread free"
                                toolTipText: "Turn off to use every processor thread"
                            }
                        }
                    }
                }

                // Logs
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Logs"
                        description: "Log files help when reporting a problem. They list file names, never passwords."
                        FormRow {
                            label: "Keep logs"
                            Item { Layout.fillWidth: true }
                            SettingSwitch {
                                key: "advanced.enable_logs"
                                saved: prefsController.enableLogs
                                accessibleName: "Keep logs"
                                toolTipText: "Logs stay on this PC; nothing is sent anywhere"
                            }
                        }
                        FormRow {
                            label: "What to log"
                            enabled: prefsController.enableLogs
                            StyledComboBox {
                                Layout.fillWidth: true
                                accessibleName: "What to log"
                                toolTipText: "Errors only, or every file processed"
                                model: prefsController.logLevelOptions
                                value: prefsController.logLevel
                                onActivated: prefsWin.save("advanced.log_level", currentValue)
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

                // Updates
                PrefsPage {
                    Card {
                        Layout.fillWidth: true
                        title: "Updates"
                        description: prefsWin._updatesText()
                        FormRow {
                            label: "Check automatically"
                            hint: "Once a day while gfgLock is open."
                            Item { Layout.fillWidth: true }
                            SettingSwitch {
                                key: "advanced.auto_check_updates"
                                saved: prefsController.autoCheckUpdates
                                accessibleName: "Check for updates automatically"
                            }
                        }
                        FormRow {
                            visible: updateController.canSelfUpdate
                            label: "Install automatically"
                            hint: updateController.needsApproval
                                ? "Downloads in the background and installs when you close gfgLock, after Windows asks for administrator approval. Not on a metered connection."
                                : "Downloads in the background and installs when you close gfgLock. Not on a metered connection."
                            Item { Layout.fillWidth: true }
                            SettingSwitch {
                                key: "advanced.auto_install_updates"
                                saved: prefsController.autoInstallUpdates
                                accessibleName: "Install updates automatically"
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.spaceMd
                            AppButton {
                                text: "Check now"
                                iconName: "sync"
                                enabled: updateController.status !== "checking" && updateController.status !== "downloading"
                                toolTipText: "Ask GitHub whether a newer version is out"
                                onClicked: updateController.checkNow()
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: updateController.message
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontCaption
                                    color: updateController.status === "error" ? Theme.danger : Theme.text
                                    wrapMode: Text.WordWrap
                                    Accessible.role: Accessible.StaticText
                                    Accessible.name: text
                                }
                                Text {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: prefsWin.lastChecked()
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.textMuted
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }

                // Advanced
                PrefsPage {
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
                                value: prefsController.encReadSize
                                onActivated: prefsWin.save("encryption.read_size", currentValue)
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
                                value: prefsController.decReadSize
                                onActivated: prefsWin.save("decryption.read_size", currentValue)
                            }
                        }
                    }
                    // The test sets the read sizes above and the files at a time under Speed.
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
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: prefsWin._statusMessage || "Changes are saved as you make them."
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                color: prefsWin._statusIsError && prefsWin._statusMessage ? Theme.danger : Theme.textMuted
                wrapMode: Text.WordWrap
                Accessible.role: Accessible.StaticText
                Accessible.name: text
            }
            AppButton {
                kind: "primary"
                text: "Close"
                toolTipText: "Close Preferences (Esc)"
                onClicked: prefsWin.close()
            }
        }
    }

    // A switch that saves its preference when toggled, then follows the saved value again (so a
    // failed save, or Reset to defaults, shows what is in use).
    component SettingSwitch: AppSwitch {
        id: settingSwitch
        required property string key
        required property bool saved
        checked: settingSwitch.saved
        onToggled: {
            var update = {}
            update[settingSwitch.key] = settingSwitch.checked
            prefsController.saveSettings(update)
            settingSwitch.checked = Qt.binding(() => settingSwitch.saved)
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
