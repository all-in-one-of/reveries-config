
import os
import json
import contextlib
import pyblish.api
from reveries.plugins import PackageExtractor
from reveries.maya import xgen, utils, capsule


class ExtractXGenInteractive(PackageExtractor):
    """
    """

    order = pyblish.api.ExtractorOrder
    hosts = ["maya"]
    label = "Extract Interactive Groom"
    families = [
        "reveries.xgen.interactive",
    ]

    representations = [
        "XGenInteractive",
    ]

    def extract_XGenInteractive(self, packager):
        from maya import cmds

        package_dir = packager.create_package()

        bound_map = dict()
        clay_shader = "initialShadingGroup"
        descriptions = self.data["igsDescriptions"]
        with capsule.assign_shader(descriptions, shadingEngine=clay_shader):

            for description in descriptions:

                desc_id = utils.get_id(description)

                # Get bounded meshes
                bound_map[desc_id] = list()
                for mesh in xgen.interactive.list_bound_meshes(description):
                    transform = cmds.listRelatives(mesh, parent=True)
                    id = utils.get_id(transform[0])
                    bound_map[desc_id].append(id)

            # Export preset
            # (NOTE) Saving as ext `.ma` instead of `.xgip` is because
            #        I'd like to use reference to load it later.
            #        Referencing file that was not `.ma`, `.mb` or other
            #        normal ext will crash Maya on file saving.
            entry_file = packager.file_name("ma")
            entry_path = os.path.join(package_dir, entry_file)

            # (NOTE) Separating grooms and bounding meshes seems not able to
            #        preserve sculpt layer data entirely correct.
            #        For example, sculpting long hair strands to really short,
            #        may ends up noisy shaped after import back.
            #
            #        So now we export the grooms with bound meshes...
            #
            # io.export_xgen_IGS_presets(descriptions, entry_path)

            with contextlib.nested(
                capsule.no_display_layers(self.member),
                capsule.maintained_selection(),
            ):
                cmds.select(descriptions)

                cmds.file(entry_path,
                          force=True,
                          typ="mayaAscii",
                          exportSelected=True,
                          preserveReferences=False,
                          channels=True,
                          constraints=True,
                          expressions=True,
                          constructionHistory=True)

        # Parse preset bounding map
        link_file = packager.file_name("json")
        link_path = os.path.join(package_dir, link_file)

        with open(link_path, "w") as fp:
            json.dump(bound_map, fp, ensure_ascii=False)

        packager.add_data({
            "linkFname": link_file,
            "entryFileName": entry_file,
        })
