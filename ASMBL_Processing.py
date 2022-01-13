# Copyright (c) 2017 Ruben Dulek
# The PostProcessingPlugin is released under the terms of the AGPLv3 or higher.

from io import BufferedRandom
import re #To perform the search and replace.
import traceback
import sys

from shapely.geometry import multipolygon

from ..Script import Script
from UM.Message import Message
from UM.Logger import Logger

from UM.Application import Application

from shapely import geometry
from shapely.ops import unary_union

import numpy as np

try:
    import matplotlib.pyplot as plt
    import geopandas as gpd
except:
    Message(traceback.format_exc(), title = "Exception").show()

debug_layer_count = 0

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
        self.polygons = []
        self.extractGCodeLayer(layer_instructions)
        self.original_gcode = layer_instructions.splitlines()

    def extractGCodeLayer(self, gcode):
        gcode_lines = gcode.splitlines()

        while ";TYPE:WALL-OUTER" in gcode_lines:
            move_instructions = []
            start_index = gcode_lines.index(";TYPE:WALL-OUTER")
            for i in range(start_index+1,len(gcode_lines)-1):
                if i == -1:
                    break
                if not "E" in gcode_lines[i]:
                    break
                if not "X" in gcode_lines[i] and not "Y" in gcode_lines[i]:
                    continue
                move_instructions.append(MoveInstruction(gcode_lines[i]))

            p = lambda arr: [(instruction.x, instruction.y) for instruction in arr]
            self.polygons.append(geometry.Polygon(p(move_instructions)))
            
            del gcode_lines[start_index]

    def coords_to_instructions(self,coordinate_sets, extrude = True):
        #Coordinate sets: 2d tuple of coordinates, representing different 'islands' of geometry
        instructions = []
        for i in range(0,len(coordinate_sets)):
            for j in range(0,len(coordinate_sets[i])):

                coordinate = coordinate_sets[i][j]

                if extrude and j > 0:
                    E = 0

                    layerHeight = Application.getInstance().getGlobalContainerStack().getProperty("layer_height", "value")
                    extruderDiameter = Application.getInstance().getGlobalContainerStack().getProperty("machine_nozzle_size", "value")

                    dx = coordinate_sets[i][j][0] - coordinate_sets[i][j-1][0]
                    dy = coordinate_sets[i][j][1] - coordinate_sets[i][j-1][1]

                    distance = (dx)**2 + (dy**2)**0.5

                    E = (4 * layerHeight * distance) / (3.1415 * extruderDiameter) #SOURCE https://3dprinting.stackexchange.com/questions/6289/how-is-the-e-argument-calculated-for-a-given-g1-command

                    ins = "G1 X" + str(coordinate[0]) + " Y" + str(coordinate[1]) + " E" + str(E) + "\n"
                else:
                    ins = "G1 X" + str(coordinate[0]) + " Y" + str(coordinate[1]) + "\n"
                instructions.append(ins)

            #INSERT TRAVEL HERE?

        #Logger.log("d","Number of coordinates = "+str(len(instructions))) Not there yet
        Logger.log("d","Number of instructions = "+str(len(instructions)))
        Logger.log("d","Instructions (return of coords_to_instructions) = "+str(instructions))


        return instructions

    def expand(self, distance):
        global debug_layer_count

        additive_polys = []
        subtractive_polys = []

        lineWidth = Application.getInstance().getGlobalContainerStack().getProperty("line_width", "value")
        
        add_coordinates_set = []
        sub_coordinates_set = []

        
        for polygon in self.polygons:
            additive_polygon = polygon.buffer(lineWidth)
            subtractive_polygon = polygon.buffer(float(distance))

            additive_coords = list(additive_polygon.exterior.coords)
            add_coordinates_set.append(additive_coords)

            subtractive_coords = list(subtractive_polygon.exterior.coords)
            sub_coordinates_set.append(subtractive_coords)

        Logger.log("d","additive coords = " +str(add_coordinates_set))
        Logger.log("d","subtractive coords = " +str(sub_coordinates_set))

        add_instructions = self.coords_to_instructions(add_coordinates_set,extrude=True)
        sub_instructions = self.coords_to_instructions(sub_coordinates_set,extrude=False)

        #Logger.log("d","Number of coordinates = "+str(len(instructions))) Not there yet
        #Logger.log("d","Number of sub instructions = "+str(len(sub_instructions)))
        #Logger.log("d","Sub Instructions (return of expand) = "+str(sub_instructions))

        return add_instructions,sub_instructions


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
                "SubtractiveEnabled":
                {
                    "label": "Subtractive Tool Enabled",
                    "description": "Enables or disables the subtractive tool",
                    "type": "bool",
                    "default_value": "True"
                },
                "SubtractivePerimeter":
                {
                    "label": "Subtractive Tool Perimeter",
                    "description": "Distance the subtractive tool shall maintain from the model",
                    "type": "float",
                    "default_value": "3.5"
                },
                "SubtractiveFeedrate":
                {
                    "label": "Subtractive Feed Rate",
                    "description": "Feedrate for the Subtractive Tool",
                    "type": "int",
                    "default_value": "3000"
                },
                "AdditiveEnabled":
                {
                    "label": "Extra Additive Layer Enabled",
                    "description": "Enables or disables the additional additive layer",
                    "type": "bool",
                    "default_value": "False"
                },
                "AdditiveFeedrate":
                {
                    "label": "Additive Feed Rate",
                    "description": "Feedrate for the Extra Wall",
                    "type": "int",
                    "default_value": "3000"
                }
            }
        }"""

    def execute(self, data):
        global debug
        global debug_layer
        debug = self.getSettingValueByKey("DebugEnabled")
        debug_layer = self.getSettingValueByKey("DebugLayer")
        
        debug_layer_count = 0
        try:
            for i in range(2,len(data)-1):
                layer = Layer(data[i])

                buffer_distance = self.getSettingValueByKey("SubtractivePerimeter")
                add_instructions,sub_instructions = layer.expand(buffer_distance)

                #Logger.log("d", "Sub instructions (execute!) = " + str(sub_instructions))

                new_instructions = ""

                if self.getSettingValueByKey("AdditiveEnabled"):
                    new_instructions += "G1 F"+str(self.getSettingValueByKey("AdditiveFeedrate"))+";VESUVIUS EXTRA WALL\n"

                    for ins in add_instructions:
                        new_instructions += ins

                    new_instructions += ";END OF VESUVIUS EXTRA WALL\n"

                if self.getSettingValueByKey("SubtractiveEnabled"):
                    new_instructions += "T1;VESUVIUS SUBTRACTIVE\n"
                    new_instructions += "G1 F"+str(self.getSettingValueByKey("SubtractiveFeedrate"))+"\n"                

                    for ins in sub_instructions:
                        new_instructions += ins

                    new_instructions += "T0;END OF VESUVIUS SUBTRACTIVE\n"

                data[i] += new_instructions

        except Exception as e:
            Message(traceback.format_exc(), title = "Exception").show()

        Message("ASMBL Processing Complete", title = "Status").show()

        return data


#
#for polygon in self.polygons:
#            subtractive_polys.append(polygon.buffer(distance))
#            additive_polys.append(polygon.buffer(lineWidth))
#            
#
#        #DEBUGGING!
#        if debug:
#            debug_layer_count += 1#

#            if debug_layer_count == debug_layer:
#                try:
#                    fig, (axs1,axs2) = plt.subplots(1,2)

#                    axs1.title.set_text("Polygon Original")
#                    axs2.title.set_text("Polygon Buffered")

#                    #axs1.title.set_x("mm")
#                    #axs1.title.set_y("mm")

#                    #axs2.title.set_x("mm")
#                    #axs2.title.set_y("mm")

#                    p = gpd.GeoSeries(unary_union(self.polygons))
#                    p.plot(ax=axs1)
#                    plt.show()
#                    p = gpd.GeoSeries(unary_union(subtractive_polys))
#                    p.plot(ax=axs2)
#                    plt.show()
#                except:
#                    Message(traceback.format_exc(), title = "Plot Exception").show()
        #END OF DEBUGGING