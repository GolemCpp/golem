import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    width: 640
    height: 480
    visible: true
    title: qsTr("Built with Golem!")

    ColumnLayout {
        anchors.centerIn: parent
        Label {
            text: qsTr("Built with Golem!")
            font.pixelSize: 34
            font.bold: true
            color: "blue"
        }
    }
}
