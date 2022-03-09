import traceback

from ..Script import Script
from UM.Message import Message
from UM.Logger import Logger

from UM.Application import Application

from shapely import geometry

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
    """This class represents a layer which has been sliced."""
    def __init__(self, layer_instructions):
        self.polygons = []
        self.extractGCodeLayer(layer_instructions)
        self.original_gcode = layer_instructions.splitlines()

    def extractGCodeLayer(self, gcode):
        """This method parses the GCode for an entire layer and extracts the exterior geometry of the layer. The geometry data is parsed into Shapely Polygon objects"""
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

            new_poly = geometry.Polygon(p(move_instructions))

            if type(new_poly) == geometry.MultiPolygon:
                for poly in list(new_poly):
                    self.polygons.append(poly)
            else:
                self.polygons.append(new_poly)
            
            del gcode_lines[start_index]

    def coords_to_instructions(self,coordinate_sets):
        #Coordinate sets: 2d tuple of coordinates, representing different 'islands' of geometry
        instructions = []
        for i in range(0,len(coordinate_sets)):
            for j in range(0,len(coordinate_sets[i])):

                coordinate = coordinate_sets[i][j]

                dp = 5

                ins = "G1 X" + str(round(coordinate[0],dp)) + " Y" + str(round(coordinate[1],dp)) + "\n"
                
                instructions.append(ins)

        return instructions

    def expand(self, distance):
        global debug_layer_count

        coordinates_set = []
        
        for polygon in self.polygons:
            buff_polygon = polygon.buffer(float(distance))

            if type(buff_polygon) == geometry.MultiPolygon:
                buff_coords = []
                for poly in buff_polygon:
                    buff_coords += list(poly.exterior.coords)
            else:
                buff_coords = list(buff_polygon.exterior.coords)

#            #Visualisation Code
#            debug_layer_count += 1
#            if debug_layer_count == 3:
#                try:
#                    fig, axs1 = plt.subplots(1,1)

#                    axs1.title.set_text("Geometry Buffering")

#                    p = gpd.GeoSeries(buff_polygon)
#                    p.plot(facecolor='skyblue', edgecolor='black',ax=axs1)
#                    plt.show()
#                    p2 = gpd.GeoSeries(polygon)
#                    p2.plot(facecolor='navajowhite', edgecolor='black',ax=axs1)
#                    plt.show()
            
#                except:
#                        Message(traceback.format_exc(), title = "Plot Exception").show()
            #End of Visualisation Code


            coordinates_set.append(buff_coords)


            
        instructions = self.coords_to_instructions(coordinates_set)

        return instructions


class ASMBL_Processing(Script):
    """The ASMBL_Processing class is the main-class of the plugin. This class is instantiated when the post-processing plugin is executed."""

    def __init__(self) -> None:
        super().__init__()

    def getSettingDataString(self):
        """Returns a JSON string, defining the settings information for the plugin."""
        return """{
            "name": "ASMBL Vesuvius",
            "key": "Vesuvius",
            "metadata": {},
            "version": 2,
            "settings":
            {
                "ASMBL_Start":
                {
                    "label": "ASMBL Start Layer",
                    "description": "After this layer is reached, the layers following shall be ASMBL processed",
                    "type": "int",
                    "default_value": "5"
                },
                "PauseAtASMBL_Start":
                {
                    "label": "Pause at ASMBL Start?",
                    "description": "When set, the printer pauses when it reaches the ASMBL Start Layer",
                    "type": "bool",
                    "default_value": "True"
                },
                "BurnishingEnabled":
                {
                    "label": "Generate Burnisher Toolpath",
                    "description": "When enabled, a toolpath for the burnishing tool is generated",
                    "type": "bool",
                    "default_value": "True"
                },
                "BurnishingDiameter":
                {
                    "label": "Burnishing Tool Diameter (mm)",
                    "description": "Diameter of the burnishing tool end effector",
                    "type": "float",
                    "default_value": "20"
                },
                "BurnishingFeedrate":
                {
                    "label": "Burnishing Tool Feed rate (mm/min)",
                    "description": "Feed rate of the burnishing toolpath",
                    "type": "int",
                    "default_value": "1500"
                },
                "BurnishingOffset":
                {
                    "label": "Burnishing Tool Offset (mm)",
                    "description": "Offset of the burnishing toolpath",
                    "type": "float",
                    "default_value": "0"
                },
                "BurnishingTemperature":
                {
                    "label": "Burnishing Tool Temperature (Celsius)",
                    "description": "Temperature of the burnishing tool",
                    "type": "float",
                    "default_value": "200"
                },
                "BurnishingStepHeight":
                {
                    "label": "Burnishing Tool Step Height (mm)",
                    "description": "Step Height of the burnishing tool",
                    "type": "float",
                    "default_value": "1"
                }
            }
        }"""

    def getLatestZ(self, data):
        """A utility function, which scans input GCode for the latest Z position and returns it."""
        final_z = None
        for line in data.splitlines():
            if "G" in line and "Z" in line:
                final_z = float(line.split("Z")[1])
        return final_z

    def execute(self, data):
        """The entry point of the plugin"""
        
        layer_no = 0
        try:
            for i in range(2,len(data)-1):
                layer_no += 1
                layer = Layer(data[i])

                Logger.log("d",self.getSettingValueByKey("ASMBL_Start"))


                if layer_no <= int(self.getSettingValueByKey("ASMBL_Start")):
                    if self.getSettingValueByKey("RemovePrintCode"):
                        data[i] = ";Removed Layer: "+str(layer_no)+"\n"
                    if layer_no == self.getSettingValueByKey("ASMBL_Start") and self.getSettingValueByKey("PauseAtASMBL_Start"): 
                        data[i] += "\nM601 ; Pause at ASMBL Start\n"
                    continue

                new_instructions = ""

                if self.getSettingValueByKey("BurnishingEnabled"):

                    new_instructions += "; Vesuvius Burnish\n"
                    new_instructions += "; Offset = "+str(self.getSettingValueByKey("BurnishingOffset"))+"\n"
                    new_instructions += "; Feed Rate = "+str(self.getSettingValueByKey("BurnishingFeedrate"))+"\n"
                    new_instructions += "; Step Height = "+str(self.getSettingValueByKey("BurnishingStepHeight"))+"\n"
                    new_instructions += "; Temperature = "+str(self.getSettingValueByKey("BurnishingTemperature"))+"\n"
                    new_instructions += "; Tool Diameter = "+str(self.getSettingValueByKey("BurnishingDiameter"))+"\n"

                    new_instructions += "T1\n"

                    new_instructions += "M109 S"+str(self.getSettingValueByKey("BurnishingTemperature"))+"\n"
                    new_instructions += "G0 F"+str(self.getSettingValueByKey("BurnishingFeedrate"))+"\n"

                    line_width = Application.getInstance().getGlobalContainerStack().getProperty("line_width", "value")
                    total_offset = (0.5 * (self.getSettingValueByKey("BurnishingDiameter") + line_width)) + self.getSettingValueByKey("BurnishingOffset")

                    burnish_instructions = layer.expand(total_offset)

                    current_z = self.getLatestZ(data[i])
                    if current_z == None:
                        continue

                    layerHeight = Application.getInstance().getGlobalContainerStack().getProperty("layer_height", "value")
                    
                    z_step = self.getSettingValueByKey("BurnishingStepHeight")

                    z = current_z

                    while z < current_z + layerHeight:

                        new_instructions += "G0 F600 Z"+str(z)+"\n"

                        new_instructions += "G0 F4000\n"
                        new_instructions += burnish_instructions[0]

                        new_instructions += "G0 F"+str(self.getSettingValueByKey("BurnishingFeedrate"))+"\n"

                        for ins in burnish_instructions:
                            new_instructions += ins

                        z += z_step

                    new_instructions += "G0 F600 Z"+str(current_z)+"\n"

                    new_instructions += "T0\n"
                    new_instructions += "; Vesuvius Burnish Finished\n"

                    if self.getSettingValueByKey("RemovePrintCode"):
                        data[i] = new_instructions
                    else:
                        data[i] += new_instructions                  

        except Exception as e:
            Message(traceback.format_exc(), title = "Exception").show()
            Logger.log("d",traceback.format_exc())

        Message("ASMBL Processing Complete", title = "Status").show()

        return data