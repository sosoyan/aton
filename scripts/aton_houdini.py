import os
import re
import time
import psutil
import socket
import fnmatch

import hou

from hutil.Qt import QtCore, QtWidgets, QtGui
from htoa.node.parms import HaNodeSetStr
from htoa.node.node import nodeSetArrayString

from arnold import *

__author__ = "Ryan Heniser, Vahan Sosoyan"
__copyright__ = "2019 All rights reserved. See Copyright.txt for more details."
__version__ = "1.3.5"


def warn(msg, *params):
    """ Warn message in Arnold Rendering process
    :param msg: str
    :param params: __repr__
    """
    header = "[%s] " % __name__
    AiMsgWarning(header + msg, *params)


def atonPatch():
    """ Patching HtoA to override the driver
    """
    import htoa.object.rop
    import htoa.session
    # Only monkey patch once -- the arnold.py soho script from HtoA can and
    # typically will be called many times. Only monkey patch (decorate) the
    # generate method once.
    if htoa.object.rop.HaRop.generate.__name__ == "generate":
        htoa.session.HaRop.generate = generate_decorated(htoa.session.HaRop.generate)


def aton_update(self):
    """ Runs this function for overrides
    :param self: htoa.session.HaRop.generate
    """
    if self.session.isInteractiveRender():

        options_node = AiUniverseGetOptions()

        if AiNodeLookUpUserParameter(options_node, "aton_enable"):

            if AiNodeGetBool(options_node, "aton_enable"):

                driver = "driver_aton"

                if not (AiNodeEntryLookUp(driver) is None):

                    aton_node = get_aton_driver(self, driver, "aton")

                    AiNodeSetStr(aton_node, "host", AiNodeGetStr(options_node, "aton_host"))
                    AiNodeSetInt(aton_node, "port", AiNodeGetInt(options_node, "aton_port"))
                    AiNodeSetStr(aton_node, "output", AiNodeGetStr(options_node, "aton_output"))

                    if AiNodeLookUpUserParameter(options_node, "aton_bucket"):
                        AiNodeSetStr(options_node, "bucket_scanning",
                                     AiNodeGetStr(options_node, "aton_bucket"))

                    if AiNodeLookUpUserParameter(options_node, "aton_region_min_x"):
                        AiNodeSetInt(options_node, "region_min_x",
                                     AiNodeGetInt(options_node, "aton_region_min_x"))

                    if AiNodeLookUpUserParameter(options_node, "aton_region_min_y"):
                        AiNodeSetInt(options_node, "region_min_y",
                                     AiNodeGetInt(options_node, "aton_region_min_y"))

                    if AiNodeLookUpUserParameter(options_node, "aton_region_max_x"):
                        AiNodeSetInt(options_node, "region_max_x",
                                     AiNodeGetInt(options_node, "aton_region_max_x"))

                    if AiNodeLookUpUserParameter(options_node, "aton_region_max_y"):
                        AiNodeSetInt(options_node, "region_max_y",
                                     AiNodeGetInt(options_node, "aton_region_max_y"))

                    if AiNodeLookUpUserParameter(options_node, "aton_ignore_mbl"):
                        AiNodeSetBool(options_node, "ignore_motion_blur",
                                      AiNodeGetBool(options_node, "aton_ignore_mbl"))

                    if AiNodeLookUpUserParameter(options_node, "aton_ignore_sdv"):
                        AiNodeSetBool(options_node, "ignore_subdivision",
                                      AiNodeGetBool(options_node, "aton_ignore_sdv"))

                    if AiNodeLookUpUserParameter(options_node, "aton_ignore_dsp"):
                        AiNodeSetBool(options_node, "ignore_displacement",
                                      AiNodeGetBool(options_node, "aton_ignore_dsp"))

                    if AiNodeLookUpUserParameter(options_node, "aton_ignore_bmp"):
                        AiNodeSetBool(options_node, "ignore_bump",
                                      AiNodeGetBool(options_node, "aton_ignore_bmp"))

                    if AiNodeLookUpUserParameter(options_node, "aton_ignore_sss"):
                        AiNodeSetBool(options_node, "ignore_sss",
                                      AiNodeGetBool(options_node, "aton_ignore_sss"))

                    # Get the outputs string array param (on the options node) as a python list
                    array = AiNodeGetArray(options_node, "outputs")
                    elements = AiArrayGetNumElements(array)
                    outputs = [AiArrayGetStr(array, i) for i in xrange(elements)]

                    # RGBA primary should be the first in outputs--its last string
                    # should be the node name of the driver_houdini (IPR) main driver
                    name = outputs[0].split()[-1]

                    # Ignoring variance outputs coming from Noice
                    aton_outputs = \
                        [i.replace(name, AiNodeGetName(aton_node)) for i in outputs if "variance_filter" not in i]
                    nodeSetArrayString(options_node, "outputs", aton_outputs)

                else:
                    warn("Aton Driver was not found.")
            else:
                warn("Aton is not Enabled.")
        else:
            warn("Aton User Options was not found.")


def generate_decorated(func):
    """ Decorating a generate method
    :param func: htoa.session.HaRop.generate
    :rtype: function
    """
    def generate_decorator(self, *args, **kwargs):
        """ Extends generate method
        :param self: htoa.session.HaRop.generate
        :rtype: function
        """
        result = func(self, *args, **kwargs)
        aton_update(self)
        return result

    return generate_decorator


def get_aton_driver(self, node_entry_name, new_sub_str):
    """  Get Aton Driver Arnold Node
    :param self: htoa.session.HaRop.generate
    :param node_entry_name: str
    :param new_sub_str: str
    :rtype: driver_aton
    """
    from htoa.object.camera import cameraTag

    node_iter = AiUniverseGetNodeIterator(AI_NODE_DRIVER)

    while not AiNodeIteratorFinished(node_iter):
        node = AiNodeIteratorGetNext(node_iter)
        node_entry = AiNodeGetNodeEntry(node)
        if node_entry_name == AiNodeEntryGetName(node_entry):
            return node

    driver_aton_node = AiNode(node_entry_name)
    cam_tag = cameraTag(self.session.camera_name)
    HaNodeSetStr(driver_aton_node, "name",
                 (self.path + ":" + new_sub_str + (":%s" % cam_tag if cam_tag else "")))
    return driver_aton_node


def generate_tiles(w, h, f):
    """ Generates 2**f tiles for the given rectangle
    :param w: int
    :param h: int
    :param f: int
    :rtype: list
    """
    x_step, y_step = w, h
    for i in range(0, f):
        if i % 2:
            y_step /= 2
        else:
            x_step /= 2

    y_min, y_max = 0, y_step
    for i in range(0, h / y_step):

        x_min, x_max = 0, x_step
        for j in range(0, w / x_step):
            yield [x_min, y_min, x_max, y_max]

            x_min += x_step if x_min < w else x_min
            x_max += x_step if x_max <= w else x_max

        y_min += y_step if y_min < h else y_min
        y_max += y_step if y_max <= h else y_max


def get_host():
    """ Returns a host name from Aton driver
    """
    aton_host = os.getenv("ATON_HOST")

    if aton_host is None:
        return "127.0.0.1"
    else:
        return str(aton_host)


def get_port():
    """ Returns a port number from Aton driver
    """
    aton_port = os.getenv("ATON_PORT")

    if aton_port is None:
        return 9201
    else:
        return int(aton_port)


def get_ui_instance_count(name):
    """ Get UI instance count for setting a Port number
    :param name: str
    :rtype: int
    """
    widgets = QtWidgets.QApplication.instance().topLevelWidgets()
    instances = [w.instance for w in widgets if w.objectName() == name]

    res = 0
    while True:
        if res in instances:
            res += 1
        else:
            return res


def get_rop_list():
    """ Returns a list of all output driver names
    :rtype: list
    """
    return list(hou.nodeType(hou.ropNodeTypeCategory(), "arnold").instances())


def get_bucket_modes():
    """ Get the list of Bucket Scanning modes
    """
    result = list()
    rop_list = get_rop_list()

    if rop_list:
        parm_template_group = rop_list[0].parmTemplateGroup()
        parm_tamplate_name = "ar_bucket_scanning"
        parm_template_exist = parm_template_group.find(parm_tamplate_name)
        if parm_template_exist:
            result = list(rop_list[0].parm(parm_tamplate_name).parmTemplate().menuItems())

    return result


def get_all_cameras(path=False):
    """ Returns a list of all camera names
    :param path: str
    :rtype: list
    """
    cameras = hou.nodeType(hou.nodeTypeCategories()["Object"], "cam").instances()
    cameras += hou.nodeType(hou.nodeTypeCategories()["Object"], "stereocam").instances()

    if path:
        return [i.path() for i in cameras]

    return cameras


class HickStatus(QtCore.QThread):
    """ Checks whether hick process is running
        and emits signal when it's finished
    """
    finished = QtCore.Signal(bool)

    def __init__(self, ipr):
        """ Gets IPRViewer
        :param ipr: hou.IPRViewer
        """
        super(HickStatus, self).__init__()

        self._ipr = ipr

    def run(self):
        """ Executes the thread
        """
        while self._ipr.isActive():
            if self.is_finished():
                self.finished.emit(True)

    @staticmethod
    def is_finished():
        """ Checks whether the hick process has finished
        :rtype: bool
        """
        for p in psutil.Process(os.getpid()).children(recursive=True):
            if p.name().startswith("hick"):
                try:
                    return p.cpu_percent(interval=1) == 0.0
                except psutil.NoSuchProcess:
                    return


class BoxWidget(QtWidgets.QFrame):
    """ Abstract Class for UI Widgets
    """
    def __init__(self, label, first=True):
        """
        :param label: str
        :param first: bool
        """
        super(BoxWidget, self).__init__()

        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setSizeConstraint(QtWidgets.QLayout.SetMaximumSize)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._label = QtWidgets.QLabel(label)

        if first:
            self._label.setText(label + ":")
            self._label.setMinimumSize(75, 20)
            self._label.setMaximumSize(75, 20)

        self._label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignCenter)
        self._layout.addWidget(self._label)


class LineEditBox(BoxWidget):
    """ QLineEdit Implementation
    """
    def __init__(self, label, text="", first=True):
        """
        :param label: str
        :param text: str
        :param first: bool
        """
        super(LineEditBox, self).__init__(label, first)

        self._widget = QtWidgets.QLineEdit()
        self._widget.setText(text)
        self._layout.addWidget(self._widget)

    def set_enabled(self, value):
        """ Sets Enabled mode
        :param value: bool
        """
        self._label.setEnabled(value)
        self._widget.setEnabled(value)

    def text(self):
        """ Gets current text
        :rtype: str
        """
        return self._widget.text()

    def set_text(self, text):
        """ Sets given text
        :param text: str
        """
        self._widget.setText(text)

    @property
    def text_changed(self):
        return self._widget.textChanged


class SliderBox(BoxWidget):
    """ SliderBox Widget based on QSpinbox and QSlider
    """
    def __init__(self, label, value=0, first=True):
        """
        :param label: str
        :param value: int
        :param first: bool
        """
        super(SliderBox, self).__init__(label, first)

        self._spinBox = QtWidgets.QSpinBox()
        self._spinBox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self._spinBox.setValue(value)

        self._slider = QtWidgets.QSlider()
        self._slider.setOrientation(QtCore.Qt.Horizontal)
        self._slider.setValue(value)

        self._slider.valueChanged.connect(self._spinBox.setValue)

        self._layout.addWidget(self._spinBox)
        self._layout.addWidget(self._slider)

    def set_minimum(self, spin_value=None, slider_value=None):
        """ Sets Min limits
        :param spin_value: int
        :param slider_value: int
        """
        if spin_value is not None:
            self._spinBox.setMinimum(spin_value)
        if slider_value is not None:
            self._slider.setMinimum(slider_value)

    def set_maximum(self, spin_value=None, slider_value=None):
        """ Set Max limits
        :param spin_value: int
        :param slider_value: int
        """
        if spin_value is not None:
            self._spinBox.setMaximum(spin_value)
        if slider_value is not None:
            self._slider.setMaximum(slider_value)

    def set_value(self, spin_value=None, slider_value=None):
        """ Sets current values
        :param spin_value: int
        :param slider_value: int
        """
        if slider_value is not None:
            self._slider.setValue(slider_value)
        if spin_value is not None:
            self._spinBox.setValue(spin_value)

    def value(self):
        """ Gets current value
        :rtype: int
        """
        return self._spinBox.value()

    def connect(self, func):
        """ Wraps the signal
        :param func: function
        """
        self._slider.valueChanged.connect(func)

    def set_enabled(self, value):
        """ Sets Enabled
        :param value: bool
        """
        self._label.setEnabled(value)
        self._spinBox.setEnabled(value)
        self._slider.setEnabled(value)

    @property
    def value_changed(self):
        """ Wraps the signal
        :rtype: QtCore.Signal
        """
        return self._spinBox.valueChanged


class SpinBox(BoxWidget):
    """ QSpinBox  implementation
    """
    def __init__(self, label, value=0, first=True):
        """
        :param label: str
        :param value: int
        :param first: bool
        """
        super(SpinBox, self).__init__(label, first)
        self._spin_box = QtWidgets.QSpinBox()
        self._spin_box.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self._spin_box.setRange(-99999, 99999)
        self._spin_box.setMaximumSize(50, 20)
        self._spin_box.setValue(value)

        self._layout.addWidget(self._spin_box)

    def value(self):
        """ Gets current value
        :rtype: int
        """
        return self._spin_box.value()

    def set_value(self, value):
        """ Sets current value
        :param value: int
        """
        self._spin_box.setValue(value)

    def set_enabled(self, value):
        """ Sets Enabled signal
        :param value: bool
        """
        self._spin_box.setEnabled(value)
        self._label.setEnabled(value)

    @property
    def value_changed(self):
        """ Wraps the signal
        :rtype: QtCore.Signal
        """
        return self._spin_box.valueChanged


class ComboBox(BoxWidget):
    """ QComboBox implementation
    """
    def __init__(self, label, first=True):
        """
        :param label:str
        :param first: bool
        """
        super(ComboBox, self).__init__(label, first)
        self._items = list()

        self._combo_box = QtWidgets.QComboBox()
        self._combo_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                      QtWidgets.QSizePolicy.Fixed)

        self._layout.addWidget(self._combo_box)

    def set_enabled(self, value):
        """ Sets Enabled mode
        :param value: bool
        """
        self._label.setEnabled(value)
        self._combo_box.setEnabled(value)

    def set_current_index(self, value):
        """ Sets current index
        :param value:int
        """
        self._combo_box.setCurrentIndex(value)

    def set_current_name(self, value):
        """ Sets given name as the current selection index
        :param value: str
        """
        for idx, item in enumerate(self._items):
            if item == value:
                self._combo_box.setCurrentIndex(idx)

    def set_default_name(self, text):
        """ Sets default text next to the name
        :param text: str
        """
        self._combo_box.setItemText(0, self._items[0] + " (%s) " % text)

    def current_index(self):
        """ Gets current index
        :rtype: int
        """
        return self._combo_box.currentIndex()

    def current_name(self):
        """ Gets current name
        :rtype: str
        """
        index = self._combo_box.currentIndex()
        if self._items:
            return self._items[index]

    def add_items(self, items):
        """ Adds new items
        :param items: list
        """
        if items:
            for i in items:
                self._combo_box.addItem(i)
            self._items += items

    def new_items(self, items):
        """ Clears and Adds new items
        :param items: list
        """
        self.clear()
        if items:
            for i in items:
                self._combo_box.addItem(i)
            self._items += items

    def clear(self):
        """ Clears the items list
        :return:
        """
        self._combo_box.clear()
        self._items = []

    @property
    def current_index_changed(self):
        return self._combo_box.currentIndexChanged


class CheckBox(BoxWidget):
    """ QCheckBox implementation
    """
    def __init__(self, label, title="", first=True):
        """
        :param label: str
        :param title: str
        :param first: bool
        """
        super(CheckBox, self).__init__(label, first)
        self._widget = QtWidgets.QCheckBox(title)

        self._layout.addWidget(self._widget)

    @property
    def state_changed(self):
        """ Wraps the signal
        :rtype: QtCore.Signal
        """
        return self._widget.stateChanged

    @property
    def toggled(self):
        """ Wraps the signal
        :rtype: QtCore.Signal
        """
        return self._widget.toggled

    def is_checked(self):
        """ Gets True if checked
        :rtype: bool
        """
        return self._widget.isChecked()

    def set_checked(self, value):
        """ Sets Checked mode
        :param value: bool
        """
        self._widget.setChecked(value)

    def set_enabled(self, value):
        """ Sets Enabled mode
        :param value:
        """
        self._widget.setEnabled(value)


class OutputListBox(BoxWidget):
    """ QListWidget implementation
    """
    def __init__(self, label, first=True):
        """
        :param label: str
        :param first: bool
        """
        BoxWidget.__init__(self, label, first)

        self._widget = QtWidgets.QListWidget()
        self._widget.setStyleSheet("background-color:#131313;")

        self._layout.addWidget(self._widget)

    def current_item(self):
        """ Gets current item
        :rtype: OutputItem
        """
        return self._widget.currentItem()

    def current_name(self):
        """ Gets current item's name
        :rtype: str
        """
        if self._widget.currentItem() is not None:
            return self._widget.currentItem().text()

    def set_current_item(self, item):
        """ Sets given item as the current selection
        :param item: QtWidgets.QListWidgetItem
        """
        self._widget.setCurrentItem(item)

    def set_first_item(self):
        """ Sets first item as the current selection
        """
        if self._widget.count():
            self._widget.setCurrentItem(self._widget.itemAt(0, 0))

    def set_enabled(self, value):
        """ Sets Enabled mode
        :param value: bool
        """
        self._widget.setEnabled(value)

    def set_multi_selection(self, value):
        """ Sets selection mode
        :param value: bool
        """
        if value:
            self._widget.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        else:
            self._widget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

    def selected_items(self):
        """ Gets selected items
        :rtype: list
        """
        return self._widget.selectedItems()

    def clear(self):
        """ Clears the items list
        """
        self._widget.clear()

    def remove_item_name(self, name):
        """ Removes given item name from the list
        :param name: str
        """
        items = self._widget.findItems(name, QtCore.Qt.MatchExactly)

        if items:
            self._widget.takeItem(self._widget.row(items[0]))

    @property
    def current_item_changed(self):
        """ Wraps the following signal
        :rtype: QtCore.Signal
        """
        return self._widget.currentItemChanged

    @property
    def widget(self):
        """ Gets Widget item
        :rtype: QtWidgets.QListWidget
        """
        return self._widget


class Signal(QtCore.QObject):
    """ Signals to use inside OutputItem
    """
    rop_name_changed = QtCore.Signal(str)
    being_deleted = QtCore.Signal(str)
    camera_changed = QtCore.Signal(str)
    resolution_changed = QtCore.Signal(tuple)
    aa_samples_changed = QtCore.Signal(int)
    bucket_scanning_changed = QtCore.Signal(str)


class OutputItem(QtWidgets.QListWidgetItem):
    """ Output object holds ROP attributes
    """
    def __init__(self, rop=None, parent=None):
        """
        :param rop: hou.RopNode
        :param parent: QtWidgets.QListWidget
        """
        QtWidgets.QListWidgetItem.__init__(self, parent)

        self.signal = Signal()

        if type(rop) == hou.RopNode:
            ar_user_options = rop.parmTemplateGroup().find("ar_user_options")

            if ar_user_options:
                self.__rop = rop
                self.__cam = self.__get_camera()
                self.__override_camera_res = self.__rop.parm("override_camerares").eval()
                self.__res_fraction = self.__rop.parm("res_fraction").eval()
                self.__res_override = self.__rop.parmTuple("res_override").eval()
                self.__aa_samples = self.__rop.parm("ar_AA_samples").eval()
                self.__user_options_enable = self.__rop.parm("ar_user_options_enable").eval()
                self.__user_options_string = self.__rop.parm("ar_user_options").eval()
                self.__empty = False

                self.setText(self.__rop.path())
                self.add_callbacks()
        else:
            self.__rop = None
            self.__cam = None
            self.__override_camera_res = False
            self.__res_fraction = str()
            self.__res_override = (0, 0)
            self.__aa_samples = 0
            self.__user_options_enable = False
            self.__user_options_string = str()
            self.__empty = True

    def __get_camera(self):
        """ Get Camera object
        :rtype: hou.Node
        """
        camera = hou.node(self.__rop.parm("camera").eval())
        if camera is None:
            scene_cameras = get_all_cameras()
            if scene_cameras:
                camera = scene_cameras[0]
        return camera

    def __get_resolution(self):
        """ Get Resolution tuple
        :rtype: tuple
        """
        if self.__rop is not None and self.__cam is not None:

            if self.__rop.parm("override_camerares").eval():
                res_scale = self.__rop.parm("res_fraction").eval()

                if res_scale == "specific":
                    return self.__rop.parmTuple("res_override").eval()
                else:
                    return (int(self.__cam.parmTuple("res").eval()[0] * float(res_scale)),
                            int(self.__cam.parmTuple("res").eval()[1] * float(res_scale)))

            return self.__cam.parmTuple("res").eval()
        else:
            return (0, 0)

    def __get_origin_resolution(self):
        """ Get Original Resolution tuple
        :rtype: tuple
        """
        if self.__cam is not None:

            if self.__override_camera_res:
                res_scale = self.__res_fraction

                if res_scale == "specific":
                    return self.__res_override
                else:
                    return (int(self.__cam.parmTuple("res").eval()[0] * float(res_scale)),
                            int(self.__cam.parmTuple("res").eval()[1] * float(res_scale)))

            return self.__cam.parmTuple("res").eval()
        else:
            return (0, 0)

    def __get_pixel_aspect(self):
        """ Get Camera Pixel Aspect Ration
        :param: float
        """
        if self.__rop is not None and self.__cam is not None:

            if self.__rop.parm("override_camerares").eval():
                return self.__rop.parm("aspect_override").eval()
            else:
                return self.__cam.parm("aspect").eval()
        else:
            return 1.0

    def __name_changed(self, **kwargs):
        """ Name changed callback
        :param kwargs: hou.Node
        :return:
        """
        node = kwargs["node"]
        self.setText(node.path())
        self.signal.rop_name_changed.emit(node.name())

    def __parm_changed(self, **kwargs):
        """ Parameter changed callback
        :param kwargs: tuple
        """
        parm_tuple = kwargs["parm_tuple"]
        parm_name = parm_tuple.name()

        if parm_name == "camera":
            self.__cam = self.__get_camera()

            self.signal.camera_changed.emit(self.__cam.path())
            self.signal.resolution_changed.emit(self.__get_resolution())

        elif parm_name == "res":
            self.__camera_resolution = self.__cam.parmTuple("res").eval()
            self.__resolution = self.__get_resolution()

            self.signal.resolution_changed.emit(self.__resolution)

        elif parm_name == "aspect":
            self.__camera_pixel_aspect = self.__cam.parm("aspect").eval()

        elif parm_name == "override_camerares":
            self.__override_camera_res = self.__rop.parm("override_camerares").eval()
            self.__resolution = self.__get_resolution()

            self.signal.resolution_changed.emit(self.__resolution)

        elif parm_name == "res_fraction":
            self.__res_fraction = self.__rop.parm("res_fraction").eval()
            self.__resolution = self.__get_resolution()

            self.signal.resolution_changed.emit(self.__resolution)

        elif parm_name == "res_override":
            self.__res_override = self.__rop.parmTuple("res_override").eval()
            self.__resolution = self.__get_resolution()

            self.signal.resolution_changed.emit(self.__resolution)

        elif parm_name == "aspect_override":
            self.__pixel_aspect = self.__get_pixel_aspect()

        elif parm_name == "ar_AA_samples":
            self.__aa_samples = self.__rop.parm("ar_AA_samples").eval()

            self.signal.aa_samples_changed.emit(self.__aa_samples)

        elif parm_name == "ar_bucket_scanning":
            self.__bucket_scanning = self.__rop.parm("ar_bucket_scanning").eval()

            self.signal.bucket_scanning_changed.emit(self.__bucket_scanning)

        elif parm_name == "ar_user_options_enable":
            self.__user_options_enable = self.__rop.parm("ar_user_options_enable").eval()

        elif parm_name == "ar_user_options":
            self.__user_options_parm = self.__rop.parm("ar_user_options")
            self.__user_options_str = self.__user_options_parm.eval()

    def __being_deleted(self, **kwargs):
        """ Being deleted callback
        :param kwargs: hou.Node
        :return:
        """
        node = kwargs["node"]

        self.__rop = None
        self.__empty = True
        self.signal.being_deleted.emit(node.path())

    def rollback_camera(self):
        """ Rollback ROP camera to default
        """
        if self.__rop is not None:
            if self.__cam is not None:
                self.__rop.parm("camera").set(self.__cam.path())

    def rollback_resolution(self):
        """ Rollback Resolution to default
        """
        if self.__rop is not None:
            self.__rop.parm("override_camerares").set(self.__override_camera_res)
            self.__rop.parm("res_fraction").set(self.__res_fraction)
            self.__rop.parmTuple("res_override").set(self.__res_override)

    def rollback_aa_samples(self):
        """ Rollback AA Samples to default
        """
        if self.__rop is not None:
            self.__rop.parm("ar_AA_samples").set(self.__aa_samples)

    def rollback_user_options(self):
        """ Rollback User Options to default
        """
        if self.__rop is not None:
            self.__rop.parm("ar_user_options_enable").set(self.__user_options_enable)
            self.__rop.parm("ar_user_options").set(re.sub("declare aton_enable.*", "", self.__user_options_string))

    def set_status(self, status=""):
        """ Set Item's status
        :param status: str
        """
        if status:
            self.setText(self.rop_path + " ( %s )" % status)
        else:
            self.setText(self.rop_path)

    def add_callbacks(self):
        """ Adds callbacks for the ROP
        """
        if self.__rop is not None:
            self.__rop.addEventCallback((hou.nodeEventType.NameChanged,), self.__name_changed)
            self.__rop.addEventCallback((hou.nodeEventType.BeingDeleted,), self.__being_deleted)
            self.__rop.addEventCallback((hou.nodeEventType.ParmTupleChanged,), self.__parm_changed)

    def remove_callbacks(self):
        """ Removes callbacks for the ROP
        """
        try:
            if self.__rop is not None:
                self.__rop.removeEventCallback((hou.nodeEventType.NameChanged,), self.__name_changed)
                self.__rop.removeEventCallback((hou.nodeEventType.BeingDeleted,), self.__being_deleted)
                self.__rop.removeEventCallback((hou.nodeEventType.ParmTupleChanged,), self.__parm_changed)
        except hou.OperationFailed:
            return

    @property
    def rop(self):
        """ Returns rop object
        """
        return self.__rop

    @property
    def rop_path(self):
        """ Returns rop path
        """
        if self.__rop is not None:
            return self.__rop.path()

    @property
    def rop_name(self):
        """ Returns rop name
        """
        if self.__rop is not None:
            return self.__rop.name()

    @property
    def cam_path(self):
        """ Returns camera path
        """
        if self.__cam is not None:
            return self.__cam.path()

    @property
    def cam_name(self):
        """ Returns camera name
        """
        if self.__cam is not None:
            return self.__cam.name()

    @property
    def aa_samples(self):
        """ Returns AA samples
        """
        if self.__rop is not None:
            return self.__rop.parm("ar_AA_samples").eval()

    @property
    def origin_aa_samples(self):
        """ Returns original AA samples
        """
        return self.__aa_samples

    @property
    def res_x(self):
        """ Returns Resolution X
        """
        if self.__rop is not None:
            return self.__get_resolution()[0]
        else:
            return 0

    @property
    def res_y(self):
        """ Returns Resolution Y
        """
        if self.__rop is not None:
            return self.__get_resolution()[1]
        else:
            return 0

    @property
    def origin_res_x(self):
        """ Returns Resolution X
        """
        if self.__cam is not None:
            return self.__get_origin_resolution()[0]
        else:
            return 0

    @property
    def origin_res_y(self):
        """ Returns Resolution Y
        """
        if self.__cam is not None:
            return self.__get_origin_resolution()[1]
        else:
            return 0

    @property
    def res_fraction(self):
        """ Returns Resolution fraction
        """
        if self.__rop is not None:
            return self.__rop.parm("res_fraction").eval()

    @property
    def bucket_scanning(self):
        """ Returns Bucket scanning
        """
        if self.__rop is not None:
            return self.__rop.parm("ar_bucket_scanning").eval()

    @property
    def origin_user_options(self):
        """ Returns original User options string
        """
        return self.__user_options_string

    @property
    def user_options(self):
        """ Returns User options string from the ROP
        """
        if self.__rop is not None:
            return self.__rop.parm("ar_user_options").eval()

    @user_options.setter
    def user_options(self, string):
        """ Sets User Options on the ROP
        :param string: str
        """
        if self.__rop is not None:
            self.__rop.parm("ar_user_options").set(string)

    @property
    def pixel_aspect(self):
        """ Returns Pixel aspect
        """
        if self.__rop is not None:
            return self.__get_pixel_aspect()

    @property
    def override_camera_res(self):
        """ Return True if Override camera resolution checkbox is enabled
        """
        if self.__rop is not None:
            return self.__rop.parm("override_camerares").eval()

    @property
    def empty(self):
        """ Returns True if empty
        """
        return self.__empty


class Aton(QtWidgets.QWidget):
    """ Main UI Object
    """
    def __init__(self, icon_path=None):
        QtWidgets.QWidget.__init__(self)

        self.__obj_name = self.__class__.__name__.lower()

        # Properties
        self.__output = None
        self.__hick_status = None
        self.__instance = get_ui_instance_count(self.__obj_name)
        self.__default_port = get_port()
        self.__default_host = get_host()

        # Init UI
        self.setObjectName(self.__obj_name)
        self.setProperty("saveWindowPref", True)
        self.setProperty("houdiniStyle", True)
        self.setStyleSheet(hou.qt.styleSheet())
        self.setWindowIcon(QtGui.QIcon(icon_path))
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips)

        # Create widgets
        self.__mode_combo_box = ComboBox("Mode")
        self.__cpu_combo_box = ComboBox("CPU:", False)
        self.__ram_combo_box = ComboBox("RAM:", False)
        self.__distribute_combo_box = ComboBox("Distribute:", False)
        self.__port_slider = SliderBox("Port")
        self.__port_increment_check_box = CheckBox("", "Increment on the Farm", False)
        self.__output_list_box = OutputListBox("Output")
        self.__filter_line_edit = LineEditBox("Filter")
        self.__camera_combo_box = ComboBox("Camera")
        self.__ipr_update_check_box = CheckBox("IPR", "Auto Update")
        self.__bucket_combo_box = ComboBox("Bucket Scan")
        self.__resolution_combo_box = ComboBox("Resolution")
        self.__camera_aa_combo_box = ComboBox("Camera (AA)")
        self.__camera_aa_slider = SliderBox("", 3, False)
        self.__render_region_check_box = CheckBox("Region")
        self.__render_region_x_spin_box = SpinBox("X:", 0, False)
        self.__render_region_y_spin_box = SpinBox("Y:", 0, False)
        self.__render_region_r_spin_box = SpinBox("R:", 0, False)
        self.__render_region_t_spin_box = SpinBox("T:", 0, False)
        self.__render_region_reset_button = QtWidgets.QPushButton("Reset")
        self.__render_region_get_button = QtWidgets.QPushButton("Get")
        self.__sequence_checkbox = CheckBox("Sequence")
        self.__seq_start_spin_box = SpinBox("Start:", int(self.start_frame), False)
        self.__seq_end_spin_box = SpinBox("End:", int(self.end_frame), False)
        self.__seq_step_spin_box = SpinBox("Step:", 1, False)
        self.__seq_rebuild_checkbox = CheckBox("", "Rebuild", False)
        self.__motion_blur_check_box = CheckBox("", "Motion Blur", False)
        self.__subdivs_check_box = CheckBox("", "Subdivs", False)
        self.__displace_check_box = CheckBox("", "Displace", False)
        self.__bump_check_box = CheckBox("", "Bump", False)
        self.__sss_check_box = CheckBox("", "SSS", False)
        self.__start_button = QtWidgets.QPushButton("Start / Refresh")
        self.__stop_button = QtWidgets.QPushButton("Stop")
        self.__reset_button = QtWidgets.QPushButton("Reset")

        # Setup UI
        self.__build_ui()
        self.__initialise_ui()
        self.__connect_signals_ui()
        self.__connect_output_signals_ui()
        self.__add_callbacks()

        # Set window title
        self.setWindowTitle("%s %s - %s" % (self.__class__.__name__, __version__, self.output.rop_name))

    def closeEvent(self, event):
        """ Called when the UI has been closed
        :param event: QEvent
        """
        if self.ipr.isActive():
            self.ipr.killRender()

        self.__remove_aton_overrides()
        self.__remove_callbacks()

        self.setParent(None)
        self.deleteLater()
        self.destroy()

    def __add_callbacks(self):
        """ Adds callbacks
        """
        # Adding a reset_callback
        hou.hipFile.addEventCallback(self.__reset_ui_callback)

    def __remove_callbacks(self):
        """ Removes callbacks
        """
        hou.hipFile.removeEventCallback(self.__reset_ui_callback)

        for item in self.__output_list:
            item.remove_callbacks()

    def __reset_ui_callback(self, event):
        """ Reset the UI if the scene was cleared or the new scene was loaded
        :param event: hou.hipFileEventType
        """
        if event == hou.hipFileEventType.AfterLoad or event == hou.hipFileEventType.AfterClear:
            self.__output_list = list()
            self.__reset_ui()

    def __generate_res_list(self):
        """ Generate Resolution List for the UI
        """
        res_x, res_y = self.output.res_x, self.output.res_y
        l = ["Use ROPs"]
        l += ["%d%% (%dx%d)" % (i, res_x / 100.0 * i, res_y / 100.0 * i) for i in [100.0, 75.0, 50.0, 25.0, 10.0, 5.0]]
        return l

    def __build_ui(self):
        """ Build Aton UI
        """
        # Main Layout
        main_layout = QtWidgets.QVBoxLayout()

        # General Group
        general_group_box = QtWidgets.QGroupBox("General")
        general_layout = QtWidgets.QVBoxLayout(general_group_box)

        # Mode Layout
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(self.__mode_combo_box)
        mode_layout.addWidget(self.__cpu_combo_box)
        mode_layout.addWidget(self.__ram_combo_box)
        mode_layout.addWidget(self.__distribute_combo_box)

        # Port Layout
        port_layout = QtWidgets.QHBoxLayout()
        port_layout.addWidget(self.__port_slider)
        port_layout.addWidget(self.__port_increment_check_box)

        # Output Driver Layout
        output_driver_layout = QtWidgets.QVBoxLayout()
        output_driver_layout.addWidget(self.__output_list_box)
        output_driver_layout.addWidget(self.__filter_line_edit)

        # Camera Layout
        camera_layout = QtWidgets.QHBoxLayout()
        camera_layout.addWidget(self.__camera_combo_box)

        # Overrides Group
        overrides_group_box = QtWidgets.QGroupBox("Overrides")
        overrides_layout = QtWidgets.QVBoxLayout(overrides_group_box)

        # IPR Update Layout
        ipr_update_layout = QtWidgets.QHBoxLayout()
        ipr_update_layout.addWidget(self.__ipr_update_check_box)

        # Bucket Layout
        bucket_layout = QtWidgets.QHBoxLayout()
        bucket_layout.addWidget(self.__bucket_combo_box)

        # Resolution Layout
        resolution_layout = QtWidgets.QHBoxLayout()
        resolution_layout.addWidget(self.__resolution_combo_box)

        # Camera AA Layout
        camera_aa_layout = QtWidgets.QHBoxLayout()
        camera_aa_layout.addWidget(self.__camera_aa_combo_box)
        camera_aa_layout.addWidget(self.__camera_aa_slider)

        # Render region layout
        render_region_layout = QtWidgets.QHBoxLayout()
        render_region_layout.addWidget(self.__render_region_check_box)
        render_region_layout.addWidget(self.__render_region_x_spin_box)
        render_region_layout.addWidget(self.__render_region_y_spin_box)
        render_region_layout.addWidget(self.__render_region_r_spin_box)
        render_region_layout.addWidget(self.__render_region_t_spin_box)
        render_region_layout.addWidget(self.__render_region_reset_button)
        render_region_layout.addWidget(self.__render_region_get_button)

        # Ignore Layout
        ignores_group_box = QtWidgets.QGroupBox("Ignore")
        ignores_layout = QtWidgets.QVBoxLayout(ignores_group_box)
        ignore_layout = QtWidgets.QHBoxLayout()
        ignore_layout.addWidget(self.__motion_blur_check_box)
        ignore_layout.addWidget(self.__subdivs_check_box)
        ignore_layout.addWidget(self.__displace_check_box)
        ignore_layout.addWidget(self.__bump_check_box)
        ignore_layout.addWidget(self.__sss_check_box)

        # Sequence layout
        sequence_group_box = QtWidgets.QGroupBox("Sequence")
        sequence_layout = QtWidgets.QHBoxLayout(sequence_group_box)
        sequence_layout.addWidget(self.__sequence_checkbox)
        sequence_layout.addWidget(self.__seq_start_spin_box)
        sequence_layout.addWidget(self.__seq_end_spin_box)
        sequence_layout.addWidget(self.__seq_step_spin_box)
        sequence_layout.addWidget(self.__seq_rebuild_checkbox)

        # Main Buttons Layout
        main_buttons_layout = QtWidgets.QHBoxLayout()
        main_buttons_layout.addWidget(self.__start_button)
        main_buttons_layout.addWidget(self.__stop_button)
        main_buttons_layout.addWidget(self.__reset_button)

        # Add Layouts to Main
        general_layout.addLayout(mode_layout)
        general_layout.addLayout(port_layout)
        general_layout.addLayout(output_driver_layout)
        overrides_layout.addLayout(ipr_update_layout)
        overrides_layout.addLayout(camera_layout)
        overrides_layout.addLayout(bucket_layout)
        overrides_layout.addLayout(resolution_layout)
        overrides_layout.addLayout(camera_aa_layout)
        overrides_layout.addLayout(render_region_layout)
        ignores_layout.addLayout(ignore_layout)

        main_layout.addWidget(general_group_box)
        main_layout.addWidget(overrides_group_box)
        main_layout.addWidget(sequence_group_box)
        main_layout.addWidget(ignores_group_box)
        main_layout.addLayout(main_buttons_layout)

        self.setLayout(main_layout)

    def __initialise_ui(self):
        """ Initialise Aton UI
        """
        # Mode Layout
        self.__mode_combo_box.add_items(["Local"])

        # Farm support if implemented
        if not issubclass(Aton, self.__class__):
            self.__mode_combo_box.add_items(["Farm"])

        self.__cpu_combo_box.add_items(self.farm_cpu_menu())
        self.__cpu_combo_box.setEnabled(False)
        self.__ram_combo_box.add_items(self.farm_ram_menu())
        self.__ram_combo_box.setEnabled(False)
        self.__distribute_combo_box.add_items(self.farm_distribute_menu())
        self.__distribute_combo_box.setEnabled(False)

        # Port Layout
        self.__port_slider.set_minimum(0, 0)
        self.__port_slider.set_maximum(9999, 15)
        self.__port_slider.set_value(self.port, self.port - self.__default_port)
        self.__port_increment_check_box.set_checked(False)
        self.__port_increment_check_box.set_enabled(False)

        # Output items list
        self.__output_list = [OutputItem(rop, self.output_list_box) for rop in get_rop_list()]
        self.__output_list_box.set_first_item()

        # Camera Layout
        self.__camera_combo_box.add_items(["Use ROPs"] + get_all_cameras(path=True))
        self.__camera_combo_box.set_default_name(self.output.cam_path)

        # IPR Update Layout
        self.__ipr_update_check_box.set_checked(self.ipr.isAutoUpdateOn())

        # Bucket Layout
        self.__bucket_combo_box.add_items(["Use ROPs"] + get_bucket_modes())
        self.__bucket_combo_box.set_default_name(self.output.bucket_scanning)

        # Resolution Layout
        self.__resolution_combo_box.add_items(self.__generate_res_list())
        self.__resolution_combo_box.set_default_name("%dx%d" % (self.output.res_x,
                                                                self.output.res_y))
        # Camera AA Layout
        self.__camera_aa_combo_box.add_items(["Use ROPs", "Custom"])
        self.__camera_aa_slider.set_minimum(-64, -3)
        self.__camera_aa_slider.set_maximum(64, 16)
        self.__camera_aa_slider.set_value(self.output.aa_samples, self.output.aa_samples)
        self.__camera_aa_slider.set_enabled(False)

        # Render region layout
        self.__render_region_x_spin_box.set_enabled(False)
        self.__render_region_y_spin_box.set_enabled(False)
        self.__render_region_r_spin_box.set_enabled(False)
        self.__render_region_t_spin_box.set_enabled(False)
        self.__render_region_reset_button.setEnabled(False)
        self.__render_region_get_button.setEnabled(False)
        self.__render_region_r_spin_box.set_value(self.output.res_x)
        self.__render_region_t_spin_box.set_value(self.output.res_y)

        # Sequence layout
        self.__seq_rebuild_checkbox.set_enabled(False)
        self.__seq_start_spin_box.set_enabled(False)
        self.__seq_end_spin_box.set_enabled(False)
        self.__seq_step_spin_box.set_enabled(False)

    def __connect_signals_ui(self):
        """ Connects UI Signals
        """
        self.__mode_combo_box.current_index_changed.connect(self.__mode_update_ui)
        self.__mode_combo_box.current_index_changed.connect(self.__port_increment_check_box.set_enabled)
        self.__port_slider.connect(self.__port_update_ui)
        self.__output_list_box.current_item_changed.connect(self.__output_update_ui)
        self.__filter_line_edit.text_changed.connect(self.__output_filter_ui)
        self.__ipr_update_check_box.toggled.connect(self.__set_auto_update)
        self.__camera_combo_box.current_index_changed.connect(self.__add_aton_overrides)
        self.__bucket_combo_box.current_index_changed.connect(self.__add_aton_overrides)
        self.__resolution_combo_box.current_index_changed.connect(self.__add_aton_overrides)
        self.__camera_aa_combo_box.current_index_changed.connect(self.__add_aton_overrides)
        self.__camera_aa_combo_box.current_index_changed.connect(self.__camera_aa_update_ui)
        self.__camera_aa_slider.value_changed.connect(self.__add_aton_overrides)
        self.__render_region_check_box.toggled.connect(self.__add_aton_overrides)
        self.__render_region_check_box.toggled.connect(self.__render_region_x_spin_box.set_enabled)
        self.__render_region_check_box.toggled.connect(self.__render_region_y_spin_box.set_enabled)
        self.__render_region_check_box.toggled.connect(self.__render_region_r_spin_box.set_enabled)
        self.__render_region_check_box.toggled.connect(self.__render_region_t_spin_box.set_enabled)
        self.__render_region_check_box.toggled.connect(self.__render_region_reset_button.setEnabled)
        self.__render_region_check_box.toggled.connect(self.__render_region_get_button.setEnabled)
        self.__render_region_x_spin_box.value_changed.connect(self.__add_aton_overrides)
        self.__render_region_y_spin_box.value_changed.connect(self.__add_aton_overrides)
        self.__render_region_r_spin_box.value_changed.connect(self.__add_aton_overrides)
        self.__render_region_t_spin_box.value_changed.connect(self.__add_aton_overrides)
        self.__render_region_reset_button.clicked.connect(self.__reset_region_ui)
        self.__render_region_get_button.clicked.connect(self.__get_render_region)
        self.__sequence_checkbox.toggled.connect(self.__seq_start_spin_box.set_enabled)
        self.__sequence_checkbox.toggled.connect(self.__seq_end_spin_box.set_enabled)
        self.__sequence_checkbox.toggled.connect(self.__seq_step_spin_box.set_enabled)
        self.__sequence_checkbox.toggled.connect(self.__seq_rebuild_checkbox.set_enabled)
        self.__motion_blur_check_box.toggled.connect(self.__add_aton_overrides)
        self.__subdivs_check_box.toggled.connect(self.__add_aton_overrides)
        self.__displace_check_box.toggled.connect(self.__add_aton_overrides)
        self.__bump_check_box.toggled.connect(self.__add_aton_overrides)
        self.__sss_check_box.toggled.connect(self.__add_aton_overrides)
        self.__start_button.clicked.connect(self.__start_render)
        self.__stop_button.clicked.connect(self.__stop_render)
        self.__reset_button.clicked.connect(self.__reset_ui)

    def __connect_output_signals_ui(self):
        """ Connects OutputItem signals to the UI
        """
        for output in self.__output_list:
            output.signal.rop_name_changed.connect(self.__output_update_ui)
            output.signal.being_deleted.connect(self.__remove_output_item)
            output.signal.camera_changed.connect(self.__camera_update_ui)
            output.signal.resolution_changed.connect(self.__res_update_ui)
            output.signal.aa_samples_changed.connect(self.__camera_aa_update_ui)
            output.signal.bucket_scanning_changed.connect(self.__bucket_scanning_update_ui)

    def __remove_output_item(self, output_name):
        """ Removes output item name from OutputListBox
        :param output_name: str
        """
        self.__output_list_box.remove_item_name(output_name)

    def __reset_ui(self):
        """ Reset UI
        """
        if self.ipr.isActive():
            self.__stop_render()

        self.__mode_combo_box.set_current_index(0)

        # Store current item name
        current_name = self.__output_list_box.current_name()

        # Removes callbacks
        for output in self.__output_list:
            output.remove_callbacks()

        self.__output_list_box.clear()
        self.__output_list = [OutputItem(rop, self.output_list_box) for rop in get_rop_list()]
        self.__connect_output_signals_ui()

        # Update to default settings
        self.__port_slider.set_value(self.port, self.port - self.__default_port)
        self.__port_increment_check_box.set_checked(False)
        self.__ipr_update_check_box.set_checked(True)
        self.__bucket_combo_box.new_items(["Use ROPs"] + get_bucket_modes())
        self.__camera_combo_box.new_items(["Use ROPs"] + get_all_cameras(path=True))
        self.__resolution_combo_box.set_current_index(0)
        self.__camera_aa_combo_box.set_current_index(0)
        self.__render_region_x_spin_box.set_value(0)
        self.__render_region_y_spin_box.set_value(0)
        self.__render_region_check_box.set_checked(False)
        self.__sequence_checkbox.set_checked(False)
        self.__seq_rebuild_checkbox.set_checked(False)
        self.__seq_start_spin_box.set_value(hou.playbar.frameRange()[0])
        self.__seq_end_spin_box.set_value(hou.playbar.frameRange()[1])
        self.__seq_step_spin_box.set_value(1)
        self.__motion_blur_check_box.set_checked(False)
        self.__subdivs_check_box.set_checked(False)
        self.__displace_check_box.set_checked(False)
        self.__bump_check_box.set_checked(False)
        self.__sss_check_box.set_checked(False)

        # Restore
        for item in self.__output_list:
            if current_name == item.rop_path:
                self.__output_list_box.set_current_item(item)
                break

        # Set Resolution list
        self.__res_update_ui()

        self.__output_list_box.set_multi_selection(False)

    def __mode_update_ui(self, value):
        """ Updates UI Local vs Farm mode
        :param value: int
        """
        self.__output_list_box.set_multi_selection(value)
        self.__cpu_combo_box.setEnabled(value)
        self.__ram_combo_box.setEnabled(value)
        self.__distribute_combo_box.setEnabled(value)
        self.__ipr_update_check_box.set_enabled(not value)

        sequence_checked = self.__sequence_checkbox.is_checked()
        self.__sequence_checkbox.set_enabled(not value)
        self.__seq_start_spin_box.set_enabled(not value and sequence_checked)
        self.__seq_end_spin_box.set_enabled(not value and sequence_checked)
        self.__seq_step_spin_box.set_enabled(not value and sequence_checked)
        self.__seq_rebuild_checkbox.set_enabled(not value and sequence_checked)

    def __port_update_ui(self, value):
        """ Update Port UI
        :param: int
        """
        self.__port_slider._spinBox.setValue(value + self.__default_port)

    def __output_filter_ui(self, pattern):
        """ Output filter update ui
        :param pattern: str
        """
        pattern_list = pattern.strip().split(" ")

        for item in self.__output_list:
            item.setHidden(True)
            for text in pattern_list:
                if fnmatch.fnmatchcase(item.rop_path, "*" + text + "*"):
                    item.setHidden(False)

    def __output_update_ui(self, item):
        """ Update the UI when changing the output rop
        :param: item: OutputItem
        """
        if type(item) is OutputItem:
            self.__res_update_ui()
            self.__camera_combo_box.set_default_name(item.cam_path)
            self.__bucket_combo_box.set_default_name(item.bucket_scanning)

            if not self.__camera_aa_combo_box.current_index():
                self.__camera_aa_slider.set_value(item.aa_samples, item.aa_samples)

            self.__render_region_x_spin_box.set_value(0)
            self.__render_region_y_spin_box.set_value(0)
            self.__render_region_r_spin_box.set_value(item.res_x)
            self.__render_region_t_spin_box.set_value(item.res_y)

        self.setWindowTitle("%s %s - %s" % (self.__class__.__name__, __version__, self.output.rop_name))

    def __camera_update_ui(self, value):
        """ Updates Camera combo box UI
        :param value: str
        """
        self.__camera_combo_box.set_default_name(value)

    def __bucket_scanning_update_ui(self, value):
        """ Update Bucket scanning UI
        :param value: str
        """
        self.__bucket_combo_box.set_default_name(value)

    def __res_update_ui(self):
        """ Update Resolution UI
        """
        index = self.__resolution_combo_box.current_index()
        self.__resolution_combo_box.new_items(self.__generate_res_list())
        self.__resolution_combo_box.set_current_index(index)
        self.__resolution_combo_box.set_default_name("%dx%d" % (self.output.origin_res_x,
                                                                self.output.origin_res_y))

        self.__render_region_r_spin_box.set_value(self.output.origin_res_x)
        self.__render_region_t_spin_box.set_value(self.output.origin_res_y)

    def __camera_aa_update_ui(self):
        """ Updates Camera AA Samples UI
        """
        if self.__camera_aa_combo_box.current_index():
            self.__camera_aa_slider.set_enabled(True)
        else:
            self.__camera_aa_slider.set_enabled(False)
            self.__camera_aa_slider.set_value(self.output.origin_aa_samples,
                                              self.output.origin_aa_samples)

    def __reset_region_ui(self):
        """ Reset Region UI
        """
        self.__render_region_x_spin_box.set_value(0)
        self.__render_region_y_spin_box.set_value(0)
        self.__render_region_r_spin_box.set_value(self.output.origin_res_x)
        self.__render_region_t_spin_box.set_value(self.output.origin_res_y)

    def __general_ui_set_enabled(self, value):
        """ Toggle UI Enabled during the rendering process
        :param: bool
        """
        self.__port_slider.set_enabled(value)
        self.__output_list_box.set_enabled(value)

    def __get_render_region(self):
        """ Get crop node data from Nuke
        """
        data = QtWidgets.QApplication.clipboard().text()

        crop_data = data.split(",")

        if crop_data is not None:

            if len(crop_data) == 5:
                nk_x = float(crop_data[0])
                nk_y = float(crop_data[1])
                nk_r = float(crop_data[2])
                nk_t = float(crop_data[3])
                nk_res = float(crop_data[4])

                region_mult = self.output.origin_res_x / nk_res

                self.__render_region_x_spin_box.set_value(int(nk_x * region_mult))
                self.__render_region_y_spin_box.set_value(int(nk_y * region_mult))
                self.__render_region_r_spin_box.set_value(int(nk_r * region_mult))
                self.__render_region_t_spin_box.set_value(int(nk_t * region_mult))

    def __get_resolution(self, attr, output):
        """ Get Resolution and Region overrides
        :param attr: int
        :param output: OutputItem
        :rtype: int
        """
        index = self.__resolution_combo_box.current_index()

        if index == 2:
            res_value = 75
        elif index == 3:
            res_value = 50
        elif index == 4:
            res_value = 25
        elif index == 5:
            res_value = 10
        elif index == 6:
            res_value = 5
        else:
            res_value = 100

        xres = output.origin_res_x * res_value / 100
        yres = output.origin_res_y * res_value / 100

        result = {0: lambda: xres,
                  1: lambda: yres,
                  2: lambda: (self.__render_region_x_spin_box.value() * res_value / 100),
                  3: lambda: yres - (self.__render_region_t_spin_box.value() * res_value / 100),
                  4: lambda: (self.__render_region_r_spin_box.value() * res_value / 100) - 1,
                  5: lambda: (yres - (self.__render_region_y_spin_box.value() * res_value / 100)) - 1}[attr]()

        return result

    def __set_auto_update(self, value):
        """ Sets Auto Update on in
        :param value:
        """
        self.ipr.setAutoUpdate(value)

    def __start_render(self, caller=None):
        """ Start Button Command
        :param caller: function
        """
        if not self.__mode_combo_box.current_index():

            if not self.output.empty:

                # Set IPR Options
                try:
                    self.ipr.setRopNode(self.output.rop)
                except hou.ObjectWasDeleted:
                    return

                self.ipr.killRender()

                # Sequence rendering mode
                if self.__sequence_checkbox.is_checked():
                    self.ipr.setPreview(False)
                    if caller is None:
                        hou.setFrame(self.__seq_start_spin_box.value())
                else:
                    self.ipr.setPreview(True)

                self.ipr.startRender()
                self.ipr.pauseRender()

                if self.__add_aton_overrides():

                    self.ipr.resumeRender()
                    self.__general_ui_set_enabled(False)
                    self.output.set_status("Rendering...")

                    if self.__sequence_checkbox.is_checked():
                        self.hick_status.start()
                else:
                    self.__stop_render()
            else:
                self.__reset_ui()
        else:
            self.__export_ass()

    def __stop_render(self):
        """ Stop Button command
        """
        if not self.__mode_combo_box.current_index():
            self.ipr.killRender()
            self.__remove_aton_overrides()
            self.__general_ui_set_enabled(True)
            self.output.set_status()
        else:
            self.farm_stop()

    def __change_time(self):
        """ Change time for sequence rendering
        """
        current_frame = int(self.current_frame)
        end_frame = self.__seq_end_spin_box.value()
        step = self.__seq_step_spin_box.value()
        rebuild = self.__seq_rebuild_checkbox.is_checked()

        if step > 1 and current_frame < end_frame - step + 1:
            next_frame = current_frame + step
        elif step > 1 and current_frame == end_frame - step + 1:
            next_frame = end_frame
        else:
            next_frame = current_frame + step

        if next_frame <= end_frame:
            hou.setFrame(next_frame)
        else:
            self.__stop_render()
            return

        if rebuild:
            self.__stop_render()
            self.__start_render(self.__change_time)

    def __export_ass(self):
        """ Exports an ass file, calls overrides and submits to the farm job
        """
        port = self.__port_slider.value()

        for output in self.__output_list_box.selected_items():

            output.set_status("Exporting ASS...")

            if output.rop is not None:
                ass_path = self.export_ass_path(output.rop_name)
                ass_name = self.export_ass_name(output.rop_name)

                if ass_path and ass_name:
                    rop_ass_enable_param = output.rop.parm("ar_ass_export_enable")
                    rop_ass_file_parm = output.rop.parm("ar_ass_file")
                    rop_picture_param = output.rop.parm("ar_picture")

                    if rop_ass_file_parm is not None:

                        default_state = rop_ass_enable_param.eval()
                        default_path = rop_ass_file_parm.rawValue()
                        default_picture = rop_picture_param.eval()

                        rop_picture_param.set("")
                        rop_ass_enable_param.set(1)
                        ass_file_path = os.path.join(ass_path, ass_name)
                        rop_ass_file_parm.set(ass_file_path)
                        ass_file_path = rop_ass_file_parm.eval()

                        output.rop.parm("execute").pressButton()

                        rop_ass_enable_param.set(default_state)
                        rop_ass_file_parm.set(default_path)
                        rop_picture_param.set(default_picture)

                        # Exported
                        output.set_status()

                        if self.__add_ass_overrides(output, ass_file_path, port):

                            self.__init_farm_job(output, ass_file_path)

                            if self.__port_increment_check_box.is_checked():
                                port += 1

    def __init_farm_job(self, output, ass_file_path):
        """ Initialises farm job requirements
        :param output: OutputItem
        :param ass_file_path: str
        """
        distribute = self.__distribute_combo_box.current_index()

        x_res = self.__get_resolution(0, output)
        y_res = self.__get_resolution(1, output)
        x_reg = self.__get_resolution(2, output)
        y_reg = self.__get_resolution(3, output)
        r_reg = self.__get_resolution(4, output)
        t_reg = self.__get_resolution(5, output)

        if self.__region_changed():
            x_res = r_reg - x_reg
            y_res = t_reg - y_reg

        for tile in generate_tiles(x_res, y_res, distribute):

            if distribute:
                if self.__region_changed():
                    region_list = [tile[0] + x_reg,
                                   tile[1] + y_reg,
                                   tile[2] + r_reg - x_res + 1,
                                   tile[3] + t_reg - y_res]
                else:
                    region_list = [tile[0], tile[1], tile[2] - 1, tile[3] - 1]
            else:
                region_list = list()

            self.farm_start(ass_file_path,
                            output.rop_name,
                            self.current_frame,
                            self.__cpu_combo_box.current_name(),
                            self.__ram_combo_box.current_name(),
                            region_list)

    def __aa_samples_changed(self):
        """ Check if the AA Samples has been overridden
        :rtype: bool
        """
        if self.__camera_aa_combo_box.current_index():
            return self.__camera_aa_slider.value() != self.output.origin_aa_samples
        else:
            return False

    def __camera_changed(self):
        """ Check if the Camera has been overridden
        :rtype: bool
        """
        return self.__camera_combo_box.current_index() and \
               self.__camera_combo_box.current_name() != self.output.cam_path

    def __resolution_changed(self, output=None):
        """ Check if the Resolution and Region have been overridden
        :param: OutputItem
        :rtype: bool
        """
        if output is None:
            output = self.output

        x_res = self.__get_resolution(0, output)
        y_res = self.__get_resolution(1, output)
        x_reg = self.__get_resolution(2, output)
        y_reg = self.__get_resolution(3, output)
        r_reg = self.__get_resolution(4, output)
        t_reg = self.__get_resolution(5, output)

        if x_res != output.origin_res_x or y_res != output.origin_res_y:
            return True
        elif x_reg != 0 or y_reg != 0 or r_reg != x_res - 1 or t_reg != y_res - 1:
            return True
        else:
            return False

    def __region_changed(self, output=None):
        """ Check if the Region have been overridden
        :param: OutputItem
        :rtype: bool
        """
        if output is None:
            output = self.output

        x_res = self.__get_resolution(0, output)
        y_res = self.__get_resolution(1, output)
        x_reg = self.__get_resolution(2, output)
        y_reg = self.__get_resolution(3, output)
        r_reg = self.__get_resolution(4, output)
        t_reg = self.__get_resolution(5, output)

        return self.__render_region_check_box.is_checked() and \
               (x_reg != 0 or y_reg != 0 or r_reg != x_res - 1 or t_reg != y_res - 1)

    def __bucket_scanning_changed(self):
        """ Check if the Bucket Scanning has been overridden
        :rtype: bool
        """
        return self.__bucket_combo_box.current_index() and \
               self.__bucket_combo_box.current_name() != self.output.bucket_scanning

    def __ignore_mbl_changed(self):
        """ Check if the Ignore Motion Blur has been Enabled
        :rtype: bool
        """
        return self.__motion_blur_check_box.is_checked()

    def __ignore_sdv_changed(self):
        """ Check if the Ignore Subdivisions has been Enabled
        :rtype: bool
        """
        return self.__subdivs_check_box.is_checked()

    def __ignore_dsp_changed(self):
        """ Check if the Ignore Displacement has been Enabled
        :rtype: bool
        """
        return self.__displace_check_box.is_checked()

    def __ignore_bmp_changed(self):
        """ Check if the Ignore Bump has been Enabled
        :rtype: bool
        """
        return self.__bump_check_box.is_checked()

    def __ignore_sss_changed(self):
        """ Check if the Ignore Sub Surface Scattering has been Enabled
        :rtype: bool
        """
        return self.__sss_check_box.is_checked()

    def __add_ass_overrides(self, output, ass_file_path, port):
        """ Overrides exported ASS files parameters
        :param output: OutputItem
        :param ass_file_path: str
        :param port: int
        :rtype: bool
        """
        AiBegin()
        AiMsgSetConsoleFlags(AI_LOG_ALL)

        AiASSLoad(ass_file_path)

        # Creates driver_aton node
        aton_node = AiNode("driver_aton")
        AiNodeSetStr(aton_node, "name", output.rop_path + ":aton:" + output.cam_name)
        AiNodeSetStr(aton_node, "host", socket.gethostbyname(socket.gethostname()))
        AiNodeSetInt(aton_node, "port", port)
        AiNodeSetStr(aton_node, "output", output.rop_name)

        # Distributive rendering session
        if self.__distribute_combo_box.current_index():
            AiNodeSetInt(aton_node, "session", int(time.time()))

        # Gets option node
        options_node = AiUniverseGetOptions()

        # Get the outputs string array param (on the options node) as a python list
        array = AiNodeGetArray(options_node, "outputs")
        elements = AiArrayGetNumElements(array)
        outputs = [AiArrayGetStr(array, i) for i in xrange(elements)]

        if outputs:

            # Get output name to be replaced with Aton
            name = outputs[0].split()[-1]

            # Ignoring variance outputs coming from Noice
            aton_outputs = [i.replace(name, AiNodeGetName(aton_node)) for i in outputs if "variance_filter" not in i]
            nodeSetArrayString(options_node, "outputs", aton_outputs)

            if self.__camera_changed():
                AiNodeSetStr(options_node, "camera", self.__camera_combo_box.current_name())

            if self.__bucket_scanning_changed():
                AiNodeSetStr(options_node, "bucket_scanning", self.__bucket_combo_box.current_name())

            if self.__resolution_changed(output):
                AiNodeSetInt(options_node, "xres", self.__get_resolution(0, output))
                AiNodeSetInt(options_node, "yres", self.__get_resolution(1, output))

            if self.__aa_samples_changed():
                AiNodeSetInt(options_node, "AA_samples", self.__camera_aa_slider.value())

            if self.__region_changed(output):
                AiNodeSetInt(options_node, "region_min_x", self.__get_resolution(2, output))
                AiNodeSetInt(options_node, "region_min_y", self.__get_resolution(3, output))
                AiNodeSetInt(options_node, "region_max_x", self.__get_resolution(4, output))
                AiNodeSetInt(options_node, "region_max_y", self.__get_resolution(5, output))

            if self.__ignore_mbl_changed():
                AiNodeSetBool(options_node, "ignore_motion_blur", self.__motion_blur_check_box.is_checked())

            if self.__ignore_sdv_changed():
                AiNodeSetBool(options_node, "ignore_subdivision", self.__subdivs_check_box.is_checked())

            if self.__ignore_dsp_changed():
                AiNodeSetBool(options_node, "ignore_displacement", self.__displace_check_box.is_checked())

            if self.__ignore_bmp_changed():
                AiNodeSetBool(options_node, "ignore_bump", self.__bump_check_box.is_checked())

            if self.__ignore_sss_changed():
                AiNodeSetBool(options_node, "ignore_sss", self.__sss_check_box.is_checked())

            AiASSWrite(ass_file_path)
            AiEnd()

            return True

    def __add_aton_overrides(self):
        """ Adds overrides as a User Options
        :rtype: bool
        """
        if self.ipr.isActive():

            self.output.remove_callbacks()

            # Main Attributes
            self.output.user_options = self.output.origin_user_options
            self.output.user_options += " " if self.output.user_options else ""
            self.output.user_options += "declare aton_enable constant BOOL aton_enable on "
            self.output.user_options += "declare aton_host constant STRING aton_host \"%s\" " % self.__default_host
            self.output.user_options += "declare aton_port constant INT aton_port %d " % self.__port_slider.value()
            self.output.user_options += "declare aton_output constant STRING aton_output \"%s\" " % self.output.rop_name

            # Enable User Options Overrides
            user_options_enabled = self.output.rop.parm("ar_user_options_enable").eval()
            if not user_options_enabled:
                self.output.rop.parm("ar_user_options_enable").set(True)

            # Camera
            if self.__camera_changed():
                self.output.rop.parm("camera").set(self.__camera_combo_box.current_name())
            else:
                self.output.rop.parm("camera").set(self.output.cam_path)

            # Bucket Scanning
            if self.__bucket_scanning_changed():
                self.output.user_options += "declare aton_bucket constant STRING aton_bucket \"%s\" " % \
                                self.__bucket_combo_box.current_name()

            # Resolution
            if self.__resolution_changed():
                self.output.rop.parm("override_camerares").set(True)
                self.output.rop.parm("res_fraction").set("specific")
                self.output.rop.parm("res_overridex").set(self.__get_resolution(0, self.output))
                self.output.rop.parm("res_overridey").set(self.__get_resolution(1, self.output))
                self.output.rop.parm("aspect_override").set(self.output.pixel_aspect)
            else:
                self.output.rop.parm("override_camerares").set(self.output.override_camera_res)
                self.output.rop.parm("res_fraction").set(self.output.res_fraction)
                self.output.rop.parm("res_overridex").set(self.output.res_x)
                self.output.rop.parm("res_overridey").set(self.output.res_y)
                self.output.rop.parm("aspect_override").set(self.output.pixel_aspect)

            # AA Samples
            if self.__aa_samples_changed():
                self.output.rop.parm("ar_AA_samples").set(self.__camera_aa_slider.value())
            else:
                self.output.rop.parm("ar_AA_samples").set(self.output.aa_samples)

            # Render Region
            if self.__region_changed():
                self.output.user_options += "declare aton_region_min_x constant INT aton_region_min_x %d " % \
                                            self.__get_resolution(2, self.output)
                self.output.user_options += "declare aton_region_min_y constant INT aton_region_min_y %d " % \
                                            self.__get_resolution(3, self.output)
                self.output.user_options += "declare aton_region_max_x constant INT aton_region_max_x %d " % \
                                            self.__get_resolution(4, self.output)
                self.output.user_options += "declare aton_region_max_y constant INT aton_region_max_y %d " % \
                                            self.__get_resolution(5, self.output)

            # Ignore Features
            if self.__ignore_mbl_changed():
                self.output.user_options += "declare aton_ignore_mbl constant BOOL aton_ignore_mbl %s  " % \
                                ("on" if self.__motion_blur_check_box.is_checked() else "off")
            if self.__ignore_sdv_changed():
                self.output.user_options += "declare aton_ignore_sdv constant BOOL aton_ignore_sdv %s " % \
                                ("on" if self.__subdivs_check_box.is_checked() else "off")
            if self.__ignore_dsp_changed():
                self.output.user_options += "declare aton_ignore_dsp constant BOOL aton_ignore_dsp %s " % \
                                ("on" if self.__displace_check_box.is_checked() else "off")
            if self.__ignore_bmp_changed():
                self.output.user_options += "declare aton_ignore_bmp constant BOOL aton_ignore_bmp %s " % \
                                ("on" if self.__bump_check_box.is_checked() else "off")
            if self.__ignore_sss_changed():
                self.output.user_options += "declare aton_ignore_sss constant BOOL aton_ignore_sss %s " % \
                                ("on" if self.__sss_check_box.is_checked() else "off")

            self.output.add_callbacks()

            return True

    def __remove_aton_overrides(self):
        """ Remove all Aton Overrides
        """
        for output in self.__output_list:

            output.remove_callbacks()

            if self.__camera_changed():
                output.rollback_camera()

            if self.__resolution_changed():
                output.rollback_resolution()

            if self.__aa_samples_changed():
                output.rollback_aa_samples()
            
            output.rollback_user_options()
            
            output.add_callbacks()

    def farm_cpu_menu(self):
        """ Farm CPU list menu to be implemented in sub-classes
        :rtype: list: str
        """
        return list()

    def farm_ram_menu(self):
        """ Farm RAM list menu to be implemented in sub-classes
        :rtype: list: str
        """
        return list()

    def farm_distribute_menu(self):
        """ Farm Distribution list menu to be implemented in sub-classes
        :rtype: list: str
        """
        return list()

    def export_ass_path(self, rop_name):
        """ Export ASS path to be implemented in sub-classes
        :param rop_name: str
        :rtype: str
        """
        return str()

    def export_ass_name(self, rop_name):
        """ Export ASS name to be implemented in sub-classes
        :param rop_name: str
        :rtype: str
        """
        return str()

    def farm_start(self, ass_file_path, rop_name, frame, cpu, ram, region):
        """ Farm submission start method to be implemented in the sub-classes
        :param ass_file_path: str
        :param rop_name: str
        :param frame: float
        :param cpu: int
        :param ram: int
        :param region: list[4]: int
        :rtype: None
        """
        pass

    def farm_stop(self):
        """ Farm submission stop method to be implemented in the sub-classes
        :rtype: None
        """
        pass

    @property
    def output_list_box(self):
        """ Gets OutputListBox object's widget
        :return:
        """
        return self.__output_list_box.widget

    @property
    def instance(self):
        """ Gets UI instance count
        :rtype: int
        """
        return self.__instance

    @property
    def ipr(self):
        """ Gets IPRViewer object
        :rtype: hou.paneTabType.IPRViewer
        """
        desk = hou.ui.curDesktop()
        return desk.paneTabOfType(hou.paneTabType.IPRViewer)

    @property
    def output(self):
        """ Gets output object based on the current selection
        :rtype: OutputItem
        """
        item = self.__output_list_box.current_item()
        if item is not None:
            return self.__output_list_box.current_item()
        else:
            return OutputItem()

    @property
    def hick_status(self):
        """ Gets HickStatus object
        :rtype: HickStatus
        """
        if self.__hick_status is None:
            self.__hick_status = HickStatus(self.ipr)
            self.__hick_status.finished.connect(self.__change_time)

        return self.__hick_status

    @property
    def port(self):
        """ Gets Port number based on UI instance count
        :rtype: int
        """
        if self.__instance > 0:
            return self.__default_port + self.__instance
        else:
            return self.__default_port

    @property
    def current_frame(self):
        """ Gets Current frame number
        :rtype: float
        """
        return hou.frame()

    @property
    def start_frame(self):
        """ Gets Start frame number
        :rtype: float
        """
        return hou.playbar.frameRange()[0]

    @property
    def end_frame(self):
        """ Gets End frame number
        :rtype: float
        """
        return hou.playbar.frameRange()[1]
