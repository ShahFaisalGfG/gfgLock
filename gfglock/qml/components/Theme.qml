pragma Singleton
import QtQuick

// Design tokens shared by every window, matching CC-Gen-Ultimate's so both apps look alike.
// Colors are chosen so body and muted text keep at least a 4.5:1 contrast ratio against their
// surfaces in both themes (WCAG 2.1 AA).
QtObject {
    id: theme

    // Bound by every AppWindow to appController.currentTheme.
    property bool dark: false

    // ── Surfaces ─────────────────────────────────────────────────────────────
    readonly property color background:   dark ? "#15171c" : "#f3f4f6"
    readonly property color surface:      dark ? "#1d2027" : "#ffffff"
    readonly property color surfaceAlt:   dark ? "#242832" : "#f7f8fa"
    readonly property color surfaceHover: dark ? "#2b303b" : "#eceff3"
    readonly property color titleBar:     dark ? "#111317" : "#e9ebef"
    readonly property color border:       dark ? "#343a46" : "#d6dae1"
    readonly property color borderStrong: dark ? "#4a5263" : "#b7bec9"

    // ── Text ─────────────────────────────────────────────────────────────────
    readonly property color text:      dark ? "#e8eaee" : "#1a1d23"
    readonly property color textMuted: dark ? "#a6adba" : "#565f6c"
    readonly property color textOnAccent: "#ffffff"

    // ── Accent and status ────────────────────────────────────────────────────
    readonly property color accent:      dark ? "#5aa9ff" : "#0b62c4"
    readonly property color accentFill:  dark ? "#2a6fd6" : "#0b62c4"
    readonly property color accentHover: dark ? "#3a7fe6" : "#0a56ad"
    readonly property color accentSoft:  dark ? "#1b2c45" : "#e5effb"
    readonly property color success:     dark ? "#4ac26b" : "#1a7f37"
    readonly property color successSoft: dark ? "#16301f" : "#e3f4e8"
    readonly property color danger:      dark ? "#ff6b63" : "#c62828"
    readonly property color dangerSoft:  dark ? "#3a1d1d" : "#fdecec"
    readonly property color warning:     dark ? "#e0b341" : "#8a5a00"
    readonly property color focusRing:   dark ? "#8cc4ff" : "#0b62c4"
    // Dims the window behind a dialog. Dark in both themes: a pale wash over the dark theme looks
    // like Windows fading out a frozen app.
    readonly property color scrim:       dark ? "#8c000000" : "#4d000000"
    // Highlights the window while files are dragged over it.
    readonly property color dropFill:    dark ? "#332a6fd6" : "#1a0b62c4"
    // Toasts use the opposite theme's colors so they stand out from the window.
    readonly property color inverseSurface: dark ? "#e8eaee" : "#22262e"
    readonly property color inverseText:    dark ? "#1a1d23" : "#ffffff"
    // The title bar's close button turns Windows red on hover in both themes.
    readonly property color closeHover:     "#c42b1c"
    readonly property color closeHoverText: "#ffffff"

    // ── Typography (pixel sizes) ─────────────────────────────────────────────
    readonly property string fontFamily: "Segoe UI Variable Text"
    readonly property int fontCaption: 12
    readonly property int fontBody: 13
    readonly property int fontSubtitle: 15
    readonly property int fontTitle: 18

    // ── Spacing and shape ────────────────────────────────────────────────────
    readonly property int spaceXs: 4
    readonly property int spaceSm: 8
    readonly property int spaceMd: 12
    readonly property int spaceLg: 16
    readonly property int spaceXl: 24
    readonly property int radius: 6
    readonly property int radiusLarge: 10
    readonly property int controlHeight: 34

    // ── Icons (Segoe Fluent Icons on Windows 11, MDL2 Assets on Windows 10) ──
    readonly property string iconFont: Qt.fontFamilies().indexOf("Segoe Fluent Icons") >= 0
        ? "Segoe Fluent Icons" : "Segoe MDL2 Assets"
    readonly property var icons: ({
        add: "",
        folder: "",
        folderOpen: "",
        remove: "",
        delete: "",
        close: "",
        cancel: "",
        minimize: "",
        maximize: "",
        restore: "",
        settings: "",
        info: "",
        play: "",
        stop: "",
        check: "",
        completed: "",
        error: "",
        warning: "",
        page: "",
        more: "",
        clear: "",
        openExternal: "",
        sync: "",
        chevronDown: "",
        lock: "",
        unlock: "",
        view: "",
        hide: "",
        key: "",
        skip: "",
        speed: "",
        notify: "",
        copy: ""
    })
}
