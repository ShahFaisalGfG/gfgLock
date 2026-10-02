// qmllint disable unqualified
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import QtQuick.Window
import "components"

ApplicationWindow {
    id: root

    width:       700
    height:      _collapsedHeight
    minimumWidth:  580
    minimumHeight: logHeader.expanded ? 420 : _collapsedHeight

    // Height of everything except the (collapsed) log, plus the 1 px window border.
    readonly property int _collapsedHeight: rootLayout.implicitHeight + 2
    property int _unseenLogEntries: 0
    visible: typeof cliLaunchMode === "undefined" || cliLaunchMode === ""
    title:   "gfgLock"
    flags:   Qt.FramelessWindowHint | Qt.Window
    font.family: "Segoe UI Emoji"

    Material.theme:  appController && appController.currentTheme === "dark" ? Material.Dark : Material.Light
    Material.accent: "#0078d4"

    Component.onCompleted: {
        x = Screen.virtualX + Math.round((Screen.desktopAvailableWidth  - width)  / 2)
        y = Screen.virtualY + Math.round((Screen.desktopAvailableHeight - height) / 2)
        if (typeof cliLaunchMode !== "undefined" && cliLaunchMode !== "")
            openEncryptDialog(cliLaunchMode)
    }

    // quitOnLastWindowClosed is disabled app-wide (see app.py) since it can
    // misfire while a QML window is still open, so closing the main window
    // must quit explicitly.
    onClosing: Qt.quit()

    // ── Background ──────────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        color:        Material.theme === Material.Dark ? "#1e1e1e" : "#f3f3f3"
        border.color: Material.theme === Material.Dark ? "#3c3c3c" : "#d0d0d0"
        border.width: 1
    }

    // ── Log bridge ───────────────────────────────────────────────────────────
    Connections {
        target: appController
        function onLogAppended(message) {
            logsArea.append(message)
            logsArea.cursorPosition = logsArea.length
            if (!logHeader.expanded) root._unseenLogEntries++
        }
        function onLogsCleared() {
            logsArea.clear()
            root._unseenLogEntries = 0
        }
    }

    Connections {
        target: prefsController
        function onSettingsChanged() {
            logsArea._wrapEnabled = prefsController.logTextWrap
        }
    }

    // ── Root layout ──────────────────────────────────────────────────────────
    // ── Keyboard shortcuts ───────────────────────────────────────────────────
    Shortcut { sequence: "Ctrl+E"; onActivated: root.openEncryptDialog("encrypt") }
    Shortcut { sequence: "Ctrl+D"; onActivated: root.openEncryptDialog("decrypt") }
    Shortcut { sequence: "Ctrl+,"; onActivated: root.openPreferences() }
    Shortcut { sequence: "Ctrl+L"; onActivated: logHeader.expanded = !logHeader.expanded }
    Shortcut { sequence: "F1"; onActivated: aboutDialog.open() }

    ColumnLayout {
        id: rootLayout
        anchors.fill: parent
        spacing: 0

        TitleBar {
            Layout.fillWidth: true
            window:      root
            title:       "gfgLock"
            showMaximize: true
        }

        // Header - icon + title + description
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 96
            color:  "transparent"

            RowLayout {
                anchors.fill:        parent
                anchors.leftMargin:  22
                anchors.rightMargin: 22
                spacing: 16

                Image {
                    Layout.preferredWidth:  52
                    Layout.preferredHeight: 52
                    source:   "../assets/icons/Square44x44Logo.targetsize-48.png"
                    fillMode: Image.PreserveAspectFit
                    smooth:   true

                    Accessible.role:   Accessible.Graphic
                    Accessible.name:   "gfgLock logo"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Text {
                        text:          "gfgLock"
                        font.pixelSize: 20
                        font.weight:    Font.Bold
                        color:          Material.foreground
                    }
                    Text {
                        text:          appController ? appController.appDescription : ""
                        font.pixelSize: 12
                        color:  Material.theme === Material.Dark ? "#aaaaaa" : "#666666"
                        elide:  Text.ElideRight
                        Layout.fillWidth: true
                    }
                }

                Rectangle {
                    Layout.alignment:    Qt.AlignRight | Qt.AlignBottom
                    Layout.bottomMargin: 4
                    radius:       9
                    implicitWidth:  vLabel.implicitWidth + 14
                    implicitHeight: 20
                    color:        Qt.rgba(0, 0.47, 0.83, 0.10)
                    border.color: "#0078d4"
                    border.width: 1

                    Text {
                        id: vLabel
                        anchors.centerIn: parent
                        text:          appController ? "v" + appController.appVersion : ""
                        font.pixelSize: 10
                        color:          "#0078d4"
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color:  Material.theme === Material.Dark ? "#3c3c3c" : "#e0e0e0"
        }

        // Action buttons
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 68
            color:  "transparent"

            RowLayout {
                anchors.fill:        parent
                anchors.leftMargin:  28
                anchors.rightMargin: 28
                spacing: 10

                Button {
                    text:      "🔒  Encrypt"
                    highlighted: true
                    Material.accent: "#0078d4"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    font.pixelSize: 13
                    onClicked: root.openEncryptDialog("encrypt")
                    Accessible.name: "Encrypt files"
                    Accessible.role: Accessible.Button
                    ToolTip.visible: hovered
                    ToolTip.text: "Protect files or folders with a password (Ctrl+E)"
                    ToolTip.delay: 500
                }
                Button {
                    text:      "🔓  Decrypt"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    font.pixelSize: 13
                    onClicked: root.openEncryptDialog("decrypt")
                    Accessible.name: "Decrypt files"
                    Accessible.role: Accessible.Button
                    ToolTip.visible: hovered
                    ToolTip.text: "Unlock .gfglock, .gfglck, or .gfgcha files with their password (Ctrl+D)"
                    ToolTip.delay: 500
                }
                Button {
                    text:      "⚙  Preferences"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    font.pixelSize: 13
                    onClicked: root.openPreferences()
                    Accessible.name: "Open Preferences"
                    Accessible.role: Accessible.Button
                    ToolTip.visible: hovered
                    ToolTip.text: "Theme, default algorithm, performance, and logging (Ctrl+,)"
                    ToolTip.delay: 500
                }
                Button {
                    text:      "ℹ  About"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    font.pixelSize: 13
                    onClicked: aboutDialog.open()
                    Accessible.name: "About gfgLock"
                    Accessible.role: Accessible.Button
                    ToolTip.visible: hovered
                    ToolTip.text: "Version information and updates (F1)"
                    ToolTip.delay: 500
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color:  Material.theme === Material.Dark ? "#3c3c3c" : "#e0e0e0"
        }

        // First-glance guidance: what the two main buttons do and that drag-and-drop works.
        Text {
            Layout.fillWidth:    true
            Layout.leftMargin:   28
            Layout.rightMargin:  28
            Layout.topMargin:    10
            text: "Choose Encrypt to lock files with a password, or Decrypt to open files ending in "
                + ".gfglock, .gfglck, or .gfgcha. You can also drag files or folders onto this window."
            font.pixelSize: 12
            wrapMode:       Text.WordWrap
            color: Material.theme === Material.Dark ? "#aaaaaa" : "#555555"
        }

        // Activity log, collapsed by default (Ctrl+L)
        CollapsibleHeader {
            id: logHeader
            Layout.fillWidth:    true
            Layout.leftMargin:   14
            Layout.rightMargin:  14
            Layout.topMargin:    8
            Layout.bottomMargin: 4
            title: "Activity log"
            badge: root._unseenLogEntries > 0 ? root._unseenLogEntries + " new" : ""
            onExpandedChanged: {
                if (expanded) {
                    root._unseenLogEntries = 0
                    if (root.height < 460) root.height = 460
                } else {
                    root.height = root._collapsedHeight
                }
            }
        }

        // Logs area
        ScrollView {
            visible:             logHeader.expanded
            Layout.fillWidth:    true
            Layout.fillHeight:   true
            Layout.leftMargin:   14
            Layout.rightMargin:  14
            Layout.bottomMargin: 4
            clip: true
            ScrollBar.horizontal.policy: logsArea._wrapEnabled ? ScrollBar.AlwaysOff : ScrollBar.AsNeeded

            TextArea {
                id: logsArea
                property bool _wrapEnabled: prefsController ? prefsController.logTextWrap : true
                readOnly:      true
                wrapMode:      _wrapEnabled ? TextEdit.WordWrap : TextEdit.NoWrap
                onWrapModeChanged: {
                    var saved = text
                    text = ""
                    text = saved
                    cursorPosition = length
                }
                ContextMenu.menu: Menu {
                    onAboutToShow: wrapLogsItem.checked = logsArea._wrapEnabled
                    MenuItem {
                        text:        qsTr("Copy")
                        enabled:     logsArea.selectedText !== ""
                        onTriggered: logsArea.copy()
                    }
                    MenuItem {
                        text:        qsTr("Select All")
                        onTriggered: logsArea.selectAll()
                    }
                    MenuSeparator {}
                    MenuItem {
                        id:          wrapLogsItem
                        text:        qsTr("Text Wrap")
                        checkable:   true
                        onTriggered: logsArea._wrapEnabled = checked
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
                    radius:       4
                    border.color: Material.theme === Material.Dark ? "#333333" : "#e0e0e0"
                    border.width: 1
                }

                Text {
                    anchors.top:        parent.top
                    anchors.left:       parent.left
                    anchors.topMargin:  8
                    anchors.leftMargin: 10
                    text:           "No activity yet…"
                    font.pixelSize: 11
                    font.family:    "Consolas, monospace"
                    color: Material.theme === Material.Dark ? "#555555" : "#aaaaaa"
                    visible: logsArea.text.length === 0
                }

                Accessible.name: "Activity log"
                Accessible.role: Accessible.StaticText

            }
        }

        // Clear log button - below logs area, right-aligned (mirrors Cancel/Close in EncryptDialog)
        RowLayout {
            visible:             logHeader.expanded
            Layout.alignment:    Qt.AlignRight
            Layout.rightMargin:  14
            Layout.bottomMargin: 6

            Button {
                text:           "🧹  Clear"
                font.pixelSize: 13
                Layout.preferredHeight: 48
                enabled:        logsArea.text.length > 0
                onClicked:      appController.clearLogs()
                Accessible.name: "Clear activity log"
                ToolTip.visible: hovered
                ToolTip.text: "Clear this log (your files are not affected)"
                ToolTip.delay: 500
            }
        }

        // Keeps the bottom edge in place if the window is enlarged while the log is collapsed.
        Item {
            visible: !logHeader.expanded
            Layout.fillHeight: true
        }

        // Resize grip
        Item {
            Layout.fillWidth: true
            implicitHeight: 14

            DragHandler {
                target: null
                onActiveChanged: if (active) root.startSystemResize(Qt.BottomEdge | Qt.RightEdge)
            }

            Row {
                anchors.right:        parent.right
                anchors.bottom:       parent.bottom
                anchors.rightMargin:  5
                anchors.bottomMargin: 3
                spacing: 2

                Repeater {
                    model: 3
                    Rectangle {
                        width: 3; height: 3; radius: 1
                        color: Material.theme === Material.Dark ? "#555555" : "#bbbbbb"
                    }
                }
            }
        }
    }

    // ── Main window drop area ────────────────────────────────────────────────
    DropArea {
        anchors.fill: parent
        z: -1

        onDropped: function(drop) {
            if (!drop.hasUrls) return
            try {
                if (!root._encDlgComp || root._encDlgComp.status === Component.Error)
                    root._encDlgComp = Qt.createComponent("EncryptDialog.qml")
                if (root._encDlgComp.status !== Component.Ready) return
                var urls = []
                var allEncrypted = drop.urls.length > 0
                for (var i = 0; i < drop.urls.length; i++) {
                    var url = drop.urls[i].toString()
                    urls.push(url)
                    if (!/\.(gfglock|gfglck|gfgcha)$/i.test(url)) allEncrypted = false
                }
                // Dropping only encrypted files opens Decrypt; anything else opens Encrypt.
                root._encDlgComp.createObject(root, { operationMode: allEncrypted ? "decrypt" : "encrypt" }).show()
                encryptController.addFiles(urls)
            } catch(e) {
                console.error("onDropped:", e)
            }
        }

        Rectangle {
            anchors.fill: parent
            visible:      parent.containsDrag
            color:        Qt.rgba(0, 0.47, 0.83, 0.06)
            border.color: "#0078d4"
            border.width: 2
            radius:       0
        }
    }

    ResizeHandles {
        window: root
    }

    // ── About dialog ─────────────────────────────────────────────────────────
    Dialog {
        id: aboutDialog
        title:           "About gfgLock"
        modal:           false
        standardButtons: Dialog.NoButton
        anchors.centerIn: parent
        width:            460
        topPadding:       20
        bottomPadding:    24
        leftPadding:      28
        rightPadding:     28
        Material.accent: "#0078d4"

        contentItem: ColumnLayout {
            spacing: 14

            Image {
                Layout.alignment:       Qt.AlignHCenter
                Layout.preferredWidth:  64
                Layout.preferredHeight: 64
                source:      "../assets/icons/Square71x71Logo.scale-100.png"
                sourceSize:  Qt.size(64, 64)
                fillMode:    Image.PreserveAspectFit
                smooth:      true
            }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text:          "gfgLock"
                font.pixelSize: 18
                font.weight:    Font.Bold
                color:          Material.foreground
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: appController
                    ? "v" + appController.appVersion + "  ·  " + appController.appAuthor
                    : ""
                font.pixelSize: 12
                color: Material.theme === Material.Dark ? "#aaaaaa" : "#666666"
            }
            Text {
                Layout.fillWidth: true
                text:             appController ? appController.appDescription : ""
                font.pixelSize:   12
                wrapMode:         Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                color:            Material.foreground
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color:  Material.theme === Material.Dark ? "#333333" : "#e0e0e0"
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 12

                Button {
                    text:                   "Check for Updates"
                    flat:                   true
                    font.pixelSize:         12
                    Layout.preferredHeight: 36
                    Layout.preferredWidth:  150
                    onClicked: { if (appController) appController.openUpdates(); aboutDialog.close() }
                    Accessible.name: "Check for updates"
                }
                Button {
                    text:                   "Close"
                    highlighted:            true
                    font.pixelSize:         12
                    Layout.preferredHeight: 36
                    Layout.preferredWidth:  100
                    onClicked: aboutDialog.close()
                    Accessible.name: "Close about dialog"
                }
            }
        }
    }

    // ── Dialog component cache ───────────────────────────────────────────────
    property var _encDlgComp:  null
    property var _prefDlgComp: null

    function openEncryptDialog(mode) {
        try {
            if (!_encDlgComp || _encDlgComp.status === Component.Error)
                _encDlgComp = Qt.createComponent("EncryptDialog.qml")
            if (_encDlgComp.status === Component.Ready) {
                _encDlgComp.createObject(root, { operationMode: mode }).show()
            } else {
                console.error("EncryptDialog not ready:", _encDlgComp.errorString())
            }
        } catch(e) {
            console.error("openEncryptDialog:", e)
        }
    }

    function openPreferences() {
        try {
            if (!_prefDlgComp || _prefDlgComp.status === Component.Error)
                _prefDlgComp = Qt.createComponent("PreferencesWindow.qml")
            if (_prefDlgComp.status === Component.Ready) {
                _prefDlgComp.createObject(root).show()
            } else {
                console.error("PreferencesWindow not ready:", _prefDlgComp.errorString())
            }
        } catch(e) {
            console.error("openPreferences:", e)
        }
    }
}
