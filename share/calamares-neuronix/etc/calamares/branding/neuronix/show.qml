/* Neuronix Calamares slideshow (install progress pane).
 * Shows calamares/image.png (merged as slide1.png) full-bleed while packages install.
 */

import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    textColor: "#EBEBEB"

    Rectangle {
        anchors.fill: parent
        color: "#151515"
        z: -2
    }

    Slide {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            color: "#151515"
            z: -1
        }

        Image {
            id: installHero
            source: "slide1.png"
            anchors.fill: parent
            anchors.margins: 8
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            smooth: true
        }
    }
}
