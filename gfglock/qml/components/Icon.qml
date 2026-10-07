import QtQuick

// A glyph from the Windows icon font. Decorative by default: screen readers skip it, since the
// control or text next to it carries the accessible name.
Text {
    id: icon

    property string name: ""
    property int size: 16

    text: Theme.icons[icon.name] ?? ""
    font.family: Theme.iconFont
    font.pixelSize: icon.size
    color: Theme.text
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering
    Accessible.ignored: true
}
