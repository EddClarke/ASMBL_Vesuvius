# Copyright (c) 2017 Ruben Dulek
# The PostProcessingPlugin is released under the terms of the AGPLv3 or higher.

import re #To perform the search and replace.
import traceback
import sys

from ..Script import Script
from UM.Message import Message
from UM.Logger import Logger

from shapely import geometry

import numpy as np
#import matplotlib.pyplot as plt

class MoveInstruction:
    def __init__(self, instruction):

        instruction = instruction.split(" ")
        for arg in instruction:
            if "X" in arg:
                self.x = float(arg.split("X")[1])
            elif "Y" in arg:
                self.y = float(arg.split("Y")[1])
            elif "E" in arg:
                self.e = float(arg.split("E")[1])
            elif "F" in arg:
                self.f = float(arg.split("F")[1])


class Layer:

    def __init__(self, layer_instructions):
        self.extractGCodeLayer(layer_instructions)

    def extractGCodeLayer(self, gcode):
        move_instructions = []

        try:
            start = ";TYPE:WALL-OUTER"
            end = ";MESH:NONMESH"
            wall_gcode = gcode[gcode.find(start)+len(start):gcode.rfind(end)]
            #wall_gcode = re.search(';TYPE:WALL-OUTER(.*);MESH:NONMESH', gcode).group(1)
        except:
            return

        #Message(gcode, title = "Parsed GCode").show()
        for line in wall_gcode.splitlines():
            if len(line) <= 0:
                continue
            if (line[0] == "G") and (("X" in line) or ("Y" in line)):
                move_instructions.append(MoveInstruction(line))

        p = lambda arr: [(instruction.x, instruction.y) for instruction in arr]

        self.polygon = geometry.Polygon(p(move_instructions))

        #x,y = self.polygon.exterior.xy
        #plt.plot(x,y)

    def expand(self, distance):

        try:
            buffered_poly = self.polygon.buffer(distance)
            
            x_coords,y_coords = buffered_poly.exterior.xy
            x_coords = list(x_coords)
            y_coords = list(y_coords)

            instructions = []

            for i in range(len(x_coords)-1):
                ins = "G1 X" + str(x_coords[i]) + " Y" + str(y_coords[i]) + "\n"
                instructions.append(ins)

            return instructions

        except:
            return ""


class ASMBL_Processing(Script):
    """Enables Vesuvius' IDEX capabilities to use ASMBL
    """

    def __init__(self) -> None:
        super().__init__()

    def getSettingDataString(self):
        return """{
            "name": "ASMBL Vesuvius",
            "key": "Vesuvius",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "SubtractivePerimeter":
                {
                    "label": "Subtractive Tool Perimeter",
                    "description": "Distance the subtractive tool shall maintain from the model",
                    "type": "float",
                    "default_value": "3.5"
                },
                "ToSub":
                {
                    "label": "Subtractive Tool Macro",
                    "description": "Macro file to remap to tool 2",
                    "type": "str",
                    "default_value": "idex_remap_tool2.gcode"
                },
                "ToAdd":
                {
                    "label": "Additive Tool Macro",
                    "description": "Macro file to remap to tool 1",
                    "type": "str",
                    "default_value": "idex_remap_tool1.gcode"
                }
            }
        }"""

    def execute(self, data):
        #Message(str(sys.version), title = "Version").show()
        try:

            for i in range(2,len(data)-1):
                layer = Layer(data[i])

                new_instructions = 'M98 P"' + self.getSettingValueByKey("ToSub") + '";VESUVIUS SUBTRACTIVE\n'

                buffer_distance = self.getSettingValueByKey("SubtractivePerimeter")

                n = layer.expand(buffer_distance)

                for ins in n:
                    new_instructions += ins

                new_instructions += 'M98 P"' + self.getSettingValueByKey("ToAdd") + ';END OF VESUVIUS SUBTRACTIVE\n'

                data[i] += new_instructions

        except Exception as e:
            Message(traceback.format_exc(), title = "Exception").show()

        return data
