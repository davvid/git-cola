try:
    import gitlab
except ImportError:
    gitlab = None
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtCore import Signal

from . import defs
from . import standard
from . import text
from .. import icons
from .. import qtutils
from .. import utils
from ..i18n import N_
from ..qtutils import get


ENABLED = gitlab is not None


def editor(context, run=True):
    view = ForgeEditor(context, parent=qtutils.active_window())
    if run:
        view.show()
        view.exec_()
    return view


def lineedit(context, hint):
    """Create a HintedLineEdit with a preset minimum width"""
    widget = text.HintedLineEdit(context, hint)
    width = qtutils.text_width(widget.font(), 'M')
    widget.setMinimumWidth(width * 32)
    return widget


class ForgeEditor(standard.Dialog):
    """Enable API access to software forges"""

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle(N_('Edit Forges'))
        if parent is not None:
            self.setWindowModality(Qt.WindowModal)

        self.context = context
        self.current_url = ''
        self.current_token = ''
        self.current_backend = ''
        self.forge_list = []
        self.forges = standard.ListWidget()
        tooltip = N_(
            'Add and remove forges using the Add(+) and Delete(-) buttons.\n'
            'Forges URLs can be changed using the editor or by selecting one from the\n'
            'the list and pressing "Enter", or by double-clicking an iten im the list.'
        )
        self.forges.setToolTip(tooltip)
        self.editor = ForgeEditorWidget(context, self)
        self.save_button = qtutils.create_button(
            text=N_('Save'), icon=icons.save(), default=True
        )
        self.reset_button = qtutils.create_button(
            text=N_('Reset'), icon=icons.discard()
        )

        icon = icons.add()
        tooltip = N_('Add new forge')
        self.add_button = qtutils.create_toolbutton(icon=icon, tooltip=tooltip)
        self.refresh_button = qtutils.create_toolbutton(
            icon=icons.sync(), tooltip=N_('Refresh')
        )
        self.delete_button = qtutils.create_toolbutton(
            icon=icons.remove(), tooltip=N_('Delete')
        )
        self.close_button = qtutils.close_button()

        self._edit_button_layout = qtutils.vbox(
            defs.no_margin,
            defs.spacing,
            self.save_button,
            self.reset_button,
            qtutils.STRETCH,
        )
        self._edit_layout = qtutils.hbox(
            defs.no_margin, defs.spacing, self.editor, self._edit_button_layout
        )
        self._edit_widget = QtWidgets.QWidget()
        self._edit_widget.setLayout(self._edit_layout)

        self._top_layout = qtutils.splitter(
            Qt.Horizontal, self.forges, self._edit_widget
        )
        width = self._top_layout.width()
        self._top_layout.setSizes([width // 4, width * 3 // 4])

        self._button_layout = qtutils.hbox(
            defs.margin,
            defs.spacing,
            self.add_button,
            self.delete_button,
            self.refresh_button,
            qtutils.STRETCH,
            self.close_button,
        )

        self._layout = qtutils.vbox(
            defs.margin, defs.spacing, self._top_layout, self._button_layout
        )
        self.setLayout(self._layout)

        self.editor.forge_url.returnPressed.connect(self.save)
        self.editor.forge_token.returnPressed.connect(self.save)
        self.editor.valid.connect(self.editor_valid)

        self.forges.itemChanged.connect(self.forge_url_changed)
        self.forges.itemSelectionChanged.connect(self.selection_changed)

        self.disable_editor()
        self.init_state(None, self.resize_widget, parent)
        self.forges.setFocus(Qt.OtherFocusReason)
        self.refresh()

        qtutils.connect_button(self.add_button, self.add)
        qtutils.connect_button(self.delete_button, self.delete)
        qtutils.connect_button(self.refresh_button, self.refresh)
        qtutils.connect_button(self.close_button, self.accept)
        qtutils.connect_button(self.save_button, self.save)
        qtutils.connect_button(self.reset_button, self.reset)
        qtutils.add_close_action(self)

    def reset(self):
        focus = self.focusWidget()
        if self.current_url:
            self.activate_forge(self.current_url)
        restore_focus(focus)

    @property
    def changed(self):
        url = self.editor.url
        token = self.editor.token
        return (
            url != self.current_url
            or token != self.current_token
        )

    def save(self):
        if not self.changed:
            return
        context = self.context
        url = self.editor.url
        token = self.editor.token
        old_url = self.current_url
        old_token = self.current_token

        url_changed = url and url != old_url
        token_changed = token and token != old_token
        focus = self.focusWidget()

        url_ok = False
        token_ok = False

        # Run the corresponding commands
        if token_changed or url_changed:
            url_ok, token_ok = cmds.do(cmds.ForgeUpdate, context, url, token)
        if url_changed and old_url:
            cmds.do(cmds.ForgeDelete, context, old_url)

        # Update state if the change succeeded
        if token_changed and token_ok:
            self.current_token = token
        # A URL change requires a refresh
        if url_changed and url_ok:
            self.current_url = url
            self.refresh(select=False)
            forges = utils.Sequence(self.forges_list)
            idx = forges.index(url)
            self.select_forge(idx)

        restore_focus(focus)

    def editor_valid(self, valid):
        changed = self.changed
        self.reset_button.setEnabled(changed)
        self.save_button.setEnabled(changed and valid)

    def disable_editor(self):
        self.save_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.editor.setEnabled(False)
        self.editor.url = ''
        self.editor.token = ''
        self.current_url = ''
        self.current_token = ''

    def resize_widget(self, parent):
        """Set the initial size of the widget"""
        width, height = qtutils.default_size(parent, 720, 445)
        self.resize(width, height)

    def select_forge(self, index):
        if index >= 0:
            item = self.forges.item(index)
            if item:
                item.setSelected(True)

    def refresh(self, select=True):
        git = self.context.git
        forge_urls = self.context.cfg.find('cola.forge.*.url')
        prefix = len('cola.forge.')
        suffix = len('.url')
        forges = sorted([name[prefix:-suffix] for (name, _) in forge_urls.items()])
        # Ignore notifications from self.forges while mutating.
        with qtutils.BlockSignals(self.forges):
            self.forges.clear()
            self.forges.addItems(forges)
            self.forge_list = forges

            for idx in range(len(forges)):
                item = self.forges.item(idx)
                item.setFlags(item.flags() | Qt.ItemIsEditable)

        if select:
            if forges and not self.current_url:
                # Nothing is selected; select the first item
                self.select_forge(0)
            elif forges and self.current_url:
                # Reselect the previously selected item
                forge_seq = utils.Sequence(forges)
                idx = forge_seq.index(self.current_url)
                if idx >= 0:
                    item = self.forges.item(idx)
                    if item:
                        item.setSelected(True)

    def add(self):
        """Add a new forge"""
        url = 'https://gitlab.com'
        if url in self.forge_list:
            url = 'http://gitlab.example.com'
        count = 1
        while url in self.forge_list:
            url = f'gitlab{count}.example.com'
            count += 1
        self.current_url = ''
        self.current_token = ''
        self.forges.addItem(url)
        self.forge_list.append(url)
        # Newly added forge will be last; select it
        self.select_forge(len(self.forge_list) - 1)
        self.editor.url = url

    def delete(self):
        forge = qtutils.selected_item(self.forges, self.forge_list)
        if not forge:
            return
        cmds.do(cmds.ForgeDelete, self.context, forge)
        self.refresh(select=False)

    def forge_url_changed(self, item):
        idx = self.forges.row(item)
        if idx < 0:
            return
        if idx >= len(self.forge_list):
            return
        old_url = self.forge_list[idx]
        new_url = item.text()
        if new_url == old_url:
            return
        if not new_url:
            item.setText(old_url)
            return
        context = self.context
        ok, status, _, _ = cmds.do(cmds.ForgeUpdateUrl, context, old_url, new_url, self.editor.token)
        if ok and status == 0:
            self.forge_list[idx] = new_url
            self.activate_forge(new_url)
        else:
            item.setText(old_url)

    def selection_changed(self):
        if self.changed:
            self.save()
        forge = qtutils.selected_item(self.forges, self.forge_list)
        if not forge:
            self.disable_editor()
            return
        self.activate_forge(forge)

    def activate_forge(self, url):
        token = self.context.cfg.get(f'cola.forge.{url}.token', default='')
        self.current_url = url
        self.current_token = token
        self.editor.url = url
        self.editor.token = token
        self.editor.setEnabled(True)


def restore_focus(focus):
    """Restore focus to the current focus widget (e.g. when resetting values)"""
    if focus is None:
        return
    focus.setFocus(Qt.OtherFocusReason)
    if hasattr(focus, 'selectAll'):
        focus.selectAll()


class ForgeEditorWidget(QtWidgets.QWidget):
    """Enable details for a forge"""

    token = property(
        lambda self: get(self.forge_token),
        lambda self, value: self.forge_token.set_value(value),
    )
    url = property(
        lambda self: get(self.forge_url),
        lambda self, value: self.forge_url.set_value(value),
    )
    valid = Signal(bool)

    def __init__(self, context, parent, readonly=False):
        super().__init__(parent)
        self.setWindowModality(Qt.WindowModal)
        self.context = context
        self.forge_token = lineedit(context, N_('API token for accessing the forge'))
        self.forge_url = lineedit(context, 'Forge URL (example: https://gitlab.com)')
        self.forge_backend = qtutils.combo(('gitlab',), tooltip=N_('Forge backend'), parent=self)

        self._form = qtutils.form(
            defs.margin,
            defs.spacing,
            (N_('Backend'), self.forge_backend),
            (N_('URL'), self.forge_url),
            (N_('API Token'), self.forge_token),
        )

        self._layout = qtutils.vbox(defs.margin, defs.spacing, self._form)
        self.setLayout(self._layout)

        self.forge_token.textChanged.connect(self.validate)
        self.forge_url.textChanged.connect(self.validate)
        if readonly:
            self.forge_backend.setReadOnly(True)
            self.forge_url.setReadOnly(True)
            self.forge_token.setReadOnly(True)

    def validate(self, _text):
        url = self.url
        token = self.token
        self.valid.emit(bool(url) and bool(token))
