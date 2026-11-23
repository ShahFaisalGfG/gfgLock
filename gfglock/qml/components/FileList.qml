pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One tab's file list: a virtualized list (fast with thousands of rows), full keyboard
// support, one shared context menu, and an empty-state prompt. Drops are handled by the window,
// which sends each file to the tab it belongs on.
//
// Keys: Up/Down move, Shift+Up/Down extend, Space toggles, Enter opens a finished file, Ctrl+A
// selects all, Ctrl+C copies the names, Delete removes, Menu or Shift+F10 opens the context menu
// for the current row. Screen readers hear each row the keyboard moves to.
FocusScope {
    id: root

    required property var fileModel
    property bool scanning: false
    property int scanFound: 0
    property bool busy: false
    property string emptyTitle: ""
    property string emptyText: ""
    property string emptyIcon: "lock"
    property string addFilesTip: "Choose files (Ctrl+O)"
    property string addFolderTip: "Add every file in a folder and its subfolders (Ctrl+Shift+O)"
    // True when a finished row's result is a file to open (Decrypt); on the Encrypt tab, Enter and
    // double-click show the encrypted file in its folder instead.
    property bool opensFiles: true
    // What the empty list explains, one step per line, for this tab.
    property var firstRunSteps: []

    signal addFilesRequested()
    signal addFolderRequested()
    signal stopScanRequested()
    signal clearRequested()
    signal showInFolderRequested(int row)
    signal openRequested(int row)
    signal copyNamesRequested()
    signal copyPathsRequested()
    signal copyResultsRequested()
    // The empty list got its first files. `focused` is true when keyboard focus is on the list or
    // the scan banner's Stop button, which stay in view; the empty state's buttons hide.
    signal filled(bool focused)

    property int _anchor: -1

    function focusAddFiles() { addFilesButton.forceActiveFocus() }

    function _click(index, modifiers) {
        if (modifiers & Qt.ShiftModifier) {
            if (root._anchor < 0) root._anchor = index
            root.fileModel.selectRange(root._anchor, index)
        } else if (modifiers & Qt.ControlModifier) {
            root.fileModel.toggleSelection(index)
            root._anchor = index
        } else {
            root.fileModel.setSingle(index)
            root._anchor = index
        }
        listView.currentIndex = index
        listView.forceActiveFocus()
    }

    function _isFinished(index) {
        return root.fileModel.outputAt(index).length > 0
    }

    // Opens the row menu at the mouse pointer, or below the row when opened from the keyboard.
    function _openMenu(index, fromKeyboard) {
        if (index < 0) return
        var item = listView.itemAtIndex(index) as FileItem
        if (!item || !item.selected)
            root._click(index, Qt.NoModifier)
        contextMenu.row = index
        contextMenu.finished = root._isFinished(index)
        if (fromKeyboard && item) contextMenu.popup(item, Theme.spaceLg, item.height)
        else contextMenu.popup()
    }

    // Says the row the keyboard moved to, as a screen reader would read it.
    function _announce(index) {
        var item = listView.itemAtIndex(index) as FileItem
        if (item) item.Accessible.announce(item.name + ", " + item.statusText + (item.message ? ", " + item.message : ""))
    }

    // After rows are removed the anchor may point at another file, so a Shift+click range starts
    // afresh. Rows added at the end (a folder scan) keep it.
    property int _lastCount: 0
    Component.onCompleted: root._lastCount = root.fileModel.count
    Connections {
        target: root.fileModel
        function onCountChanged(count) {
            if (count < root._lastCount) root._anchor = -1
            else if (root._lastCount === 0 && count > 0) root.filled(listView.activeFocus || stopScanButton.activeFocus)
            root._lastCount = count
        }
        // Showing failed files only, or moving them first, puts other files at the anchor's row.
        function onFailedOnlyChanged() { root._anchor = -1 }
        function onModelReset() { root._anchor = -1 }
    }

    clip: true

    // Empty state: centered when it fits, otherwise from the top (small windows).
    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.max(Theme.spaceMd, (root.height - height) / 2)
        width: Math.min(parent.width - 2 * Theme.spaceXl, 340)
        spacing: Theme.spaceMd
        visible: root.fileModel.count === 0 && !root.scanning

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 64
            Layout.preferredHeight: 64
            radius: 32
            color: Theme.accentSoft
            Icon { anchors.centerIn: parent; name: root.emptyIcon; size: Theme.iconXl; color: Theme.accent }
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: root.emptyTitle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSubtitle
            font.weight: Font.DemiBold
            color: Theme.text
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.Heading
            Accessible.name: text
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: root.emptyText
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontBody
            color: Theme.textMuted
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: Theme.spaceSm
            AppButton {
                id: addFilesButton
                kind: "primary"
                text: "Add files"
                iconName: "add"
                toolTipText: root.addFilesTip
                onClicked: root.addFilesRequested()
            }
            AppButton {
                text: "Add folder"
                iconName: "folder"
                toolTipText: root.addFolderTip
                onClicked: root.addFolderRequested()
            }
        }

        // How a first run works, so nobody has to guess what comes after adding files.
        Column {
            id: firstRunSteps
            Layout.fillWidth: true
            Layout.topMargin: Theme.spaceSm
            // Only when there is room; the buttons above matter more in a small window.
            visible: root.height >= 400
            spacing: Theme.spaceXs
            Repeater {
                model: root.firstRunSteps
                delegate: Text {
                    textFormat: Text.PlainText
                    required property int index
                    required property string modelData
                    width: firstRunSteps.width
                    text: (index + 1) + ".  " + modelData
                    wrapMode: Text.WordWrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    color: Theme.textMuted
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Scan progress for large folders
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            visible: root.scanning
            color: Theme.accentSoft

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spaceMd
                anchors.rightMargin: Theme.spaceSm
                spacing: Theme.spaceSm

                BusyIndicator {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    padding: 0  // the style's default padding shrinks the spinner to a sliver at this size
                    running: root.scanning
                    Accessible.ignored: true
                }
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: "Scanning folder... " + root.scanFound.toLocaleString(Qt.locale(), "f", 0) + " files found"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    color: Theme.text
                    elide: Text.ElideRight
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                }
                AppButton {
                    id: stopScanButton
                    kind: "ghost"
                    compact: true
                    text: "Stop"
                    toolTipText: "Stop scanning; files found so far stay in the list"
                    onClicked: root.stopScanRequested()
                }
            }
        }

        // "Show failed only" is on: say so, with the way back.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            visible: root.fileModel.failedOnly
            color: Theme.dangerSoft

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.spaceMd
                anchors.rightMargin: Theme.spaceSm
                spacing: Theme.spaceSm

                Icon { name: "filter"; size: Theme.iconMd; color: Theme.danger }
                Text {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: "Showing the " + root.fileModel.failedCount + " failed of " + root.fileModel.count + " files"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontCaption
                    color: Theme.text
                    elide: Text.ElideRight
                    Accessible.role: Accessible.StaticText
                    Accessible.name: text
                }
                AppButton {
                    kind: "ghost"
                    compact: true
                    text: "Show all"
                    toolTipText: "Show every file in the list again"
                    onClicked: root.fileModel.setFailedOnly(false)
                }
            }
        }

        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.fileModel.count > 0
            model: root.fileModel
            clip: true
            focus: true
            spacing: 2
            topMargin: Theme.spaceXs
            bottomMargin: Theme.spaceXs
            leftMargin: Theme.spaceXs
            rightMargin: Theme.spaceXs
            reuseItems: true
            cacheBuffer: 600
            keyNavigationEnabled: false
            activeFocusOnTab: true
            highlightFollowsCurrentItem: false
            boundsBehavior: Flickable.StopAtBounds

            Accessible.role: Accessible.List
            Accessible.name: "File list, " + root.fileModel.count + (root.fileModel.count === 1 ? " file" : " files")

            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: FileItem {
                width: ListView.view.width - listView.leftMargin - listView.rightMargin
                current: ListView.isCurrentItem
                listHasFocus: listView.activeFocus
                listBusy: root.busy
                onClicked: (index, modifiers) => root._click(index, modifiers)
                onDoubleClicked: index => { if (root._isFinished(index)) root.openRequested(index) }
                onContextMenuRequested: index => root._openMenu(index)
                onRemoveRequested: index => root.fileModel.removeAt(index)
            }

            Keys.onPressed: function(event) {
                var count = listView.count
                if (count === 0) return
                var ctrl = event.modifiers & Qt.ControlModifier
                var shift = event.modifiers & Qt.ShiftModifier
                if (event.key === Qt.Key_A && ctrl) {
                    root.fileModel.selectAll()
                } else if (event.key === Qt.Key_C && ctrl) {
                    root.copyNamesRequested()
                } else if (event.key === Qt.Key_Delete && !root.busy) {
                    root.fileModel.removeSelected()
                    listView.currentIndex = Math.min(listView.currentIndex, listView.count - 1)
                } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !ctrl
                           && listView.currentIndex >= 0 && root._isFinished(listView.currentIndex)) {
                    root.openRequested(listView.currentIndex)
                } else if (event.key === Qt.Key_Space && listView.currentIndex >= 0) {
                    root.fileModel.toggleSelection(listView.currentIndex)
                } else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && shift)) {
                    root._openMenu(Math.max(0, listView.currentIndex), true)
                } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down
                           || event.key === Qt.Key_Home || event.key === Qt.Key_End) {
                    var cur = listView.currentIndex
                    if (event.key === Qt.Key_Home) cur = 0
                    else if (event.key === Qt.Key_End) cur = count - 1
                    else if (cur < 0) cur = 0
                    else cur = event.key === Qt.Key_Down ? Math.min(count - 1, cur + 1) : Math.max(0, cur - 1)
                    if (shift) {
                        if (root._anchor < 0) root._anchor = Math.max(0, listView.currentIndex)
                        root.fileModel.selectRange(root._anchor, cur)
                    } else if (!ctrl) {
                        root.fileModel.setSingle(cur)
                        root._anchor = cur
                    }
                    listView.currentIndex = cur
                    listView.positionViewAtIndex(cur, ListView.Contain)
                    root._announce(cur)
                } else {
                    return
                }
                event.accepted = true
            }
        }
    }

    AppMenu {
        id: contextMenu
        property int row: -1
        property bool finished: false
        readonly property int selected: root.fileModel.selectedCount

        AppMenuItem {
            text: "Open"
            visible: contextMenu.finished && root.opensFiles
            onTriggered: root.openRequested(contextMenu.row)
        }
        AppMenuItem {
            text: "Show in folder"
            onTriggered: root.showInFolderRequested(contextMenu.row)
        }
        AppMenuItem {
            text: contextMenu.selected > 1 ? "Copy " + contextMenu.selected + " file names" : "Copy file name"
            onTriggered: root.copyNamesRequested()
        }
        AppMenuItem {
            text: contextMenu.selected > 1 ? "Copy " + contextMenu.selected + " full paths" : "Copy full path"
            onTriggered: root.copyPathsRequested()
        }
        AppMenuItem {
            text: "Copy results"
            onTriggered: root.copyResultsRequested()
        }
        AppMenuSeparator {}
        AppMenuItem {
            text: contextMenu.selected > 1 ? "Remove " + contextMenu.selected + " from the list" : "Remove from the list"
            enabled: !root.busy
            onTriggered: root.fileModel.removeSelected()
        }
        AppMenuItem {
            text: "Remove finished files"
            enabled: !root.busy && root.fileModel.finishedCount > 0
            onTriggered: root.fileModel.removeFinished()
        }
        AppMenuItem {
            text: "Clear the list"
            danger: true
            enabled: !root.busy
            onTriggered: root.clearRequested()
        }
    }
}
