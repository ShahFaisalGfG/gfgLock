// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"

// One tab: its file list on the left, password and options on the right, and the run bar along
// the bottom. `controller` is that tab's EncryptController ("encrypt" or "decrypt" mode).
Item {
    id: page

    required property var controller
    readonly property bool encrypting: page.controller.mode === "encrypt"
    readonly property var queue: page.controller.fileModel
    readonly property string blocker: page._blocker()
    // The toast sits above the run bar.
    readonly property int runBarHeight: runBar.height
    // The saved choice, read through a property that signals only when the value changes, so
    // saving unrelated preferences doesn't undo a choice made on this tab.
    readonly property bool _hideNamesSaved: prefsController.encFilenames
    readonly property string _addFilesTip: (page.encrypting ? "Choose files to encrypt" : "Choose encrypted files to decrypt") + " (Ctrl+O)"
    readonly property string _addFolderTip: (page.encrypting ? "Add every file in a folder and its subfolders"
                                                             : "Add every encrypted file in a folder and its subfolders")
        + " (Ctrl+Shift+O)"
    readonly property var _encryptedExts: appController.encryptedExtensions
    // ".gfgcha, .gfglck, or .gfglock"
    readonly property string _encryptedList: page._encryptedExts.slice(0, -1).join(", ") + ", or "
        + page._encryptedExts[page._encryptedExts.length - 1]
    readonly property var _method: algorithmCombo.currentIndex >= 0 ? prefsController.algorithmOptions[algorithmCombo.currentIndex] : null
    // Confirm shows a mismatch once it is as long as the password, or after Enter or leaving it,
    // not while the second copy is still being typed.
    property bool _confirmFinished: false
    readonly property bool _mismatch: confirmField.text.length > 0 && confirmField.text !== passwordField.text
        && (page._confirmFinished || confirmField.text.length >= passwordField.text.length)
    // Added files are checked by a short scan too, so the list shows a scan only once it has run
    // for a moment; a plain add then doesn't flash the scan banner.
    property bool _scanShown: false

    signal notice(string message)

    function openFiles() { filePicker.open() }
    function openFolder() { folderPicker.open() }

    function start() {
        if (page.blocker.length > 0 || page.controller.busy || page.controller.scanning) return
        page.controller.start(passwordField.text, encryptNamesSwitch.checked, algorithmCombo.currentValue || "")
    }

    // Says what is still missing before Start, or "" when the tab is ready.
    function _blocker() {
        var verb = page.encrypting ? "encrypt" : "decrypt"
        if (page._scanShown) return "Wait for the folder scan to finish, or stop it."
        if (page.queue.count === 0)
            return page.encrypting ? "Add the files or folders you want to encrypt." : "Add the encrypted files you want to decrypt."
        if (page.queue.runnableCount === 0)
            return "Every file in the list is finished. Add more files, or remove the finished ones."
        if (passwordField.text.length === 0) return "Enter the password to " + verb + " with."
        if (page._mismatch) return "The two passwords don't match."
        if (page.encrypting && confirmField.text !== passwordField.text) return "Type the password again to confirm it."
        return ""
    }

    function _rememberOptions() {
        prefsController.rememberEncryptOptions(algorithmCombo.currentValue, encryptNamesSwitch.checked)
    }

    Timer {
        interval: 150
        running: page.controller.scanning
        onTriggered: page._scanShown = true
    }

    Connections {
        target: page.controller
        function onNotice(message) { page.notice(message) }
        function onScanChanged() { if (!page.controller.scanning) page._scanShown = false }
        // Once every file is done the password is no longer needed on screen. After a failure or
        // Stop it stays, so the remaining files can run without typing it again; after a failed
        // decrypt it is selected, since a wrong password is the usual cause.
        function onOperationFinished(elapsed, total, succeeded, failed, skipped) {
            if (succeeded + skipped === total) {
                passwordField.text = ""
                confirmField.text = ""
            } else if (failed > 0 && !page.encrypting && page.visible) {
                passwordField.selectInput()
            }
        }
    }

    FileDialog {
        id: filePicker
        title: page.encrypting ? "Choose files to encrypt" : "Choose encrypted files to decrypt"
        fileMode: FileDialog.OpenFiles
        nameFilters: page.encrypting
            ? ["All files (*)"]
            : ["gfgLock encrypted files (" + page._encryptedExts.map(ext => "*" + ext).join(" ") + ")", "All files (*)"]
        onAccepted: page.controller.addFiles(selectedFiles)
    }

    FolderDialog {
        id: folderPicker
        title: page.encrypting ? "Encrypt every file in a folder (including subfolders)"
                               : "Decrypt every gfgLock file in a folder (including subfolders)"
        onAccepted: page.controller.addFolder(selectedFolder.toString())
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            handle: Rectangle {
                implicitWidth: 5
                color: SplitHandle.pressed || SplitHandle.hovered ? Theme.accentSoft : Theme.background
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 1
                    height: parent.height
                    color: Theme.border
                }
            }

            // ── File list ─────────────────────────────────────────────────
            Rectangle {
                SplitView.preferredWidth: 420
                SplitView.minimumWidth: 300
                SplitView.fillWidth: true
                color: Theme.surface

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.margins: Theme.spaceLg
                        Layout.bottomMargin: Theme.spaceSm
                        spacing: Theme.spaceSm

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "Files"
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontTitle
                                font.weight: Font.DemiBold
                                color: Theme.text
                                Accessible.role: Accessible.Heading
                                Accessible.name: text
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: page.queue.count === 0 ? ""
                                    : page.queue.count + (page.queue.count === 1 ? " file" : " files") + "  ·  " + page.queue.totalSize
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textMuted
                            }
                        }

                        // The empty list shows its own Add buttons.
                        RowLayout {
                            Layout.fillWidth: true
                            visible: page.queue.count > 0 || page._scanShown
                            spacing: Theme.spaceSm

                            AppButton {
                                kind: "primary"
                                text: "Add files"
                                iconName: "add"
                                toolTipText: page._addFilesTip
                                onClicked: filePicker.open()
                            }
                            AppButton {
                                text: "Add folder"
                                iconName: "folder"
                                toolTipText: page._addFolderTip
                                onClicked: folderPicker.open()
                            }
                            Item { Layout.fillWidth: true }
                            AppButton {
                                id: listMenuButton
                                kind: "ghost"
                                iconName: "more"
                                toolTipText: "More list actions"
                                enabled: page.queue.count > 0
                                onClicked: listMenu.popup(listMenuButton, 0, listMenuButton.height)

                                Menu {
                                    id: listMenu
                                    MenuItem {
                                        text: "Select all"
                                        onTriggered: page.queue.selectAll()
                                    }
                                    MenuItem {
                                        text: "Remove selected"
                                        enabled: !page.controller.busy && page.queue.selectedCount > 0
                                        onTriggered: page.queue.removeSelected()
                                    }
                                    MenuItem {
                                        text: "Remove finished files"
                                        enabled: !page.controller.busy && page.queue.finishedCount > 0
                                        onTriggered: page.queue.removeFinished()
                                    }
                                    MenuSeparator {}
                                    MenuItem {
                                        text: "Clear the list"
                                        enabled: !page.controller.busy
                                        onTriggered: page.controller.clearFiles()
                                    }
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

                    FileList {
                        id: fileList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        fileModel: page.queue
                        scanning: page._scanShown
                        scanFound: page.controller.scanFound
                        busy: page.controller.busy
                        emptyIcon: page.encrypting ? "lock" : "unlock"
                        addFilesTip: page._addFilesTip
                        addFolderTip: page._addFolderTip
                        emptyTitle: page.encrypting ? "Add files to encrypt" : "Add files to decrypt"
                        emptyText: page.encrypting
                            ? "Drop files or whole folders here. Files that are already encrypted are left out."
                            : "Drop " + page._encryptedList + " files, or folders containing them, here."
                        // What a run does to the files is said once, in the box beside the list.
                        firstRunSteps: page.encrypting
                            ? ["Add the files or folders to protect.",
                               "Choose a password and type it twice.",
                               "Press Encrypt or Ctrl+Enter."]
                            : ["Add the encrypted files or a folder that contains them.",
                               "Enter their password.",
                               "Press Decrypt or Ctrl+Enter."]
                        // Focus moves to the password once there is something to work on, unless
                        // it is on the list, where the next key belongs to the list.
                        onFilled: focused => {
                            if (!focused && passwordField.text.length === 0 && page.visible) passwordField.forceInputFocus()
                        }
                        onAddFilesRequested: filePicker.open()
                        onAddFolderRequested: folderPicker.open()
                        onStopScanRequested: page.controller.cancelScan()
                        onClearRequested: page.controller.clearFiles()
                        onShowInFolderRequested: row => page.controller.showInFolder(row)
                        onCopyNamesRequested: page.controller.copySelectedNames()
                        onCopyPathsRequested: page.controller.copySelectedPaths()
                    }
                }
            }

            // ── Password and options ──────────────────────────────────────
            ScrollView {
                id: settingsPane
                SplitView.preferredWidth: 400
                SplitView.minimumWidth: 320
                contentWidth: availableWidth
                contentHeight: settingsColumn.implicitHeight + 2 * Theme.spaceLg
                clip: true

                ColumnLayout {
                    id: settingsColumn
                    x: Theme.spaceXl
                    y: Theme.spaceLg
                    width: settingsPane.availableWidth - 2 * Theme.spaceXl
                    spacing: Theme.spaceLg
                    enabled: !page.controller.busy

                    Card {
                        Layout.fillWidth: true
                        title: "Password"
                        iconName: "key"
                        description: page.encrypting
                            ? "If you lose it, nobody can open the files."
                            : "Use the password the files were encrypted with."

                        PasswordField {
                            id: passwordField
                            Layout.fillWidth: true
                            label: "Password"
                            showStrength: page.encrypting
                            helpText: page.encrypting && passwordField.strength > 0 && passwordField.strength <= 2
                                ? "Longer is stronger: try 12 or more characters, or a few unrelated words." : ""
                            onAccepted: page.encrypting ? confirmField.forceInputFocus() : page.start()
                        }
                        PasswordField {
                            id: confirmField
                            Layout.fillWidth: true
                            visible: page.encrypting
                            label: "Confirm password"
                            errorText: page._mismatch ? "The two passwords don't match." : ""
                            onAccepted: page.start()
                            onEditingFinished: page._confirmFinished = confirmField.text.length > 0
                            onTextChanged: if (confirmField.text.length === 0) page._confirmFinished = false
                        }
                    }

                    // The tab keeps its own choices: each change is saved for next time.
                    Card {
                        Layout.fillWidth: true
                        visible: page.encrypting
                        title: "Options"
                        iconName: "settings"

                        FormRow {
                            label: "Hide file names"
                            hint: "The original names come back when you decrypt."
                            Item { Layout.fillWidth: true }
                            AppSwitch {
                                id: encryptNamesSwitch
                                checked: page._hideNamesSaved
                                accessibleName: "Hide file names"
                                toolTipText: "Kept for next time"
                                onToggled: page._rememberOptions()
                            }
                        }
                        FormRow {
                            label: "Encryption method"
                            hint: page._method ? page._method.hint : ""
                            StyledComboBox {
                                id: algorithmCombo
                                Layout.fillWidth: true
                                model: prefsController.algorithmOptions
                                value: prefsController.encMode
                                accessibleName: "Encryption method"
                                toolTipText: "Decrypting picks the right method automatically. Kept for next time."
                                onActivated: page._rememberOptions()
                            }
                        }
                    }

                    // What will happen to the files, said before anything changes.
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: whatHappens.implicitHeight + 2 * Theme.spaceMd
                        radius: Theme.radius
                        color: Theme.accentSoft

                        RowLayout {
                            id: whatHappens
                            anchors.fill: parent
                            anchors.margins: Theme.spaceMd
                            spacing: Theme.spaceSm
                            Icon {
                                Layout.alignment: Qt.AlignTop
                                name: "info"
                                size: Theme.iconMd
                                color: Theme.accent
                            }
                            Text {
                                Layout.fillWidth: true
                                readonly property string ext: page._method ? page._method.ext : ""
                                text: page.encrypting
                                    ? "Each file is replaced by an encrypted copy in the same folder: report.docx becomes "
                                      + (encryptNamesSwitch.checked ? "a randomly named " + ext + " file." : "report.docx" + ext + ".")
                                    : "Each file is restored next to itself under its original name, and the encrypted copy is removed. With a wrong password nothing changes. An older .gfglck file may be kept; its row says why."
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontCaption
                                color: Theme.text
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }

        RunBar {
            id: runBar
            Layout.fillWidth: true
            controller: page.controller
            blocker: page.blocker
            scanning: page._scanShown
            startText: page.encrypting ? "Encrypt" : "Decrypt"
            startIcon: page.encrypting ? "lock" : "unlock"
            onStartRequested: page.start()
        }
    }
}
