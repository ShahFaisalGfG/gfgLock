// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtQuick.Window
import Qt.labs.platform as Platform
import "components"

ApplicationWindow {
    id: encDlg

    property string operationMode:    "encrypt"
    property var    _algOpts:         prefsController.encryptionModeOptions
    property var    _chunkOpts:       prefsController.chunkSizeOptions
    property real   _elapsed:         0.0
    property bool   _done:            false
    property int    _prevFileCount:   0
    property int    _failedCount:     0
    property int    _succeededCount:  0

    readonly property color _colorSuccess: Material.theme === Material.Dark ? "#4caf50" : "#2e7d32"
    readonly property color _colorPartial: Material.theme === Material.Dark ? "#ff9800" : "#e65100"
    readonly property color _colorFailure: Material.theme === Material.Dark ? "#ef5350" : "#c62828"

    width: 920
    height: 640
    minimumWidth: 720
    minimumHeight: 520
    title: operationMode === "encrypt" ? "Encrypt Files" : "Decrypt Files"
    flags: Qt.FramelessWindowHint | Qt.Window
    modality: Qt.ApplicationModal

    Material.theme:  appController && appController.currentTheme === "dark" ? Material.Dark : Material.Light
    Material.accent: "#0078d4"

    Component.onCompleted: {
        encryptController.setMode(operationMode)
        x = Screen.virtualX + Math.round((Screen.desktopAvailableWidth  - width)  / 2)
        y = Screen.virtualY + Math.round((Screen.desktopAvailableHeight - height) / 2)
        _initCombos()
        _prevFileCount = encryptController.fileModel.count
        if (encryptController.fileModel.count > 0)
            passInput.forceActiveFocus()
    }

    onClosing: {
        elapsedTimer.stop()
        encryptController.clearFiles()
        encryptController.setMode("encrypt")
        encDlg.destroy()
        if (typeof cliLaunchMode !== "undefined" && cliLaunchMode !== "")
            Qt.quit()
    }

    Timer {
        id:       elapsedTimer
        interval: 100
        repeat:   true
        onTriggered: encDlg._elapsed = parseFloat((encDlg._elapsed + 0.1).toFixed(1))
    }

    // ── Background ────────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color:        Material.theme === Material.Dark ? "#1e1e1e" : "#f3f3f3"
        border.color: Material.theme === Material.Dark ? "#3c3c3c" : "#c8c8c8"
        border.width: 1
    }

    // ── Operation signals ─────────────────────────────────────────────────
    Connections {
        target: encryptController

        function onOperationStarted() {
            stackView.currentIndex = 1
            encDlg._done           = false
            encDlg._elapsed        = 0.0
            encDlg._failedCount    = 0
            encDlg._succeededCount = 0
            elapsedTimer.start()
            var sz = encryptController.fileModel.totalSize
            filesLabel.text = "0 / " + encryptController.fileModel.count
                            + " files" + (sz ? "  ·  " + sz : "")
            encDlg.minimumWidth  = 480
            encDlg.minimumHeight = 347
            encDlg.width  = 614
            encDlg.height = 427
            encDlg.x = Screen.virtualX + Math.round((Screen.desktopAvailableWidth  - encDlg.width)  / 2)
            encDlg.y = Screen.virtualY + Math.round((Screen.desktopAvailableHeight - encDlg.height) / 2)
        }
        function onStatusChanged(msg) {
            progressLogs.append(msg)
            progressLogs.cursorPosition = progressLogs.length
        }
        function onErrorOccurred(msg) {
            progressLogs.append("ERROR: " + msg)
        }
        function onCurrentFileChanged(path) {
            currentFileLabel.text = path
        }
        function onProgressChanged(done, total) {
            progressBar.value = total > 0 ? (done / total) : 0
        }
        function onFilesProgressChanged(done, total) {
            var sz = encryptController.fileModel.totalSize
            filesLabel.text = done + " / " + total + " files"
                            + (sz ? "  ·  " + sz : "")
        }
        function onOperationFinished(elapsed, total, succeeded, failed, skipped) {
            elapsedTimer.stop()
            encDlg._done           = true
            encDlg._failedCount    = failed
            encDlg._succeededCount = succeeded
            currentFileLabel.text = encDlg._buildStatus(elapsed, total, succeeded, failed, skipped)
            finishedLabel.text    = "100%"
            progressBar.value   = 1.0
            doneBtn.text        = "Close"
            doneBtn.highlighted = true

            var sz   = encryptController.fileModel.totalSize
            var time = new Date().toLocaleTimeString()
            appController.appendLog(
                "[" + time + "]  " + encDlg.operationMode.toUpperCase() +
                "  —  " + total + " file(s) " + sz +
                "  ·  " + elapsed.toFixed(1) + "s" +
                "  ·  " + succeeded + " ok · " + failed + " failed · " + skipped + " skipped"
            )
        }
    }

    Connections {
        target: encryptController.fileModel
        function onCountChanged(count) {
            if (count > 0 && encDlg._prevFileCount === 0)
                passInput.forceActiveFocus()
            encDlg._prevFileCount = count
        }
    }

    // ── Main layout ───────────────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TitleBar {
            Layout.fillWidth: true
            window: encDlg
            title:  encDlg.title
        }

        // StackLayout: index 0 = form, index 1 = progress
        StackLayout {
            id: stackView
            Layout.fillWidth:  true
            Layout.fillHeight: true
            currentIndex: 0

            // ── PAGE 0: file selection + options ──────────────────────────
            Item {
                ColumnLayout {
                    anchors.fill:    parent
                    anchors.margins: 16
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth:  true
                        Layout.fillHeight: true
                        spacing: 16

                        // Left column — file list
                        ColumnLayout {
                            Layout.preferredWidth: Math.max(300, Math.round((encDlg.width - 48) * 0.54))
                            Layout.fillHeight: true
                            spacing: 8

                            // File list toolbar
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text {
                                    text:           "Files"
                                    font.pixelSize: 13
                                    font.weight:    Font.Medium
                                    color:          Material.foreground
                                }
                                Text {
                                    id: fileCountLabel
                                    text:           "(" + encryptController.fileModel.count + ")"
                                    font.pixelSize: 12
                                    color: Material.theme === Material.Dark ? "#aaaaaa" : "#666666"
                                }
                                Text {
                                    text:           encryptController.fileModel.count > 0
                                                    ? "·  " + encryptController.fileModel.totalSize
                                                    : ""
                                    font.pixelSize: 11
                                    color: Material.theme === Material.Dark ? "#666666" : "#999999"
                                }
                                Item { Layout.fillWidth: true }

                                Button {
                                    text:                 "+ Files"
                                    flat:                 true
                                    font.pixelSize:       11
                                    Layout.preferredHeight: 30
                                    onClicked:            fileDialog.open()
                                    Accessible.name: "Add files"
                                    Accessible.role: Accessible.Button
                                }
                                Button {
                                    text:                 "+ Folder"
                                    flat:                 true
                                    font.pixelSize:       11
                                    Layout.preferredHeight: 30
                                    onClicked:            folderDialog.open()
                                    Accessible.name: "Add folder"
                                    Accessible.role: Accessible.Button
                                }
                                Button {
                                    text:                 "Select All"
                                    flat:                 true
                                    font.pixelSize:       11
                                    Layout.preferredHeight: 30
                                    onClicked:            encryptController.fileModel.selectAll()
                                    Accessible.name: "Select all files"
                                    Accessible.role: Accessible.Button
                                }
                                Button {
                                    text: {
                                        var n = encryptController.fileModel.selectedCount
                                        return n > 1 ? "Remove (" + n + ")" : "Remove"
                                    }
                                    flat:                 true
                                    font.pixelSize:       11
                                    Layout.preferredHeight: 30
                                    Material.foreground:  "#e0004f"
                                    onClicked:            encryptController.removeSelected()
                                    Accessible.name: "Remove selected files"
                                    Accessible.role: Accessible.Button
                                }
                            }

                            // File list container
                            Rectangle {
                                Layout.fillWidth:  true
                                Layout.fillHeight: true
                                radius: 6
                                color:        Material.theme === Material.Dark ? "#141414" : "#fafafa"
                                border.color: Material.theme === Material.Dark ? "#333333" : "#e0e0e0"
                                border.width: 1
                                clip: true

                                FileList {
                                    anchors.fill:    parent
                                    anchors.margins: 2
                                    onEmptyPanelClicked: fileDialog.open()
                                }
                            }
                        }

                        // Right column — form
                        ColumnLayout {
                            Layout.fillWidth:  true
                            Layout.fillHeight: true
                            spacing: 10

                            Text {
                                text:           encDlg.title
                                font.pixelSize: 16
                                font.weight:    Font.Bold
                                color:          Material.foreground
                            }

                            // Password
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Text {
                                    text:           "Password"
                                    font.pixelSize: 12
                                    color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                                }
                                TextField {
                                    id: passInput
                                    Layout.fillWidth:       true
                                    Layout.preferredHeight: 40
                                    echoMode:         showPassCheck.checked ? TextInput.Normal : TextInput.Password
                                    font.pixelSize:   12
                                    Accessible.name: "Password"
                                    Accessible.role: Accessible.EditableText
                                    background: Rectangle {
                                        color:        Material.theme === Material.Dark ? "#2a2a2a" : "#ffffff"
                                        border.color: passInput.activeFocus
                                            ? Material.accent
                                            : (Material.theme === Material.Dark ? "#555555" : "#aaaaaa")
                                        border.width: 1
                                        radius: 4
                                    }
                                    Item {
                                        y: passInput.activeFocus
                                            ? Math.round(-height / 2)
                                            : Math.round((parent.height - height) / 2)
                                        x:       10
                                        width:   _passLegend.implicitWidth + 8
                                        height:  _passLegend.implicitHeight
                                        visible: passInput.text.length === 0
                                        Behavior on y { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                                        Rectangle {
                                            anchors.fill: parent
                                            color: passInput.activeFocus
                                                ? (Material.theme === Material.Dark ? "#1e1e1e" : "#f3f3f3")
                                                : "transparent"
                                        }
                                        Text {
                                            id: _passLegend
                                            anchors.centerIn: parent
                                            text:           "Enter password…"
                                            font.pixelSize: 11
                                            color: passInput.activeFocus
                                                ? Material.accent
                                                : (Material.theme === Material.Dark ? "#777777" : "#999999")
                                        }
                                    }
                                }
                                Item {
                                    Layout.fillWidth:       true
                                    Layout.preferredHeight: 3
                                    visible: encDlg.operationMode === "encrypt" && passInput.text.length > 0

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 2
                                        color: Material.theme === Material.Dark ? "#2d2d2d" : "#e8e8e8"
                                    }
                                    Rectangle {
                                        height: parent.height
                                        radius: 2
                                        width: parent.width * (encDlg._passStrength(passInput.text) / 4)
                                        color: {
                                            var s = encDlg._passStrength(passInput.text)
                                            return s <= 1 ? "#e0004f" : s <= 2 ? "#ff8c00" : s <= 3 ? "#f9c104" : "#107c10"
                                        }
                                        Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                                        Behavior on color { ColorAnimation { duration: 200 } }
                                    }
                                }
                            }

                            // Confirm password (encrypt only)
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 5
                                visible: encDlg.operationMode === "encrypt"

                                Text {
                                    text:           "Confirm Password"
                                    font.pixelSize: 12
                                    color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                                }
                                TextField {
                                    id: confirmInput
                                    Layout.fillWidth:       true
                                    Layout.preferredHeight: 40
                                    echoMode:         showPassCheck.checked ? TextInput.Normal : TextInput.Password
                                    font.pixelSize:   12
                                    Accessible.name: "Confirm password"
                                    Accessible.role: Accessible.EditableText
                                    background: Rectangle {
                                        property bool mismatch: confirmInput.text.length > 0
                                            && confirmInput.text !== passInput.text
                                        color: mismatch
                                            ? Qt.rgba(1, 0, 0, 0.08)
                                            : (Material.theme === Material.Dark ? "#2a2a2a" : "#ffffff")
                                        border.color: confirmInput.activeFocus
                                            ? Material.accent
                                            : mismatch ? "#e0004f"
                                                       : (Material.theme === Material.Dark ? "#555555" : "#aaaaaa")
                                        border.width: 1
                                        radius: 4
                                    }
                                    Item {
                                        y: confirmInput.activeFocus
                                            ? Math.round(-height / 2)
                                            : Math.round((parent.height - height) / 2)
                                        x:       10
                                        width:   _confirmLegend.implicitWidth + 8
                                        height:  _confirmLegend.implicitHeight
                                        visible: confirmInput.text.length === 0
                                        Behavior on y { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                                        Rectangle {
                                            anchors.fill: parent
                                            color: confirmInput.activeFocus
                                                ? (Material.theme === Material.Dark ? "#1e1e1e" : "#f3f3f3")
                                                : "transparent"
                                        }
                                        Text {
                                            id: _confirmLegend
                                            anchors.centerIn: parent
                                            text:           "Confirm password…"
                                            font.pixelSize: 11
                                            color: confirmInput.activeFocus
                                                ? Material.accent
                                                : (Material.theme === Material.Dark ? "#777777" : "#999999")
                                        }
                                    }
                                }
                            }

                            CheckBox {
                                id:                     showPassCheck
                                text:                   "Show password"
                                font.pixelSize:         12
                                Layout.preferredHeight: 28
                                topPadding:             0
                                bottomPadding:          0
                                Accessible.name:      "Show password"
                                Accessible.role:      Accessible.CheckBox
                                Accessible.checkable: true
                                Accessible.checked:   checked
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 1
                                color: Material.theme === Material.Dark ? "#333333" : "#e0e0e0"
                            }

                            CheckBox {
                                id:                     encFilesCheck
                                text:                   "Encrypt file names"
                                font.pixelSize:         12
                                Layout.preferredHeight: 28
                                topPadding:             0
                                bottomPadding:          0
                                visible:                encDlg.operationMode === "encrypt"
                                Accessible.name:      "Encrypt file names"
                                Accessible.role:      Accessible.CheckBox
                                Accessible.checkable: true
                                Accessible.checked:   checked
                            }

                            // Algorithm
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                visible: encDlg.operationMode === "encrypt"

                                Text {
                                    text:           "Encryption Algorithm"
                                    font.pixelSize: 12
                                    color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                                }
                                StyledComboBox {
                                    id:                     algCombo
                                    Layout.fillWidth:       true
                                    Layout.preferredHeight: 34
                                    font.pixelSize:         12
                                    model:                  encDlg._algOpts.map(o => o.label)
                                    Accessible.name: "Encryption algorithm"
                                    Accessible.role: Accessible.ComboBox
                                }
                            }

                            // Threads
                            RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    text:             "CPU Threads"
                                    font.pixelSize:   12
                                    color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                      threadsCombo
                                    font.pixelSize:          12
                                    Layout.preferredWidth:   86
                                    Layout.preferredHeight:  34
                                    model: {
                                        var arr = []
                                        for (var i = 1; i <= prefsController.maxThreads; i++) arr.push(String(i))
                                        return arr
                                    }
                                    Accessible.name: "CPU threads"
                                    Accessible.role: Accessible.ComboBox
                                }
                            }

                            // Chunk size
                            RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    text:             "Chunk Size"
                                    font.pixelSize:   12
                                    color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                                    Layout.fillWidth: true
                                }
                                StyledComboBox {
                                    id:                     chunkCombo
                                    font.pixelSize:         12
                                    Layout.preferredWidth:  155
                                    Layout.preferredHeight: 34
                                    model:                  encDlg._chunkOpts.map(o => o.label)
                                    Accessible.name: "Chunk size"
                                    Accessible.role: Accessible.ComboBox
                                }
                            }

                            Item { Layout.fillHeight: true }

                            // Action buttons
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Button {
                                    text:             "Cancel"
                                    Layout.fillWidth: true
                                    font.pixelSize:   12
                                    Layout.preferredHeight: 48
                                    onClicked:        encDlg.close()
                                    Accessible.name: "Cancel"
                                    Accessible.role: Accessible.Button
                                }
                                Button {
                                    text:             encDlg.operationMode === "encrypt" ? "Encrypt" : "Decrypt"
                                    highlighted:      true
                                    Layout.fillWidth: true
                                    font.pixelSize:   12
                                    Layout.preferredHeight: 48
                                    enabled: passInput.text.length > 0 &&
                                             (encDlg.operationMode === "decrypt" || passInput.text === confirmInput.text) &&
                                             encryptController.fileModel.count > 0
                                    onClicked: encDlg.startOp()
                                    Keys.onPressed: function(event) {
                                        if (event.key === Qt.Key_Space) event.accepted = true
                                    }
                                    Accessible.name: encDlg.operationMode === "encrypt" ? "Start encryption" : "Start decryption"
                                    Accessible.role: Accessible.Button
                                }
                            }
                        }
                    }
                }
            }

            // ── PAGE 1: progress view ─────────────────────────────────────
            Item {
                ColumnLayout {
                    anchors.fill:    parent
                    anchors.margins: 22
                    spacing: 14

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            text: {
                                if (!encDlg._done)
                                    return encDlg.operationMode === "encrypt" ? "Encrypting…" : "Decrypting…"
                                var verb = encDlg.operationMode === "encrypt" ? "Encryption" : "Decryption"
                                return encDlg._failedCount > 0 ? verb + " Completed with Errors" : verb + " Complete"
                            }
                            font.pixelSize: 16
                            font.weight:    Font.Bold
                            color:          !encDlg._done          ? Material.foreground
                                            : encDlg._failedCount === 0 ? encDlg._colorSuccess
                                            : encDlg._succeededCount > 0 ? encDlg._colorPartial
                                            : encDlg._colorFailure
                            Layout.fillWidth: true
                        }
                        Text {
                            text:    encDlg._elapsed.toFixed(1) + "s"
                            font.pixelSize: 13
                            color:   Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                            visible: encDlg._elapsed > 0 && !encDlg._done
                        }
                    }

                    Text {
                        id: currentFileLabel
                        Layout.fillWidth: true
                        text:           "Preparing…"
                        font.pixelSize: 12
                        color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                        elide: Text.ElideMiddle
                    }

                    ProgressBar {
                        id:               progressBar
                        Layout.fillWidth: true
                        from: 0; to: 1; value: 0
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            id:               filesLabel
                            text:             "0 / 0 files"
                            font.pixelSize:   12
                            color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
                            Layout.fillWidth: true
                        }
                        Text {
                            text:    Math.round(progressBar.value * 100) + "%"
                            font.pixelSize: 12
                            font.weight:    Font.Medium
                            color:   "#0078d4"
                            visible: progressBar.value > 0 && !encDlg._done
                        }
                        Text {
                            id:             finishedLabel
                            text:           ""
                            font.pixelSize: 12
                            color:          "#0078d4"
                        }
                    }

                    ScrollView {
                        Layout.fillWidth:  true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        TextArea {
                            id:            progressLogs
                            readOnly:      true
                            wrapMode:      TextEdit.NoWrap
                            ContextMenu.menu: Menu {
                                MenuItem {
                                    text:        qsTr("Copy")
                                    enabled:     progressLogs.selectedText !== ""
                                    onTriggered: progressLogs.copy()
                                }
                                MenuItem {
                                    text:        qsTr("Select All")
                                    onTriggered: progressLogs.selectAll()
                                }
                            }
                            font.pixelSize: 11
                            font.family:   "Consolas, monospace"
                            color: Material.theme === Material.Dark ? "#cccccc" : "#333333"
                            leftPadding:   10
                            rightPadding:  10
                            topPadding:    8
                            bottomPadding: 8

                            background: Rectangle {
                                color:        Material.theme === Material.Dark ? "#141414" : "#fafafa"
                                border.color: Material.theme === Material.Dark ? "#333333" : "#e0e0e0"
                                border.width: 1
                                radius: 4
                            }

                            Accessible.name: "Progress log"
                            Accessible.role: Accessible.StaticText
                        }
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignRight

                        Button {
                            id:             doneBtn
                            text:           "Cancel"
                            font.pixelSize: 12
                            Accessible.name: "Cancel operation"
                            Accessible.role: Accessible.Button
                            onClicked: {
                                if (doneBtn.text === "Close") {
                                    encDlg.close()
                                } else {
                                    encryptController.cancelOperation()
                                    doneBtn.enabled = false
                                    doneBtn.text    = "Cancelling…"
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ── Enter key shortcut ───────────────────────────────────────────────────────
    Shortcut {
        sequences: ["Return", "Enter"]
        enabled:   stackView.currentIndex === 0
                   || (stackView.currentIndex === 1 && encDlg._done)
        onActivated: {
            if (stackView.currentIndex === 1 && encDlg._done) {
                encDlg.close()
            } else if (encryptController.fileModel.count === 0) {
                fileDialog.open()
            } else if (passInput.text.length > 0
                       && (encDlg.operationMode === "decrypt" || passInput.text === confirmInput.text)) {
                encDlg.startOp()
            }
        }
    }

    // ── File dialogs ──────────────────────────────────────────────────────────
    Platform.FileDialog {
        id:       fileDialog
        title:    "Select Files"
        fileMode: Platform.FileDialog.OpenFiles
        nameFilters: encDlg.operationMode === "decrypt"
            ? ["Encrypted files (*.gfglock *.gfglck *.gfgcha)", "All files (*)"]
            : ["All files (*)"]
        onAccepted: {
            var urls = []
            for (var i = 0; i < files.length; i++)
                urls.push(files[i].toString())
            encryptController.addFiles(urls)
        }
    }

    Platform.FolderDialog {
        id:    folderDialog
        title: "Select Folder"
        onAccepted: encryptController.addFolder(folder.toString())
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    function _opVerb() {
        /** Returns the past-tense verb for the current operation mode. */
        return operationMode === "encrypt" ? "encrypted" : "decrypted"
    }

    function _fileStr(n) {
        /** Returns a pluralised file count string, e.g. "3 files" or "1 file". */
        return n + (n === 1 ? " file" : " files")
    }

    function _buildStatus(elapsed, total, succeeded, failed, skipped) {
        /** Builds the completion status line shown below the progress bar. */
        try {
            var verb = _opVerb()
            var t    = elapsed.toFixed(1) + "s"
            if (failed === 0 && skipped === 0)
                return "All " + _fileStr(succeeded) + " " + verb + " successfully in " + t + "."
            if (failed === 0)
                return _fileStr(succeeded) + " " + verb + "  ·  " + _fileStr(skipped) + " already " + verb + ", skipped  ·  " + t + "."
            if (skipped === 0)
                return _fileStr(succeeded) + " of " + _fileStr(total) + " " + verb + "  ·  " + _fileStr(failed) + " failed  ·  " + t + "."
            return _fileStr(succeeded) + " of " + _fileStr(total) + " " + verb + "  ·  " + _fileStr(failed) + " failed  ·  " + _fileStr(skipped) + " skipped  ·  " + t + "."
        } catch(e) {
            console.error("_buildStatus:", e)
            return ""
        }
    }

    function _passStrength(pass) {
        if (pass.length === 0) return 0
        if (pass.length < 8)   return 1
        var score = 1
        if (pass.length >= 12) score++
        if (/[A-Z]/.test(pass) && /[a-z]/.test(pass)) score++
        if (/[0-9]/.test(pass)) score++
        if (/[^A-Za-z0-9]/.test(pass)) score++
        return Math.min(4, score)
    }

    function _initCombos() {
        try {
            var threads = operationMode === "encrypt"
                ? prefsController.encThreads
                : prefsController.decThreads
            threadsCombo.currentIndex = Math.min(Math.max(0, threads - 1), threadsCombo.count - 1)

            var chunkVal = operationMode === "encrypt"
                ? prefsController.encChunkSize
                : prefsController.decChunkSize
            for (var i = 0; i < _chunkOpts.length; i++) {
                if (_chunkOpts[i].value === chunkVal) { chunkCombo.currentIndex = i; break }
            }

            var encMode = prefsController.encMode
            for (var j = 0; j < _algOpts.length; j++) {
                if (_algOpts[j].value === encMode) { algCombo.currentIndex = j; break }
            }

            encFilesCheck.checked = prefsController.encFilenames
        } catch(e) {
            console.error("_initCombos:", e)
        }
    }

    function startOp() {
        try {
            var chunkVal = _chunkOpts[chunkCombo.currentIndex].value
            var algVal   = _algOpts[algCombo.currentIndex].value
            var threads  = parseInt(threadsCombo.currentText) || 1

            encryptController.startOperation(
                passInput.text,
                operationMode,
                encFilesCheck.checked,
                threads,
                chunkVal === -1 ? null : chunkVal,
                algVal
            )
        } catch(e) {
            console.error("startOp:", e)
        }
    }
}
