import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging
import shutil, subprocess, json
import time 

# If needed install serial pylibrary before imporing. If already installed, just import it.
try:
  import serial
  import serial.tools.list_ports
except ModuleNotFoundError:
  slicer.util.pip_install("pyserial")
  import serial
  import serial.tools.list_ports

"""

How the plugin works:
This programm creates a node to store the data coming from the Arduino device. 

To get the data one has to:
    - get the node : self.ArduinoNode = slicer.mrmlScene.GetFirstNodeByName("arduinoNode")
    - add an observer :     sceneModifiedObserverTag = self.ArduinoNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.name_of_the_method)
    - get the data : data= self.ArduinoNode.GetParameter("Data")

Knowing that the data that is read is **only** what is printed in the arduino code (Serial.println(Data_to_be_seen)), there can be as many
print as one want, just remind that you'll get them one at a time using data= self.ArduinoNode.GetParameter("Data").
Indeed if you want to print an array for example you'll print (array[0], array[1]) and only array[0] will be taken into account in the code.

This code makes pair with arduino_accelerometer_slicer.ino, the arduino code part. It works with IMU 9DoF Groove from Seeed, and one needs to 
install its librairy see here : https://github.com/Seeed-Studio/Seeed_ICM20600_AK09918.
The arduino part send(print) 6 datas :
     - 3 ints : 0 1 and 2 to know what axis the data belongs to (0 for x, 1 for y and 2 for z),
     - 3 floats : roll pitch and yaw which corresponds to the angle made by the IMU, theses are absolutes angles, they do not depends from the previous one.
The IMU works like a compass so we can get all 3 angles, and the calibration is mandatory, one needs to make 8-like movements for 10seconds otherwise
the datas are going to be false.

"""


#
# ArduinoAppTemplate
#

class ArduinoAppTemplate():
  """ Template class for writing code on top of Arduino Connector
  """
  def __init__(self):

    # As the datas are received one at a time, we should separate angle from axis x (elevation), y (roll) and z (azimuth)
    global axisToBeChanged, previousAxis
    axisToBeChanged=0
    previousAxis= 0

    #As the azimuth roll and elevation methods depends on the previous angle and that the accelerometer gives us absolute angle, we have to substract the new angle to the former to make our move
    global previousElevation, previousRoll, previousAzimuth
    previousElevation=0.0    
    previousRoll=0.0
    previousAzimuth=0.0 #on considere qu'on commence avec un accelerometre a plat avec les branchements a gauche

    global newAzimuth, newElevation, newRoll
    newElevation=0.0
    newRoll=0.0 
    newAzimuth=0.0

    print("Start figure-8 calibration.")

    self.ArduinoNode = slicer.mrmlScene.GetFirstNodeByName("arduinoNode")
    sceneModifiedObserverTag = self.ArduinoNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.moveThreeDView)

    self.view = slicer.app.layoutManager().threeDWidget(0).threeDView()  
    self.renderers = self.view.renderWindow().GetRenderers() 
    self.camera = self.renderers.GetFirstRenderer().GetActiveCamera() 


  def moveThreeDView(self, caller, event):

    global axisToBeChanged
    global previousElevation, previousRoll, previousAzimuth
    global newAzimuth, newElevation, newRoll


     valeurLue= float(self.ArduinoNode.GetParameter("Data"))

    if valeurLue==0 or valeurLue==1 or valeurLue==2:
      if valeurLue==0:
        # Alors la prochaine valeur à être affiché sera la donnée sur l'axe X donc le roll
        axisToBeChanged=0
      elif valeurLue==1:
        axisToBeChanged=1
      else: # valeurLue==2:
        axisToBeChanged=2
      # print("Axe qui va etre changé")
      # print(axisToBeChanged)

    else : 
      if axisToBeChanged==0: 
      # Equivalent to roll on arduino and elevation on Slicer (switch in the axis), around axis X on the accelerometer, from 0 to 180 degree
        if previousElevation>=0 and valeurLue<=0:
            newElevation= - valeurLue - previousElevation 
        elif previousElevation<=0 and valeurLue>=0:
            newElevation = valeurLue - previousElevation
        elif previousElevation>=0 and valeurLue>=0 :
          if valeurLue>previousElevation:
            newElevation= valeurLue - previousElevation
          else : #on part dans le sens oppose a la rotation normale de l'axe
            newElevation= -(previousElevation - valeurLue)
        else : # both negatives
            if abs(valeurLue)>abs(previousElevation):
              newElevation= -(- valeurLue + previousElevation)
            else :
              newElevation= - previousElevation + valeurLue 

        if 0<=newElevation<=2 or -2<=newElevation<=0:  #pour quand meme arriver a se stabiliser si on arrete de bouger
          #  if (0 < newRoll< 10 or -10 < newRoll< 0) and (0 < newAzimuth < 10 or -10 < newAzimuth < 0):  #pour ne bouger que le long d'un axe 
          #    newRoll=0
          #    newAzimuth=0
          newElevation=0
          # le previous roll ne change pas on ne s'est pas deplace
        else :
          previousElevation=valeurLue

        # print("Elevation lue")
        # print(valeurLue)
        self.camera.Elevation(newElevation)
      
      
      elif axisToBeChanged==1 :
        # Equivalent to Pitch on arduino and roll on Slicer, around axis Y, from 0 to 90 degree
        if previousRoll>=0 and valeurLue<=0:
          newRoll= valeurLue - previousRoll
        elif previousRoll<=0 and valeurLue>=0:
          newRoll= - previousRoll + valeurLue
        elif previousRoll>=0 and valeurLue>=0: # Pour faire des tours complet et ne pas se limiter a 0 +90 
            if valeurLue>previousRoll:
                newRoll= valeurLue- previousRoll
            else :
                newRoll= valeurLue - previousRoll
        else: # previousRoll<0 and valeurLue<0
            if abs(valeurLue)>abs(previousRoll):
                newRoll=valeurLue-previousRoll
            else :
                newRoll= - previousRoll + valeurLue

        if 85<=valeurLue<=90 or (-90)<=valeurLue<=(-85): #on depasse pas les 90 -90 degré 
          if valeurLue>=0:
            newRoll=90-valeurLue
          else :
            newRoll=-90-valeurLue

        if 0<= newRoll <=2 or -2<= newRoll <=0:  #pour quand meme arriver a se stabiliser si on arrete de bouger
          # if (0 < newElevation< 10 or -10 < newElevation< 0) and (0 < newAzimuth < 10 or -10 < newAzimuth < 0):  #pour ne bouger que le long d'un axe 
          #   newElevation=0
          #   newAzimuth=0
          newRoll=0
            #on ne change pas previous elevation car on a pas bouge
        else :
          previousRoll=valeurLue

        # print("Roll lu")
        # print(valeurLue)
        self.camera.Roll(newRoll)

      
      else :
        # equivalent to Heading on arduino and azimuth on Slicer, around axis z, from 0 to 360 degree
        if previousAzimuth>=valeurLue:
          newAzimuth=-(valeurLue-previousAzimuth)
        else :
          newAzimuth= previousAzimuth - valeurLue

        if 0 <=newAzimuth<=2 or -2<=newAzimuth<=0:  #pour quand meme arriver a se stabiliser si on arrete de bouger
          # if (0 < newRoll< 10 or -10 < newRoll< 0) and (0 < newElevation < 10 or -10 < newElevation < 0):  #pour ne bouger que le long d'un axe 
          #   newRoll=0
          #   newElevation=0
          newAzimuth=0
        # le previous roll ne change pas on ne s'est pas deplace
        else :
          previousAzimuth=valeurLue

        # print("Azimuth lu")
        # print(valeurLue)
        self.camera.Azimuth(newAzimuth)
        
      self.camera.OrthogonalizeViewUp()


  def sendDataToArduino(self, message):
    messageSent = slicer.modules.arduinoconnect.widgetRepresentation().self().logic.sendMessage(message)

#
#ArduinoPlotter
#

class ArduinoPlotter():
  def __init__(self, numberOfSamples):

    self.active = True

    self.ArduinoNode = slicer.mrmlScene.GetFirstNodeByName("arduinoNode")
    sceneModifiedObserverTag = self.ArduinoNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.addPointToPlot)

    # Add data into table vtk
    self.tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
    self.tableNode.SetName("Arduino plotting table")
    self.table = self.tableNode.GetTable()

    self.numberOfSamples = numberOfSamples
    self.initializeTable()

    # Create plot node
    self.plotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode", "Amplitude")
    self.plotSeriesNode.SetName("Arduino plot series")
    self.plotSeriesNode.SetAndObserveTableNodeID(self.tableNode.GetID())
    self.plotSeriesNode.SetXColumnName("Samples")
    self.plotSeriesNode.SetYColumnName("Amplitude")
    self.plotSeriesNode.SetPlotType(slicer.vtkMRMLPlotSeriesNode.PlotTypeLine)
    self.plotSeriesNode.SetLineStyle(slicer.vtkMRMLPlotSeriesNode.LineStyleSolid)
    self.plotSeriesNode.SetMarkerStyle(slicer.vtkMRMLPlotSeriesNode.MarkerStyleSquare)
    self.plotSeriesNode.SetUniqueColor()

    # Create plot chart node
    self.plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
    self.plotChartNode.SetName("Arduino plot chart")
    self.plotChartNode.AddAndObservePlotSeriesNodeID(self.plotSeriesNode.GetID())
    self.plotChartNode.SetTitle('Arduino Data')
    self.plotChartNode.SetXAxisTitle('Samples')
    self.plotChartNode.SetYAxisTitle('Amplitude')
    self.plotChartNode.LegendVisibilityOff()
    self.plotChartNode.SetXAxisRangeAuto(True)
    self.plotChartNode.SetYAxisRangeAuto(True)

    # Switch to a layout that contains a plot view to create a plot widget
    self.layoutManager = slicer.app.layoutManager()
    layoutWithPlot = slicer.modules.plots.logic().GetLayoutWithPlot(self.layoutManager.layout)
    self.layoutManager.setLayout(layoutWithPlot)

    # Select chart in plot view
    self.plotWidget = self.layoutManager.plotWidget(0)
    self.plotViewNode = self.plotWidget.mrmlPlotViewNode()
    self.plotViewNode.SetPlotChartNodeID(self.plotChartNode.GetID())

  def initializeTable(self):

    self.table.Initialize()

    self.arrX = vtk.vtkFloatArray()
    self.arrX.SetName("Samples")
    self.table.AddColumn(self.arrX)

    self.arrY = vtk.vtkFloatArray()
    self.arrY.SetName("Amplitude")
    self.table.AddColumn(self.arrY)

    self.table.SetNumberOfRows(self.numberOfSamples)
    for i in range(self.numberOfSamples):
        self.table.SetValue(i, 0, i)
        self.table.SetValue(i, 1, 0)

    self.table.Modified()

  def addPointToPlot(self, caller, event):

    if self.active:

      # Only float data type can be plot
      try:
        messageFloat = float(self.ArduinoNode.GetParameter("Data"))
      except ValueError:
        return

      self.arrY.InsertNextTuple1(messageFloat)
      self.arrY.RemoveFirstTuple()

      self.table.Modified()
      self.plotWidget.plotView().fitToContent()

#
# Arduino Monitor
#

class ArduinoMonitor():
  """ Class for plotting arduno data into a separate window
  """
  def __init__(self):

    self.ArduinoNode = slicer.mrmlScene.GetFirstNodeByName("arduinoNode")
    sceneModifiedObserverTag = self.ArduinoNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.addLine)

    self.monitor = qt.QTextEdit()
    self.monitor.setWindowTitle("Arduino monitor")
    self.monitor.setReadOnly(True)
    self.monitor.show()

    self.messageLenghtLimit = 50

  def addLine(self, caller, event):
    message = self.ArduinoNode.GetParameter("Data")

    if len(message) > self.messageLenghtLimit:
      message = "WARNING: message too long to be shown here\n"
    elif len(message) <= self.messageLenghtLimit and not message.endswith("\n"):
      message = message + "\n"

    self.monitor.insertPlainText(message)

    # Show always the last message
    verticalScrollBar = self.monitor.verticalScrollBar()
    verticalScrollBar.setValue(verticalScrollBar.maximum)

#
# ArduinoConnect
#

class ArduinoConnect(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Arduino Move it" # TODO make this more human readable by adding spaces
    self.parent.categories = ["Developer Tools"]
    self.parent.dependencies = []
    self.parent.contributors = ["Marine Camba (Paris Brain Institute, France)", "Sara Fernandez Vidal (Paris Brain Institute, France)", "Sinan Haliyon (ISIR - Institut des systèmes inteligents et robotiques, France)"]
    self.parent.helpText = """
    This module allows move the 3D modèle using an IMU 9DoF connected to an Arduino.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """This module has been created thanks to the already existing Arduino Controller module. Infos can be found (here)[https://github.com/pzaffino/SlicerArduinoController]  """ # replace with organization, grant and thanks. 

#
# ArduinoConnectWidget
#

class ArduinoConnectWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Plotter
    self.plotter = None

    # Configuration
    self.configFileName = __file__.replace("ArduinoConnect.py", "Resources%sArduinoConnectConfig.json" % (os.sep))
    with open(self.configFileName) as f:
      self.config = json.load(f)

    self.logic = ArduinoConnectLogic()

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/ArduinoConnect.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set IDE labels
    self.arduinoIDEExe = self.config["IDEExe"]
    if self.arduinoIDEExe == "":
      self.arduinoIDEExe = self.autoFindIDEExe()
    self.ui.IDEPathText.setText(self.arduinoIDEExe)

    # connections
    self.ui.portSelectorComboBox.setEnabled(False)
    self.ui.detectDevice.connect('clicked(bool)', self.onDetectDeviceButton)
    self.ui.connectButton.connect('toggled(bool)', self.onConnectButton)
    self.ui.setIDEButton.connect('clicked(bool)', self.onSetIDEButton)
    self.ui.runIDEButton.connect('clicked(bool)', self.onRunIDEButton)
    self.ui.sendButton.connect('clicked(bool)', self.onSendButton)
    self.ui.monitorButton.connect('clicked(bool)', self.onMonitorButton)
    self.ui.plotterButton.connect('toggled(bool)', self.onPlotterButton)
    self.ui.samplesToPlotText.textChanged.connect(self.onSamplesToPlot)
    self.ui.threeDButton.connect('clicked(bool)', self.onThreeDButton) 


    # Add vertical spacer
    self.layout.addStretch(1)

    # Default values for QLineEdit
    self.ui.samplesPerSecondText.setText("10")
    self.ui.samplesToPlotText.setText("30")

    

  def cleanup(self):
    pass

  def writeConfig(self):
    with open(self.configFileName, 'w') as json_file:
      json.dump(self.config, json_file)

  def autoFindIDEExe(self):
    arduinoIDEExe = shutil.which("arduino")
    if arduinoIDEExe is None:
      return ""
    else:
      return arduinoIDEExe

  def onConnectButton(self, toggle):

    # clicked connect and the device list has elements
    if toggle and self.ui.portSelectorComboBox.currentText != "":

        self.connected = self.logic.connect(self.ui.portSelectorComboBox.currentText,
                                            self.ui.baudSelectorComboBox.currentText,
                                            self.ui.samplesPerSecondText.text)

        if self.connected:
          self.ui.connectButton.setText("Disconnect")
          self.ui.connectButton.setStyleSheet("background-color:#ff0000")
          self.ui.portSelectorComboBox.setEnabled(False)
          self.ui.baudSelectorComboBox.setEnabled(False)
          self.ui.detectDevice.setEnabled(False)
          self.ui.sendButton.setEnabled(True)
          self.ui.samplesPerSecondText.setEnabled(False)
        else:
          self.deviceError("Device not found", "Impssible to connect the selected device.", "critical")
          self.ui.connectButton.setChecked(False)
          self.ui.connectButton.setText("Connect")
          self.ui.connectButton.setStyleSheet("background-color:#f1f1f1;")

    # clicked connect but device list has no elements
    elif toggle and self.ui.portSelectorComboBox.currentText == "":
        self.deviceError("Ports scan", "Any device has been set!", "warning")
        self.ui.connectButton.setChecked(False)
        return

    # clicked disconnect with a running connection
    elif not toggle and self.logic.arduinoConnection is not None and self.connected:
      self.logic.disconnect()
      self.ui.connectButton.setText("Connect")
      self.ui.connectButton.setStyleSheet("background-color:#f1f1f1;")
      self.ui.portSelectorComboBox.setEnabled(True)
      self.ui.baudSelectorComboBox.setEnabled(True)
      self.ui.detectDevice.setEnabled(True)
      self.ui.sendButton.setEnabled(False)
      self.ui.samplesPerSecondText.setEnabled(True)

  def onDetectDeviceButton(self, clicked):

    self.ui.portSelectorComboBox.setEnabled(True)
    self.ui.portSelectorComboBox.clear()

    devices = [port.device for port in serial.tools.list_ports.comports() if port[2] != 'n/a']

    if len(devices)==0:
        self.deviceError("Ports scan", "Any device has been found!", "warning")
    elif len(devices)>0:
        for device in devices:
            self.ui.portSelectorComboBox.addItem(device)

  def onSetIDEButton(self, clicked):
    dialog = qt.QFileDialog()
    self.arduinoIDEExe = dialog.getOpenFileName(None, "Arduino IDE executable", os.path.expanduser("~"))
    self.ui.IDEPathText.setText(self.arduinoIDEExe)

    # Update config
    self.config["IDEExe"] = self.arduinoIDEExe
    self.writeConfig()

  def onRunIDEButton(self, clicked):
    if self.arduinoIDEExe != "":
      subprocess.Popen(self.arduinoIDEExe)

  def onSendButton(self, clicked):
    message = self.ui.messageText.text
    self.logic.sendMessage(message)

  def onMonitorButton(self, clicked):
    monitor = ArduinoMonitor()

  def onPlotterButton(self, clicked):
    if clicked and self.plotter is None:
      self.plotter = ArduinoPlotter(int(self.ui.samplesToPlotText.text))
      self.ui.plotterButton.setText("Stop plotting")

    if not clicked and self.plotter is not None:
      self.plotter.active = False
      self.ui.plotterButton.setText("Plot data")

    if clicked and self.plotter is not None:
      self.plotter.active = True
      self.ui.plotterButton.setText("Stop plotting")

  def onSamplesToPlot(self, event):
    samplesToPlot = int(self.ui.samplesToPlotText.text)
    if self.plotter is not None and samplesToPlot > 0:
      self.plotter.numberOfSamples = samplesToPlot
      self.plotter.initializeTable()

  #------------------------------------------------------ 
  def onThreeDButton(self, clicked): 
    threeDButton = ArduinoAppTemplate() 

  def deviceError(self, title, message, error_type="warning"):
    deviceMBox = qt.QMessageBox()
    if error_type == "warning":
      deviceMBox.setIcon(qt.QMessageBox().Warning)
    elif error_type == "critical":
      deviceMBox.setIcon(qt.QMessageBox().Critical)
    deviceMBox.setWindowTitle(title)
    deviceMBox.setText(message)
    deviceMBox.exec()

#
# ArduinoConnectLogic
#

class ArduinoConnectLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
      ScriptedLoadableModuleLogic.__init__(self)

      import serial

      self.parameterNode=slicer.vtkMRMLScriptedModuleNode()
      self.parameterNode.SetName("arduinoNode")
      slicer.mrmlScene.AddNode(self.parameterNode)

      self.arduinoConnection = None

  def sendMessage(self, messageToSend):
      #print(messageToSend)
      if self.arduinoConnection is not None:
        self.arduinoConnection.write(str.encode(messageToSend))
        return True
      else:
        return False

  def connect(self, port, baud, samplesPerSecond):
      self.arduinoEndOfLine = '\n'
      self.arduinoRefreshRateFps = float(samplesPerSecond)

      try:
        self.arduinoConnection = serial.Serial(port, baud)
      except serial.serialutil.SerialException:
        return False

      qt.QTimer.singleShot(1000/self.arduinoRefreshRateFps, self.pollSerialDevice)
      return True

  def disconnect(self):
      self.arduinoConnection.close()
      self.arduinoConnection = None

  def pollSerialDevice(self):

      if self.arduinoConnection is None:
        return

      if self.arduinoConnection.isOpen() and self.arduinoConnection.in_waiting == 0: # No messages from arduino
          qt.QTimer.singleShot(1000/self.arduinoRefreshRateFps, self.pollSerialDevice)
      elif self.arduinoConnection.isOpen() and self.arduinoConnection.in_waiting > 0: # Some messages from arduino
          arduinoReceiveBuffer = self.arduinoConnection.readline().decode('ascii')
          if self.arduinoEndOfLine in arduinoReceiveBuffer: # Valid message
              message = arduinoReceiveBuffer.split(self.arduinoEndOfLine)[0]
              message = self.processMessage(message)
              if len(message) >= 1:

                  # Fire a message even if the message is unchanged
                  if message == self.parameterNode.GetParameter("Data"):
                    self.parameterNode.Modified()
                  else:
                    self.parameterNode.SetParameter("Data", message)

          qt.QTimer.singleShot(1000/self.arduinoRefreshRateFps, self.pollSerialDevice)

  def processMessage(self, msg):
      return msg


class ArduinoConnectTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    self.mrmlScene.Clear(0)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_ArduinoConnect1()

  def test_ArduinoConnect1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """

    self.delayDisplay("Starting the test")
    #
    # first, get some data
    #
    import SampleData
    SampleData.downloadFromURL(
      nodeNames='FA',
      fileNames='FA.nrrd',
      uris='http://self.kitware.com/midas3/download?items=5767',
      checksums='SHA256:12d17fba4f2e1f1a843f0757366f28c3f3e1a8bb38836f0de2a32bb1cd476560')
    self.delayDisplay('Finished with download and loading')

    volumeNode = slicer.util.getNode(pattern="FA")
    logic = ArduinoConnectLogic()
    self.assertIsNotNone( logic.hasImageData(volumeNode) )
    self.delayDisplay('Test passed!')



