import logging

from avalon.vendor.Qt import QtWidgets, QtCore
from avalon.vendor import qtawesome

from avalon.tools import lib

from . import models
from . import commands
from . import views


class AssetOutliner(QtWidgets.QWidget):

    refreshed = QtCore.Signal()
    selection_changed = QtCore.Signal()

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        layout = QtWidgets.QVBoxLayout()

        title = QtWidgets.QLabel("Assets")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 12px")

        model = models.AssetModel()
        view = views.View()
        view.setModel(model)
        view.customContextMenuRequested.connect(self.right_mouse_menu)
        view.setSortingEnabled(False)
        view.setHeaderHidden(False)
        view.setIndentation(10)

        asset_all = QtWidgets.QPushButton("All Assets")
        asset_sel = QtWidgets.QPushButton("From Selection")

        lister_layout = QtWidgets.QHBoxLayout()
        lister_layout.addWidget(asset_all)
        lister_layout.addWidget(asset_sel)

        layout.addWidget(title)
        layout.addLayout(lister_layout)
        layout.addWidget(view)

        # Build connections
        asset_all.clicked.connect(self.list_all_assets)
        asset_sel.clicked.connect(self.list_assets_from_selection)

        selection_model = view.selectionModel()
        selection_model.selectionChanged.connect(self.selection_changed)

        self.view = view
        self.model = model

        self.setLayout(layout)

        self.log = logging.getLogger(__name__)

    def clear(self):
        self.model.clear()

        # fix looks remaining visible when no items present after "refresh"
        # todo: figure out why this workaround is needed.
        self.selection_changed.emit()

    def add_items(self, items):
        """Add new items to the outliner"""

        self.model.add_items(items)
        self.refreshed.emit()

    def get_selected_items(self):
        """Get current selected items from view

        Returns:
            list: list of dictionaries
        """

        selection_model = self.view.selectionModel()
        items = [row.data(self.model.ItemRole) for row in
                 selection_model.selectedRows(0)]

        return items

    def list_all_assets(self):
        """Add all items from the current scene"""

        with lib.preserve_expanded_rows(self.view):
            with lib.preserve_selection(self.view):
                self.clear()
                nodes = commands.get_all_asset_nodes()
                items = commands.create_items(nodes)
                self.add_items(items)

        return len(items) > 0

    def list_assets_from_selection(self):
        """Add all selected items from the current scene"""

        with lib.preserve_expanded_rows(self.view):
            with lib.preserve_selection(self.view):
                self.clear()
                nodes = commands.get_selected_asset_nodes()
                items = commands.create_items(nodes, selected_only=True)
                self.add_items(items)

    def get_nodes(self):
        """Find the nodes in the current scene per asset."""

        items = self.get_selected_items()

        # Collect the asset item entries per asset
        asset_nodes = dict()
        for item in items:
            nodes = list()
            asset_name = item["asset"]["name"]

            if isinstance(item["nodes"], list):
                # cached
                nodes = item["nodes"]

            elif "subset" in item:
                namespace = item["namespace"]
                if not item["nodes"]:
                    group = commands.group_from_namespace(namespace)
                    if group is not None:
                        nodes.append(group)
                else:
                    nodes += item["nodes"]

            else:
                for namespace in item["namespaces"]:
                    namespace_nodes = item["nodes"][namespace]
                    if not namespace_nodes:
                        group = commands.group_from_namespace(namespace)
                        if group is not None:
                            nodes.append(group)
                    else:
                        nodes += namespace_nodes

            item["nodes"] = nodes  # cache
            asset_nodes[item.get("namespace") or asset_name] = item

        return asset_nodes

    def select_asset_from_items(self):  #
        """Select nodes from listed asset"""

        asset_nodes = self.get_nodes()
        nodes = []
        for item in asset_nodes.values():
            nodes.extend(item["nodes"])

        commands.select(nodes)

    def remove_look_from_items(self):

        asset_nodes = self.get_nodes()
        nodes = []
        asset_ids = set()
        for item in asset_nodes.values():
            nodes.extend(item["nodes"])
            asset_ids.add(str(item["asset"]["_id"]))

        commands.remove_look(nodes, asset_ids)

    def right_mouse_menu(self, pos):
        """Build RMB menu for asset outliner"""

        active = self.view.currentIndex()  # index under mouse
        active = active.sibling(active.row(), 0)  # get first column
        globalpos = self.view.viewport().mapToGlobal(pos)

        menu = QtWidgets.QMenu(self.view)

        apply_action = QtWidgets.QAction(menu, text="Select nodes")
        apply_action.triggered.connect(self.select_asset_from_items)

        remove_action = QtWidgets.QAction(menu, text="Remove look")
        remove_action.triggered.connect(self.remove_look_from_items)

        if not active.isValid():
            apply_action.setEnabled(False)
            remove_action.setEnabled(False)

        menu.addAction(apply_action)
        menu.addAction(remove_action)

        menu.exec_(globalpos)


class LookOutliner(QtWidgets.QWidget):

    menu_apply_action = QtCore.Signal()
    menu_apply_via_uv_action = QtCore.Signal()

    TITLE = "Published Looks"
    MODEL = models.LookModel

    def __init__(self, title=None, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        # look manager layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Looks from database
        title = QtWidgets.QLabel(self.TITLE)
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 12px")
        title.setAlignment(QtCore.Qt.AlignCenter)

        model = self.MODEL()

        # Proxy for dynamic sorting
        proxy = QtCore.QSortFilterProxyModel()
        proxy.setSourceModel(model)

        view = views.View()
        view.setModel(proxy)
        view.setMinimumHeight(80)
        view.setIndentation(4)
        view.setToolTip("Use right mouse button menu for direct actions")
        view.customContextMenuRequested.connect(self.right_mouse_menu)
        view.sortByColumn(0, QtCore.Qt.AscendingOrder)

        layout.addWidget(title)
        layout.addWidget(view)

        self.view = view
        self.model = model

    def clear(self):
        self.model.clear()

    def add_items(self, items):
        self.model.add_items(items)

    def get_selected_items(self):
        """Get current selected items from view

        Returns:
            list: list of dictionaries
        """

        datas = [i.data(self.model.ItemRole) for i in self.view.get_indices()]
        items = [d for d in datas if d is not None]  # filter Nones

        return items

    def right_mouse_menu(self, pos):
        """Build RMB menu for look view"""

        active = self.view.currentIndex()  # index under mouse
        active = active.sibling(active.row(), 0)  # get first column
        globalpos = self.view.viewport().mapToGlobal(pos)

        if not active.isValid():
            return

        menu = QtWidgets.QMenu(self.view)

        # Direct assignment
        apply_action = QtWidgets.QAction(menu, text="Assign looks..")
        apply_action.triggered.connect(self.menu_apply_action)

        menu.addAction(apply_action)

        # Assign via UUID-UV relation
        apply_via_uv_action = QtWidgets.QAction(menu,
                                                text="Assign looks via UV..")
        apply_via_uv_action.triggered.connect(self.menu_apply_via_uv_action)

        menu.addAction(apply_via_uv_action)

        menu.exec_(globalpos)


class LoadedLookOutliner(LookOutliner):

    TITLE = "Loaded Looks"
    MODEL = models.LoadedLookModel
