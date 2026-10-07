// qmllint disable unqualified
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"

AppWindow {
    id: mainWin

    width: 1000
    height: 720
    minimumWidth: 720
    minimumHeight: 520
    visible: true
    title: appController.appName + " " + appController.appVersion

    property var _prefsWindow: null
    // Set once the user chose to close during a run; the window closes when both tabs are idle.
    property bool _closeWhenIdle: false
    readonly property bool _anyBusy: encryptController.busy || decryptController.busy

    // Both tabs, in order. Shortcuts (Ctrl+1, Ctrl+2) and the About text derive from this list.
    readonly property var tasks: [
        { key: "encrypt", label: "Encrypt", icon: "lock", controller: encryptController },
        { key: "decrypt", label: "Decrypt", icon: "unlock", controller: decryptController }
    ]
    readonly property var currentPage: pages.children[tabs.currentIndex]
    readonly property var currentController: mainWin.tasks[tabs.currentIndex].controller

    // quitOnLastWindowClosed is disabled app-wide (see app.py) since it can misfire while a
    // QML window is still open, so closing the main window quits explicitly. During a run it asks
    // first, then lets the files in progress finish so none is left half written.
    onClosing: function(close) {
        if (mainWin._anyBusy) {
            close.accepted = false
            if (!mainWin._closeWhenIdle) closeDialog.open()
            return
        }
        Qt.quit()
    }
    on_AnyBusyChanged: if (!mainWin._anyBusy && mainWin._closeWhenIdle) Qt.quit()

    titleActions: [
        AppButton {
            kind: "ghost"
            compact: true
            text: "Preferences"
            iconName: "settings"
            toolTipText: "Default settings, appearance, speed, and logs (Ctrl+,)"
            focusPolicy: Qt.TabFocus
            onClicked: mainWin.openPreferences()
        },
        AppButton {
            kind: "ghost"
            compact: true
            iconName: "info"
            toolTipText: "About " + appController.appName + " (F1)"
            focusPolicy: Qt.TabFocus
            onClicked: aboutDialog.open()
        }
    ]

    function openPreferences() {
        if (!mainWin._prefsWindow) {
            var comp = Qt.createComponent("PreferencesWindow.qml")
            if (comp.status !== Component.Ready) { console.error(comp.errorString()); return }
            mainWin._prefsWindow = comp.createObject(mainWin)
            mainWin._prefsWindow.closing.connect(function() { mainWin._prefsWindow = null })
        }
        mainWin._prefsWindow.show()
        mainWin._prefsWindow.raise()
        mainWin._prefsWindow.requestActivate()
    }

    function bringToFront() {
        if (mainWin.visibility === Window.Minimized) mainWin.showNormal()
        mainWin.raise()
        mainWin.requestActivate()
    }

    function tabIndex(key) {
        return mainWin.tasks.findIndex(t => t.key === key)
    }

    // Sends each dropped or opened item to the tab it belongs on: encrypted files to Decrypt,
    // other files to Encrypt, folders to the tab in view (or the given one). Switches to the tab
    // that received files when only one did.
    function receive(urls, preferredKey) {
        var encrypted = [], plain = [], folders = []
        for (var i = 0; i < urls.length; i++) {
            var url = urls[i].toString()
            if (appController.isFolder(url)) folders.push(url)
            else if (/\.(gfglock|gfglck|gfgcha)$/i.test(url)) encrypted.push(url)
            else plain.push(url)
        }
        var folderKey = preferredKey || mainWin.tasks[tabs.currentIndex].key
        if (folderKey === "decrypt") encrypted = encrypted.concat(folders)
        else plain = plain.concat(folders)
        if (plain.length > 0) encryptController.addFiles(plain)
        if (encrypted.length > 0) decryptController.addFiles(encrypted)
        if (plain.length > 0 && encrypted.length === 0) tabs.currentIndex = mainWin.tabIndex("encrypt")
        else if (encrypted.length > 0 && plain.length === 0) tabs.currentIndex = mainWin.tabIndex("decrypt")
        else if (plain.length > 0 && encrypted.length > 0)
            toast.show("Encrypted files went to the Decrypt tab; the rest to the Encrypt tab.")
    }

    Connections {
        target: appController
        function onFilesOpened(mode, paths) {
            tabs.currentIndex = Math.max(0, mainWin.tabIndex(mode))
            mainWin.receive(paths, mode)
            mainWin.bringToFront()
        }
        function onActivateRequested() { mainWin.bringToFront() }
    }

    // ── Keyboard shortcuts ─────────────────────────────────────────────────

    Shortcut { sequences: [StandardKey.Open]; onActivated: mainWin.currentPage.openFiles() }
    Shortcut { sequence: "Ctrl+Shift+O"; onActivated: mainWin.currentPage.openFolder() }
    Shortcut { sequences: ["Ctrl+Return", "Ctrl+Enter", "F5"]; onActivated: mainWin.currentPage.start() }
    // Esc stops the run, or else the folder scan, of the tab in view.
    Shortcut {
        sequence: "Escape"
        enabled: mainWin.currentController.busy || mainWin.currentController.scanning
        onActivated: mainWin.currentController.busy ? mainWin.currentController.cancel()
                                                    : mainWin.currentController.cancelScan()
    }
    Shortcut { sequence: "Ctrl+,"; onActivated: mainWin.openPreferences() }
    Shortcut { sequence: "F1"; onActivated: aboutDialog.open() }
    Shortcut { sequence: "Ctrl+1"; onActivated: tabs.currentIndex = 0 }
    Shortcut { sequence: "Ctrl+2"; onActivated: tabs.currentIndex = 1 }

    // ── Layout ─────────────────────────────────────────────────────────────

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TabBar {
            id: tabs
            Layout.fillWidth: true
            Layout.leftMargin: Theme.spaceLg
            Layout.topMargin: Theme.spaceSm
            background: Item {}

            Repeater {
                model: mainWin.tasks
                delegate: TabButton {
                    id: tabButton
                    required property var modelData
                    required property int index
                    width: implicitWidth + 28
                    font.pixelSize: Theme.fontBody
                    Accessible.name: modelData.label + (modelData.controller.busy ? ", running" : "")
                    ToolTip.visible: hovered
                    ToolTip.text: modelData.label + " (Ctrl+" + (index + 1) + ")"
                    ToolTip.delay: 600

                    contentItem: RowLayout {
                        spacing: Theme.spaceSm
                        Icon {
                            name: tabButton.modelData.icon
                            size: 14
                            color: tabButton.checked ? Theme.accent : Theme.textMuted
                        }
                        Text {
                            text: tabButton.modelData.label
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontBody
                            font.weight: tabButton.checked ? Font.DemiBold : Font.Normal
                            color: tabButton.checked ? Theme.text : Theme.textMuted
                        }
                        BusyIndicator {
                            visible: tabButton.modelData.controller.busy
                            running: visible
                            Layout.preferredWidth: 14
                            Layout.preferredHeight: 14
                            padding: 0
                            Accessible.ignored: true
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }

        StackLayout {
            id: pages
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabs.currentIndex

            LockPage {
                controller: encryptController
                onNotice: message => toast.show(message)
            }
            LockPage {
                controller: decryptController
                onNotice: message => toast.show(message)
            }
        }
    }

    // Drops anywhere in the window; each file goes to the tab it belongs on.
    DropArea {
        id: dropArea
        anchors.fill: parent
        onDropped: function(drop) {
            if (!drop.hasUrls) return
            mainWin.receive(drop.urls, "")
            drop.acceptProposedAction()
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.spaceSm
            radius: Theme.radiusLarge
            color: Theme.dropFill
            border.color: Theme.accent
            border.width: 2
            visible: dropArea.containsDrag

            Text {
                anchors.centerIn: parent
                width: parent.width - 2 * Theme.spaceXl
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "Drop to add. Encrypted files go to Decrypt, everything else to Encrypt."
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.DemiBold
                color: Theme.accent
            }
        }
    }

    Toast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 88
        z: 50
    }

    // ── Close during a run ─────────────────────────────────────────────────

    AppDialog {
        id: closeDialog
        title: "Stop and close?"
        width: Math.min(440, mainWin.width - 48)
        standardButtons: Dialog.Yes | Dialog.No
        Component.onCompleted: {
            closeDialog.standardButton(Dialog.Yes).text = "Stop and close"
            closeDialog.standardButton(Dialog.No).text = "Keep working"
        }
        onAccepted: {
            mainWin._closeWhenIdle = true
            encryptController.cancel()
            decryptController.cancel()
        }

        Text {
            width: parent.width
            text: "Files being worked on now are finished first, then gfgLock closes. Files not started yet stay as they are."
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: Theme.text
        }
    }

    // ── About ──────────────────────────────────────────────────────────────

    AppDialog {
        id: aboutDialog
        title: "About " + appController.appName
        width: Math.min(480, mainWin.width - 48)
        standardButtons: Dialog.Close

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.spaceMd

            RowLayout {
                spacing: Theme.spaceLg
                Image {
                    source: "../assets/icons/Square44x44Logo.targetsize-48.png"
                    Layout.preferredWidth: 48
                    Layout.preferredHeight: 48
                    fillMode: Image.PreserveAspectFit
                    Accessible.ignored: true
                }
                ColumnLayout {
                    spacing: 2
                    Text {
                        text: appController.appName + " " + appController.appVersion
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.text
                    }
                    Text {
                        text: "By " + appController.appAuthor
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                text: appController.appDescription + ". Everything runs on this computer; your files and password never leave it."
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBody
                color: Theme.text
                wrapMode: Text.WordWrap
            }
            Text {
                Layout.fillWidth: true
                text: "Shortcuts: Ctrl+O add files, Ctrl+Shift+O add folder, Ctrl+Enter or F5 start, Esc stop, "
                    + "Ctrl+, preferences, F1 about, Ctrl+1 Encrypt, Ctrl+2 Decrypt. In the list: Ctrl+A select all, "
                    + "Space select, Ctrl+C copy names, Delete remove, Shift+F10 or Menu key for more."
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
                wrapMode: Text.WordWrap
            }
            AppButton {
                text: "Check for updates"
                iconName: "openExternal"
                toolTipText: "Open the gfgLock releases page in your browser"
                onClicked: appController.openUpdates()
            }
        }
    }
}
