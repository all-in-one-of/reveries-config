# -*-coding: utf-8

import os
import tempfile
import hashlib
import codecs
import shutil
import weakref
import getpass
import pymongo
import datetime

from distutils import dir_util, errors as distutils_err

from avalon import io, Session

import pyblish.api
import avalon
from pyblish_qml.ipc import formatting

from .plugins import message_box_error


class LocalTZ(datetime.tzinfo):
    """Local time zone info, I guess. ¯\_(ツ)_/¯ """
    delta = datetime.datetime.now() - datetime.datetime.utcnow()
    utcoffset = dst = lambda self, dt: self.delta


localtz = LocalTZ()


def temp_dir(prefix="pyblish_tmp_"):
    """Provide a temporary directory for staging

    This temporary directory is generated through `tempfile.mkdtemp()`

    Arguments:
        prefix (str, optional): Prefix name of the temporary directory

    """
    return tempfile.mkdtemp(prefix=prefix)


def clear_stage(prefix="pyblish_tmp_"):
    """Remove temporary staging directory with prefix

    Remove temporary directory which named with prefix in
    `tempfile.gettempdir()`

    Arguments:
        prefix (str, optional): Prefix name of the temporary directory

    """
    tempdir = tempfile.gettempdir()
    cwd_backup = os.getcwd()

    os.chdir(tempdir)
    for item in os.listdir(tempdir):
        if not (os.path.isdir(item) and item.startswith(prefix)):
            continue

        # Remove
        full_path = os.path.join(tempdir, item)
        print("Removing {!r}".format(full_path))
        shutil.rmtree(full_path)
        print("Removed.")

    os.chdir(cwd_backup)


def get_timeline_data(project=None, asset_name=None, current_fps=None):
    """Get asset timeline data from project document

    Get timeline data from asset if asset has it's own settings, or get from
    project.

    Arguments:
        project (dict, optional): Project document, query from database if
            not provided.
        asset_name (str, optional): Asset name, get from `avalon.Session` if
            not provided.
        current_fps (float, optional): For preserving current FPS setting if
            project has multiple valid FPS.

    Returns:
        edit_in (int),
        edit_out (int),
        handles (int),
        fps (float)

    """
    if project is None:
        project = avalon.io.find_one({"type": "project"})
    asset_name = asset_name or avalon.Session["AVALON_ASSET"]
    asset = avalon.io.find_one({"name": asset_name, "type": "asset"})

    assert asset is not None, ("Asset {!r} not found, this is a bug."
                               "".format(asset_name))

    def get(key):
        return asset["data"].get(key, project["data"][key])

    edit_in = get("edit_in")
    edit_out = get("edit_out")
    handles = get("handles")
    fps = get("fps")

    # If project has multiple valid FPS, try preserving current FPS
    fpses = project["data"].get("fpses")
    if fpses and current_fps in fpses:
        fps = current_fps

    return edit_in, edit_out, handles, fps


def compose_timeline_data(project=None, asset_name=None, current_fps=None):
    """Compute and return start frame, end frame and fps

    Get timeline data from asset if asset has it's own settings, or get from
    project.

    Arguments:
        project (dict, optional): Project document, query from database if
            not provided.
        asset_name (str, optional): Asset name, get from `avalon.Session` if
            not provided.
        current_fps (float, optional): For preserving current FPS setting if
            project has multiple valid FPS.

    Returns:
        start_frame (int),
        end_frame (int),
        fps (float)

    """
    edit_in, edit_out, handles, fps = get_timeline_data(project,
                                                        asset_name,
                                                        current_fps)
    start_frame = edit_in - handles
    end_frame = edit_out + handles

    return start_frame, end_frame, fps


def get_resolution_data(project=None, asset_name=None):
    """Get resolution data from asset/project settings

    If resolution data is not defined in asset, query from project.

    Arguments:
        project (dict, optional): Project document, query from database if
            not provided.
        asset_name (str, optional): Asset name, get from `avalon.Session` if
            not provided.

    Returns:
        resolution_width (int),
        resolution_height (int)

    """
    if project is None:
        project = avalon.io.find_one({"type": "project"})
    asset_name = asset_name or avalon.Session["AVALON_ASSET"]
    asset = avalon.io.find_one({"name": asset_name, "type": "asset"})

    assert asset is not None, ("Asset {!r} not found, this is a bug."
                               "".format(asset_name))

    def get(key):
        return asset["data"].get(key, project["data"][key])

    resolution_width = get("resolution_width")
    resolution_height = get("resolution_height")

    return resolution_width, resolution_height


def init_app_workdir(*args):
    """Wrapped function of app initialize

    Copied from Colorbleed config, modified.
    Useful when changing task context, e.g. on_task_changed

    """

    # Inputs (from the switched session and running app)
    session = avalon.Session.copy()
    app_name = os.environ["AVALON_APP_NAME"]

    # Find the application definition
    app_definition = avalon.lib.get_application(app_name)

    App = type(
        "app_%s" % app_name,
        (avalon.api.Application,),
        {
            "name": app_name,
            "config": app_definition.copy()
        }
    )

    # Initialize within the new session's environment
    app = App()
    env = app.environ(session)
    app.initialize(env)


def override_event(event, callback):
    """Override existing event callback

    Copied from Colorbleed config.

    Args:
        event (str): name of the event
        callback (function): callback to be triggered

    Returns:
        None

    """

    ref = weakref.WeakSet()
    ref.add(callback)

    avalon.pipeline._registered_event_handlers[event] = ref


def publish_results_formatting(context):
    formatted = []
    for result in context.data["results"]:
        formatted.append(formatting.format_result(result))
    return formatted


def hash_file(file_path):
    hasher = AssetHasher()
    hasher.add_file(file_path)
    return hasher.digest()


def plugins_by_range(base=1.5, offset=2, paths=None):
    """Find plugins by thier order which fits in range

    Default param will return plugins that -0.5<=order<3.5, which is standard
    range of Pyblish CVEI.

    -.5 <= C < 0.5
    0.5 <= V < 1.5
    1.5 <= E < 2.5
    2.5 <= I < 3.5

    Arguments:
        base (float): Center of range
        offset (float, optional): Amount of offset from base

    """
    _min = base - offset
    _max = base + offset

    plugins = list()

    for plugin in pyblish.api.discover(paths=paths):
        if ("order" in plugin.__dict__ and
                _min <= plugin.order < _max):

            plugins.append(plugin)

    return plugins


class _C4Hasher(object):

    CHUNK_SIZE = 4096 * 10  # magic number
    PREFIX = "c4"

    def __init__(self):
        self.hash_obj = None
        self.clear()

    def clear(self):
        """Start a new hash session
        """
        self.hash_obj = hashlib.sha512()

    def _b58encode(self, bytes):
        """Base58 Encode bytes to string
        """
        b58chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        b58base = 58

        long_value = int(codecs.encode(bytes, "hex_codec"), 16)

        result = ""
        while long_value >= b58base:
            div, mod = divmod(long_value, b58base)
            result = b58chars[mod] + result
            long_value = div

        result = b58chars[long_value] + result

        return result

    def digest(self):
        """Return hash value of data added so far
        """
        c4_id_length = 90
        b58_hash = self._b58encode(self.hash_obj.digest())

        padding = ""
        if len(b58_hash) < (c4_id_length - 2):
            padding = "1" * (c4_id_length - 2 - len(b58_hash))

        c4id = self.PREFIX + padding + b58_hash
        return c4id


class AssetHasher(_C4Hasher):
    """A data hasher for digital content creation

    This is a Python implemtation of Avalanche-io C4 Asset ID.

    Usage:
        >> hasher = AssetHasher()
        >> hasher.add_file("/path/to/file")
        >> hasher.add_dir("/path/to/dir")

        You can keep adding more assets.
        And get the hash value by
        >> hasher.digest()
        'c463d2Wh5NyBMQRHyxbdBxCzZfaKXvBQaawgfgG18moxQU2jdmaSbCWL...'

        You can still adding more assets at this point
        >> hasher.add_file("/path/to/more/file")

        And get the hash value of all asset added so far
        >> hasher.digest()
        'c43cysVyTd7kYurvAa5ooR6miJJgUZ9QnBCHZeNK3en9aQ96KHsoJyJX...'

        Until you call `clear`
        >> hasher.clear()

    """

    def add_file(self, file_path):
        """Add one file to hasher

        Arguments:
            file_path (str): File path string

        """
        chunk_size = self.CHUNK_SIZE

        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(chunk_size), b""):
                self.hash_obj.update(chunk)

    def add_dir(self, dir_path, recursive=True, followlinks=True):
        """Add one directory to hasher

        Arguments:
            dir_path (str): Directory path string
            recursive (bool, optional): Add sub-dir as well, default is True
            followlinks (bool, optional): Add directories pointed to by
                symlinks, default is True

        """
        for root, dirs, files in os.walk(dir_path, followlinks=followlinks):
            for name in files:
                self.add_file(os.path.join(root, name))

            if not recursive:
                continue

            for name in dirs:
                path = os.path.join(root, name)
                self.add_dir(path, recursive=True, followlinks=followlinks)


def get_representation_path_(representation, parents):
    """Get filename from representation document

    Decoupled from `avalon.pipeline.get_representation_path`

    Args:
        representation (dict): representation document from the database
        parents (list): Documents returned from `io.parenthood`

    Returns:
        str: fullpath of the representation

    """
    version, subset, asset, project = parents
    template_publish = project["config"]["template"]["publish"]

    repr_root = representation["data"].get("reprRoot")
    root = repr_root or avalon.api.registered_root()

    return template_publish.format(**{
        "root": root,
        "project": project["name"],
        "asset": asset["name"],
        "silo": asset["silo"],
        "subset": subset["name"],
        "version": version["name"],
        "representation": representation["name"],
        "user": avalon.api.Session.get("AVALON_USER", getpass.getuser()),
        "app": avalon.api.Session.get("AVALON_APP", ""),
        "task": avalon.api.Session.get("AVALON_TASK", "")
    })


def deep_update(d, update):
    """Recursively update dict value"""
    for k, v in update.items():
        if isinstance(v, dict):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class AssetGraber(object):
    """Copy asset and it's dependencies to another project

    This is used for copying asset representation and all it's dependency
    assets from current project to another project.

    Example:
        >>> # Init with the name of the destination project
        >>> graber = AssetGraber("other_project")
        >>> # Input representation ID
        >>> graber.grab("5c6159dbed9f0d0509a34e27")
        >>> # Grab another...
        >>> graber.grab("5c6159dbed9f0d0509a34e38")

    """

    def __init__(self, project):
        self.project = project
        self._project = None
        self._mongo_client = None
        self._database = None
        self._collection = None
        self._connected = False

    def grab(self, representation_id):
        """Copy representation to project

        Args:
            representation_id (str or ObjectId): representation id

        """
        if not self._connected:
            self._connect()
        if isinstance(representation_id, str):
            representation_id = io.ObjectId(representation_id)
        self._copy_representations(representation_id)

    def _connect(self):
        timeout = int(Session["AVALON_TIMEOUT"])
        self._mongo_client = pymongo.MongoClient(
            Session["AVALON_MONGO"], serverSelectionTimeoutMS=timeout)
        self._database = self._mongo_client[Session["AVALON_DB"]]
        self._collection = self._database[self.project]
        self._connected = True

        self._project = self._find_one({"type": "project"})

    def _insert_one(self, item):
        assert isinstance(item, dict), "item must be of type <dict>"
        return self._collection.insert_one(item)

    def _find_one(self, filter, projection=None, sort=None):
        assert isinstance(filter, dict), "filter must be <dict>"
        return self._collection.find_one(
            filter=filter,
            projection=projection,
            sort=sort
        )

    def _copy_representations(self, representation_id):
        """Copy all documents and files of representation and dependencies"""
        # Representation
        representation = self._find_one({"_id": representation_id})
        if not representation:
            representation = io.find_one({"_id": representation_id})
            self._insert_one(representation)

            # Version
            version = io.find_one({"_id": representation["parent"]})
            if not self._find_one({"_id": version["_id"]}):
                self._insert_one(version)

                # Subset
                subset = io.find_one({"_id": version["parent"]})
                if not self._find_one({"_id": subset["_id"]}):
                    self._insert_one(subset)

                    # Asset
                    asset = io.find_one({"_id": subset["parent"]})
                    if not self._find_one({"_id": asset["_id"]}):
                        asset["parent"] = self._project["_id"]
                        self._insert_one(asset)

                        # Asset Visual Parent
                        parent_id = asset["data"]["visualParent"]
                        if parent_id:
                            parent_id = io.ObjectId(parent_id)
                            if not self._find_one({"_id": parent_id}):
                                parent_asset = io.find_one({"_id": parent_id})
                                parent_asset["parent"] = self._project["_id"]
                                self._insert_one(parent_asset)

                # Dependencies
                for dependency_id in version["data"]["dependencies"]:
                    dependency_id = io.ObjectId(dependency_id)
                    for representation_ in io.find({"parent": dependency_id}):
                        self._copy_representations(representation_["_id"])

        # Copy package
        parents = io.parenthood(representation)
        src_package = get_representation_path_(representation, parents)
        parents = parents[:-1] + [self._project]
        representation["data"]["reprRoot"] = self._project["data"].get("root")
        dst_package = get_representation_path_(representation, parents)
        self._copy_dir(src_package, dst_package)

    def _copy_dir(self, src, dst):
        """ Copy given source to destination"""
        src = os.path.normpath(src)
        dst = os.path.normpath(dst)
        print("Copying: %s" % src)
        print("     To: %s" % dst)
        try:
            dir_util.copy_tree(src, dst)
        except distutils_err.DistutilsFileError as e:
            message_box_error("Error", e)
            raise e


def get_versions_from_sourcefile(source, project):
    """Get version documents by the source path

    By matching the path with field `version.data.source` to query latest
    versions.

    Args:
        source (str): A path string where subsets been published from
        project (str): Project name

    """
    source = source.split(project, 1)[-1].replace("\\", "/")
    source = {"$regex": "/*{}".format(source), "$options": "i"}

    cursor = io.find({"type": "version",
                      "data.source": source},
                     sort=[("name", -1)])
    # (NOTE) Each version usually coming from different source file, but
    #        let's not making this assumtion.
    #        So here we filter out other versions that belongs to the same
    #        subset.
    subsets = set()
    for version in cursor:
        if version["parent"] not in subsets:
            subsets.add(version["parent"])

            yield version

        else:
            continue


def overlay_clipinfo_on_image(image_path,
                              output_path,
                              project,
                              task,
                              subset,
                              version,
                              representation_id,
                              artist,
                              date,
                              shot_name,
                              frame_num,
                              edit_in,
                              edit_out,
                              handles,
                              duration,
                              focal_length,
                              resolution,
                              fps,
                              expand_hight=False):
    """Overlay clipinfo onto image for human reviewing

    (NOTE): This function requires package `PIL` be installed in the
            environment, or `ImportError` raised.

    Args:
        image_path (str): Image file path
        output_path (str): Output file path
        project (str): Project name
        task (str): Task name
        subset (str): Subset name
        version (int): Version number
        representation_id (str): Representation ID string
        artist (str): Artist name
        date (str): date string
        shot_name (str): Shot asset name
        frame_num (int): Frame number of this image
        edit_in (int): In frame number of the shot
        edit_out (int): Out frame number of the shot
        handles (int): Handle range
        duration (int): Image sequence length
        focal_length (float): Camera focal length
        resolution (tuple): Image resolution
        fps (float): Shot frame rate
        expand_hight (bool): Instead of scaling down the source image, expand
            hight for clipinfo

    """
    from PIL import Image, ImageDraw, ImageFont

    width, height = resolution

    # Templates

    _TOP = "{project}".format(project=project.split("_", 1)[-1])

    _TOP_LEFT = """
  Shot: {shot_name}  ver {version:0>3}
 Frame: {frame_num:0>4}
FocalL: {focal_length} mm
"""[1:-1].format(frame_num=frame_num,
                 shot_name=shot_name,
                 version=version,
                 focal_length=focal_length)

    _TOP_RIGHT = """
  Date: {date}
Artist: {artist}
  Task: {task}
"""[1:-1].format(date=date, artist=artist, task=task)

    _BTM = "{frame_num:0>4}".format(frame_num=frame_num)

    _BTM_LEFT = """
   Range: {edit_in:0>4} - {edit_out:0>4}
Duration: {duration:0>4}
 Handles: {handles}  FPS: {fps}
"""[1:-1].format(edit_in=edit_in,
                 edit_out=edit_out,
                 duration=duration,
                 handles=handles,
                 fps=fps)

    _BTM_RIGHT = """
    Subset: {subset_name}
      RPID: {representation_id}
Resolution: {width}px * {height}px
"""[1:-1].format(subset_name=subset,
                 representation_id=representation_id,
                 width=width,
                 height=height)

    # Compute font size and spacing base on image resolution

    spacing = int(width / 320)    # 6 in Full HD
    titlesize = int(width / 48)  # 40 in Full HD
    datasize = int(width / 96)   # 20 in Full HD
    border = datasize

    if expand_hight:
        expand = ((datasize + spacing) * 3 +  # 3 lines of info
                  border * 2)
        height += expand * 2  # Above and below

    # Get font

    FONTDIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "res",
                           "fonts").replace("\\", "/")

    fontfile = FONTDIR + "/SourceCodePro/Sauce Code Powerline Regular.otf"
    titlefont = ImageFont.truetype(fontfile, size=titlesize)
    datafont = ImageFont.truetype(fontfile, size=datasize)

    # Create new image

    im = Image.new("RGBA", size=(width, height), color=(0, 0, 0, 255))
    draw = ImageDraw.Draw(im)

    def textsize(text, title=False):
        font = titlefont if title else datafont
        return draw.textsize(text, font=font, spacing=spacing)

    def puttext(text, pos, title=False):
        font = titlefont if title else datafont
        align = "center" if title else "left"
        draw.text(pos, text, fill=(200, 200, 200, 255),
                  font=font, align=align, spacing=spacing)

    # Start painting

    # Top Center
    size_top = textsize(_TOP, title=True)
    x = (width - size_top[0]) / 2
    y = border
    pos_top = (x, y)
    puttext(_TOP, pos_top, title=True)

    # Bottom Center
    size_btm = textsize(_BTM, title=True)
    x = (width - size_btm[0]) / 2
    y = height - border - size_btm[1]
    pos_btm = (x, y)
    # Disabled, but still take into calculation
    # puttext(_BTM, pos_btm, title=True)

    # Top Left
    size_top_left = textsize(_TOP_LEFT)
    x = border
    y = border
    pos_top_left = (x, y)
    puttext(_TOP_LEFT, pos_top_left)

    # Top Right
    size_top_right = textsize(_TOP_RIGHT)
    x = width - size_top_right[0] - border
    y = border
    pos_top_right = (x, y)
    puttext(_TOP_RIGHT, pos_top_right)

    # Bottom Left
    size_btm_left = textsize(_BTM_LEFT)
    x = border
    y = height - size_btm_left[1] - border
    pos_btm_left = (x, y)
    puttext(_BTM_LEFT, pos_btm_left)

    # Bottom Right
    size_btm_right = textsize(_BTM_RIGHT)
    x = width - size_btm_right[0] - border
    y = height - size_btm_right[1] - border
    pos_btm_right = (x, y)
    puttext(_BTM_RIGHT, pos_btm_right)

    # Assemble

    if expand_hight:

        src = Image.open(image_path)
        holdout = Image.new("L", src.size)
        background = Image.new("L", im.size, 255)
        background.paste(holdout, box=(0, expand))
        im.putalpha(background)

    else:

        # Comput the size that the original image need to be scaled
        # after the clipinfo applied on.
        retract = (max(pos_top[1] + size_top[1],
                       pos_top_left[1] + size_top_left[1],
                       pos_top_right[1] + size_top_right[1]) +
                   max(height - pos_btm[1] + size_btm[1],
                       height - pos_btm_left[1] + size_btm_left[1],
                       height - pos_btm_right[1] + size_btm_right[1]))

        scale = float(height) / (height + retract)
        scaled_w = int(width * scale) - border
        scaled_h = int(height * scale) - border
        box = (int((width - scaled_w) / 2), int((height - scaled_h) / 2))

        src = Image.open(image_path)
        src.load()  # required for src.split()

        background = Image.new("RGB", src.size, (255, 255, 255))
        background.paste(src)
        background.paste(src, mask=src.split()[3])  # 3 is the alpha channel
        # Put resized original image into new image that has clipinfo
        # overlaied
        im.paste(background.resize((scaled_w, scaled_h),
                                   resample=Image.BICUBIC),
                 box=box)

    # save over to original image
    im.save(output_path)
