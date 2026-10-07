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
    // The saved defaults. Read through these properties, which only signal a real change, so
    // saving unrelated preferences doesn't undo a choice made on this tab.
    readonly property bool _hideNamesDefault: prefsController.encFilenames
    readonly property string _addFilesTip: (page.encrypting ? "Choose files to encrypt" : "Choose encrypted files to decrypt") + " (Ctrl+O)"
    readonly property string _addFolderTip: (page.encrypting ? "Add every file in a folder and its subfolders"
                                                             : "Add every encrypted file in a folder and its subfolders")
        + " (Ctrl+Shift+O)"
    readonly property var _extensions: ({ aes256_gcm: ".gfglock", chacha20_poly1305: ".gfgcha", aes256_cfb: ".gfglck" })

    signal notice(string message)

    function openFiles() { filePicker.open() }
    function openFolder() { folderPicker.open() }

    function start() {
        if (page.blocker.length > 0 || page.controller.busy) return
        page.controller.start(passwordField.text, encryptNamesSwitch.checked, algorithmCombo.currentValue || "")
    }

    // Says what is still missing before Start, or "" when the tab is ready.
    function _blocker() {
        var verb = page.encrypting ? "encrypt" : "decrypt"
        if (page.controller.scanning) return "Wait for the folder scan to finish, or stop it."
        if (page.queue.count === 0)
            return page.encrypting ? "Add the files or folders you want to encrypt." : "Add the encrypted files you want to decrypt."
        if (page.queue.runnableCount === 0)
            return "Every file in the list is finished. Add more files, or remove the finished ones."
        if (passwordField.text.length === 0) return "Enter the password to " + verb + " with."
        if (page.encrypting && confirmField.text.length === 0) return "Type the password again to confirm it."
        if (page.encrypting && confirmField.text !== passwordField.text) return "The two passwords don't match."
        return ""
    }

    Connections {
        target: page.controller
        function onNotice(message) { page.notice(message) }
        // Once every file is done the password is no longer needed on screen. After a failure or
        // Stop it stays, so the remaining files can run without typing it again.
        function onOperationFinished(elapsed, total, succeeded, failed, skipped) {
            if (succeeded + skipped === total) {
                passwordField.text = ""
                confirmField.text = ""
            }
        }
    }

    // Moves focus to the password as soon as there is something to work on.
    Connections {
        target: page.queue
        function onCountChanged(count) {
            if (count > 0 && passwordField.text.length === 0 && page.visible) passwordField.forceInputFocus()
        }
    }

    FileDialog {
        id: filePicker
        title: page.encrypting ? "Choose files to encrypt" : "Choose encrypted files to decrypt"
        fileMode: FileDialog.OpenFiles
        nameFilters: page.encrypting
            ? ["All files (*)"]
            : ["gfgLock encrypted files (*.gfglock *.gfglck *.gfgcha)", "All files (*)"]
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

                        RowLayout {
                            Layout.fillWidth: true
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
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        fileModel: page.queue
                        scanning: page.controller.scanning
                        scanFound: page.controller.scanFound
                        busy: page.controller.busy
                        emptyIcon: page.encrypting ? "lock" : "unlock"
                        addFilesTip: page._addFilesTip
                        addFolderTip: page._addFolderTip
                        emptyTitle: page.encrypting ? "Add files to encrypt" : "Add files to decrypt"
                        emptyText: page.encrypting
                            ? "Drop files or whole folders here. Files that are already encrypted are left out."
                            : "Drop .gfglock, .gfglck, or .gfgcha files, or folders containing them, here."
                        firstRunSteps: page.encrypting
                            ? ["Add the files or folders to protect.",
                               "Choose a password and type it twice.",
                               "Press Encrypt. Each file is replaced by an encrypted copy next to it."]
                            : ["Add the encrypted files or a folder that contains them.",
                               "Enter the password they were encrypted with.",
                               "Press Decrypt. Each file gets its original name back."]
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
                clip: true

                ColumnLayout {
                    width: settingsPane.availableWidth
                    spacing: Theme.spaceLg

                    Item { Layout.preferredHeight: Theme.spaceXs }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.spaceXl
                        Layout.rightMargin: Theme.spaceXl
                        spacing: Theme.spaceLg
                        enabled: !page.controller.busy

                        Card {
                            Layout.fillWidth: true
                            title: "Password"
                            iconName: "key"
                            description: page.encrypting
                                ? "Anyone with this password can open the files. Without it, nobody can, including you."
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
                                errorText: confirmField.text.length > 0 && confirmField.text !== passwordField.text
                                    ? "The two passwords don't match." : ""
                                onAccepted: page.start()
                            }
                        }

                        Card {
                            Layout.fillWidth: true
                            visible: page.encrypting
                            title: "Options"
                            iconName: "settings"

                            FormRow {
                                label: "Hide file names"
                                hint: "Encrypted files get random names; the original name comes back when you decrypt."
                                Item { Layout.fillWidth: true }
                                AppSwitch {
                                    id: encryptNamesSwitch
                                    checked: page._hideNamesDefault
                                    accessibleName: "Hide file names"
                                    toolTipText: "Also hide each file's name"
                                }
                            }
                            FormRow {
                                label: "Encryption method"
                                hint: algorithmCombo.currentIndex >= 0
                                    ? prefsController.algorithmOptions[algorithmCombo.currentIndex].hint : ""
                                StyledComboBox {
                                    id: algorithmCombo
                                    Layout.fillWidth: true
                                    model: prefsController.algorithmOptions
                                    value: prefsController.encMode
                                    accessibleName: "Encryption method"
                                    toolTipText: "Decrypting picks the right method automatically."
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
                                    size: 14
                                    color: Theme.accent
                                }
                                Text {
                                    Layout.fillWidth: true
                                    readonly property string ext: page._extensions[algorithmCombo.currentValue] || ".gfglock"
                                    text: page.encrypting
                                        ? "Each file is replaced by an encrypted copy in the same folder ("
                                          + (encryptNamesSwitch.checked ? "report.docx becomes a randomly named " + ext + " file"
                                                                        : "report.docx becomes report.docx" + ext)
                                          + "). Keep the password safe: it can't be recovered."
                                        : "Each file is restored next to itself under its original name, and the encrypted copy is removed. With a wrong password nothing changes."
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontCaption
                                    color: Theme.text
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }

                    Item { Layout.preferredHeight: Theme.spaceLg }
                }
            }
        }

        RunBar {
            Layout.fillWidth: true
            controller: page.controller
            blocker: page.blocker
            startText: page.encrypting ? "Encrypt" : "Decrypt"
            startIcon: page.encrypting ? "lock" : "unlock"
            onStartRequested: page.start()
        }
    }
}
