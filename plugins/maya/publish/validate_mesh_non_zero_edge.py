from maya import cmds

import pyblish.api
from reveries.maya.plugins import MayaSelectInvalidInstanceAction
from reveries.maya import lib


class ValidateMeshNonZeroEdgeLength(pyblish.api.InstancePlugin):
    """Validate meshes don't have edges with a zero length.

    Based on Maya's polyCleanup 'Edges with zero length'.

    Note:
        This can be slow for high-res meshes.

    """

    order = pyblish.api.ValidatorOrder + 0.3
    hosts = ["maya"]
    label = "Mesh Edge Length Non Zero"
    families = [
        "reveries.model",
    ]
    actions = [
        pyblish.api.Category("Select"),
        MayaSelectInvalidInstanceAction,
    ]

    optional = True

    __tolerance = 1e-5

    @classmethod
    def get_invalid(cls, instance):
        """Return the invalid edges.
        Also see:
            http://help.autodesk.com/view/MAYAUL/2015/ENU/?guid=Mesh__Cleanup

        """

        meshes = cmds.ls(instance, type="mesh", long=True, noIntermediate=True)
        if not meshes:
            return list()

        # Get all edges
        edges = ["{0}.e[*]".format(node) for node in meshes]

        # Filter by constraint on edge length
        invalid = lib.polyConstraint(edges,
                                     t=0x8000,  # type=edge
                                     length=1,
                                     lengthbound=(0, cls.__tolerance))

        return invalid

    def process(self, instance):
        """Process all meshes"""
        invalid = self.get_invalid(instance)
        if invalid:
            raise RuntimeError("Meshes found with zero "
                               "edge length: {0}".format(invalid))
