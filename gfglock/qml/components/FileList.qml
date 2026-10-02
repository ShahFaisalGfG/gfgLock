pragma ComponentBehavior: Bound
// qmllint disable unqualified import
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Item {
    id: fileListRoot

    // "encrypt" or "decrypt": which files a folder add keeps, shown in the empty state.
    property string mode: "encrypt"
    property int _anchor: -1
    property int _cursor: -1

    function handleClick(idx, mods) {
        try {
            if (mods & Qt.ShiftModifier) {
                if (_anchor < 0) _anchor = idx
                encryptController.fileModel.selectRange(_anchor, idx)
                _cursor = idx
            } else if (mods & Qt.ControlModifier) {
                encryptController.fileModel.toggleSelection(idx)
                _anchor = idx
                _cursor = idx
            } else {
                encryptController.fileModel.setSingle(idx)
                _anchor = idx
                _cursor = idx
            }
            listView.forceActiveFocus()
        } catch(e) {}
    }

    function openContextMenu(idx) {
        if (idx < 0) return
        _cursor = idx
        contextMenu.popup()
    }

    // One context menu shared by every row (a Menu per row made long lists slow to scroll).
    Menu {
        id: contextMenu
        MenuItem {
            text:           encryptController.fileModel.selectedCount > 1 ? "Copy file names" : "Copy file name"
            height:         32
            font.pixelSize: 12
            onTriggered: encryptController.copySelectedNames()
        }
        MenuItem {
            text:           encryptController.fileModel.selectedCount > 1 ? "Copy full paths" : "Copy full path"
            height:         32
            font.pixelSize: 12
            onTriggered: encryptController.copySelectedPaths()
        }
        MenuItem {
            text:           encryptController.fileModel.selectedCount > 1
                                ? "Remove " + encryptController.fileModel.selectedCount + " selected from list"
                                : "Remove from list"
            height:         32
            font.pixelSize: 12
            onTriggered: encryptController.fileModel.removeSelected()
        }
    }

    // Background folder scan indicator, with a way to stop a scan of a huge folder.
    // Laid out as the first row above the list (same 5 px inset and radius as the file rows), so
    // it never covers a row; every child is sized to fit inside its 40 px height.
    Rectangle {
        id: scanBanner
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 5
        height: 40
        visible: encryptController.scanning
        radius: 6
        color: Material.theme === Material.Dark ? "#16304d" : "#e3f2fd"
        border.color: "#0078d4"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 6
            spacing: 10

            BusyIndicator {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                padding: 0
                running: encryptController.scanning
            }
            Text {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                text: "Scanning folder... " + encryptController.scanFound.toLocaleString(Qt.locale(), "f", 0) + " files found"
                font.pixelSize: 12
                color: Material.foreground
                elide: Text.ElideRight
            }
            Button {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredHeight: 30
                topInset: 0
                bottomInset: 0
                text: "Stop"
                flat: true
                font.pixelSize: 11
                onClicked: encryptController.cancelScan()
                Accessible.name: "Stop scanning"
                ToolTip.visible: hovered
                ToolTip.text: "Stop scanning; files found so far stay in the list"
                ToolTip.delay: 600
            }
        }
    }

    // Empty-state placeholder
    Rectangle {
        anchors.centerIn: parent
        width:  Math.min(parent.width * 0.78, 340)
        height: 130
        radius: 12
        visible: encryptController.fileModel.count === 0 && !encryptController.scanning
        color:        Material.theme === Material.Dark ? "#1c1c1c" : "#f8f8f8"
        border.color: Material.theme === Material.Dark ? "#3a3a3a" : "#cccccc"
        border.width: 1

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 6

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "📂"
                font.pixelSize: 34
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "Drop files or folders here, or click + Files"
                color: Material.theme === Material.Dark ? "#777777" : "#888888"
                font.pixelSize: 13
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: fileListRoot.mode === "decrypt"
                    ? "Only .gfglock, .gfglck, and .gfgcha files are added"
                    : "Any file type; files that are already encrypted are skipped"
                color: Material.theme === Material.Dark ? "#444444" : "#aaaaaa"
                font.pixelSize: 11
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: fileListRoot.emptyPanelClicked()
        }
    }

    signal emptyPanelClicked()

    // Scrollable file list
    ScrollView {
        anchors.fill: parent
        anchors.topMargin: scanBanner.visible ? scanBanner.height + scanBanner.anchors.margins : 0
        clip: true
        visible: encryptController.fileModel.count > 0
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        ListView {
            id: listView
            model: encryptController.fileModel
            spacing: 5
            topMargin: 5
            bottomMargin: 5
            leftMargin: 5
            rightMargin: 5
            clip: true
            focus: true
            reuseItems: true
            cacheBuffer: 800

            delegate: FileItem {
                width: ListView.view.width - 10
                onItemClicked: function(idx, mods) { fileListRoot.handleClick(idx, mods) }
                onContextMenuRequested: function(idx) { fileListRoot.openContextMenu(idx) }
            }

            displaced: Transition {
                NumberAnimation { properties: "x,y"; easing.type: Easing.OutQuad; duration: 120 }
            }

            Keys.onPressed: function(event) {
                var count = encryptController.fileModel.count
                if (count === 0) { event.accepted = false; return }

                if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
                    encryptController.fileModel.selectAll()
                    fileListRoot._anchor = 0
                    fileListRoot._cursor = count - 1
                    event.accepted = true
                } else if (event.key === Qt.Key_C && (event.modifiers & Qt.ControlModifier)) {
                    encryptController.copySelectedNames()
                    event.accepted = true
                } else if (event.key === Qt.Key_Space && fileListRoot._cursor >= 0) {
                    encryptController.fileModel.toggleSelection(fileListRoot._cursor)
                    event.accepted = true
                } else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
                    fileListRoot.openContextMenu(Math.max(0, fileListRoot._cursor))
                    event.accepted = true
                } else if (event.key === Qt.Key_Delete) {
                    encryptController.fileModel.removeSelected()
                    fileListRoot._anchor = -1
                    fileListRoot._cursor = -1
                    event.accepted = true
                } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                    var isDown  = event.key === Qt.Key_Down
                    var isShift = !!(event.modifiers & Qt.ShiftModifier)
                    var cur     = fileListRoot._cursor

                    if (cur < 0) {
                        cur = isDown ? 0 : count - 1
                    } else {
                        cur = isDown ? Math.min(count - 1, cur + 1) : Math.max(0, cur - 1)
                    }

                    if (isShift) {
                        if (fileListRoot._anchor < 0)
                            fileListRoot._anchor = fileListRoot._cursor < 0 ? cur : fileListRoot._cursor
                        fileListRoot._cursor = cur
                        encryptController.fileModel.selectRange(fileListRoot._anchor, cur)
                    } else {
                        fileListRoot._anchor = cur
                        fileListRoot._cursor = cur
                        encryptController.fileModel.setSingle(cur)
                    }
                    positionViewAtIndex(cur, ListView.Contain)
                    event.accepted = true
                }
            }
        }
    }

    // Drag-and-drop overlay
    DropArea {
        anchors.fill: parent
        onDropped: function(drop) {
            if (drop.hasUrls) {
                var urls = []
                for (var i = 0; i < drop.urls.length; i++)
                    urls.push(drop.urls[i].toString())
                encryptController.addFiles(urls)
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: 8
            color: Qt.rgba(0, 0.47, 0.83, 0.08)
            border.color: "#0078d4"
            border.width: 2
            visible: parent.containsDrag
        }
    }
}
