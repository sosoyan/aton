__author__ = "Vahan Sosoyan"
__copyright__ = "2016 All rights reserved. See Copyright.txt for more details."
__version__ = "v1.1.3"

import sys

import maya.mel as mel
import maya.OpenMaya as OM
import pymel.core as pm
from maya import cmds, OpenMayaUI

try:
    from arnold import *
    import mtoa.core as core
except ImportError:
    cmds.warning("MtoA was not found.")

from PySide import QtCore
from PySide import QtGui
from shiboken import wrapInstance

def maya_main_window():
    main_window_ptr = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(long(main_window_ptr), QtGui.QWidget)

class Aton(QtGui.QDialog):

    def __init__(self, parent = maya_main_window()):
        super(Aton, self).__init__(parent)

        self.windowName = "Aton"
        if cmds.window(self.windowName, exists = True):
            cmds.deleteUI(self.windowName, wnd = True)

        self.timeChangedCB = None
        self.selectionChangedCB = None
        self.defaultPort = self.getSceneOption(0)
        self.setupUi()

    def getActiveCamera(self):
        ''' Returns active camera shape name '''
        cam = cmds.modelEditor(cmds.playblast(ae=1), q=1, cam=1)
        if cmds.listRelatives(cam) != None:
            cam = cmds.listRelatives(cam)[0]
        return cam

    def getSceneOption(self, attr):
        ''' Returns requested scene options attribute value'''
        result = 0
        if cmds.getAttr("defaultRenderGlobals.ren") == "arnold":

            try: # To init Arnold Render settings
                cmds.getAttr("defaultArnoldDisplayDriver.port")
            except ValueError:
                mel.eval("unifiedRenderGlobalsWindow;")

            result = {0 : lambda: cmds.getAttr("defaultArnoldDisplayDriver.port"),
                      1 : lambda: self.getActiveCamera(),
                      2 : lambda: cmds.getAttr("defaultResolution.width"),
                      3 : lambda: cmds.getAttr("defaultResolution.height"),
                      4 : lambda: cmds.getAttr("defaultArnoldRenderOptions.AASamples"),
                      5 : lambda: cmds.getAttr("defaultArnoldRenderOptions.ignoreMotionBlur"),
                      6 : lambda: cmds.getAttr("defaultArnoldRenderOptions.ignoreSubdivision"),
                      7 : lambda: cmds.getAttr("defaultArnoldRenderOptions.ignoreDisplacement"),
                      8 : lambda: cmds.getAttr("defaultArnoldRenderOptions.ignoreBump"),
                      9 : lambda: cmds.getAttr("defaultArnoldRenderOptions.ignoreSss")}[attr]()
        return result

    def setupUi(self):
        ''' Building the GUI '''
        def resUpdateUi():
            self.resolutionSpinBox.setValue(resolutionSlider.value() * 5)

        def camUpdateUi():
            self.cameraAaSpinBox.setValue(cameraAaSlider.value())

        def portUpdateUi():
            self.portSpinBox.setValue(portSlider.value() + self.defaultPort)

        def resetUi(*args):
            self.portSpinBox.setValue(self.defaultPort)
            portSlider.setValue(0)
            self.cameraComboBox.setCurrentIndex(0)
            self.resolutionSpinBox.setValue(100)
            resolutionSlider.setValue(20)
            self.cameraAaSpinBox.setValue(self.getSceneOption(4))
            cameraAaSlider.setValue(self.getSceneOption(4))
            self.renderRegionXSpinBox.setValue(0)
            self.renderRegionYSpinBox.setValue(0)
            self.renderRegionRSpinBox.setValue(self.getSceneOption(2))
            self.renderRegionTSpinBox.setValue(self.getSceneOption(3))
            self.motionBlurCheckBox.setChecked(self.getSceneOption(5))
            self.subdivsCheckBox.setChecked(self.getSceneOption(6))
            self.displaceCheckBox.setChecked(self.getSceneOption(7))
            self.bumpCheckBox.setChecked(self.getSceneOption(8))
            self.sssCheckBox.setChecked(self.getSceneOption(9))
            self.shaderComboBox.setCurrentIndex(0)
            textureRepeatSlider.setValue(4)
            self.selectedShaderCheckbox.setChecked(0)

        self.setObjectName(self.windowName)
        self.setWindowTitle("Aton %s"%__version__)
        self.setWindowFlags(QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setMinimumSize(400, 350)
        self.setMaximumSize(400, 350)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.setContentsMargins(5,5,5,5)
        mainLayout.setSpacing(2)

        generalGroupBox = QtGui.QGroupBox("General")
        generalLayout = QtGui.QVBoxLayout(generalGroupBox)

        # Port Layout
        portLayout = QtGui.QHBoxLayout()
        portLabel = QtGui.QLabel("Port:")
        portLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
        portLabel.setMaximumSize(75, 20)
        portLabel.setMinimumSize(75, 20)
        self.portSpinBox = QtGui.QSpinBox()
        self.portSpinBox.setButtonSymbols(QtGui.QAbstractSpinBox.NoButtons)
        self.portSpinBox.setMaximum(1024)
        self.portSpinBox.setMaximum(9999)
        self.portSpinBox.setValue(self.defaultPort)
        portSlider = QtGui.QSlider()
        portSlider.setOrientation(QtCore.Qt.Horizontal)
        portSlider.setMinimum(0)
        portSlider.setMaximum(15)
        portSlider.setValue(0)
        portLayout.addWidget(portLabel)
        portLayout.addWidget(self.portSpinBox)
        portLayout.addWidget(portSlider)

        # Camera Layout
        cameraLayout = QtGui.QHBoxLayout()
        cameraLabel = QtGui.QLabel("Camera:")
        cameraLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
        cameraLabel.setMaximumSize(75, 20)
        cameraLabel.setMinimumSize(75, 20)
        self.cameraComboBox = QtGui.QComboBox()
        self.cameraComboBoxDict = {}
        self.cameraComboBox.addItem("Current view")
        for i in cmds.listCameras():
            self.cameraComboBox.addItem(i)
            self.cameraComboBoxDict[cmds.listCameras().index(i)+1] = i
        cameraLayout.addWidget(cameraLabel)
        cameraLayout.addWidget(self.cameraComboBox)

        overridesGroupBox = QtGui.QGroupBox("Overrides")
        overridesLayout = QtGui.QVBoxLayout(overridesGroupBox)

        # Resolution Layout
        resolutionLayout = QtGui.QHBoxLayout()
        resolutionLabel = QtGui.QLabel("Resolution %:")
        resolutionLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
        resolutionLabel.setMinimumSize(75, 20)
        self.resolutionSpinBox = QtGui.QSpinBox()
        self.resolutionSpinBox.setButtonSymbols(QtGui.QAbstractSpinBox.NoButtons)
        self.resolutionSpinBox.setMinimum(1)
        self.resolutionSpinBox.setMaximum(900)
        self.resolutionSpinBox.setValue(100)
        resolutionSlider = QtGui.QSlider()
        resolutionSlider.setOrientation(QtCore.Qt.Horizontal)
        resolutionSlider.setValue(20)
        resolutionSlider.setMaximum(20)
        resolutionLayout.addWidget(resolutionLabel)
        resolutionLayout.addWidget(self.resolutionSpinBox)
        resolutionLayout.addWidget(resolutionSlider)

        # Camera Layout
        cameraAaLayout = QtGui.QHBoxLayout()
        cameraAaLabel = QtGui.QLabel("Camera (AA):")
        cameraAaLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
        cameraAaLabel.setMinimumSize(75, 20)
        self.cameraAaSpinBox = QtGui.QSpinBox()
        self.cameraAaSpinBox.setButtonSymbols(QtGui.QAbstractSpinBox.NoButtons)
        self.cameraAaSpinBox.setMaximum(64)
        self.cameraAaSpinBox.setMinimum(-64)
        self.cameraAaSpinBox.setValue(self.getSceneOption(4))
        cameraAaSlider = QtGui.QSlider()
        cameraAaSlider.setOrientation(QtCore.Qt.Horizontal)
        cameraAaSlider.setValue(self.cameraAaSpinBox.value())
        cameraAaSlider.setMaximum(16)
        cameraAaSlider.valueChanged[int].connect(self.cameraAaSpinBox.setValue)
        cameraAaLayout.addWidget(cameraAaLabel)
        cameraAaLayout.addWidget(self.cameraAaSpinBox)
        cameraAaLayout.addWidget(cameraAaSlider)

        # Render region layout
        renderRegionLayout = QtGui.QHBoxLayout()
        renderRegionLabel = QtGui.QLabel("Region X:")
        renderRegionLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
        self.renderRegionXSpinBox = QtGui.QSpinBox()
        renderRegionYLabel = QtGui.QLabel("Y:")
        self.renderRegionYSpinBox = QtGui.QSpinBox()
        renderRegionRLabel = QtGui.QLabel("R:")
        self.renderRegionRSpinBox = QtGui.QSpinBox()
        renderRegionTLabel = QtGui.QLabel("T:")
        self.renderRegionTSpinBox = QtGui.QSpinBox()
        renderRegionCheckBox = QtGui.QCheckBox()
        renderRegionGetNukeButton = QtGui.QPushButton("Get")
        renderRegionGetNukeButton.clicked.connect(self.getNukeCropNode)
        renderRegionCheckBox.setLayoutDirection(QtCore.Qt.RightToLeft)
        renderRegionLayout.addWidget(renderRegionLabel)
        renderRegionLayout.addWidget(self.renderRegionXSpinBox)
        renderRegionLayout.addWidget(renderRegionYLabel)
        renderRegionLayout.addWidget(self.renderRegionYSpinBox)
        renderRegionLayout.addWidget(renderRegionRLabel)
        renderRegionLayout.addWidget(self.renderRegionRSpinBox)
        renderRegionLayout.addWidget(renderRegionTLabel)
        renderRegionLayout.addWidget(self.renderRegionTSpinBox)
        renderRegionLayout.addWidget(renderRegionGetNukeButton)

        for i in [renderRegionLabel,
                  renderRegionYLabel,
                  renderRegionRLabel,
                  renderRegionTLabel]:
            i.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)

        for i in [self.renderRegionXSpinBox,
                  self.renderRegionYSpinBox,
                  self.renderRegionRSpinBox,
                  self.renderRegionTSpinBox]:
            i.setRange(0,99999)
            i.setMaximumSize(60,25)
            i.setButtonSymbols(QtGui.QAbstractSpinBox.NoButtons)

        self.renderRegionRSpinBox.setValue(self.getSceneOption(2))
        self.renderRegionTSpinBox.setValue(self.getSceneOption(3))

        # Shaders layout
        shaderLayout = QtGui.QHBoxLayout()
        shaderLabel = QtGui.QLabel("Shader override:")
        shaderLabel.setMaximumSize(85, 20)
        self.shaderComboBox = QtGui.QComboBox()
        self.shaderComboBox.addItem("Disabled")
        self.shaderComboBox.addItem("Checker")
        self.shaderComboBox.addItem("Grey")
        self.shaderComboBox.addItem("Mirror")
        self.shaderComboBox.addItem("Normal")
        self.shaderComboBox.addItem("Occlusion")
        self.shaderComboBox.addItem("UV")
        self.selectedShaderCheckbox = QtGui.QCheckBox("Selected objects only")
        shaderLayout.addWidget(shaderLabel)
        shaderLayout.addWidget(self.shaderComboBox)
        shaderLayout.addWidget(self.selectedShaderCheckbox)

        textureRepeatLayout = QtGui.QHBoxLayout()
        textureRepeatLabel = QtGui.QLabel("Texture repeat:")
        textureRepeatLabel.setMaximumSize(85, 20)
        self.textureRepeatSpinbox = QtGui.QSpinBox()
        self.textureRepeatSpinbox.setValue(1)
        self.textureRepeatSpinbox.setButtonSymbols(QtGui.QAbstractSpinBox.NoButtons)
        textureRepeatSlider = QtGui.QSlider()
        textureRepeatSlider.setMinimum(1)
        textureRepeatSlider.setMaximum(64)
        textureRepeatSlider.setOrientation(QtCore.Qt.Horizontal)
        textureRepeatSlider.valueChanged[int].connect(self.textureRepeatSpinbox.setValue)
        textureRepeatSlider.setValue(4)
        textureRepeatLayout.addWidget(textureRepeatLabel)
        textureRepeatLayout.addWidget(self.textureRepeatSpinbox)
        textureRepeatLayout.addWidget(textureRepeatSlider)

        # Ignore Layout
        ignoresGroupBox = QtGui.QGroupBox("Ignore")
        ignoresLayout = QtGui.QVBoxLayout(ignoresGroupBox)
        ignoreLayout = QtGui.QHBoxLayout()
        ignoreLabel = QtGui.QLabel("Ignore:")
        ignoreLabel.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
        self.motionBlurCheckBox = QtGui.QCheckBox("Motion Blur")
        self.motionBlurCheckBox.setChecked(self.getSceneOption(5))
        self.subdivsCheckBox = QtGui.QCheckBox("Subdivs")
        self.subdivsCheckBox.setChecked(self.getSceneOption(6))
        self.displaceCheckBox = QtGui.QCheckBox("Displace")
        self.displaceCheckBox.setChecked(self.getSceneOption(7))
        self.bumpCheckBox = QtGui.QCheckBox("Bump")
        self.bumpCheckBox.setChecked(self.getSceneOption(8))
        self.sssCheckBox = QtGui.QCheckBox("SSS")
        self.sssCheckBox.setChecked(self.getSceneOption(9))
        ignoreLayout.addWidget(self.motionBlurCheckBox)
        ignoreLayout.addWidget(self.subdivsCheckBox)
        ignoreLayout.addWidget(self.displaceCheckBox)
        ignoreLayout.addWidget(self.bumpCheckBox)
        ignoreLayout.addWidget(self.sssCheckBox)

        # Main Buttons Layout
        mainButtonslayout = QtGui.QHBoxLayout()
        startButton = QtGui.QPushButton("Start / Refresh")
        stopButton = QtGui.QPushButton("Stop")
        resetButton = QtGui.QPushButton("Reset")
        startButton.clicked.connect(self.render)
        stopButton.clicked.connect(self.stop)
        resetButton.clicked.connect(resetUi)
        mainButtonslayout.addWidget(startButton)
        mainButtonslayout.addWidget(stopButton)
        mainButtonslayout.addWidget(resetButton)

        # Add Layouts to Main
        generalLayout.addLayout(portLayout)
        generalLayout.addLayout(cameraLayout)
        overridesLayout.addLayout(resolutionLayout)
        overridesLayout.addLayout(cameraAaLayout)
        overridesLayout.addLayout(renderRegionLayout)
        overridesLayout.addLayout(shaderLayout)
        overridesLayout.addLayout(textureRepeatLayout)
        ignoresLayout.addLayout(ignoreLayout)

        mainLayout.addWidget(generalGroupBox)
        mainLayout.addWidget(overridesGroupBox)
        mainLayout.addWidget(ignoresGroupBox)
        mainLayout.addLayout(mainButtonslayout)

        # UI Updates
        self.connect(portSlider, QtCore.SIGNAL("valueChanged(int)"), portUpdateUi)
        self.connect(resolutionSlider, QtCore.SIGNAL("valueChanged(int)"), resUpdateUi)

        # IPR Updates
        self.connect(self.cameraComboBox, QtCore.SIGNAL("currentIndexChanged(int)"), lambda: self.IPRUpdate(0))
        self.connect(self.resolutionSpinBox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(1))
        self.connect(self.cameraAaSpinBox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(2))
        self.connect(self.renderRegionXSpinBox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(1))
        self.connect(self.renderRegionYSpinBox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(1))
        self.connect(self.renderRegionRSpinBox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(1))
        self.connect(self.renderRegionTSpinBox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(1))
        self.connect(self.motionBlurCheckBox, QtCore.SIGNAL("toggled(bool)"), lambda: self.IPRUpdate(3))
        self.connect(self.subdivsCheckBox, QtCore.SIGNAL("toggled(bool)"), lambda: self.IPRUpdate(3))
        self.connect(self.displaceCheckBox, QtCore.SIGNAL("toggled(bool)"), lambda: self.IPRUpdate(3))
        self.connect(self.bumpCheckBox, QtCore.SIGNAL("toggled(bool)"), lambda: self.IPRUpdate(3))
        self.connect(self.sssCheckBox, QtCore.SIGNAL("toggled(bool)"), lambda: self.IPRUpdate(3))
        self.connect(self.shaderComboBox, QtCore.SIGNAL("currentIndexChanged(int)"), lambda: self.IPRUpdate(4))
        self.connect(self.textureRepeatSpinbox, QtCore.SIGNAL("valueChanged(int)"), lambda: self.IPRUpdate(5))
        self.connect(self.selectedShaderCheckbox, QtCore.SIGNAL("toggled(bool)"), lambda: self.IPRUpdate(4))

        self.setLayout(mainLayout)

    def getCamera(self):
        ''' Returns current selected camera from GUI '''
        if self.cameraComboBox.currentIndex() == 0:
            camera = self.getSceneOption(1)
        else:
            camera = self.cameraComboBoxDict[self.cameraComboBox.currentIndex()]
            if cmds.listRelatives(camera, s=1) != None:
                camera = cmds.listRelatives(camera, s=1)[0]
        return camera

    def getNukeCropNode(self, *args):
        ''' Get crop node data from Nuke '''
        def find_between(s, first, last):
            try:
                start = s.index(first) + len(first)
                end = s.index(last, start)
                return s[start:end]
            except ValueError:
                return ""

        clipboard = QtGui.QApplication.clipboard()
        data = clipboard.text()

        checkData1 = "set cut_paste_input [stack 0]"
        checkData2 = "Crop {"

        if (checkData1 in data.split('\n', 10)[0]) and \
           (checkData2 in data.split('\n', 10)[3]):
                cropData = find_between(data.split('\n', 10)[4], "box {", "}" ).split()
                nkX, nkY, nkR, nkT = int(float(cropData[0])),\
                                     int(float(cropData[1])),\
                                     int(float(cropData[2])),\
                                     int(float(cropData[3]))

                self.renderRegionXSpinBox.setValue(nkX)
                self.renderRegionYSpinBox.setValue(nkY)
                self.renderRegionRSpinBox.setValue(nkR)
                self.renderRegionTSpinBox.setValue(nkT)

                return cropData

    def render(self):
        ''' Starts the render '''
        try: # If MtoA was not found
            defaultTranslator = cmds.getAttr("defaultArnoldDisplayDriver.aiTranslator")
        except ValueError:
            cmds.warning("Current renderer is not set to Arnold.")
            return

        try: # If Aton driver for Arnold is not installed
            cmds.setAttr("defaultArnoldDisplayDriver.aiTranslator", "aton", type="string")
        except RuntimeError:
            cmds.warning("Aton driver for Arnold is not installed")
            return

        # Updating the port from UI
        if self.defaultPort != 0:
            port = self.portSpinBox.value()
            cmds.setAttr("defaultArnoldDisplayDriver.port", port)
        else:
            cmds.warning("Current renderer is not set to Arnold.")
            return

        # Adding time changed callback
        if self.timeChangedCB == None:
            self.timeChangedCB = OM.MEventMessage.addEventCallback("timeChanged", self.timeChnaged)

        # Adding selection changed callback
        if self.selectionChangedCB == None:
            self.selectionChangedCB = OM.MEventMessage.addEventCallback('SelectionChanged', self.selectionChanged)

        try: # If render session is not started yet
            cmds.arnoldIpr(mode='stop')
        except RuntimeError:
            pass

        # Temporary makeing hidden cameras visible before scene export
        hCams = [x for x in cmds.listCameras() if not cmds.getAttr("%s.visibility"%x) or
                                                  not cmds.getAttr("%s.visibility"%cmds.listRelatives(x, s=1)[0])]
        for i in hCams: cmds.showHidden(i)

        try: # Start IPR
            camera = self.getCamera()
            cmds.arnoldIpr(cam=camera, mode='start')
        except RuntimeError:
            cmds.warning("Current renderer is not set to Arnold.")

        # Update IPR
        self.IPRUpdate()
        sys.stdout.write("// Info: Aton - Render started.\n")

        # Setting back to default
        for i in hCams: cmds.hide(i)
        cmds.setAttr("defaultArnoldDisplayDriver.aiTranslator", defaultTranslator, type="string")
        cmds.setAttr("defaultArnoldDisplayDriver.port", self.defaultPort)

    def initOvrShaders(self):
        ''' Initilize override shaders '''
        # Checker shader
        self.checkerShader = AiNode("standard")
        checkerTexture = AiNode("MayaChecker")
        self.placeTexture = AiNode("MayaPlace2DTexture")
        AiNodeLink(self.placeTexture, "uvCoord", checkerTexture)
        AiNodeLink(checkerTexture, "Kd", self.checkerShader)

        # Grey Shader
        self.greyShader = AiNode("standard")
        AiNodeSetFlt(self.greyShader, "Kd", 0.225)
        AiNodeSetFlt(self.greyShader, "Ks", 1)
        AiNodeSetFlt(self.greyShader, "specular_roughness", 0.6)
        AiNodeSetBool(self.greyShader, "specular_Fresnel", True)
        AiNodeSetBool(self.greyShader, "Fresnel_use_IOR", True)
        AiNodeSetFlt(self.greyShader, "IOR", 1.1)

        # Mirror Shader
        self.mirrorShader = AiNode("standard")
        AiNodeSetFlt(self.mirrorShader, "Kd", 0)
        AiNodeSetFlt(self.mirrorShader, "Ks", 1)
        AiNodeSetFlt(self.mirrorShader, "specular_roughness", 0)
        AiNodeSetBool(self.mirrorShader, "specular_Fresnel", True)
        AiNodeSetFlt(self.mirrorShader, "Ksn", 0.6)

        # Normal Shader
        self.normalShader = AiNode("utility")
        AiNodeSetInt(self.normalShader, "shade_mode", 2)
        AiNodeSetInt(self.normalShader, "color_mode", 2)

        # Occlusion Shader
        self.occlusionShader = AiNode("utility")
        AiNodeSetInt(self.occlusionShader, "shade_mode", 3)

        # UV Shader
        self.uvShader = AiNode("utility")
        AiNodeSetInt(self.uvShader, "shade_mode", 2)
        AiNodeSetInt(self.uvShader, "color_mode", 5)

    def IPRUpdate(self, attr = None):
        ''' This method is called during IPR session '''
        try: # If render session is not started yet
            cmds.arnoldIpr(mode='pause')
        except (AttributeError, RuntimeError):
            return

        options = AiUniverseGetOptions()

        # Camera Update
        if attr == None or attr == 0:
            camera = self.getCamera()
            iterator = AiUniverseGetNodeIterator(AI_NODE_CAMERA)
            while not AiNodeIteratorFinished(iterator):
                node = AiNodeIteratorGetNext(iterator)
                if AiNodeGetName(node) == camera:
                    AiNodeSetPtr(options, "camera", node)

        # Resolution and Region Update
        if attr == None or attr == 1:
            xres = self.getSceneOption(2) * self.resolutionSpinBox.value() / 100
            yres = self.getSceneOption(3) * self.resolutionSpinBox.value() / 100

            AiNodeSetInt(options, "xres", xres)
            AiNodeSetInt(options, "yres", yres)

            rMinX = self.renderRegionXSpinBox.value()
            rMinY = yres - self.renderRegionTSpinBox.value()
            rMaxX = self.renderRegionRSpinBox.value() -1
            rMaxY = (yres - self.renderRegionYSpinBox.value()) - 1

            if (rMinX >= 0) and (rMinY >= 0) and (rMaxX <= xres) and (rMaxY <= yres):
                AiNodeSetInt(options, "region_min_x", rMinX)
                AiNodeSetInt(options, "region_min_y", rMinY)
                AiNodeSetInt(options, "region_max_x", rMaxX)
                AiNodeSetInt(options, "region_max_y", rMaxY)
            else:
                AiNodeSetInt(options, "region_min_x", 0)
                AiNodeSetInt(options, "region_min_y", 0)
                AiNodeSetInt(options, "region_max_x", xres-1)
                AiNodeSetInt(options, "region_max_y", yres-1)

        # Camera AA Update
        if attr == None or attr == 2:
            cameraAA = self.cameraAaSpinBox.value()
            options = AiUniverseGetOptions()
            AiNodeSetInt(options, "AA_samples", cameraAA)

        # Ignore options Update
        if attr == None or attr == 3:
            motionBlur = self.motionBlurCheckBox.isChecked()
            subdivs = self.subdivsCheckBox.isChecked()
            displace = self.displaceCheckBox.isChecked()
            bump = self.bumpCheckBox.isChecked()
            sss = self.sssCheckBox.isChecked()

            AiNodeSetBool(options, "ignore_motion_blur", motionBlur)
            AiNodeSetBool(options, "ignore_subdivision", subdivs)
            AiNodeSetBool(options, "ignore_displacement", displace)
            AiNodeSetBool(options, "ignore_bump", bump)
            AiNodeSetBool(options, "ignore_sss", sss)

        # Storing default shader assignments
        if attr == None:
            self.initOvrShaders()
            self.shadersDict = {}
            iterator = AiUniverseGetNodeIterator(AI_NODE_SHAPE)
            while not AiNodeIteratorFinished(iterator):
                node = AiNodeIteratorGetNext(iterator)
                name = AiNodeGetName(node)
                try: # If object name is not exist i.e. "root"
                    sgList = cmds.listConnections(name, type='shadingEngine')
                    if sgList > 0:
                        self.shadersDict[name] = AiNodeGetPtr(node, "shader")
                except ValueError:
                    continue

        # Shader override Update
        shaderIndex = self.shaderComboBox.currentIndex()
        if attr == 4 or shaderIndex > 0:
            iterator = AiUniverseGetNodeIterator(AI_NODE_SHAPE)
            while not AiNodeIteratorFinished(iterator):
                node = AiNodeIteratorGetNext(iterator)
                name = AiNodeGetName(node)

                selChecked = self.selectedShaderCheckbox.isChecked()
                if shaderIndex != 0 and selChecked:
                    selectionList = cmds.ls(dag=1, sl=1, s=1)
                    if selectionList > 0 and name not in selectionList:
                        if name in self.shadersDict:
                            defShader = self.shadersDict[AiNodeGetName(node)]
                            AiNodeSetPtr(node, "shader", defShader)
                        continue

                # Setting overrides
                if name in self.shadersDict:
                    defShader = self.shadersDict[AiNodeGetName(node)]
                    result = {0: lambda: AiNodeSetPtr(node, "shader", defShader),
                              1: lambda: AiNodeSetPtr(node, "shader", self.checkerShader),
                              2: lambda: AiNodeSetPtr(node, "shader", self.greyShader),
                              3: lambda: AiNodeSetPtr(node, "shader", self.mirrorShader),
                              4: lambda: AiNodeSetPtr(node, "shader", self.normalShader),
                              5: lambda: AiNodeSetPtr(node, "shader", self.occlusionShader),
                              6: lambda: AiNodeSetPtr(node, "shader", self.uvShader)}[shaderIndex]()

        # Texture Repeat Udpate
        if attr == None or attr == 5:
            texRepeat = self.textureRepeatSpinbox.value()
            AiNodeSetPnt2(self.placeTexture, "repeatUV", texRepeat, texRepeat)

        try:
            cmds.arnoldIpr(mode='unpause')
        except RuntimeError:
            pass

    def timeChnaged(self, *args):
        ''' Callback method to update the frame number attr '''
        options = AiUniverseGetOptions()
        time = cmds.currentTime(q=1)
        AiNodeSetFlt(options, "frame", time)

    def selectionChanged(self, *args):
        ''' Callback method to update the frame number attr '''
        shaderIndex = self.shaderComboBox.currentIndex()
        selectedObjects = self.selectedShaderCheckbox.isChecked()
        if shaderIndex > 0 and selectedObjects:
            self.IPRUpdate(4)

    def stop(self):
        ''' Stops the render session and removes the callbacks '''
        if self.timeChangedCB != None:
            OM.MEventMessage.removeCallback(self.timeChangedCB)
            self.timeChangedCB = None

        if self.selectionChangedCB != None:
            OM.MEventMessage.removeCallback(self.selectionChangedCB)
            self.selectionChangedCB = None

        try:
            cmds.arnoldIpr(mode='stop')
            sys.stdout.write("// Info: Aton - Render stopped.\n")
        except (AttributeError, RuntimeError):
            return

    def closeEvent(self, event):
        ''' Removes callback when closing the GUI '''
        if self.timeChangedCB != None:
            OM.MEventMessage.removeCallback(self.timeChangedCB)
            self.timeChangedCB = None

        if self.selectionChangedCB != None:
            OM.MEventMessage.removeCallback(self.selectionChangedCB)
            self.selectionChangedCB = None

if __name__ == "__main__":
    aton = Aton()
    aton.show()
