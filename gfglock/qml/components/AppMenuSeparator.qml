import QtQuick
import QtQuick.Controls

// A thin Theme-coloured line between groups of an AppMenu.
MenuSeparator {
    topPadding: Theme.spaceXs
    bottomPadding: Theme.spaceXs
    leftPadding: Theme.spaceSm
    rightPadding: Theme.spaceSm

    contentItem: Rectangle {
        implicitWidth: 160
        implicitHeight: 1
        color: Theme.border
    }
}
