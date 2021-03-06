
import logging
from avalon import io


main_logger = logging.getLogger("modeldiffer")


def profile_from_database(version_id):
    """
    """
    representation = io.find_one({"type": "representation",
                                  "name": "mayaBinary",
                                  "parent": version_id})
    if representation is None:
        main_logger.critical("Representation not found. This is a bug.")
        return

    model_profile = representation["data"].get("modelProfile")

    if model_profile is None:
        main_logger.critical("'data.modelProfile' not found."
                             "This is a bug.")
        return

    profile = dict()

    for id, meshes_data in model_profile.items():
        for data in meshes_data:

            name = data.pop("hierarchy")
            # No need to compare normals
            data.pop("normals")

            data["avalonId"] = id

            profile[name] = data

    return profile


profile_from_host = NotImplemented
select_from_host = NotImplemented


def is_supported_loader(name):
    return name in ("ModelLoader",)  # "RigLoader")


def is_supported_subset(name):
    return any(name.startswith(family)
               for family in ("model",))  # "rig"))
