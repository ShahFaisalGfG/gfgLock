// qmllint disable unqualified
import QtQuick
import QtQuick.Window

// Invisible grips along every edge and corner of a frameless window, so it resizes from any
// side like a native window instead of only the bottom-right corner.
Item {
    id: handles

    required property Window window
    property int grip: 6

    anchors.fill: parent
    z: 100

    component Grip: MouseArea {
        property int edges: 0
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        onPressed: handles.window.startSystemResize(edges)
    }

    Grip { edges: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor
        x: 0; y: handles.grip; width: handles.grip; height: parent.height - 2 * handles.grip }
    Grip { edges: Qt.RightEdge; cursorShape: Qt.SizeHorCursor
        x: parent.width - handles.grip; y: handles.grip; width: handles.grip; height: parent.height - 2 * handles.grip }
    Grip { edges: Qt.TopEdge; cursorShape: Qt.SizeVerCursor
        x: handles.grip; y: 0; width: parent.width - 2 * handles.grip; height: 3 }
    Grip { edges: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor
        x: handles.grip; y: parent.height - handles.grip; width: parent.width - 2 * handles.grip; height: handles.grip }
    Grip { edges: Qt.TopEdge | Qt.LeftEdge; cursorShape: Qt.SizeFDiagCursor
        x: 0; y: 0; width: handles.grip; height: handles.grip }
    Grip { edges: Qt.TopEdge | Qt.RightEdge; cursorShape: Qt.SizeBDiagCursor
        x: parent.width - handles.grip; y: 0; width: handles.grip; height: handles.grip }
    Grip { edges: Qt.BottomEdge | Qt.LeftEdge; cursorShape: Qt.SizeBDiagCursor
        x: 0; y: parent.height - handles.grip; width: handles.grip; height: handles.grip }
    Grip { edges: Qt.BottomEdge | Qt.RightEdge; cursorShape: Qt.SizeFDiagCursor
        x: parent.width - handles.grip * 2; y: parent.height - handles.grip * 2; width: handles.grip * 2; height: handles.grip * 2 }
}
