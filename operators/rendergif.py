import bpy
import os
import sys
import shutil
import subprocess
from bpy_extras.io_utils import ExportHelper
from .utilities.remove_bads import remove_bads
from .utilities.update_progress import update_progress
from .utilities.is_gifsicle_installed import is_gifsicle_installed
from .utilities.is_magick_installed import is_magick_installed


def pngs_2_gifs(context, frames_folder):
    """Convert the PNGs to gif images and report progress"""

    images = list(sorted(os.listdir(frames_folder)))

    total = len(images)
    wm = context.window_manager
    wm.progress_begin(0, 100.0)

    magick = "magick"
    if not context.scene.magick_path.strip() == "":
        magick = context.scene.magick_path.strip()

    for ii in range(total):
        update_progress("Converting PNG to GIF frames", ii / total)
        wm.progress_update(ii / total * 100)
        png = os.path.join(frames_folder, images[ii])
        gif = os.path.splitext(png)[0] + '.gif'

        command = [magick]
        if context.scene.gif_dither_conversion:
            command.append("+dither")

        command.append(png)
        command.append(gif)

        subprocess.call(command)

    update_progress("Converting PNG to GIF frames", 1)


def gifs_2_animated_gif(context, abspath, frames_folder):
    """Combines gifs into animated gif"""

    scene = context.scene

    gifsicle = "gifsicle"
    if not context.scene.gifsicle_path.strip() == "":
        gifsicle = f"\"{context.scene.gifsicle_path.strip()}\""

    command = [gifsicle]

    command.append(f"--disposal={scene.gif_disposal}")

    if not scene.gif_dither == "none":
        command.append(f"--dither={scene.gif_dither}")

    command.append(f"--color-method={scene.gif_color_method}")

    if scene.gif_transparent:
        command.append("-t {},{},{}".format(*tuple(int(v * 255) for v in scene.gif_transparent_color)))

    if not scene.gif_color_map == "none":
        if not scene.gif_color_map == "custom":
            command.append(f"--use-colormap={scene.gif_color_map}")
        elif not scene.gif_mapfile == "":
            command.append(f"--use-colormap=\"{bpy.path.abspath(scene.gif_mapfile)}\"")

    if scene.gif_careful:
        command.append("--careful")

    if scene.gif_optimize:
        command.append(f"--optimize={scene.gif_optimize}")
    else:
        command.append("--unoptimize")

    if scene.gif_loop_count == 0:
        command.append("--loop")
    elif scene.gif_loop_count == 1:
        command.append("--no-loopcount")
    else:
        command.append(f"--loopcount={scene.gif_loop_count - 1}")

    fps = scene.render.fps / scene.render.fps_base
    command.append(f"--delay {int(100 / fps)}")
    command.append(f"--colors={scene.gif_colors}")

    command.append(f"\"{frames_folder}\*.gif\"")  # source gifs
    command.append("--output")
    command.append(f"\"{abspath}\"")  # output gif

    print("Combining GIF frames into animated GIF...")
    subprocess.call(" ".join(command), shell=True)

    context.window_manager.progress_end()


class SEQUENCER_OT_render_gif(bpy.types.Operator, ExportHelper):
    bl_label = "Render GIF"
    bl_idname = "bligify.render_gif"
    bl_description = "Render an animated GIF."

    filename_ext = ".gif"

    @classmethod
    def poll(self, context):
        scene = context.scene
        if scene and scene.sequence_editor:
            return True
        else:
            return False

    def make_gif(self, context):
        scene = context.scene
        frames_folder = scene.render.filepath
        abspath = os.path.abspath(self.filepath)

        pngs_2_gifs(context, frames_folder)
        gifs_2_animated_gif(context, abspath, frames_folder)
        scene.render.filepath = self.original_file_path
        scene.render.image_settings.file_format = self.original_file_format
        scene.render.image_settings.color_depth = self.original_color_depth
        scene.render.image_settings.compression = self.original_compression

        if scene.delete_frames:
            shutil.rmtree(frames_folder)

    def execute(self, context):
        if context.scene.gifsicle_path.strip() == "":
            if not is_gifsicle_installed():
                self.report({'ERROR'}, "This function requires Gifsicle to work.")
                return {"FINISHED"}

        if context.scene.magick_path.strip() == "":
            if not is_magick_installed():
                self.report({'ERROR'}, "This function requires ImageMagick to work.")
                return {"FINISHED"}

        scene = context.scene

        self.original_file_path = scene.render.filepath
        self.original_file_format = scene.render.image_settings.file_format
        self.original_color_depth = scene.render.image_settings.color_depth
        self.original_compression = scene.render.image_settings.compression

        abspath = os.path.abspath(self.filepath)
        folder_path = os.path.dirname(abspath)
        file_name = os.path.splitext(os.path.basename(abspath))[0]
        frames_folder = os.path.join(folder_path, file_name + "_frames")
        while os.path.isdir(frames_folder):
            frames_folder += "_frames"

        frames_folder += '\\'

        scene.render.filepath = frames_folder
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_depth = "8"  # higher depths not likely needed
        scene.render.image_settings.compression = 0  # maximize speed of PNG output stage

        os.mkdir(frames_folder)

        wm = context.window_manager
        wm.modal_handler_add(self)
        self.timer = wm.event_timer_add(0.5, window=context.window)

        bpy.ops.render.render('INVOKE_DEFAULT', animation=True)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        scene = context.scene
        frames_folder = scene.render.filepath

        if event.type == 'TIMER':
            try:
                frame_count = (scene.frame_end - scene.frame_start) // scene.frame_step + 1
                if len(os.listdir(frames_folder)) == frame_count:

                    self.make_gif(context)
                    context.area.type = "SEQUENCE_EDITOR"
                    return {"FINISHED"}

                else:
                    return {"PASS_THROUGH"}
            except FileNotFoundError:
                return {"FINISHED"}

        else:
            return {"PASS_THROUGH"}
