// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtQuick.Window
import "components"

ApplicationWindow {
    id: prefsWin

    width: 560
    height: 650
    minimumWidth: 480
    minimumHeight: 560
    title: "Preferences"
    flags: Qt.FramelessWindowHint | Qt.Window
    modality: Qt.ApplicationModal

    Material.theme: appController && appController.currentTheme === "dark" ? Material.Dark : Material.Light
    Material.accent: "#0078d4"

    Component.onCompleted: {
        x = Screen.virtualX + Math.round((Screen.desktopAvailableWidth  - width)  / 2)
        y = Screen.virtualY + Math.round((Screen.desktopAvailableHeight - height) / 2)
        prefsWin.loadValues()
    }

    onClosing: prefsWin.destroy()

    property bool _dirty: false
    property var  _algOpts:   prefsController.encryptionModeOptions
    property var  _chunkOpts: prefsController.chunkSizeOptions

    Connections {
        target: prefsController
        function onSettingsChanged() { prefsWin.loadValues() }
    }

    // ── Background ────────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Material.theme === Material.Dark ? "#1e1e1e" : "#f3f3f3"
        border.color: Material.theme === Material.Dark ? "#3c3c3c" : "#c8c8c8"
        border.width: 1
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TitleBar {
            Layout.fillWidth: true
            window: prefsWin
            title: "Preferences"
        }

        TabBar {
            id: tabBar
            Layout.fillWidth:       true
            Layout.preferredHeight: 44
            Material.accent: "#0078d4"

            TabButton { text: "Appearance"; font.pixelSize: 12; implicitHeight: 44 }
            TabButton { text: "Encryption"; font.pixelSize: 12; implicitHeight: 44 }
            TabButton { text: "Decryption"; font.pixelSize: 12; implicitHeight: 44 }
            TabButton { text: "Advanced";   font.pixelSize: 12; implicitHeight: 44 }
        }

        StackLayout {
            id: tabContent
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            // ── Appearance tab ───────────────────────────────────────────
            Flickable {
                contentHeight: appearanceCol.implicitHeight
                clip: true

                ColumnLayout {
                    id: appearanceCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    Item { implicitHeight: 8 }

                    GroupBox {
                        Layout.fillWidth: true
                        title: "Theme"
                        font.pixelSize: 12

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 6

                            Text {
                                text: "Application theme"
                                font.pixelSize: 12
                                color: Material.foreground
                            }
                            StyledComboBox {
                                id: themeCombo
                                Layout.fillWidth:       true
                                Layout.preferredHeight: 34
                                font.pixelSize:         12
                                model: ["System (auto)", "Light", "Dark"]
                                onCurrentIndexChanged: prefsWin._dirty = true
                            }
                            Text {
                                text: "System will follow your Windows light/dark setting."
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                color: Material.theme === Material.Dark ? "#888888" : "#777777"
                                Layout.fillWidth: true
                            }
                        }
                    }

                    Item { implicitHeight: 4 }
                }
            }

            // ── Encryption tab ───────────────────────────────────────────
            Flickable {
                contentHeight: encCol.implicitHeight
                clip: true

                ColumnLayout {
                    id: encCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    Item { implicitHeight: 8 }

                    GroupBox {
                        Layout.fillWidth: true
                        title: "Encryption Defaults"
                        font.pixelSize: 12

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "CPU Threads"
                                    font.pixelSize: 12
                                    color: Material.foreground
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                     encThreadsCombo
                                    font.pixelSize:         12
                                    Layout.preferredWidth:  86
                                    Layout.preferredHeight: 34
                                    model: {
                                        var a = []
                                        for (var i = 1; i <= prefsController.maxThreads; i++) a.push(String(i))
                                        return a
                                    }
                                    onCurrentIndexChanged: prefsWin._dirty = true
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "Chunk Size"
                                    font.pixelSize: 12
                                    color: Material.foreground
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                     encChunkCombo
                                    font.pixelSize:         12
                                    Layout.preferredWidth:  155
                                    Layout.preferredHeight: 34
                                    model:                  prefsWin._chunkOpts.map(o => o.label)
                                    onCurrentIndexChanged: prefsWin._dirty = true
                                }
                            }

                            CheckBox {
                                id: encFilenamesCheck
                                text: "Encrypt filenames by default"
                                font.pixelSize: 12
                                onCheckedChanged: prefsWin._dirty = true
                            }
                        }
                    }

                    GroupBox {
                        Layout.fillWidth: true
                        title: "Default Algorithm"
                        font.pixelSize: 12

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 6

                            StyledComboBox {
                                id:                     algCombo
                                Layout.fillWidth:       true
                                Layout.preferredHeight: 34
                                font.pixelSize:         12
                                model:                  prefsWin._algOpts.map(o => o.label)
                                onCurrentIndexChanged: prefsWin._dirty = true
                            }
                            Text {
                                text: "AES-256 GCM is recommended (AEAD authenticated encryption)."
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                color: Material.theme === Material.Dark ? "#888888" : "#777777"
                                Layout.fillWidth: true
                            }
                        }
                    }

                    Item { implicitHeight: 4 }
                }
            }

            // ── Decryption tab ───────────────────────────────────────────
            Flickable {
                contentHeight: decCol.implicitHeight
                clip: true

                ColumnLayout {
                    id: decCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    Item { implicitHeight: 8 }

                    GroupBox {
                        Layout.fillWidth: true
                        title: "Decryption Defaults"
                        font.pixelSize: 12

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "CPU Threads"
                                    font.pixelSize: 12
                                    color: Material.foreground
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                     decThreadsCombo
                                    font.pixelSize:         12
                                    Layout.preferredWidth:  86
                                    Layout.preferredHeight: 34
                                    model: {
                                        var a = []
                                        for (var i = 1; i <= prefsController.maxThreads; i++) a.push(String(i))
                                        return a
                                    }
                                    onCurrentIndexChanged: prefsWin._dirty = true
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "Chunk Size"
                                    font.pixelSize: 12
                                    color: Material.foreground
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                     decChunkCombo
                                    font.pixelSize:         12
                                    Layout.preferredWidth:  155
                                    Layout.preferredHeight: 34
                                    model:                  prefsWin._chunkOpts.map(o => o.label)
                                    onCurrentIndexChanged: prefsWin._dirty = true
                                }
                            }

                        }
                    }

                    Item { implicitHeight: 4 }
                }
            }

            // ── Advanced tab ─────────────────────────────────────────────
            Flickable {
                contentHeight: advCol.implicitHeight
                clip: true

                ColumnLayout {
                    id: advCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 20
                    spacing: 16

                    Item { implicitHeight: 8 }

                    GroupBox {
                        Layout.fillWidth: true
                        title: "Performance"
                        font.pixelSize: 12

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 8

                            CheckBox {
                                id: disableClampCheck
                                text: "Disable CPU thread clamping"
                                font.pixelSize: 12
                                onCheckedChanged: prefsWin._dirty = true
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "When enabled, one CPU thread is reserved for the OS. Disabling allows all threads to be used."
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                color: Material.theme === Material.Dark ? "#888888" : "#777777"
                            }
                        }
                    }

                    GroupBox {
                        Layout.fillWidth: true
                        title: "Logging"
                        font.pixelSize: 12

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 10

                            CheckBox {
                                id: enableLogsCheck
                                text: "Enable logging"
                                font.pixelSize: 12
                                onCheckedChanged: prefsWin._dirty = true
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                enabled: enableLogsCheck.checked

                                Text {
                                    text: "Log level"
                                    font.pixelSize: 12
                                    color: Material.foreground
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                     logLevelCombo
                                    font.pixelSize:         12
                                    Layout.preferredWidth:  135
                                    Layout.preferredHeight: 34
                                    model: ["Critical", "Full"]
                                    onCurrentIndexChanged: prefsWin._dirty = true
                                }
                            }

                            RowLayout {
                                spacing: 10

                                Button {
                                    text: "Clear Logs"
                                    flat: true
                                    font.pixelSize: 11
                                    Material.foreground: "#e0004f"
                                    onClicked: {
                                        prefsController.clearLogs()
                                        appController.clearLogs()
                                    }
                                }
                                Button {
                                    text: "Open Logs Folder"
                                    flat: true
                                    font.pixelSize: 11
                                    onClicked: prefsController.openLogsFolder()
                                }
                            }
                        }
                    }

                    Item { implicitHeight: 4 }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: Material.theme === Material.Dark ? "#3c3c3c" : "#e0e0e0"
        }

        // ── Bottom button bar ──────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 16
            spacing: 10

            Button {
                text: "Reset to Defaults"
                flat: true
                font.pixelSize: 12
                Layout.preferredHeight: 48
                Material.foreground: "#e0004f"
                onClicked: {
                    prefsController.resetDefaults()
                    prefsWin.loadValues()
                    prefsWin._dirty = false
                }
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Cancel"
                font.pixelSize: 12
                Layout.preferredHeight: 48
                onClicked: prefsWin.close()
            }
            Button {
                text: "Apply"
                font.pixelSize: 12
                Layout.preferredHeight: 48
                enabled: prefsWin._dirty
                onClicked: prefsWin.applyValues()
            }
            Button {
                text: "Save"
                highlighted: true
                font.pixelSize: 12
                Layout.preferredHeight: 48
                onClicked: { prefsWin.applyValues(); prefsWin.close() }
            }
        }
    }

    // ── Value helpers ──────────────────────────────────────────────────────────

    function loadValues() {
        try {
            var themeMap = { "system": 0, "light": 1, "dark": 2 }
            themeCombo.currentIndex = themeMap[prefsController.theme] ?? 0
            encThreadsCombo.currentIndex = Math.min(
                Math.max(0, prefsController.encThreads - 1), encThreadsCombo.count - 1)
            decThreadsCombo.currentIndex = Math.min(
                Math.max(0, prefsController.decThreads - 1), decThreadsCombo.count - 1)
            encFilenamesCheck.checked = prefsController.encFilenames
            disableClampCheck.checked = !prefsController.clampThreads
            enableLogsCheck.checked = prefsController.enableLogs
            logLevelCombo.currentIndex = prefsController.logLevel === "all" ? 1 : 0

            var encChunk = prefsController.encChunkSize
            for (var i = 0; i < _chunkOpts.length; i++) {
                if (_chunkOpts[i].value === encChunk) { encChunkCombo.currentIndex = i; break }
            }
            var decChunk = prefsController.decChunkSize
            for (var j = 0; j < _chunkOpts.length; j++) {
                if (_chunkOpts[j].value === decChunk) { decChunkCombo.currentIndex = j; break }
            }
            var encMode = prefsController.encMode
            for (var k = 0; k < _algOpts.length; k++) {
                if (_algOpts[k].value === encMode) { algCombo.currentIndex = k; break }
            }
            prefsWin._dirty = false
        } catch(e) {
            console.error("loadValues:", e)
        }
    }

    function applyValues() {
        try {
            var themeValues = ["system", "light", "dark"]
            var encChunkVal = _chunkOpts[encChunkCombo.currentIndex].value
            var decChunkVal = _chunkOpts[decChunkCombo.currentIndex].value

            var updates = {
                "theme":                          themeValues[themeCombo.currentIndex],
                "encryption.cpu_threads":         encThreadsCombo.currentIndex + 1,
                "encryption.chunk_size":          encChunkVal,
                "encryption.encrypt_filenames":   encFilenamesCheck.checked,
                "decryption.cpu_threads":         decThreadsCombo.currentIndex + 1,
                "decryption.chunk_size":          decChunkVal,
                "advanced.encryption_mode":       _algOpts[algCombo.currentIndex].value,
                "advanced.enable_logs":           enableLogsCheck.checked,
                "advanced.log_level":             logLevelCombo.currentIndex === 1 ? "all" : "critical",
                "advanced.clamp_cpu_threads":     !disableClampCheck.checked
            }
            prefsController.saveSettings(updates)
            appController.applyTheme(themeValues[themeCombo.currentIndex])
            prefsWin._dirty = false
        } catch(e) {
            console.error("applyValues:", e)
        }
    }
}
