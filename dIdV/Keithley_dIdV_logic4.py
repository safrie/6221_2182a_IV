#!/usr/bin/env python
"""
This module holds all the logic for running the dI/dV UI--functions for the signals,
graph updates, instrument communications, timers, data saving/plotting, and
ramp generation.

Copyright 2018 Sarah Friedensen
This file is part of Keithley_dIdV
."""

import sys
import os
import time
import visa
import numpy as np
import re
from collections import deque
import Keithley_dIdV_design2
# import pyqtgraph as pg
from qtpy import QtGui
#from qtpy.QtCore import QBasicTimer, QTimer
from qtpy.QtGui import QFileDialog, QMessageBox, QInputDialog

__author__ = "Sarah Friedensen"
__credits__ = "Sarah Friedensen"
__license__ = "GPL3+"
__version__ = "1.0"
__maintainer__ = "Sarah Friedensen"
__email__ = "safrie@sas.upenn.edu"
__status__ = "Development"

class dIdVGui(QtGui.QMainWindow, Keithley_dIdV_design2.Ui_MainWindow):
    """This class holds all the methods necessary for running the user
    interface. It is defined as a class so that the logic is accessible while
    the UI is running."""

    def __init__(self):
        """Initialize the overarching program and allow for threading."""
        super().__init__()
        self.init_ui()

    def init_ui(self, parent=None):
        """Build the UI and set up the initial parameters for the system.

        build the user interface and connect signals from the UI to methods
        defined below. This is inherited from PyQt5 and pyqtgraph (for
        antialiasing). ADD MORE OF WHAT THE METHOD DOES HERE."""

        super(dIdVGui, self).__init__(parent)
        self.setupUi(self)
        #pg.setConfigOptions(antialias=True)
        #%% Initial Differential Conductance Variables
        self.dIdV_rate = self.dIdVRate.value()
        self.dIdV_start = self.dIdVStartCurr.value()
        self.dIdV_stop = self.dIdVStopCurr.value()
        self.dIdV_step = self.dIdVStepSize.value()
        self.dIdV_delta = self.dIdVDeltaCurr.value()
        self.dIdV_delay = self.dIdVDelay.value()

        #%% Initial Delta Variables
        #self.delta_rate = self.DeltaRate.value()
        self.delta_high = self.DeltaHighCurr.value()
        self.delta_low = self.DeltaLowCurr.value()
        self.delta_num_points = self.DeltaPulseCount.value()
        self.delta_delay = self.DeltaDelay.value()


        #%% Initial Fixed Pulse Delta Variables

        #%% Initial Sweep Pulse Delta Variables
        self.compliance_list = []
        self.I_list = []
        self.I_list_float = []
        self.cycle_list = []
        self.spd_start = self.SweepPulseDeltaStartI.value() * 1E-6
        self.spd_end = self.SweepPulseDeltaEndI.value() * 1E-6
        self.spd_step = self.SweepPulseDeltaIStep.value() * 1E-6
        self.spd_delay = self.SweepPulseDeltaCycle.value() * 16.667E-3
        self.spd_type_index = self.SweepTypeComboBox.currentIndex()

        self.spd_points_switch = {
                0: self.spd_get_linear_num, #self.num_points_sweep(
                    #    self.spd_start, self.spd_end, self.spd_step),
                1: self.spd_get_log_num, #self.SweepPulseDeltaPoints.value(),
                2: self.spd_get_list_num #len(self.I_list)
                }

        self.spd_points = self.spd_points_switch.get(
                self.spd_type_index, None)()

        self.list_label = None
        self.window_title = None
        self.I_list_points = 0
        self.compliance_list_points = 0
        self.cycle_list_points = 0

        self.spd_sweep_arm_switch = {
            0: self.spd_arm_linear_sweep,
            1: self.spd_arm_log_sweep,
            2: self.spd_arm_custom_sweep
            }

        #$%% Initial Filtering Variables
        self.filter_on = False
        self.filter_command = None

        #%% Initial General Variables
        self.current_tab = self.TabWidget.currentIndex()
        self.filename = None
        self.currentfile = None
        self.header_string = None
        self.I_source_list = None
        self.I_source = None
        self.V_meter_connected = 0
        self.rm = visa.ResourceManager()
        self.resources = self.rm.list_resources()
        self.connected = False
        self.armed = 0
        self.num_points = 0
        self.datalist = []
        self.volt_array = []
        self.time_array = []
        self.avg_volt_array = []
        self.curr_array = []
        self.num_array = []

        self.source_range_type_index = self.SourceRangeType.currentIndex()
        self.source_range_index = self.SourceRangeValue.currentIndex()
        self.volt_range_index = self.VoltmeterRangeValue.currentIndex()
        self.compliance_voltage = self.ComplianceVoltage.value()
        self.voltmeter_rate = str(self.dIdVRate.value())
        self.units_index = self.UnitsComboBox.currentIndex()


        self.message_box = QMessageBox()
        self.list_box = QInputDialog()
        self.list_box.setInputMode(0)

        self.cmd = None
        self.errors_exist = False
        self.error_queue = deque([])
        self.error_code = None

        self.signals_slots_dict = {
                "combo": {
                        # Comboboxes. Set Disabled at runtime. Signal is
                        # "currentIndexChanged"
                        self.SourceRangeType: self.update_source_range_type,
                        self.SourceRangeValue: self.update_source_range,
                        self.VoltmeterRangeValue: self.update_volt_range,
                        self.SweepTypeComboBox: self.update_spd_sweep_type,
                        self.UnitsComboBox: self.update_units,
                        self.DeltaFilterComboBox: self.set_filtering,
                        self.FixedPulseDeltaComboBox: self.set_filtering
                        },
                "field": {
                        # Fields to type settings. Set to "Read Only" at run.
                        # Signal is "editingFinished"
                        self.GPIB: self.update_GPIB,
                        self.ComplianceVoltage: self.update_compliance,
                        self.FilePath: self.new_file,
                        self.dIdVDelay: self.update_dIdV_vars,
                        self.dIdVDeltaCurr: self.update_dIdV_vars,
                        self.dIdVRate: self.update_volt_rate,
                        self.dIdVStartCurr: self.update_dIdV_vars,
                        self.dIdVStepSize: self.update_dIdV_vars,
                        self.dIdVStopCurr: self.update_dIdV_vars,
                        self.dIdVFilterWindow: self.update_dIdV_vars,
                        self.dIdVFilterCount: self.update_dIdV_vars,
                        self.DeltaDelay: self.update_delta_vars,
                        self.DeltaHighCurr: self.update_delta_vars,
                        self.DeltaLowCurr: self.update_delta_vars,
                        self.DeltaPulseCount: self.update_delta_vars,
                        self.DeltaRate: self.update_volt_rate,
                        #Add Filtering
                        self.DeltaFilterWindow: self.update_delta_vars,
                        self.DeltaFilterCount: self.update_delta_vars,
                        self.FixedPulseDeltaCount:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaCycle:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaDelay:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaHighI:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaLowI:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaWidth:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaFilterWindow:
                            self.update_fixed_pulse_delta_vars,
                        self.FixedPulseDeltaFilterCount:
                            self.update_fixed_pulse_delta_vars,
                        self.SweepPulseDeltaCycle:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaEndI:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaIStep:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaPoints:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaStartI:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaSweeps:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaWidth:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaFilterWindow:
                            self.update_sweep_pulse_delta_vars,
                        self.SweepPulseDeltaFilterCount:
                            self.update_sweep_pulse_delta_vars
                        },
                "button1": {
                        # Buttons on the UI. Set to do nothing at runtime.
                        # Signal is "clicked"
                        self.StartButton: self.run_measurement,
                        self.ComplianceVoltageList:
                            self.create_compliance_list,
                        self.SaveNewButton: self.new_file,
                        self.CalibrateButton: self.calibrate_meter,
                        self.SweepPulseDeltaCycleList:
                            self.create_cycle_list,
                        self.SweepPulseDeltaIList: self.create_I_list
                        },
                "button2": {
                        # Buttons on the UI that maintain functionality during
                        # runtime. Signal is "clicked"
                        self.ClearButton: self.clear_graphs,
                        self.StopButton: self.stop_measurement,
                        self.ExitButton: self.exit
                        },
                "checkbox": {
                        # Checkboxes in the UI. Set to setCheckable(False) at
                        # run. Signal is "clicked""
                        self.ComplianceAbortCheckBox:
                            self.set_compliance_abort,
                        self.FixedPulseDeltaLowMeasure: self.set_low_measure,
                        self.SweepPulseDeltaLowMeasure: self.set_low_measure,
                        self.dIdVFilterCheckbox: self.update_filter_on,
                        self.DeltaFilterCheckbox: self.update_filter_on,
                        self.FixedPulseDeltaFilterCheckbox:
                            self.update_filter_on,
                        self.SweepPulseDeltaFilterCheckbox:
                            self.update_filter_on
                        },
                "tab": {
                        # The tab widget in the UI. Unlinks the signal at run.
                        # Signal is "currentChanged"
                        self.TabWidget: self.update_tab
                        }
                }


        self.source_range_switch = {
                0: "CURR:RANG 2e-9",
                1: "CURR:RANG 20e-9",
                2: "CURR:RANG 200e-9",
                3: "CURR:RANG 2e-6",
                4: "CURR:RANG 20e-6",
                5: "CURR:RANG 200e-6",
                6: "CURR:RANG 2e-3",
                7: "CURR:RANG 20e-3",
                8: "CURR:RANG 100e-3"
        }

        self.source_range_type_switch = {
                1: "CURR:RANG:AUTO ON", # Delta autorange
                2: "SOUR:PDEL:RANG BEST", # Fixed Pulse Delta best range
                3: "SOUR:SWE:RANG BEST", # Sweep Pulse Delta best range
                4: "CURR:RANG:AUTO OFF", # Delta Fixed range
                5: "SOUR:PDEL:RANG FIX", # Fixed Pulse Delta Fixed range
                6: "SOUR:SWE:RANG FIX" # Sweep Pulse Delta Fixed range
                }

        self.source_range_type_query = {
                0: "CURR:RANG:AUTO?",
                1: "CURR:RANG:AUTO?", # Delta range query
                2: "SOUR:PDEL:RANG?", # Fixed Pulse Delta range type query
                3: "SOUR:SWE:RANG?" # Sweep Pulse Delta range query
                }

        self.volt_range_switch = {
                0: "SYST:COMM:SER:SEND ':SENS:VOLT:RANG 10e-3'",
                1: "SYST:COMM:SER:SEND ':SENS:VOLT:RANG 100e-3'",
                2: "SYST:COMM:SER:SEND ':SENS:VOLT:RANG 1'",
                3: "SYST:COMM:SER:SEND ':SENS:VOLT:RANG 10'",
                4: "SYST:COMM:SER:SEND ':SENS:VOLT:RANG 100'"
                }

        self.unit_switch = {
                0: "UNIT V",
                1: "UNIT SIEM",
                2: "UNIT OHMS",
                3: "UNIT W; POWER AVER",
                4: "UNIT W; POWER PEAK"
                }

        self.header_string_unit_switch = {
                0: "Reading (V)",
                1: "Reading (S)",
                2: "Reading (Ohms)",
                3: "Reading (W, avg.)",
                4: "Reading (W, peak)"
                }

        self.update_variables_switch = {
                0: self.update_dIdV_vars,
                1: self.update_delta_vars,
                2: self.update_fixed_pulse_delta_vars,
                3: self.update_sweep_pulse_delta_vars
                }

        self.arm_switch = {
                0: self.arm_dIdV,
                1: self.arm_delta,
                2: self.arm_fixed_pulse_delta,
                3: self.arm_sweep_pulse_delta
                }

        self.query_arm_switch = {
                0: "SOUR:DCON:ARM?",
                1: "SOUR:DELT:ARM?",
                2: "SOUR:PDEL:ARM?",
                3: "SOUR:PDEL:ARM?"
                }

        self.measurement_type_switch = {
                0: self.get_dIdV_parameter_string,
                1: self.get_delta_parameter_string,
                2: self.get_fpd_parameter_string,
                3: self.get_spd_parameter_string
                }

        self.filter_window_switch = {
                0: self.dIdVFilterWindow.value,
                1: self.DeltaFilterWindow.value,
                2: self.FixedPulseDeltaFilterWindow.value,
                3: self.SweepPulseDeltaFilterWindow.value
                }

        self.filter_count_switch = {
                0: self.dIdVFilterCount.value,
                1: self.DeltaFilterCount.value,
                2: self.FixedPulseDeltaFilterCount.value,
                3: self.SweepPulseDeltaFilterCount.value
                }

        self.filter_on_switch = {
                0: self.dIdVFilterCheckbox.isChecked,
                1: self.DeltaFilterCheckbox.isChecked,
                2: self.FixedPulseDeltaFilterCheckbox.isChecked,
                3: self.SweepPulseDeltaFilterCheckbox.isChecked
                }

        self.error_messages = {
                0: ("Invalid DC source (6221) address. Ensure the instrument "
                    + "is connected with the correct GPIB address input."),
                1: ("Voltmeter is not connected to the 6221. Check the RS232 "
                    + "connection."),
                2: "No file selected. Please specify a location to save data.",
                3: ("Number of points requested exceeds maximum buffer size"
                    + " (65,536).")
                }

    #%% Initial function calls
        for k, v in self.signals_slots_dict["combo"].items():
            k.currentIndexChanged.connect(v)
        for k, v in self.signals_slots_dict["field"].items():
            k.editingFinished.connect(v)
        for k, v in self.signals_slots_dict["button1"].items():
            k.clicked.connect(v)
        for k, v in self.signals_slots_dict["button2"].items():
            k.clicked.connect(v)
        for k, v in self.signals_slots_dict["checkbox"].items():
            k.clicked.connect(v)
        for k, v in self.signals_slots_dict["tab"].items():
            k.currentChanged.connect(v)

        self.update_GPIB()
        self.update_sweep_pulse_delta_vars()
        self.update_fixed_pulse_delta_vars()
        self.update_delta_vars()
        self.update_dIdV_vars()


    #%% Differential Conductance Methods
    def update_dIdV_vars(self):
        self.dIdV_start = self.dIdVStartCurr.value() * 1E-6
        self.dIdV_stop = self.dIdVStopCurr.value() * 1E-6
        self.dIdV_step = self.dIdVStepSize.value() * 1E-6
        self.dIdV_delta = self.dIdVDeltaCurr.value() * 1E-6
        self.dIdV_delay = self.dIdVDelay.value() * 1E-3
        #self.dIdV_rate = self.dIdVRate.value()
        self.update_volt_rate()
        #self.set_low_measure()
        self.dIdV_num_points = self.num_points_sweep(
                self.dIdV_start, self.dIdV_stop, self.dIdV_step)
        self.num_points = self.dIdV_num_points
        self.set_filtering()
        self.dIdV_parameter_string = ("Measured Differential Conductance \n"
                    + "Start Current (uA) = " + str(self.dIdVStartCurr.value())
                    + "\t"
                    + "End Current (uA) = " + str(self.dIdVStopCurr.value())
                    + "\t"
                    + "Step Size (uA) = " + str(self.dIdVStepSize.value())
                    + "\t"
                    + "Delta Current (uA) = " + str(self.dIdVDeltaCurr.value())
                    + "\t"
                    + "Delay (ms) = " + str(self.dIdVDelay.value()) + "\t"
                    + "Rate (PLC) = " + self.voltmeter_rate + "\t"
                    + "Compliance Voltage (V) = "
                    + str(self.compliance_voltage) + "\t"
                    + str(self.filter_command)
                    + "\n" + "\n"
                    )
        #print(self.num_points)

    def get_dIdV_parameter_string(self):
#        print(self.dIdV_parameter_string)
        return self.dIdV_parameter_string

    #%% Delta Methods
    def update_delta_vars(self):
        self.delta_high = self.DeltaHighCurr.value()*1E-6
        self.delta_low = self.DeltaLowCurr.value()*1E-6
        self.delta_num_points = self.DeltaPulseCount.value()
        self.num_points = self.delta_num_points
        #print(self.num_points)
        self.delta_delay = self.DeltaDelay.value()*1E-3
        self.delta_rate = self.DeltaRate.value()
        self.update_volt_rate()
        self.set_filtering()
        self.delta_parameter_string = ("Measured Delta \n"
                    + "High Current (uA) = " + str(self.DeltaHighCurr.value())
                    + "\t"
                    + "Low Current (uA) = " + str(self.DeltaLowCurr.value())
                    + "\t"
                    + "Pulse Count = " + str(self.delta_num_points) + "\t"
                    + "Delay (ms) = " + str(self.DeltaDelay.value()) + "\t"
                    + "Measurement Rate (PLC) = " + self.voltmeter_rate + "\t"
                    + "Compliance Voltage (V) = "
                    + str(self.compliance_voltage) + "\t"
                    + str(self.filter_command)
                    + "\n" + "\n"
                    )

    def get_delta_parameter_string(self):
#        print(self.delta_parameter_string)
        return self.delta_parameter_string

    #%% Fixed Pulse Delta Methods
    def update_fixed_pulse_delta_vars(self):
        self.fpd_high = self.FixedPulseDeltaHighI.value() * 1E-6
        self.fpd_low = self.FixedPulseDeltaLowI.value() * 1E-6
        self.fpd_delay = self.FixedPulseDeltaDelay.value() * 1E-6
        self.fpd_num_points = self.FixedPulseDeltaCount.value()
        self.num_points = self.fpd_num_points
        #print(self.num_points)
        self.fpd_width = self.FixedPulseDeltaWidth.value() * 1E-6
        self.fpd_cycle = self.FixedPulseDeltaCycle.value()
        self.DutyCycle.setValue(self.fpd_width/(self.fpd_cycle * 0.016667) * 100)
        self.set_low_measure()
        self.set_filtering()
        self.fpd_parameter_string = ("Measured Fixed Pulse Delta \n"
                 + "High Current (uA) = "
                 + str(self.FixedPulseDeltaHighI.value()) + "\t"
                 + "Low Current (uA) = "
                 + str(self.FixedPulseDeltaLowI.value()) + "\t"
                 + "Pulse Count = " + str(self.fpd_num_points) + "\t"
                 + "Delay (ms) = " + str(self.FixedPulseDeltaDelay.value())
                 + "\t"
                 + "Pulse Width (us) = "
                 + str(self.FixedPulseDeltaWidth.value()) + "\t"
                 + "Cycle Interval (PLC) = " + str(self.fpd_cycle) + "\t"
                 + "Low Measurements = " + self.low_measure + "\t"
                 + "Compliance Voltage (V) = " + str(self.compliance_voltage)
                 + "\t" + str(self.filter_command)
                 + "\n" + "\n"
                )

    def get_fpd_parameter_string(self):
#        print(self.fpd_parameter_string)
        return self.fpd_parameter_string

    #%% Sweep Pulse Delta Methods
    def update_sweep_pulse_delta_vars(self):
        self.spd_start = self.SweepPulseDeltaStartI.value() * 1E-6
        self.spd_end = self.SweepPulseDeltaEndI.value() * 1E-6
        self.spd_step = self.SweepPulseDeltaIStep.value() * 1E-6
        self.spd_delay = self.SweepPulseDeltaCycle.value() * 16.667E-3
        self.spd_type_index = int(self.SweepTypeComboBox.currentIndex())
        self.spd_num_sweeps = self.SweepPulseDeltaSweeps.value()
        self.spd_points = self.spd_points_switch.get(
                self.spd_type_index, None)()
        if self.spd_type_index != 1:
            self.SweepPulseDeltaPoints.setReadOnly(False)
            self.SweepPulseDeltaPoints.setValue(self.spd_points)
            self.SweepPulseDeltaPoints.setReadOnly(True)
        self.spd_num_points = self.spd_points * self.spd_num_sweeps
        self.num_points = self.spd_num_points
        #print(self.num_points)
        self.spd_width = self.SweepPulseDeltaWidth.value() * 1E-6
        self.set_low_measure()
        self.set_filtering()
        self.update_spd_parameter_string()


    def get_spd_parameter_string(self):
        return self.spd_parameter_string

    def update_spd_parameter_string(self):
        if self.spd_type_index < 2:
            self.spd_parameter_string = ("Measured Sweep Pulse Delta \n"
                 + "Sweep type = " + ("Log \t" if self.spd_type_index
                                      else "Linear \t")
                 + "Start Current (uA) = "
                 + str(self.SweepPulseDeltaStartI.value()) + "\t"
                 + "Stop Current (uA) = "
                 + str(self.SweepPulseDeltaEndI.value()) + "\t"
                 + ("Step Size (uA) = "
                    + str(self.SweepPulseDeltaIStep.value()) + "\t"
                    if not self.spd_type_index else "")
                 + "Pulse Count = " + str(self.spd_points) + "\t"
                 + "Pulse Width (us) = "
                 + str(self.SweepPulseDeltaWidth.value()) + "\t"
                 + "Cycle Interval (PLC) = "
                 + str(self.SweepPulseDeltaCycle.value()) + "\t"
                 + "Low Measurements = " + self.low_measure + "\t"
                 + "Number Sweeps = " + str(self.spd_num_sweeps) + "\t"
                 + "Compliance Voltage (V) = " + str(self.compliance_voltage)
                 + "\t" + str(self.filter_command)
                 + "\n" + "\n"
                 )
        else:
            self.spd_parameter_string = ("Measured Sweep Pulse Delta \n"
                     + "Sweep Type = Custom \t"
                     + "Pulse Count = " + str(self.spd_points) + "\t"
                     + "Pulse Width (us) = " + str(self.spd_width * 1E6) + "\t"
                     + "Low Measurements = " + self.low_measure + "\t"
                     + "Number Sweeps = " + str(self.spd_num_sweeps) + "\t"
                     + (("\n" + self.get_filter_string() if self.filter_on
                         else "\n #NoFilter")
                     + "\n" + "\n"
                     ))

    def spd_get_linear_num(self):
#        print(self.num_points_sweep(self.spd_start, self.spd_end,
#                                      self.spd_step))
        return (self.num_points_sweep(self.SweepPulseDeltaStartI.value(),
                                      self.SweepPulseDeltaEndI.value(),
                                      self.SweepPulseDeltaIStep.value()))

    def spd_get_log_num(self):
        return self.SweepPulseDeltaPoints.value()

    def spd_get_list_num(self):
        return len(self.I_list_float)

    def update_spd_sweep_type(self):
        self.spd_type_index = self.SweepTypeComboBox.currentIndex()
        self.update_sweep_pulse_delta_vars()
        self.update_spd_parameter_string()
        if self.spd_type_index == 1:
            self.SweepPulseDeltaStartI.setReadOnly(False)
            self.SweepPulseDeltaEndI.setReadOnly(False)
            self.SweepPulseDeltaIStep.setReadOnly(True)
            self.SweepPulseDeltaCycle.setReadOnly(False)
            self.SweepPulseDeltaPoints.setReadOnly(False)
        elif self.spd_type_index == 2:
            #self.spd_points_switch[2] = int(self.I_source.query(
            #        "SOUR:LIST:CURR:POIN?"))
            self.spd_points = self.spd_points_switch.get(self.spd_type_index,
                                                         None)()
            self.SweepPulseDeltaStartI.setReadOnly(True)
            self.SweepPulseDeltaPoints.setReadOnly(False)
            self.SweepPulseDeltaPoints.setValue(int(self.spd_points))
            self.SweepPulseDeltaPoints.setReadOnly(True)
            self.SweepPulseDeltaEndI.setReadOnly(True)
            self.SweepPulseDeltaIStep.setReadOnly(True)
            self.SweepPulseDeltaCycle.setReadOnly(True)
            #if self.cycle_list:
            #    self.SweepPulseDeltaCycle.setValue(self.cycle_list_float[0])
        else:
            self.spd_points = self.spd_points_switch.get(self.spd_type_index,
                                                         None)()
#            print("spd points = " + str(self.spd_points))
            self.SweepPulseDeltaPoints.setReadOnly(False)
            self.SweepPulseDeltaPoints.setValue(int(self.spd_points))
            self.SweepPulseDeltaStartI.setReadOnly(False)
            self.SweepPulseDeltaEndI.setReadOnly(False)
            self.SweepPulseDeltaIStep.setReadOnly(False)
            self.SweepPulseDeltaCycle.setReadOnly(False)
            self.SweepPulseDeltaPoints.setReadOnly(True)

    def create_compliance_list(self):
        """Open a dialog box and create a compliance list for a custom sweep.
        Will save the list so that it may be passed to the instruments.

        SLIGHTLY BUGGY BUT OK
        """
        self.compliance_list = None
        self.list_label = ("Enter a list of compliance voltages (V) separated "
                      "by commas (e.g. 1, 2, 3). Range is 0.1 to 105. Must "
                      "have same number of points as current list or be "
                      "empty. An empty list will turn autocopy on.")
        self.window_title = "Compliance Voltages"

        if self.spd_type_index == 2 and self.connected:
            self.compliance_list = self.list_box.getText(self, self.window_title,
                                                    self.list_label)[0]
            if self.compliance_list:
                self.I_source.write("SOUR:LIST:COMP " + self.compliance_list)
                self.compliance_list = list(
                    map(float, re.sub(',', '', self.compliance_list).split())
                    )
                self.ComplianceVoltage.setValue(self.compliance_list[0])
            else:
                self.cmd = ', '.join(str(e) for e in
                                   [self.ComplianceVoltage.value()
                                   for x in range(self.spd_points)])
                self.I_source.write("SOUR:LIST:COMP " + self.cmd)
                #self.I_source.write(self.autocopy_on + "; SOUR:LIST:COMP "
                #                    + str(self.ComplianceVoltage.value()))
            print(self.I_source.query("SOUR:LIST:COMP?"))
            self.update_spd_sweep_type()

    def create_I_list(self):
        """Open a dialog box and create a current list for a custom sweep.
        Will return the list as a string so that it may be passed to the
        instruments.

        SLIGHTLY BUGGY BUT OK
        """
        self.I_list = ['0']
        self.list_label = ("Enter a list of source currents (A) separated by "
                           "commas (e.g., 1e-3, 2e-6, 3e-4). Range is -0.105 "
                           "to 0.105. If empty list, sets 1-point list with "
                           "output current 0.")
        self.window_title = "Current Biases"

        if self.spd_type_index == 2 and self.connected:
            self.I_list = self.list_box.getText(self, self.window_title,
                                            self.list_label)[0]
            self.I_source.write("SOUR:LIST:CURR " + self.I_list)
            print(self.I_source.query("SOUR:LIST:CURR?"))
            self.I_list_float = list(
                    map(float, re.sub(',', '', self.I_list).split())
                    )
            if not self.I_list:
                self.I_source.write("SOUR:LIST:CURR 0")
                self.I_list = ['0']
                self.I_list_float = [0]
            else:
                self.SweepPulseDeltaStartI.setValue(self.I_list_float[0]*1E6)
                self.SweepPulseDeltaEndI.setValue(self.I_list_float[-1]*1E6)
#            self.spd_points_switch[2] = int(self.I_source.query(
#            "SOUR:LIST:CURR:POIN?"))
            #self.spd_points = int(self.I_source.query("SOUR:LIST:CURR:POIN?"))
            self.update_spd_sweep_type()

    def create_cycle_list(self):
        """Open a dialog box and create a cycle interval list for a custom
        sweep. Will return the list as a string so that it may be passed to the
        instruments.

        SLIGHTLY BUGGY BUT OK
        """
        self.cycle_list = None
        self.list_label = ("Enter a list of cycle times (in integer PLC) "
                           "separated by commas (e.g., 1, 5, 7). Must "
                           "have same number of points as current list or be "
                           "empty. An empty list will autocopy the cycle time."
                           )
        self.window_title = "Cycle Intervals"
        if self.spd_type_index == 2 and self.connected:
            self.cycle_list = self.list_box.getText(self, self.window_title,
                                                    self.list_label)[0]
            self.cycle_list_float =list(
                    map(float, re.sub(',', '', self.cycle_list).split())
                    )

            self.cycle_list_time = [i * 16.667e-3 for i
                                    in self.cycle_list_float]

            if self.cycle_list:
                self.cmd = ", ".join(str(e) for e in
                                   self.cycle_list_time)
                print(self.cmd)
                self.I_source.write("SOUR:LIST:DEL " + self.cmd)
                self.SweepPulseDeltaCycle.setValue(self.cycle_list_float[0])

            #print(self.I_source.query("SOUR:LIST:COMP:POIN?"))

            else:
                self.cmd = ', '.join(str(e) for e in
                                   [self.SweepPulseDeltaCycle.value()*16.667e-3
                                   for x in range(self.spd_points)])
                self.cycle_list_float = [self.SweepPulseDeltaCycle.value()
                                        for x in range(self.spd_points)]
                self.cycle_list = ' '.join(str(e) for e in
                                           self.cycle_list_float)
                self.I_source.write("SOUR:LIST:DEL " + self.cmd)
            #print(self.I_source.query("SOUR:LIST:DEL?"))
            self.update_spd_sweep_type()

    def spd_arm_linear_sweep(self):
        self.I_source.write("SOUR:SWE:SPAC LIN")
        self.cmd = ("SOUR:DEL " + str(self.spd_delay)
                    + "; CURR:STAR " + str(self.spd_start)
                    + "; STOP " + str(self.spd_end)
                    + "; STEP " + str(self.spd_step)
                    )
        self.I_source.write(self.cmd)

    def spd_arm_log_sweep(self):
        self.I_source.write("SOUR:SWE:SPAC LOG; POIN " + str(self.spd_points))
        self.cmd = ("SOUR:DEL " + str(self.spd_delay)
                    + "; CURR:STAR " + str(self.spd_start)
                    + "; STOP " + str(self.spd_end)
                    )
        self.I_source.write(self.cmd)

    def spd_arm_custom_sweep(self):
        self.I_source.write("SOUR:SWE:SPAC LIST")

    #%% Filtering Methods
    def set_filtering(self):
        self.cmd = ("SENS:AVER:TCON " + self.get_filter_type()
                    + "; WIND "
                    + str(self.filter_window_switch.get(self.current_tab, 0)())
                    + "; COUN "
                    + str(self.filter_count_switch.get(self.current_tab, 10)())
                    )
        self.filter_command = self.cmd
        if self.connected:
            self.I_source.write(self.cmd)
#            print("Setting filtering")
#            self.run_error_messages()
            self.cmd = "SENS:AVER " + ("ON; " if self.filter_on else "OFF; ")
            self.filter_command += " " + self.cmd
            self.I_source.write(self.cmd)
#            print("Toggling Filtering")
#            self.run_error_messages()

    def get_filter_string(self):
        return ("Filter Type = " + self.get_filter_type()
                         + "Filter Window = " + str(
                           self.filter_window_switch.get(self.current_tab, 0)()
                             )
                         + "Filter Count = " + str(
                           self.filter_count_switch.get(self.current_tab, 0)())
                         )


    def update_filter_on(self):
        self.filter_on = self.filter_on_switch.get(self.current_tab, False)()
        self.set_filtering()

    def get_filter_type(self):
        if not self.current_tab:
            return "REP"
        elif self.current_tab == 1:
            if self.DeltaFilterComboBox.currentIndex():
                return "REP"
            else:
                return "MOV"
        elif self.current_tab == 2:
            if self.FixedPulseDeltaComboBox.currentIndex():
                return "REP"
            else:
                return "MOV"
        else:
            return "MOV"



    #%% General Methods
    def set_compliance_abort(self):
        """TEST"""
        self.CAB = "ON" if self.ComplianceAbortCheckBox.isChecked() else "OFF"

    def set_low_measure(self):
        """TEST"""

        if self.current_tab-2:
            self.low_measure = ("2"
                                if self.SweepPulseDeltaLowMeasure.isChecked()
                                else "1")
        else:
            self.low_measure = ("2"
                                if self.FixedPulseDeltaLowMeasure.isChecked()
                                else "1")

    def num_points_sweep(self, start, stop, step):
        """Calculate the number of points in a sweep."""
        return(abs((stop - start)//step) + 1)

    def update_source_range_type(self):
        """If instruments are connected, set the source range type based on the
        combo box selection and the measurement type. The function inside get()
        returns unique keys for all non-differential conductance measurements.
        Since differential conductance automatically has 'best' ranging, its
        keys don't matter.

        WORKING"""
        self.source_range_type_index = self.SourceRangeType.currentIndex()
        self.cmd = None
        if self.current_tab:
            self.cmd = self.source_range_type_switch.get(
                    self.current_tab + 3*self.source_range_type_index, None)
        if self.cmd and self.connected:
            self.I_source.write(self.cmd)
            self.update_source_range()

    def update_source_range(self):
        """If instruments are connected and 'fixed' ranging is selected for the
        source, set the range for the current source.

        WORKING"""
        self.source_range_index = self.SourceRangeValue.currentIndex()
        self.cmd = None
        if self.source_range_type_index and self.connected:
            self.cmd = self.source_range_switch.get(
                    self.source_range_index, None)
            self.I_source.write(self.cmd)

    def update_volt_range(self):
        """"If instruments connected and the voltmeter is set to manual
        ranging, update the value of the voltmeter range.

        WORKING"""
        self.volt_range_index = self.VoltmeterRangeValue.currentIndex()
        self.cmd = self.volt_range_switch.get(self.volt_range_index, None)
        if self.connected:
           self.I_source.write(self.cmd)

    def update_volt_rate(self):
        """If instruments connected, update voltmeter rate. Only functional for
        dIdV and delta measurements.

        WORKING"""
        self.cmd = None
        if self.connected:
            self.cmd = ("SYST:COMM:SER:SEND ':SENS:VOLT:NPLC "
                        + (str(self.DeltaRate.value()) if self.current_tab
                           else str(self.dIdVRate.value())) + "'")
            self.voltmeter_rate = (str(self.DeltaRate.value())
                                    if self.current_tab
                                    else str(self.dIdVRate.value()))
            self.I_source.write(self.cmd)

    def update_compliance(self):
        """If the instruments are connected and the user alters the compliance
        voltage, send a command to update the instruments.

        WORKING"""
        self.compliance_voltage = str(self.ComplianceVoltage.value())
        #self.cmd = None
        if self.connected:
            self.cmd = "CURR:COMP " + self.compliance_voltage
            self.I_source.write(self.cmd)

    def update_units(self):
        """If instruments connected and the user alters the specified units in
        the dropdown menu, send a command to update the unit type.

        WORKING"""
        self.units_index = self.UnitsComboBox.currentIndex()
        self.cmd = None
        if self.connected:
            self.cmd = self.unit_switch.get(self.units_index, None)
            self.I_source.write(self.cmd)
            self.update_header_string()


    def clear_buffer(self):
        """FIGURE OUT HOW TO DO PROPERLY"""
        self.cmd = "TRAC:CLE"
        self.I_source.write(self.cmd)
        self.in_buffer = int(self.I_source.query("TRAC:POIN:ACT?"))

    def calibrate_meter(self):
        """FIGURE OUT HOW TO DO PROPERLY

        self.cmd = None
        if self.connected:
            self.cmd = ("SYST:COMM:SER:SEND :CAL:UNPR:ACAL:INIT; "
                        + "SYST:COMM:SER:SEND :CAL:UNPR:ACAL:STEP2; "
                        + "SYST:COMM:SER:SEND :CAL:UNPR:ACAL:DONE")"""
        print("meter calibrated")

    def update_tab(self):
        """If the user selects a different measurement type from the tab menu,
        update the variables and the ranging.

        WORKING"""
        self.current_tab = self.TabWidget.currentIndex()
#        print("Tab = " + str(self.current_tab))
        self.update_source_range_type()
        self.update_variables_switch[self.current_tab]()
        self.update_header_string()
        self.update_filter_on()

    def update_GPIB(self):
        """Check GPIB address of current source and initialize if valid.

        If the user-given GPIB address for the 6221 is in the list of
        resources, then assign it to self.I_source and send the following
        commands: reset instrument, change output response to slow.
        Note if GPIB address is not in the resource list. Either way, update
        connected flag accordingly."""
        self.check_errors(False, False)
        #self.I_source_list = [
        #        x for x in self.resources
        #        if (str(self.GPIB.value()) and 'GPIB') in x
        #        ]

        if not self.errors_exist:
            self.I_source = self.rm.open_resource(self.I_source_list[0])
            self.I_source.write('*RST; OUTP:RESP SLOW')
            self.connected = bool(self.I_source) and self.V_meter_connected
        if self.connected:
            self.update_source_range_type()
            self.update_source_range()
            self.update_volt_range()
            self.set_compliance_abort()
            self.in_buffer = int(self.I_source.query("TRAC:POIN:ACT?"))

    def update_header_string(self):
        self.header_string = ''.join(
                [self.measurement_type_switch.get(self.current_tab)(),
                self.header_string_unit_switch.get(self.units_index), '\t',
                'timestamp (s)', '\t', 'Current (A)', '\t', 'Avg. Voltage (V)',
                '\t', 'Reading Number']
                )
#        print(self.header_string)

    def new_file(self):
        """Create/overwrite a new save file and write a standard header.

        Open a dialog box that allows the user to name the .txt file the
        program will write measurements to. Record the name of this file, open
        it for writing (overwrite all previous data), and write a header to
        the file. Reset the local variable for number of measured points and
        set the number of saved files to 1 if user saves a file. This does not
        occur if the user instead clicks cancel.

        FIGURE OUT HOW DATA IS SAVED FOR HEADER STRINGS"""
        self.filename = QFileDialog.getSaveFileName(
                None, 'Title', '', 'TXT (*.txt)'
                )
        if self.filename[0]:
            self.currentfile = open(self.filename[0], 'w')
            (self.base_name, self.ext) = os.path.splitext(self.filename[0])
            self.FilePath.setText(self.filename[0])

    def clear_graphs(self):
        print("graphs cleared")

    def arm_dIdV(self):
        # Send all commands, then arm.
        # MOSTLY WORKING VERIFY BUFFER
        #self.update_volt_rate()
        self.set_filtering()
        self.update_units()
        self.update_dIdV_vars()
        self.update_volt_range()
        self.update_source_range_type()
        self.cmd = (#"*RST"
                    "SOUR:DCON:STAR " + str(self.dIdV_start)
                    + "; STEP " + str(self.dIdV_step)
                    + "; STOP " + str(self.dIdV_stop)
                    + "; DELTA " + str(self.dIdV_delta)
                    + "; DELAY " + str(self.dIdV_delay)
                    + "; CAB " + self.CAB
                    )
        self.I_source.write(self.cmd)
        self.I_source.write("TRAC:POIN " + str(self.dIdV_num_points))
#        print(self.dIdV_num_points)
        self.I_source.write("SOUR:DCON:ARM")
        self.armed = '1' in self.I_source.query("SOUR:DCON:ARM?")

    def arm_delta(self):
        # Send all commands, then arm
        # MOSTLY WORKING VERIFY BUFFER
        self.set_filtering()
        self.update_volt_rate()
        self.update_source_range_type()
        self.update_delta_vars()
        self.cmd = None
        self.cmd = ("SOUR:DELT:HIGH " + str(self.delta_high)
                    + "; LOW " + str(self.delta_low)
                    + "; DEL " + str(self.delta_delay)
                    + "; COUN " + str(self.delta_num_points)
                    + "; CAB " + self.CAB
                    )
        self.I_source.write(self.cmd)
        self.I_source.write("TRAC:POIN " + str(self.delta_num_points))
        self.I_source.write("SOUR:DELT:ARM")
        self.armed = '1' in self.I_source.query("SOUR:DELT:ARM?")
#        self.num_points = self.delta_num_points

    def arm_fixed_pulse_delta(self):
        # Send all commands, then arm
        # MOSTLY WORKING VERIFY BUFFER
        self.set_filtering()
        self.update_source_range_type()
        self.update_fixed_pulse_delta_vars()
        self.cmd = None
        self.cmd = ("SOUR:PDEL:HIGH " + str(self.fpd_high)
                    + "; LOW " + str(self.fpd_low)
                    + "; WIDT " + str(self.fpd_width)
                    + "; SDEL " + str(self.fpd_delay)
                    + "; COUN " + str(self.fpd_num_points)
                    + "; INT " + str(self.fpd_cycle)
                    + "; SWE OFF"
                    + "; LME " + self.low_measure
                    )
        self.I_source.write(self.cmd)
        self.I_source.write("TRAC:POIN " + str(self.fpd_num_points))
        self.I_source.write("SOUR:PDEL:ARM")
        self.armed = '1' in self.I_source.query("SOUR:PDEL:ARM?")
#        print("fixed pulse delta armed = " + str(self.armed))

    def arm_sweep_pulse_delta(self):
        # Send all commands, then arm.
        # MOSTLY WORKING VERIFY BUFFER
        self.set_filtering()
        self.update_source_range_type()
        self.update_sweep_pulse_delta_vars()
        self.cmd = None
        self.cmd = (
                    "SOUR:PDEL:WIDT " + str(self.spd_width)
                    + "; COUN " + str(self.spd_points) # or spd_points*spd_num_sweeps
                    + "; LME " + self.low_measure
                    + "; SWE ON")
        self.I_source.write(self.cmd)
        self.cmd = (
                    "SOUR:SWE:COUN " + str(self.spd_num_sweeps)
                    + "; CAB " + self.CAB
                )
        self.I_source.write(self.cmd)
        self.spd_sweep_arm_switch.get(self.spd_type_index, None)()
        self.I_source.write("TRAC:POIN " + str(self.spd_num_points))
        self.I_source.write("SOUR:PDEL:ARM")
        self.armed = '1' in self.I_source.query("SOUR:PDEL:ARM?")
#        print("sweep pulse delta armed = " + str(self.armed))

    def run_measurement(self):
        # Part where it arms the measurement
        self.check_errors(False, True) # Change to True, True once files worked out
        if not self.errors_exist:
            self.clear_buffer()
            self.arm_switch[self.current_tab]()
            if self.armed:
                self.RunningButton.setChecked(True)
                for k, v in self.signals_slots_dict["combo"].items():
                    k.setEnabled(False)
                for k, v in self.signals_slots_dict["field"].items():
                    k.setReadOnly(True)
                for k, v in self.signals_slots_dict["button1"].items():
                    k.blockSignals(True)
                for k, v in self.signals_slots_dict["checkbox"].items():
                    k.setCheckable(False)
                for k, v in self.signals_slots_dict["tab"].items():
                    k.blockSignals(True)
                if self.currentfile:
                    self.currentfile.write(self.header_string)
                self.I_source.write("FORM:ELEM READ, TST, RNUM, SOUR, AVOL")
                self.I_source.write("INIT:IMM")
                time.sleep(5)
                print("Initializing and starting")
                self.run_error_messages()
                self.i = 0
                while (self.in_buffer < self.num_points
                       and self.i < 1000 * self.num_points):
                    self.in_buffer = int(self.I_source.query("TRAC:POIN:ACT?"))
                    self.i += 1
                    time.sleep(2)
#                    print("points in buffer = " + str( self.in_buffer) + '\n'
#                          + "total points = " + str(self.num_points))
                self.datalist = self.I_source.query("TRAC:DATA?").split(',')
                self.volt_array = [
                        x for (i, x) in enumerate(self.datalist)
                        if (not i % 5)
                        ]
                self.time_array = [
                        x for (i, x) in enumerate(self.datalist)
                        if (i % 5 == 1)
                        ]
                self.curr_array = [
                        x for (i, x) in enumerate(self.datalist)
                        if (i % 5 == 2)
                        ]
                self.avg_volt_array = [
                        x for (i, x) in enumerate(self.datalist)
                        if (i % 5 == 3)
                        ]
                self.num_array = [
                        x for (i, x) in enumerate(self.datalist)
                        if (i % 5 == 4)
                        ]
                self.num_array[-1].rstrip()
                self.datalist = [
                        x for y in (
                                self.datalist[i:i+1]
                                + (['\t'] * (i < len(self.datalist) - 0)
                                if (i % 5 != 4) else ['\n'])
                                for i in range(0, len(self.datalist), 1)
                                )
                        for x in y
                        ]
                del self.datalist[-1]
                self.datalist = ['\n'] + self.datalist
                self.datalist[-1].rstrip()
#                print(''.join(self.datalist))
                if self.currentfile:
                    self.currentfile.write(''.join(self.datalist))
                self.stop_measurement()
            else:
                print('Unarmed')
                self.run_error_messages()

    def stop_measurement(self):
        # Part where it disarms the measurement and wraps up
        if self.RunningButton.isChecked():
            for k, v in self.signals_slots_dict["combo"].items():
                k.setEnabled(True)
            for k, v in self.signals_slots_dict["field"].items():
                k.setReadOnly(False)
            for k, v in self.signals_slots_dict["button1"].items():
                k.blockSignals(False)
            for k, v in self.signals_slots_dict["checkbox"].items():
                k.setCheckable(True)
            for k, v in self.signals_slots_dict["tab"].items():
                k.blockSignals(False)
            self.I_source.write("SOUR:SWE:ABOR")
            print("Stopping Measurement")
            self.run_error_messages()
            #self.I_source.write("OUTP OFF; *RST")
            self.update_spd_sweep_type() # To reenable properly?
            # File closing stuff
            if self.currentfile:
                self.currentfile.close()
                self.currentfile = None
                self.FilePath.setText("")
            print("measurement stopped")
            self.RunningButton.setChecked(False)

    def check_errors(self, checkfile, checkbuffer):
        self.errors_exist = False
        self.error_queue = deque([])
        self.I_source_list = [
                x for x in self.resources
                if (str(self.GPIB.value()) and 'GPIB') in x
                ]
        if not self.I_source_list:
            self.I_source = False
            self.error_queue.append(0)
            self.errors_exist = True
            self.run_error_messages()
        else:
            self.I_source = self.rm.open_resource(self.I_source_list[0])
            self.V_meter_connected = self.I_source.query('SOUR:DCON:NVPR?')
            if not self.V_meter_connected:
                self.error_queue.append(1)
                self.errors_exist = True
                if not checkfile and not checkbuffer:
                    self.run_error_messages()
            if checkfile and not self.currentfile:
                self.error_queue.append(2)
                self.errors_exist = True
                if not checkbuffer:
                    self.run_error_messages
            if checkbuffer and ((self.dIdV_num_points > 65536
                                 and self.current_tab == 0)
                                or (self.delta_num_points > 65536
                                    and self.current_tab == 1)
                                or (self.fpd_num_points > 65536
                                    and self.current_tab == 2)
                                or (self.spd_num_points > 65536
                                    and self.current_tab == 3)):
                self.error_queue.append(3)
                self.errors_exist = True
                self.run_error_messages()


    def run_error_messages(self):
        """Create a dialog box explaining why measurement cannot start."""
        self.error = ""
        #while self.error_queue:
            #self.error += (self.error_messages.get(
             #       self.error_queue.popleft, None
              #      ) + " ")
        #self.error += self.I_source.query("STAT:QUE?")
        #print(self.error)
        #self.I_source.write("STAT:QUE:CLE")
        #self.message_box.setText(self.error)
        #self.message_box.exec_()

    def exit(self):
        self.stop_measurement()
        sys.exit()

def main():
    """Execute the UI loop"""
    app = QtGui.QApplication(sys.argv)
    form = dIdVGui()
    form.show()
    app.exec_()

if __name__ == '__main__':
    main()